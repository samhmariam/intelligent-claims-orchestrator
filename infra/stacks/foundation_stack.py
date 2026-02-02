from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_s3_notifications as s3n,
    aws_events as events,
    aws_events_targets as targets,
    aws_sqs as sqs,
    aws_iam as iam,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    aws_sns as sns,
    aws_kms as kms,
)
import aws_cdk as cdk
from constructs import Construct

class FoundationStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ==============================================================================
        # S3 Buckets (Phase 0)
        # ==============================================================================
        
        # 1. Raw Bucket: Ingestion intake logs/documents
        self.raw_bucket = s3.Bucket(self, "RawBucket",
            bucket_name="icpa-raw-intake", # Note: Bucket names must be globally unique, considering adding suffix if needed
            removal_policy=RemovalPolicy.DESTROY, # For dev/test, easier cleanup
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteAfter30Days",
                    expiration=cdk.Duration.days(30)
                )
            ]
        )

        # 2. Clean Bucket: Sanitized/Extracted data
        self.clean_bucket = s3.Bucket(self, "CleanBucket",
            bucket_name="icpa-clean-data",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteAfter180Days",
                    expiration=cdk.Duration.days(180)
                )
            ]
        )

        # 3. Quarantine Bucket: Schema violations / PHI review
        self.quarantine_bucket = s3.Bucket(self, "QuarantineBucket",
            bucket_name="icpa-quarantine",
            removal_policy=RemovalPolicy.DESTROY, # Verify retention policy vs dev cleanup
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteAfter365Days",
                    expiration=cdk.Duration.days(365)
                )
            ]
        )

        # ==============================================================================
        # DynamoDB Tables (Phase 0)
        # ==============================================================================

        # 1. ICPA_Claims: Core Claim State & Audit Trail
        self.claims_table = dynamodb.Table(self, "ClaimsTable",
            table_name="ICPA_Claims",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY, 
            point_in_time_recovery=True, # Recommended for prod, good for dev too
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES
        )

        # GSI: ExternalIdIndex (Context Propagation)
        self.claims_table.add_global_secondary_index(
            index_name="ExternalIdIndex",
            partition_key=dynamodb.Attribute(name="external_id", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.INCLUDE,
            non_key_attributes=["claim_id", "status"]
        )

        # 2. ICPA_Idempotency: API Response Cache
        self.idempotency_table = dynamodb.Table(self, "IdempotencyTable",
            table_name="ICPA_Idempotency",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=RemovalPolicy.DESTROY
        )

        # 3. ICPA_Evaluation: Test Results & Golden Set Stats
        self.evaluation_table = dynamodb.Table(self, "EvaluationTable",
            table_name="ICPA_Evaluation",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY
        )

        # ==============================================================================
        # Lambda Functions (Phase 1)
        # ==============================================================================

        # ==============================================================================
        # Lambda Functions (Phase 1 - Robust)
        # ==============================================================================

        # 1. Dead Letter Queue for Ingestion
        self.ingestion_dlq = sqs.Queue(self, "IngestionDLQ",
            queue_name="icpa-ingestion-dlq",
            retention_period=cdk.Duration.days(14)
        )

        # 2. Powertools Layer (Local Bundle)
        self.powertools_layer = lambda_.LayerVersion(self, "PowertoolsLayer",
            code=lambda_.Code.from_asset("layers/powertools"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_13],
            description="Local build of aws-lambda-powertools"
        )

        self.ingestion_lambda = lambda_.Function(self, "IngestionLambda",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="icpa.ingestion.handlers.ingestion_handler",
            code=lambda_.Code.from_asset("../src"), 
            environment={
                "CLEAN_BUCKET_NAME": self.clean_bucket.bucket_name,
                "CLAIMS_TABLE_NAME": self.claims_table.table_name,
                "IDEMPOTENCY_TABLE_NAME": self.idempotency_table.table_name,
                "POWERTOOLS_SERVICE_NAME": "ingestion-service",
                "POWERTOOLS_METRICS_NAMESPACE": "ICPA/Production",
            },
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            tracing=lambda_.Tracing.ACTIVE, # X-Ray Enabled
            layers=[self.powertools_layer],
            dead_letter_queue=self.ingestion_dlq
        )

        # Permissions
        self.raw_bucket.grant_read(self.ingestion_lambda)
        self.clean_bucket.grant_write(self.ingestion_lambda)
        self.claims_table.grant_write_data(self.ingestion_lambda)
        self.idempotency_table.grant_read_write_data(self.ingestion_lambda)
        
        # Additional Permissions for Context Propagation
        self.ingestion_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:Query"],
            resources=[f"{self.claims_table.table_arn}/index/ExternalIdIndex"]
        ))
        
        self.ingestion_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:PutObjectTagging"],
            resources=[f"{self.clean_bucket.bucket_arn}/*"]
        ))
        
        # Explicitly grant DynamoDB Write permissions (Redundant safety for AccessDenied issue)
        self.ingestion_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"],
            resources=[self.claims_table.table_arn]
        ))
        
        # X-Ray Permissions (Managed by Tracing.ACTIVE, but ensuring)
        
        # ==============================================================================
        # Triggers (EventBridge)
        # ==============================================================================
        
        # 1. Enable EventBridge on Raw Bucket
        self.raw_bucket.enable_event_bridge_notification()

        # 2. Create EventBridge Rule
        self.ingestion_rule = events.Rule(self, "IngestionRule",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {
                        "name": [self.raw_bucket.bucket_name]
                    },
                    "object": {
                        "key": [{"wildcard": "*/raw/documents/*"}, {"wildcard": "*/raw/photos/*"}]
                    }
                }
            )
        )

        self.ingestion_rule.add_target(targets.LambdaFunction(
            self.ingestion_lambda,
            dead_letter_queue=self.ingestion_dlq,
            retry_attempts=2
        ))

        # ==============================================================================
        # Phase 2 & 3: Intelligent Orchestration
        # ==============================================================================
        
        # 1. Document Processor Lambda (Textract + Redaction)
        self.doc_processor_lambda = lambda_.Function(self, "DocumentProcessorLambda",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="icpa.processing.handlers.processing_handler",
            code=lambda_.Code.from_asset("../src"),
            environment={
                "CLEAN_BUCKET_NAME": self.clean_bucket.bucket_name,
                "QUARANTINE_BUCKET_NAME": self.quarantine_bucket.bucket_name,
                "CLAIMS_TABLE_NAME": self.claims_table.table_name,
                "POWERTOOLS_SERVICE_NAME": "processing-service",
            },
            timeout=cdk.Duration.seconds(300),
            memory_size=1024,
            tracing=lambda_.Tracing.ACTIVE,
            layers=[self.powertools_layer]
        )
        
        # Permissions
        self.clean_bucket.grant_read_write(self.doc_processor_lambda)
        self.quarantine_bucket.grant_put(self.doc_processor_lambda)
        # PHASE 1: Changed to grant_read_write_data to allow cache lookups (GetItem)
        self.claims_table.grant_read_write_data(self.doc_processor_lambda)
        
        self.doc_processor_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "textract:AnalyzeDocument",
                "textract:DetectDocumentText",
                "comprehendmedical:DetectPHI",
                "events:PutEvents",
                "s3:ListBucket" # Required for Batch Listing
            ],
            resources=["*"]
        ))
        
        # 2. Decision Engine Lambda (Phase 3)
        self.decision_engine_lambda = lambda_.Function(self, "DecisionEngineLambda",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="icpa.decision.handlers.decision_handler",
            code=lambda_.Code.from_asset("../src"),
            timeout=cdk.Duration.seconds(300),
            environment={
                "POWERTOOLS_SERVICE_NAME": "decision-engine",
                "CLEAN_BUCKET_NAME": self.clean_bucket.bucket_name
            },

            memory_size=256,
            tracing=lambda_.Tracing.ACTIVE,
            layers=[self.powertools_layer]
        )
        self.decision_engine_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"], 
            resources=[self.clean_bucket.bucket_arn]
        ))
        
        # Permissions: Read S3 (Extracts)
        self.clean_bucket.grant_read(self.decision_engine_lambda) 
        # Also ListBucket for Aggregation
        self.clean_bucket.grant_read(self.decision_engine_lambda)
        
        # Phase 3b: Intelligent Agents (Bedrock + SSM)
        self.decision_engine_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[
                "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0",
                "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0"
            ]
        ))
        
        self.decision_engine_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/icpa/prompts/*"]
        ))

        # 3. Context Assembler Lambda (Phase 4)
        self.context_assembler_lambda = lambda_.Function(self, "ContextAssemblerLambda",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="icpa.context.assembler.handler",
            code=lambda_.Code.from_asset("../src"),
            timeout=cdk.Duration.seconds(60),
            memory_size=1024,
            environment={
                "POWERTOOLS_SERVICE_NAME": "context-assembler",
                "CLEAN_BUCKET_NAME": self.clean_bucket.bucket_name,
                "CLAIMS_TABLE_NAME": self.claims_table.table_name
            },
            tracing=lambda_.Tracing.ACTIVE,
            layers=[self.powertools_layer]
        )
        
        # Permissions
        self.clean_bucket.grant_read_write(self.context_assembler_lambda)
        self.claims_table.grant_read_write_data(self.context_assembler_lambda)
        
        # 4. SNS Topic for Notifications (Encrypted)
        # Create KMS Key for SNS
        self.sns_key = kms.Key(self, "ICPASNSKey",
            description="KMS Key for ICPA Notifications",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        self.notifications_topic = sns.Topic(self, "ICPANotifications",
            topic_name="ICPA_Notifications",
            master_key=self.sns_key
        )
        
        # Grant Step Function permissions (via IAM Role later generated by CDK)
        # We need to explicitly allow the State Machine Principal to use the Key?
        # CDK StateMachine construct usually handles role creation. We can attach policy.

        # 4. Orchestration Step Function
        
        # Step 0: Wait for Packet (Buffer)
        # Step 0: Wait for Packet (Buffer)
        wait_for_uploads = sfn.Wait(self, "Wait For Uploads",
            time=sfn.WaitTime.duration(cdk.Duration.seconds(30))
        )
        
        # Step 1: Extract Document
        extract_task = sfn_tasks.LambdaInvoke(self, "Extract Document",
            lambda_function=self.doc_processor_lambda,
            payload=sfn.TaskInput.from_object({
                "claim_uuid": sfn.JsonPath.string_at("$.claim_uuid")
            }),
            output_path="$.Payload",
        )
        extract_task.add_retry(
            errors=["ThrottlingException", "ProvisionedThroughputExceededException", "LimitExceededException"],
            interval=cdk.Duration.seconds(2), max_attempts=3, backoff_rate=2.0
        )

        # Step 1b: Assemble Context (Reducer)
        assemble_task = sfn_tasks.LambdaInvoke(self, "Assemble Context",
            lambda_function=self.context_assembler_lambda,
            result_path="$.assembler_output",
            payload_response_only=True,
            payload=sfn.TaskInput.from_object({
                "claim_uuid": sfn.JsonPath.string_at("$.claim_uuid"),
                "execution_start_time": sfn.JsonPath.string_at("$$.Execution.StartTime")
            })
        )
        assemble_task.add_retry(errors=["States.ALL"], interval=cdk.Duration.seconds(2), max_attempts=3)

        # Step 2: Evaluate Result (Decision Engine)
        evaluate_task = sfn_tasks.LambdaInvoke(self, "Evaluate Result",
            lambda_function=self.decision_engine_lambda,
            result_path="$.decision",
            payload_response_only=True
        )
        
        # Error Handling: Catch ALL -> Handle Failure
        handle_failure = sfn.Pass(self, "HandleFailure",
            result=sfn.Result.from_object({"status": "ERROR_REVIEW", "reason": "Technical Failure"}),
            result_path="$.error"
        )
        # We could update DynamoDB here to ERROR_REVIEW status.
        # For simplicity in this iteration, we pass to a Fail state or specific Review path.
        # Let's update DB to ERROR_REVIEW via a DynamoDB Task (but keeping it simple with Pass + Fail for now in code flow)
        # User requested: "Update DB: ERROR_REVIEW".
        # Let's add a DynamoDB UpdateItem Task for failure.
        
        update_error_db_task = sfn_tasks.DynamoUpdateItem(self, "Set Error Status",
            table=self.claims_table,
            key={"PK": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.format("CLAIM#{}", sfn.JsonPath.string_at("$.claim_uuid"))), "SK": sfn_tasks.DynamoAttributeValue.from_string("META")},
            update_expression="SET #s = :s",
            expression_attribute_names={"#s": "status"},
            expression_attribute_values={":s": sfn_tasks.DynamoAttributeValue.from_string("ERROR_REVIEW")},
        )
        
        evaluate_task.add_catch(update_error_db_task, result_path="$.error")

        # Step 3: Decision Choice
        decision_choice = sfn.Choice(self, "Decision Choice")
        
        # Branch A: Approve
        update_approve_db = sfn_tasks.DynamoUpdateItem(self, "Set Approved",
            table=self.claims_table,
            key={"PK": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.format("CLAIM#{}", sfn.JsonPath.string_at("$.claim_uuid"))), "SK": sfn_tasks.DynamoAttributeValue.from_string("META")},
            update_expression="SET #s = :s, #r = :r, #c = :c, recommendation = :rec, fraud_score = :fs, payout_gbp = :p",
            expression_attribute_names={"#s": "status", "#r": "decision_reason", "#c": "context_bundle_s3_key"},
            expression_attribute_values={
                ":s": sfn_tasks.DynamoAttributeValue.from_string("APPROVED"),
                ":r": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.decision.decision_reason")),
                ":c": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.assembler_output.bundle_s3_key")),
                ":rec": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.decision.recommendation")),
                ":fs": sfn_tasks.DynamoAttributeValue.number_from_string(sfn.JsonPath.format("{}", sfn.JsonPath.string_at("$.decision.fraud_score"))),
                ":p": sfn_tasks.DynamoAttributeValue.number_from_string(sfn.JsonPath.format("{}", sfn.JsonPath.string_at("$.decision.payout_gbp")))
            },
            result_path=sfn.JsonPath.DISCARD
        )
        
        # 5. Payment Lambda (Phase 5)
        self.payment_lambda = lambda_.Function(self, "PaymentLambda",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="icpa.payout.handlers.handler",
            code=lambda_.Code.from_asset("../src"),
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "POWERTOOLS_SERVICE_NAME": "payment-service",
                "CLAIMS_TABLE_NAME": self.claims_table.table_name
            },
            tracing=lambda_.Tracing.ACTIVE,
            layers=[self.powertools_layer]
        )
        self.claims_table.grant_read_write_data(self.payment_lambda)

        # 6. EventBridge & Rules
        bus = events.EventBus(self, "ICPABus", event_bus_name="ICPA_EventBus")
        
        # Rule 1: Payout (Approved)
        payout_rule = events.Rule(self, "PayoutRule",
            event_bus=bus,
            event_pattern=events.EventPattern(
                source=["com.icpa.orchestration"],
                detail_type=["ClaimDecision"],
                detail={"status": ["APPROVED"]}
            )
        )
        payout_rule.add_target(targets.LambdaFunction(self.payment_lambda))
        
        # Rule 2: Notify (Denied/Review)
        notify_rule = events.Rule(self, "NotifyRule",
            event_bus=bus,
            event_pattern=events.EventPattern(
                source=["com.icpa.orchestration"],
                detail_type=["ClaimDecision"],
                detail={"status": ["DENIED", "NEEDS_REVIEW"]}
            )
        )
        notify_rule.add_target(targets.SnsTopic(self.notifications_topic))
        
        # Rule 3: Human Override (Phase 6 - HITL Dashboard)
        # Handles manual overrides from adjusters
        override_payout_rule = events.Rule(self, "HumanOverridePayoutRule",
            event_bus=bus,
            event_pattern=events.EventPattern(
                source=["com.icpa.human_override"],
                detail_type=["ManualOverride"],
                detail={"status": ["APPROVED"]}
            )
        )
        override_payout_rule.add_target(targets.LambdaFunction(self.payment_lambda))
        
        override_notify_rule = events.Rule(self, "HumanOverrideNotifyRule",
            event_bus=bus,
            event_pattern=events.EventPattern(
                source=["com.icpa.human_override"],
                detail_type=["ManualOverride"],
                detail={"status": ["DENIED"]}
            )
        )
        override_notify_rule.add_target(targets.SnsTopic(self.notifications_topic))
        
        # KMS Permission for EventBridge -> SNS
        self.sns_key.add_to_resource_policy(iam.PolicyStatement(
            sid="AllowEventBridgeToUseKey",
            actions=["kms:GenerateDataKey", "kms:Decrypt"],
            resources=["*"],
            principals=[iam.ServicePrincipal("events.amazonaws.com")]
        ))

        # 7. Orchestration Step Function (Updated)
        
        # ... (Previous steps remain) ...
        
        # Step 4: Emit Final Event
        # We replace the direct SNS publish / DB update chains with a single Event Emission
        # The EventBridge Rule will handle the fan-out.
        
        emit_event_task = sfn_tasks.EventBridgePutEvents(self, "Emit Decision Event",
            entries=[sfn_tasks.EventBridgePutEventsEntry(
                event_bus=bus,
                detail=sfn.TaskInput.from_object({
                    "claim_uuid": sfn.JsonPath.string_at("$.claim_uuid"),
                    "external_id": sfn.JsonPath.string_at("$.decision.external_id"), # Ensure this is passed/available
                    "status": sfn.JsonPath.string_at("$.decision.decision"), # APPROVE/DENY/REVIEW
                    "reason": sfn.JsonPath.string_at("$.decision.reason"),
                    "payout_gbp": sfn.JsonPath.string_at("$.decision.payout_gbp"),
                    "context_bundle_s3_key": sfn.JsonPath.string_at("$.assembler_output.bundle_s3_key")
                }),
                detail_type="ClaimDecision",
                source="com.icpa.orchestration"
            )],
            result_path="$.event_result"
        )
        
        # Update Chain: Decision -> Emit Event -> End
        # We still want to update DynamoDB with the *Initial* decision (APPROVED/DENIED) so the UI reflects it immediately.
        # But the *Final* state (CLOSED_PAID) comes from PaymentLambda.
        
        # Re-linking the Decision Choice to Emit Event
        # To keep it simple: ALL decisions go to Emit Event.
        # But we need to format the payload correctly first.
        # decision_handler returns { "recommendation": "...", "reason": "...", "payout_gbp": ... }
        # We need to map "recommendation" (APPROVE) to "status" (APPROVED).
        
        # Let's clean up the Choice logic.
        # Actually, let's simplify:
        # 1. Decision Engine runs.
        # 2. Emit Event (with the raw decision).
        # 3. End.
        # The EventBridge rules handle the rest.
        
        # But wait, we need to update DynamoDB to at least "DECIDED" or specific status so UI isn't stuck.
        # Let's keep the DB updates in SF, but remove the SNS publish / complex branching if possible.
        # Or just append Emit Event to the end of each branch.
        
        # Branch A (Approve) -> Update DB -> Emit Event
        approve_chain = update_approve_db.next(emit_event_task)
        
        # Branch B: Review
        update_review_db = sfn_tasks.DynamoUpdateItem(self, "Set Review Needed",
            table=self.claims_table,
            key={"PK": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.format("CLAIM#{}", sfn.JsonPath.string_at("$.claim_uuid"))), "SK": sfn_tasks.DynamoAttributeValue.from_string("META")},
            update_expression="SET #s = :s, #r = :r, #c = :c, recommendation = :rec, fraud_score = :fs",
            expression_attribute_names={"#s": "status", "#r": "decision_reason", "#c": "context_bundle_s3_key"},
            expression_attribute_values={
                ":s": sfn_tasks.DynamoAttributeValue.from_string("NEEDS_REVIEW"),
                ":r": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.decision.decision_reason")),
                ":c": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.assembler_output.bundle_s3_key")),
                ":rec": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.decision.recommendation")),
                ":fs": sfn_tasks.DynamoAttributeValue.number_from_string(sfn.JsonPath.format("{}", sfn.JsonPath.string_at("$.decision.fraud_score")))
            },
            result_path=sfn.JsonPath.DISCARD
        )
        
        review_chain = update_review_db.next(emit_event_task)
        
        # Branch C: Deny
        update_deny_db = sfn_tasks.DynamoUpdateItem(self, "Set Denied",
            table=self.claims_table,
            key={"PK": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.format("CLAIM#{}", sfn.JsonPath.string_at("$.claim_uuid"))), "SK": sfn_tasks.DynamoAttributeValue.from_string("META")},
            update_expression="SET #s = :s, #r = :r, #c = :c, recommendation = :rec, fraud_score = :fs",
            expression_attribute_names={"#s": "status", "#r": "decision_reason", "#c": "context_bundle_s3_key"},
            expression_attribute_values={
                ":s": sfn_tasks.DynamoAttributeValue.from_string("DENIED"),
                ":r": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.decision.decision_reason")),
                ":c": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.assembler_output.bundle_s3_key")),
                ":rec": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.decision.recommendation")),
                ":fs": sfn_tasks.DynamoAttributeValue.number_from_string(sfn.JsonPath.format("{}", sfn.JsonPath.string_at("$.decision.fraud_score")))
            },
            result_path=sfn.JsonPath.DISCARD
        )
        
        deny_chain = update_deny_db.next(emit_event_task)

        # Old SNS Publish logic removed in favor of EventBridge Rule
        # notify_review = sfn_tasks.SnsPublish(...)
        # review_chain = update_review_db.next(notify_review) -> Removed

        # Definition Linking
        definition = wait_for_uploads.next(extract_task).next(assemble_task).next(evaluate_task).next(
            decision_choice
            .when(sfn.Condition.string_equals("$.decision.recommendation", "APPROVE"), approve_chain)
            .when(sfn.Condition.string_equals("$.decision.recommendation", "REVIEW"), review_chain)
            .when(sfn.Condition.string_equals("$.decision.recommendation", "DENY"), deny_chain)
            .otherwise(review_chain) # Default to review for safety
        )
        
        self.orchestration_state_machine = sfn.StateMachine(self, "OrchestrationStateMachineV3",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=cdk.Duration.minutes(10),
            tracing_enabled=True
        )
        
        # Grant KMS permissions to State Machine Role
        self.sns_key.grant_decrypt(self.orchestration_state_machine)
        self.sns_key.grant(self.orchestration_state_machine, "kms:GenerateDataKey")
        
        # 5. Trigger: Ingestion Lambda (Explicit Trigger)
        # We removed the S3 EventBridge Rule to prevent "12 brains" problem.
        # Now IngestionLambda triggers the SF once packet is ready.
        
        # We must keep this enabled to avoid Custom Resource Deletion issues during stack update
        self.clean_bucket.enable_event_bridge_notification()

        self.ingestion_lambda.add_environment("STATE_MACHINE_ARN", self.orchestration_state_machine.state_machine_arn)
        self.orchestration_state_machine.grant_start_execution(self.ingestion_lambda)
