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
                        "key": [{"prefix": "raw/documents/"}, {"prefix": "raw/photos/"}]
                    }
                }
            )
        )

        self.ingestion_rule.add_target(targets.LambdaFunction(
            self.ingestion_lambda,
            dead_letter_queue=self.ingestion_dlq, # DLQ for async invocation failure from EB
            retry_attempts=2
        ))
