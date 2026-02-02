#!/usr/bin/env python3
"""
Phase 7 Verification Script: Analytics & Reporting
===================================================
Validates that the analytics data lake is correctly configured and receiving data.

Tests:
1. S3 analytics bucket exists and is accessible
2. Kinesis Firehose delivery stream is active
3. DynamoDB Stream is enabled on Claims table
4. Lambda stream processor is connected
5. Glue Database and Crawler are configured
6. Athena can query the data
7. Sample claims have been processed to analytics lake

Usage:
    uv run scripts/verify_phase_7.py
    uv run scripts/verify_phase_7.py --run-crawler
    uv run scripts/verify_phase_7.py --query-athena
"""

import argparse
import boto3
import time
import json
from datetime import datetime
from botocore.exceptions import ClientError

# AWS Clients
s3 = boto3.client('s3')
firehose = boto3.client('firehose')
dynamodb = boto3.client('dynamodb')
glue = boto3.client('glue')
athena = boto3.client('athena')
lambda_client = boto3.client('lambda')

# Configuration (from CDK outputs)
ANALYTICS_BUCKET = "icpa-analytics-lake"
FIREHOSE_STREAM = "icpa-claims-analytics-stream"
CLAIMS_TABLE = "ICPA_Claims"
GLUE_DATABASE = "icpa_analytics_db"
GLUE_CRAWLER = "icpa-claims-analytics-crawler"
STREAM_PROCESSOR_FUNCTION = "icpa-dynamodb-stream-processor"
ATHENA_WORKGROUP = "icpa-analytics-workgroup"
ATHENA_RESULTS_BUCKET = "icpa-athena-query-results"


