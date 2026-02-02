"""
Phase 7: Analytics & Reporting Stack
=====================================
Implements a low-cost, serverless data lake for real-time operational insights
and long-term business intelligence.

Architecture:
- DynamoDB Streams capture every INSERT/MODIFY in ICPA_Claims table
- Kinesis Data Firehose batches changes and streams to S3 in Parquet format
- AWS Glue Crawler indexes the data for SQL queries
- Amazon Athena enables ad-hoc reporting
- Amazon QuickSight provides dashboards (configured manually)

Three Dashboard Views:
1. Financial Operations (CFO View): Textract savings, payout tracking, cost per claim
2. Model Performance (Data Science View): AI agreement rate, rationale audit, fraud heatmap
3. Operational Efficiency (Manager View): Latency, throughput, bottleneck detection
"""

import json
from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_kinesisfirehose as firehose,
    aws_glue as glue,
    aws_athena as athena,
    aws_logs as logs,
    CfnOutput,
)
import aws_cdk as cdk
from constructs import Construct


class AnalyticsStack(Stack):

    def __init__(
        self, 
        scope: Construct, 
        construct_id: str,
        foundation_stack,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ==============================================================================
        # Step 7.1: Analytics Data Lake S3 Bucket
        # ==============================================================================
        
        self.analytics_bucket = s3.Bucket(
            self, "AnalyticsBucket",
            bucket_name="icpa-analytics-lake",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                # Transition to Intelligent-Tiering after 30 days
                s3.LifecycleRule(
                    id="TransitionToIntelligentTiering",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                            transition_after=Duration.days(30)
                        )
                    ]
                ),
                # Transition to Glacier after 180 days for long-term analysis
                s3.LifecycleRule(
                    id="TransitionToGlacier",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(180)
                        )
                    ]
                )
            ]
        )

        # ==============================================================================
        # Step 7.1: Kinesis Data Firehose Delivery Stream
        # ==============================================================================
        
        # IAM Role for Firehose
        firehose_role = iam.Role(
            self, "FirehoseRole",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
            description="Role for Kinesis Firehose to write to S3 analytics bucket"
        )
        
        self.analytics_bucket.grant_write(firehose_role)

        firehose_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "glue:GetDatabase",
                "glue:GetTable",
                "glue:GetTableVersion",
                "glue:GetTableVersions"
            ],
            resources=[
                f"arn:aws:glue:{self.region}:{self.account}:catalog",
                f"arn:aws:glue:{self.region}:{self.account}:database/icpa_analytics_db",
                f"arn:aws:glue:{self.region}:{self.account}:table/icpa_analytics_db/claims"
            ]
        ))

        firehose_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "glue:GetDatabase",
                "glue:GetTable",
                "glue:GetTableVersion",
                "glue:GetTableVersions"
            ],
            resources=["*"]
        ))
        
        # CloudWatch Logs for Firehose
        firehose_log_group = logs.LogGroup(
            self, "FirehoseLogGroup",
            log_group_name="/aws/kinesisfirehose/icpa-claims-stream",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK
        )
        
        firehose_log_stream = logs.LogStream(
            self, "FirehoseLogStream",
            log_group=firehose_log_group,
            log_stream_name="S3Delivery"
        )
        
        # Grant Firehose permission to write logs
        firehose_log_group.grant_write(firehose_role)
        
        # Firehose Delivery Stream with Parquet conversion
        self.firehose_stream = firehose.CfnDeliveryStream(
            self, "ClaimsFirehoseStream",
            delivery_stream_name="icpa-claims-analytics-stream",
            delivery_stream_type="DirectPut",
            extended_s3_destination_configuration=firehose.CfnDeliveryStream.ExtendedS3DestinationConfigurationProperty(
                bucket_arn=self.analytics_bucket.bucket_arn,
                role_arn=firehose_role.role_arn,
                prefix="claims/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/",
                error_output_prefix="errors/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/!{firehose:error-output-type}/",
                buffering_hints=firehose.CfnDeliveryStream.BufferingHintsProperty(
                    interval_in_seconds=300,  # 5 minutes
                    size_in_m_bs=128  # 128 MB
                ),
                compression_format="UNCOMPRESSED",  # Parquet has built-in compression
                cloud_watch_logging_options=firehose.CfnDeliveryStream.CloudWatchLoggingOptionsProperty(
                    enabled=True,
                    log_group_name=firehose_log_group.log_group_name,
                    log_stream_name=firehose_log_stream.log_stream_name
                ),
                # Parquet conversion configuration
                data_format_conversion_configuration=firehose.CfnDeliveryStream.DataFormatConversionConfigurationProperty(
                    enabled=True,
                    input_format_configuration=firehose.CfnDeliveryStream.InputFormatConfigurationProperty(
                        deserializer=firehose.CfnDeliveryStream.DeserializerProperty(
                            open_x_json_ser_de=firehose.CfnDeliveryStream.OpenXJsonSerDeProperty(
                                convert_dots_in_json_keys_to_underscores=True,
                                case_insensitive=True
                            )
                        )
                    ),
                    output_format_configuration=firehose.CfnDeliveryStream.OutputFormatConfigurationProperty(
                        serializer=firehose.CfnDeliveryStream.SerializerProperty(
                            parquet_ser_de=firehose.CfnDeliveryStream.ParquetSerDeProperty(
                                compression="SNAPPY",
                                enable_dictionary_compression=True,
                                max_padding_bytes=0,
                                page_size_bytes=1048576,  # 1 MB
                                writer_version="V2"
                            )
                        )
                    ),
                    schema_configuration=firehose.CfnDeliveryStream.SchemaConfigurationProperty(
                        database_name="icpa_analytics_db",
                        table_name="claims",
                        region=self.region,
                        role_arn=firehose_role.role_arn
                    )
                )
            )
        )

        # ==============================================================================
        # Step 7.1: DynamoDB Stream Processing Lambda
        # ==============================================================================
        
        # Lambda function to process DynamoDB Stream events and send to Firehose
        self.stream_processor = lambda_.Function(
            self, "StreamProcessor",
            function_name="icpa-dynamodb-stream-processor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=lambda_.Code.from_inline('''
import json
import boto3
import base64
from datetime import datetime
from decimal import Decimal

firehose = boto3.client('firehose')
DELIVERY_STREAM_NAME = 'icpa-claims-analytics-stream'

def decimal_default(obj):
    """JSON serializer for Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

def transform_record(dynamodb_record):
    """Transform DynamoDB record into analytics format"""
    
    # Extract the new image (current state after change)
    if 'NewImage' not in dynamodb_record:
        return None
    
    new_image = dynamodb_record['NewImage']
    
    # Build analytics record with key metrics
    record = {
        'event_time': dynamodb_record.get('ApproximateCreationDateTime', datetime.utcnow().isoformat()),
        'event_type': dynamodb_record.get('eventName', 'UNKNOWN'),
        'claim_id': new_image.get('claim_id', {}).get('S', ''),
        'external_id': new_image.get('external_id', {}).get('S', ''),
        'status': new_image.get('status', {}).get('S', ''),
        'policy_number': new_image.get('policy_number', {}).get('S', ''),
        'claimant_name': new_image.get('claimant_name', {}).get('S', ''),
        
        # Financial metrics
        'claim_amount': float(new_image.get('claim_amount', {}).get('N', 0)),
        'payout_amount': float(new_image.get('payout_amount', {}).get('N', 0)),
        'ai_recommended_payout': float(new_image.get('ai_recommended_payout', {}).get('N', 0)),
        
        # Cost tracking (Phase 7 focus: Textract savings)
        'textract_operation': new_image.get('textract_operation', {}).get('S', ''),
        'textract_cost': float(new_image.get('textract_cost', {}).get('N', 0)),
        'bedrock_cost': float(new_image.get('bedrock_cost', {}).get('N', 0)),
        'total_aws_cost': float(new_image.get('total_aws_cost', {}).get('N', 0)),
        
        # Model performance metrics
        'fraud_score': float(new_image.get('fraud_score', {}).get('N', 0)),
        'confidence_score': float(new_image.get('confidence_score', {}).get('N', 0)),
        'ai_agreement_flag': new_image.get('ai_agreement_flag', {}).get('S', ''),
        'adjuster_override': new_image.get('adjuster_override', {}).get('BOOL', False),
        'override_justification': new_image.get('override_justification', {}).get('S', ''),
        
        # Operational efficiency metrics
        'created_at': new_image.get('created_at', {}).get('S', ''),
        'updated_at': new_image.get('updated_at', {}).get('S', ''),
        'processing_duration_ms': int(new_image.get('processing_duration_ms', {}).get('N', 0)),
        
        # Metadata
        'vehicle_type': new_image.get('vehicle_type', {}).get('S', ''),
        'incident_date': new_image.get('incident_date', {}).get('S', ''),
        'region': new_image.get('region', {}).get('S', 'UK')
    }
    
    return record

def handler(event, context):
    """Process DynamoDB Stream events and send to Firehose"""
    
    records_to_send = []
    
    for record in event.get('Records', []):
        if record['eventName'] in ['INSERT', 'MODIFY']:
            transformed = transform_record(record['dynamodb'])
            if transformed:
                # Convert to JSON and prepare for Firehose
                json_data = json.dumps(transformed, default=decimal_default) + '\\n'
                records_to_send.append({
                    'Data': json_data
                })
    
    # Batch send to Firehose (up to 500 records per request)
    if records_to_send:
        batch_size = 500
        for i in range(0, len(records_to_send), batch_size):
            batch = records_to_send[i:i + batch_size]
            try:
                response = firehose.put_record_batch(
                    DeliveryStreamName=DELIVERY_STREAM_NAME,
                    Records=batch
                )
                print(f"Sent {len(batch)} records to Firehose. Failed: {response.get('FailedPutCount', 0)}")
            except Exception as e:
                print(f"Error sending batch to Firehose: {str(e)}")
                raise
    
    return {
        'statusCode': 200,
        'body': json.dumps(f'Processed {len(records_to_send)} records')
    }
'''),
            timeout=Duration.seconds(60),
            memory_size=256,
            reserved_concurrent_executions=10,
            environment={
                'DELIVERY_STREAM_NAME': self.firehose_stream.delivery_stream_name or 'icpa-claims-analytics-stream'
            }
        )
        
        # Grant Lambda permission to write to Firehose
        self.stream_processor.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    'firehose:PutRecord',
                    'firehose:PutRecordBatch'
                ],
                resources=[
                    f"arn:aws:firehose:{self.region}:{self.account}:deliverystream/{self.firehose_stream.delivery_stream_name or 'icpa-claims-analytics-stream'}"
                ]
            )
        )
        
        # Enable DynamoDB Stream on the Claims table
        cfn_table = foundation_stack.claims_table.node.default_child
        cfn_table.stream_specification = dynamodb.CfnTable.StreamSpecificationProperty(
            stream_view_type="NEW_AND_OLD_IMAGES"
        )
        
        # Add DynamoDB Stream as event source for Lambda
        self.stream_processor.add_event_source_mapping(
            "DynamoDBStreamMapping",
            event_source_arn=foundation_stack.claims_table.table_stream_arn,
            starting_position=lambda_.StartingPosition.LATEST,
            batch_size=100,
            max_batching_window=Duration.seconds(10),
            retry_attempts=3,
            bisect_batch_on_error=True
        )
        
        # Grant Lambda permission to read DynamoDB Stream
        foundation_stack.claims_table.grant_stream_read(self.stream_processor)

        # ==============================================================================
        # Step 7.2: AWS Glue Data Catalog
        # ==============================================================================
        
        # Create Glue Database
        self.glue_database = glue.CfnDatabase(
            self, "GlueDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="icpa_analytics_db",
                description="ICPA Claims Analytics Data Lake"
            )
        )

        firehose_role_policy = firehose_role.node.try_find_child("DefaultPolicy")
        if firehose_role_policy is not None:
            self.firehose_stream.node.add_dependency(firehose_role_policy)

        self.glue_claims_table = glue.CfnTable(
            self, "GlueClaimsTable",
            catalog_id=self.account,
            database_name=self.glue_database.ref,
            table_input=glue.CfnTable.TableInputProperty(
                name="claims",
                table_type="EXTERNAL_TABLE",
                parameters={
                    "classification": "json"
                },
                storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                    location=f"s3://{self.analytics_bucket.bucket_name}/claims/",
                    input_format="org.apache.hadoop.mapred.TextInputFormat",
                    output_format="org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    serde_info=glue.CfnTable.SerdeInfoProperty(
                        serialization_library="org.openx.data.jsonserde.JsonSerDe"
                    ),
                    columns=[
                        glue.CfnTable.ColumnProperty(name="event_time", type="string"),
                        glue.CfnTable.ColumnProperty(name="event_type", type="string"),
                        glue.CfnTable.ColumnProperty(name="claim_id", type="string"),
                        glue.CfnTable.ColumnProperty(name="external_id", type="string"),
                        glue.CfnTable.ColumnProperty(name="status", type="string"),
                        glue.CfnTable.ColumnProperty(name="policy_number", type="string"),
                        glue.CfnTable.ColumnProperty(name="claimant_name", type="string"),
                        glue.CfnTable.ColumnProperty(name="claim_amount", type="double"),
                        glue.CfnTable.ColumnProperty(name="payout_amount", type="double"),
                        glue.CfnTable.ColumnProperty(name="ai_recommended_payout", type="double"),
                        glue.CfnTable.ColumnProperty(name="textract_operation", type="string"),
                        glue.CfnTable.ColumnProperty(name="textract_cost", type="double"),
                        glue.CfnTable.ColumnProperty(name="bedrock_cost", type="double"),
                        glue.CfnTable.ColumnProperty(name="total_aws_cost", type="double"),
                        glue.CfnTable.ColumnProperty(name="fraud_score", type="double"),
                        glue.CfnTable.ColumnProperty(name="confidence_score", type="double"),
                        glue.CfnTable.ColumnProperty(name="ai_agreement_flag", type="string"),
                        glue.CfnTable.ColumnProperty(name="adjuster_override", type="boolean"),
                        glue.CfnTable.ColumnProperty(name="override_justification", type="string"),
                        glue.CfnTable.ColumnProperty(name="created_at", type="string"),
                        glue.CfnTable.ColumnProperty(name="updated_at", type="string"),
                        glue.CfnTable.ColumnProperty(name="processing_duration_ms", type="int"),
                        glue.CfnTable.ColumnProperty(name="vehicle_type", type="string"),
                        glue.CfnTable.ColumnProperty(name="incident_date", type="string"),
                        glue.CfnTable.ColumnProperty(name="region", type="string")
                    ]
                )
            )
        )

        self.firehose_stream.node.add_dependency(self.glue_database)
        self.firehose_stream.node.add_dependency(self.glue_claims_table)
        
        # IAM Role for Glue Crawler
        glue_crawler_role = iam.Role(
            self, "GlueCrawlerRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
            ],
            description="Role for Glue Crawler to catalog analytics data"
        )
        
        self.analytics_bucket.grant_read(glue_crawler_role)
        
        # Glue Crawler to automatically index S3 data
        self.glue_crawler = glue.CfnCrawler(
            self, "AnalyticsCrawler",
            name="icpa-claims-analytics-crawler",
            role=glue_crawler_role.role_arn,
            database_name=self.glue_database.ref,
            targets=glue.CfnCrawler.TargetsProperty(
                s3_targets=[
                    glue.CfnCrawler.S3TargetProperty(
                        path=f"s3://{self.analytics_bucket.bucket_name}/claims/"
                    )
                ]
            ),
            schema_change_policy=glue.CfnCrawler.SchemaChangePolicyProperty(
                update_behavior="UPDATE_IN_DATABASE",
                delete_behavior="LOG"
            ),
            configuration=json.dumps({
                "Version": 1.0,
                "CrawlerOutput": {
                    "Partitions": {"AddOrUpdateBehavior": "InheritFromTable"}
                },
                "Grouping": {
                    "TableGroupingPolicy": "CombineCompatibleSchemas"
                }
            }),
            schedule=glue.CfnCrawler.ScheduleProperty(
                # Run crawler every 6 hours to index new data
                schedule_expression="cron(0 */6 * * ? *)"
            )
        )

        # ==============================================================================
        # Step 7.3: Athena Query Configuration
        # ==============================================================================
        
        # S3 bucket for Athena query results
        self.athena_results_bucket = s3.Bucket(
            self, "AthenaResultsBucket",
            bucket_name="icpa-athena-query-results",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteQueryResultsAfter7Days",
                    expiration=Duration.days(7)
                )
            ]
        )
        
        # Athena Workgroup
        self.athena_workgroup = athena.CfnWorkGroup(
            self, "AthenaWorkgroup",
            name="icpa-analytics-workgroup",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{self.athena_results_bucket.bucket_name}/",
                    encryption_configuration=athena.CfnWorkGroup.EncryptionConfigurationProperty(
                        encryption_option="SSE_S3"
                    )
                ),
                enforce_work_group_configuration=True,
                publish_cloud_watch_metrics_enabled=True
            ),
            description="Workgroup for ICPA analytics queries"
        )

        # ==============================================================================
        # Outputs
        # ==============================================================================
        
        CfnOutput(self, "AnalyticsBucketName",
            value=self.analytics_bucket.bucket_name,
            description="S3 bucket for analytics data lake"
        )
        
        CfnOutput(self, "FirehoseStreamName",
            value=self.firehose_stream.delivery_stream_name or 'icpa-claims-analytics-stream',
            description="Kinesis Firehose delivery stream name"
        )
        
        CfnOutput(self, "GlueDatabaseName",
            value=self.glue_database.ref,
            description="Glue database name for analytics"
        )
        
        CfnOutput(self, "GlueCrawlerName",
            value=self.glue_crawler.ref,
            description="Glue crawler name"
        )
        
        CfnOutput(self, "AthenaWorkgroupName",
            value=self.athena_workgroup.ref,
            description="Athena workgroup for queries"
        )
        
        CfnOutput(self, "AthenaResultsBucketOutput",
            value=self.athena_results_bucket.bucket_name,
            description="S3 bucket for Athena query results"
        )
