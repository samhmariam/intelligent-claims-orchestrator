import boto3
import sys
from botocore.exceptions import ClientError

def verify_bucket_exists(s3, bucket_name):
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"[OK] Bucket exists: {bucket_name}")
        return True
    except ClientError as e:
        print(f"[FAIL] Bucket {bucket_name} not found or access denied: {e}")
        return False

def verify_table_active(dynamodb, table_name):
    try:
        table = dynamodb.Table(table_name)
        status = table.table_status
        if status == 'ACTIVE':
            print(f"[OK] Table active: {table_name}")
            return True
        else:
            print(f"[FAIL] Table {table_name} is {status}")
            return False
    except ClientError as e:
        print(f"[FAIL] Table {table_name} check failed: {e}")
        return False

def main():
    # Enforce us-east-1 as per PRD Phase 1 Requirement 1.1
    session = boto3.Session(region_name='us-east-1')
    s3 = session.client('s3')
    dynamodb = session.resource('dynamodb')

    print("=== Verifying Phase 0: Foundations ===")
    
    # Check Buckets
    buckets = ["icpa-raw-intake", "icpa-clean-data", "icpa-quarantine"]
    bucket_results = [verify_bucket_exists(s3, b) for b in buckets]

    # Check Tables
    tables = ["ICPA_Claims", "ICPA_Idempotency", "ICPA_Evaluation"]
    table_results = [verify_table_active(dynamodb, t) for t in tables]

    if all(bucket_results) and all(table_results):
        print("\nSUCCESS: Phase 0 Foundations verified.")
        sys.exit(0)
    else:
        print("\nFAILURE: Phase 0 verification failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