def print_header(title):
    """Print formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_success(message):
    """Print success message"""
    print(f"✓ {message}")


def print_error(message):
    """Print error message"""
    print(f"✗ {message}")


def print_info(message):
    """Print info message"""
    print(f"ℹ {message}")


def verify_s3_bucket():
    """Verify S3 analytics bucket exists and has correct configuration"""
    print_header("Step 7.1: Verifying S3 Analytics Bucket")
    
    try:
        # Check bucket exists
        response = s3.head_bucket(Bucket=ANALYTICS_BUCKET)
        print_success(f"Analytics bucket '{ANALYTICS_BUCKET}' exists")
        
        # Check lifecycle rules
        lifecycle = s3.get_bucket_lifecycle_configuration(Bucket=ANALYTICS_BUCKET)
        print_success(f"Lifecycle rules configured: {len(lifecycle['Rules'])} rules")
        
        for rule in lifecycle['Rules']:
            if rule.get('Status') == 'Enabled':
                print_info(f"  - {rule['ID']}: {rule.get('Transitions', [])[0].get('StorageClass', 'N/A') if rule.get('Transitions') else 'Expiration'}")
        
        # Check for existing data
        response = s3.list_objects_v2(Bucket=ANALYTICS_BUCKET, Prefix='claims/', MaxKeys=10)
        if 'Contents' in response:
            print_success(f"Found {len(response['Contents'])} files in claims/ prefix")
            print_info(f"  Latest file: {response['Contents'][-1]['Key']}")
        else:
            print_info("No data files yet (expected if no claims processed)")
        
        return True
        
    except ClientError as e:
        print_error(f"S3 bucket verification failed: {e}")
        return False


def verify_firehose_stream():
    """Verify Kinesis Firehose delivery stream is active"""
    print_header("Step 7.1: Verifying Kinesis Firehose Stream")
    
    try:
        response = firehose.describe_delivery_stream(
            DeliveryStreamName=FIREHOSE_STREAM
        )
        
        stream = response['DeliveryStreamDescription']
        status = stream['DeliveryStreamStatus']
        
        if status == 'ACTIVE':
            print_success(f"Firehose stream '{FIREHOSE_STREAM}' is {status}")
        else:
            print_error(f"Firehose stream status: {status} (expected ACTIVE)")
            return False
        
        # Check destination configuration
        destinations = stream['Destinations']
        if destinations:
            dest = destinations[0]['ExtendedS3DestinationDescription']
            print_success(f"Destination bucket: {dest['BucketARN'].split(':')[-1]}")
            print_info(f"  Buffering: {dest['BufferingHints']['IntervalInSeconds']}s / {dest['BufferingHints']['SizeInMBs']}MB")
            
            # Check Parquet conversion
            if 'DataFormatConversionConfiguration' in dest:
                conversion = dest['DataFormatConversionConfiguration']
                if conversion.get('Enabled'):
                    print_success("Parquet conversion enabled")
                    schema_config = conversion.get('SchemaConfiguration', {})
                    print_info(f"  Schema: {schema_config.get('DatabaseName')}.{schema_config.get('TableName')}")
                else:
                    print_error("Parquet conversion not enabled")
            else:
                print_error("Parquet conversion not configured")
        
        return True
        
    except ClientError as e:
        print_error(f"Firehose verification failed: {e}")
        return False


def verify_dynamodb_stream():
    """Verify DynamoDB Stream is enabled on Claims table"""
    print_header("Step 7.1: Verifying DynamoDB Stream")
    
    try:
        response = dynamodb.describe_table(TableName=CLAIMS_TABLE)
        table = response['Table']
        
        if 'StreamSpecification' in table and table['StreamSpecification'].get('StreamEnabled'):
            print_success(f"DynamoDB Stream enabled on '{CLAIMS_TABLE}'")
            print_info(f"  Stream ARN: {table['LatestStreamArn']}")
            print_info(f"  View Type: {table['StreamSpecification']['StreamViewType']}")
            return True
        else:
            print_error("DynamoDB Stream not enabled")
            return False
        
    except ClientError as e:
        print_error(f"DynamoDB Stream verification failed: {e}")
        return False


def verify_stream_processor():
    """Verify Lambda stream processor is connected to DynamoDB Stream"""
    print_header("Step 7.1: Verifying Stream Processor Lambda")
    
    try:
        # Check Lambda function exists
        response = lambda_client.get_function(FunctionName=STREAM_PROCESSOR_FUNCTION)
        print_success(f"Stream processor function '{STREAM_PROCESSOR_FUNCTION}' exists")
        
        # Check event source mapping
        mappings = lambda_client.list_event_source_mappings(
            FunctionName=STREAM_PROCESSOR_FUNCTION
        )
        
        if mappings['EventSourceMappings']:
            for mapping in mappings['EventSourceMappings']:
                if CLAIMS_TABLE in mapping['EventSourceArn']:
                    state = mapping['State']
                    if state == 'Enabled':
                        print_success(f"Event source mapping is {state}")
                        print_info(f"  Batch size: {mapping['BatchSize']}")
                        print_info(f"  Starting position: {mapping.get('StartingPosition', 'N/A')}")
                        return True
                    else:
                        print_error(f"Event source mapping state: {state} (expected Enabled)")
                        return False
        else:
            print_error("No event source mapping found for DynamoDB Stream")
            return False
        
    except ClientError as e:
        print_error(f"Stream processor verification failed: {e}")
        return False


def verify_glue_database():
    """Verify Glue Database exists"""
    print_header("Step 7.2: Verifying Glue Data Catalog")
    
    try:
        response = glue.get_database(Name=GLUE_DATABASE)
        print_success(f"Glue database '{GLUE_DATABASE}' exists")
        print_info(f"  Description: {response['Database'].get('Description', 'N/A')}")
        
        # Check for tables
        tables = glue.get_tables(DatabaseName=GLUE_DATABASE)
        if tables['TableList']:
            print_success(f"Found {len(tables['TableList'])} tables:")
            for table in tables['TableList']:
                print_info(f"  - {table['Name']} ({table.get('StorageDescriptor', {}).get('Location', 'N/A')})")
        else:
            print_info("No tables yet (run Glue Crawler to create)")
        
        return True
        
    except ClientError as e:
        print_error(f"Glue database verification failed: {e}")
        return False


def verify_glue_crawler():
    """Verify Glue Crawler is configured"""
    print_header("Step 7.2: Verifying Glue Crawler")
    
    try:
        response = glue.get_crawler(Name=GLUE_CRAWLER)
        crawler = response['Crawler']
        
        print_success(f"Glue crawler '{GLUE_CRAWLER}' exists")
        print_info(f"  State: {crawler['State']}")
        print_info(f"  Database: {crawler['DatabaseName']}")
        
        if 'Targets' in crawler and 'S3Targets' in crawler['Targets']:
            for target in crawler['Targets']['S3Targets']:
                print_info(f"  Target: {target['Path']}")
        
        # Check last crawl
        if 'LastCrawl' in crawler:
            last_crawl = crawler['LastCrawl']
            print_info(f"  Last crawl: {last_crawl.get('Status', 'N/A')}")
            if 'StartTime' in last_crawl:
                print_info(f"  Last run: {last_crawl['StartTime']}")
        else:
            print_info("  Crawler has not run yet")
        
        return True
        
    except ClientError as e:
        print_error(f"Glue crawler verification failed: {e}")
        return False


def run_glue_crawler():
    """Start the Glue Crawler"""
    print_header("Running Glue Crawler")
    
    try:
        glue.start_crawler(Name=GLUE_CRAWLER)
        print_success(f"Started crawler '{GLUE_CRAWLER}'")
        print_info("Crawler will take 2-5 minutes to complete")
        print_info("Check status with: aws glue get-crawler --name " + GLUE_CRAWLER)
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'CrawlerRunningException':
            print_info("Crawler is already running")
            return True
        else:
            print_error(f"Failed to start crawler: {e}")
            return False


def verify_athena_workgroup():
    """Verify Athena workgroup is configured"""
    print_header("Step 7.3: Verifying Athena Workgroup")
    
    try:
        response = athena.get_work_group(WorkGroup=ATHENA_WORKGROUP)
        workgroup = response['WorkGroup']
        
        print_success(f"Athena workgroup '{ATHENA_WORKGROUP}' exists")
        print_info(f"  State: {workgroup['State']}")
        
        config = workgroup['Configuration']
        result_config = config.get('ResultConfigurationUpdates', config.get('ResultConfiguration', {}))
        if 'OutputLocation' in result_config:
            print_info(f"  Output location: {result_config['OutputLocation']}")
        
        return True
        
    except ClientError as e:
        print_error(f"Athena workgroup verification failed: {e}")
        return False


def query_athena():
    """Run a sample Athena query"""
    print_header("Running Sample Athena Query")
    
    try:
        # Check if table exists first
        tables = glue.get_tables(DatabaseName=GLUE_DATABASE)
        if not tables['TableList']:
            print_error("No tables in Glue catalog. Run Glue Crawler first.")
            return False
        
        # Simple count query
        query = f"""
        SELECT 
            COUNT(*) as total_claims,
            COUNT(DISTINCT claim_id) as unique_claims,
            AVG(payout_amount) as avg_payout,
            SUM(total_aws_cost) as total_cost
        FROM {GLUE_DATABASE}.claims
        WHERE event_type = 'INSERT'
        """
        
        print_info("Executing query:")
        print(query)
        
        # Start query execution
        response = athena.start_query_execution(
            QueryString=query,
            QueryExecutionContext={'Database': GLUE_DATABASE},
            WorkGroup=ATHENA_WORKGROUP
        )
        
        query_execution_id = response['QueryExecutionId']
        print_info(f"Query execution ID: {query_execution_id}")
        
        # Wait for query to complete
        max_wait = 30  # seconds
        waited = 0
        while waited < max_wait:
            status = athena.get_query_execution(QueryExecutionId=query_execution_id)
            state = status['QueryExecution']['Status']['State']
            
            if state == 'SUCCEEDED':
                print_success("Query completed successfully")
                
                # Get results
                results = athena.get_query_results(QueryExecutionId=query_execution_id)
                if results['ResultSet']['Rows']:
                    # Skip header row
                    for row in results['ResultSet']['Rows'][1:]:
                        values = [col.get('VarCharValue', 'NULL') for col in row['Data']]
                        print_info(f"  Total Claims: {values[0]}")
                        print_info(f"  Unique Claims: {values[1]}")
                        print_info(f"  Avg Payout: £{float(values[2]):.2f}" if values[2] != 'NULL' else "  Avg Payout: N/A")
                        print_info(f"  Total AWS Cost: £{float(values[3]):.4f}" if values[3] != 'NULL' else "  Total AWS Cost: N/A")
                
                return True
                
            elif state in ['FAILED', 'CANCELLED']:
                reason = status['QueryExecution']['Status'].get('StateChangeReason', 'Unknown')
                print_error(f"Query {state}: {reason}")
                return False
            
            time.sleep(2)
            waited += 2
        
        print_error(f"Query timed out after {max_wait}s")
        return False
        
    except ClientError as e:
        print_error(f"Athena query failed: {e}")
        return False


def verify_data_flow():
    """Verify end-to-end data flow"""
    print_header("Verifying End-to-End Data Flow")
    
    print_info("Checking if claims have been processed to analytics lake...")
    
    try:
        # Check DynamoDB for CLAIM# records (not DOC#/EXTRACT rows)
        response = dynamodb.scan(
            TableName=CLAIMS_TABLE,
            Limit=1,
            FilterExpression="begins_with(PK, :p)",
            ProjectionExpression="PK, SK, claim_id, created_at, #status",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":p": {"S": "CLAIM#"}}
        )
        
        if response['Items']:
            print_success("Found CLAIM# records in DynamoDB table")
            
            # Check S3 for Firehose deliveries
            response = s3.list_objects_v2(
                Bucket=ANALYTICS_BUCKET,
                Prefix='claims/',
                MaxKeys=5
            )
            
            if 'Contents' in response:
                print_success(f"Found {len(response['Contents'])} files in analytics bucket")
                
                # Check file ages
                now = datetime.now(response['Contents'][0]['LastModified'].tzinfo)
                latest_file = response['Contents'][-1]
                age_minutes = (now - latest_file['LastModified']).total_seconds() / 60
                
                print_info(f"  Latest file: {latest_file['Key']}")
                print_info(f"  File age: {age_minutes:.1f} minutes")
                
                if age_minutes < 10:
                    print_success("Data is flowing in real-time")
                else:
                    print_info("Data delivery may be delayed (check Firehose buffering)")
                
                return True
            else:
                print_info("No files in analytics bucket yet")
                print_info("Wait 5-10 minutes for Firehose to deliver first batch")
                return False
        else:
            print_info("No claims in DynamoDB yet")
            print_info("Process some claims first using verify_phase_6.py")
            return False
        
    except ClientError as e:
        print_error(f"Data flow verification failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Verify Phase 7: Analytics & Reporting Implementation'
    )
    parser.add_argument('--run-crawler', action='store_true',
                       help='Start the Glue Crawler after verification')
    parser.add_argument('--query-athena', action='store_true',
                       help='Run a sample Athena query')
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("  ICPA Phase 7 Verification: Analytics & Reporting")
    print("=" * 80)
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)
    
    # Run verifications
    results = []
    
    results.append(("S3 Analytics Bucket", verify_s3_bucket()))
    results.append(("Kinesis Firehose Stream", verify_firehose_stream()))
    results.append(("DynamoDB Stream", verify_dynamodb_stream()))
    results.append(("Stream Processor Lambda", verify_stream_processor()))
    results.append(("Glue Database", verify_glue_database()))
    results.append(("Glue Crawler", verify_glue_crawler()))
    results.append(("Athena Workgroup", verify_athena_workgroup()))
    results.append(("Data Flow", verify_data_flow()))
    
    # Optional: Run crawler
    if args.run_crawler:
        results.append(("Run Glue Crawler", run_glue_crawler()))
    
    # Optional: Query Athena
    if args.query_athena:
        results.append(("Athena Query", query_athena()))
    
    # Summary
    print_header("Verification Summary")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print("\n" + "=" * 80)
    print(f"  Results: {passed}/{total} tests passed")
    print("=" * 80)
    
    if passed == total:
        print_success("\n✓ Phase 7 implementation verified successfully!")
        print_info("\nNext steps:")
        print_info("  1. Wait 5-10 minutes for Firehose to deliver data")
        print_info("  2. Run Glue Crawler: uv run scripts/verify_phase_7.py --run-crawler")
        print_info("  3. Query data: uv run scripts/verify_phase_7.py --query-athena")
        print_info("  4. Set up QuickSight dashboards: docs/quicksight-dashboards.md")
        return 0
    else:
        print_error(f"\n✗ {total - passed} verification(s) failed")
        print_info("\nTroubleshooting:")
        print_info("  1. Ensure Analytics Stack is deployed: cdk deploy ICPA-AnalyticsStack")
        print_info("  2. Check CloudWatch logs for errors")
        print_info("  3. Verify IAM permissions for Firehose and Lambda")
        return 1


if __name__ == "__main__":
    exit(main())
