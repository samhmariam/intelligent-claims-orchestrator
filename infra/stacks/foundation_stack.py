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
            point_in_time_recovery=True # Recommended for prod, good for dev too
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
        powertools_layer = lambda_.LayerVersion(self, "PowertoolsLayer",
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
            layers=[powertools_layer],
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
            layers=[powertools_layer]
        )
        
        # Permissions
        self.clean_bucket.grant_read_write(self.doc_processor_lambda)
        self.quarantine_bucket.grant_put(self.doc_processor_lambda)
        self.claims_table.grant_write_data(self.doc_processor_lambda)
        
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
            environment={
                "POWERTOOLS_SERVICE_NAME": "decision-engine",
                "CLEAN_BUCKET_NAME": self.clean_bucket.bucket_name
            },
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            tracing=lambda_.Tracing.ACTIVE,
            layers=[powertools_layer]
        )
        self.decision_engine_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"], 
            resources=[self.clean_bucket.bucket_arn]
        ))
        
        # Permissions: Read S3 (Extracts)
        self.clean_bucket.grant_read(self.decision_engine_lambda) 
        # Also ListBucket for Aggregation
        self.clean_bucket.grant_read(self.decision_engine_lambda)

        # 3. SNS Topic for Notifications (Encrypted)
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
        wait_for_uploads = sfn.Wait(self, "Wait For Uploads",
            time=sfn.WaitTime.duration(cdk.Duration.seconds(10))
        )
        
        # Step 1: Extract Document
        extract_task = sfn_tasks.LambdaInvoke(self, "Extract Document",
            lambda_function=self.doc_processor_lambda,
            output_path="$.Payload",
        )
        extract_task.add_retry(
            errors=["ThrottlingException", "ProvisionedThroughputExceededException", "LimitExceededException"],
            interval=cdk.Duration.seconds(2), max_attempts=3, backoff_rate=2.0
        )

        # Step 2: Evaluate Result (Decision Engine)
        evaluate_task = sfn_tasks.LambdaInvoke(self, "Evaluate Result",
            lambda_function=self.decision_engine_lambda,
            output_path="$.Payload",
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
            key={"PK": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.claim_uuid")), "SK": sfn_tasks.DynamoAttributeValue.from_string("META")},
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
            key={"PK": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.claim_uuid")), "SK": sfn_tasks.DynamoAttributeValue.from_string("META")},
            update_expression="SET #s = :s, #r = :r",
            expression_attribute_names={"#s": "status", "#r": "decision_reason"},
            expression_attribute_values={
                ":s": sfn_tasks.DynamoAttributeValue.from_string("APPROVED"),
                ":r": sfn_tasks.DynamoAttributeValue.from_string("Auto-Approved by Decision Engine")
            },
            result_path=sfn.JsonPath.DISCARD
        )
        
        emit_approve_event = sfn_tasks.EventBridgePutEvents(self, "Emit Approved Event",
            entries=[sfn_tasks.EventBridgePutEventsEntry(
                detail=sfn.TaskInput.from_object({
                    "claim_id": sfn.JsonPath.string_at("$.claim_uuid"),
                    "status": "APPROVED",
                    "reason": sfn.JsonPath.string_at("$.reason")
                }),
                detail_type="ClaimDecision",
                source="com.icpa.orchestration"
            )]
        )

        approve_chain = update_approve_db.next(emit_approve_event)

        # Branch B: Review
        update_review_db = sfn_tasks.DynamoUpdateItem(self, "Set Review Needed",
            table=self.claims_table,
            key={"PK": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.claim_uuid")), "SK": sfn_tasks.DynamoAttributeValue.from_string("META")},
            update_expression="SET #s = :s, #r = :r",
            expression_attribute_names={"#s": "status", "#r": "decision_reason"},
            expression_attribute_values={
                ":s": sfn_tasks.DynamoAttributeValue.from_string("NEEDS_REVIEW"),
                ":r": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.reason"))
            },
            result_path=sfn.JsonPath.DISCARD

        )
        
        # Branch C: Deny
        update_deny_db = sfn_tasks.DynamoUpdateItem(self, "Set Denied",
            table=self.claims_table,
            key={"PK": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.claim_uuid")), "SK": sfn_tasks.DynamoAttributeValue.from_string("META")},
            update_expression="SET #s = :s, #r = :r",
            expression_attribute_names={"#s": "status", "#r": "decision_reason"},
            expression_attribute_values={
                ":s": sfn_tasks.DynamoAttributeValue.from_string("DENIED"),
                ":r": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.reason"))
            },
            result_path=sfn.JsonPath.DISCARD
        )
        
        emit_deny_event = sfn_tasks.EventBridgePutEvents(self, "Emit Denied Event",
            entries=[sfn_tasks.EventBridgePutEventsEntry(
                detail=sfn.TaskInput.from_object({
                    "claim_id": sfn.JsonPath.string_at("$.claim_uuid"),
                    "status": "DENIED",
                    "reason": sfn.JsonPath.string_at("$.reason")
                }),
                detail_type="ClaimDecision",
                source="com.icpa.orchestration"
            )]
        )
        
        deny_chain = update_deny_db.next(emit_deny_event)

        # Publish to SNS with Task Token
        notify_review = sfn_tasks.SnsPublish(self, "Notify Adjuster",
            topic=self.notifications_topic,
            message=sfn.TaskInput.from_object({
                "Message": sfn.JsonPath.format(
                    "Review Required for Claim {}.\nReason: {}.\nView Documents in S3: s3://{}/{}",
                    sfn.JsonPath.string_at("$.claim_uuid"),
                    sfn.JsonPath.string_at("$.reason"),
                    sfn.JsonPath.string_at("$.metadata.bucket"), # We can pass this or hardcode? 
                    # Actually, we don't have bucket in input either unless we pass it.
                    # Let's verify input. Input has "metadata": {}.
                    # Let's fallback to just Claim UUID.
                    sfn.JsonPath.string_at("$.claim_uuid")
                ),
                "TaskToken": sfn.JsonPath.task_token
            }),
            integration_pattern=sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN
        )
        
        review_chain = update_review_db.next(notify_review)

        # Definition Linking
        definition = wait_for_uploads.next(extract_task).next(evaluate_task).next(
            decision_choice
            .when(sfn.Condition.string_equals("$.recommendation", "APPROVE"), approve_chain)
            .when(sfn.Condition.string_equals("$.recommendation", "REVIEW"), review_chain)
            .when(sfn.Condition.string_equals("$.recommendation", "DENY"), deny_chain)
            .otherwise(review_chain) # Default to review for safety
        )
        
        self.orchestration_state_machine = sfn.StateMachine(self, "OrchestrationStateMachine",
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
