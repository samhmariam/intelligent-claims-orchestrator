import boto3
import sys
import os
import time
import uuid
from botocore.exceptions import ClientError

def upload_test_file(s3, bucket, key, content):
    print(f"Uploading to {bucket}/{key}...")
    s3.put_object(Bucket=bucket, Key=key, Body=content)
    return True

def wait_for_clean_object(s3, bucket, claim_id, timeout=30):
    print(f"Polling {bucket} for claim {claim_id}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        # List objects with prefix = claim_id
        # We expect <claim_id>/doc_id=<uuid>/test.txt
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=claim_id)
        if 'Contents' in resp:
            for obj in resp['Contents']:
                print(f"[OK] Found object: {obj['Key']}")
                return True
        time.sleep(2)
    print(f"[FAIL] Timeout waiting for object in {bucket}")
    return False

def wait_for_dynamo_item(dynamodb, table_name, claim_id, timeout=30):
    print(f"Polling {table_name} for CLAIM#{claim_id}...")
    table = dynamodb.Table(table_name)
    start_time = time.time()
    while time.time() - start_time < timeout:
        resp = table.get_item(Key={'PK': f"CLAIM#{claim_id}", 'SK': 'META'})
        if 'Item' in resp:
            item = resp['Item']
            print(f"[OK] Found DynamoDB item: {item}")
            if item.get('status') == 'INTAKE':
                 return True
            else:
                 print(f"[WARN] Item status is {item.get('status')}, expected INTAKE")
        time.sleep(2)
    print(f"[FAIL] Timeout or missing item in {table_name}")
    return False

def main():
    # Enforce us-east-1
    session = boto3.Session(region_name='us-east-1')
    s3 = session.client('s3')
    dynamodb = session.resource('dynamodb')

    # Config
    RAW_BUCKET = "icpa-raw-intake"
    CLEAN_BUCKET = "icpa-clean-data"
    CLAIMS_TABLE = "ICPA_Claims"

    claim_id = str(uuid.uuid4())
    filename = "tracer_bullet.txt"
    # Format: raw/documents/<claim_id>/<filename> (Matches EventBridge Rule)
    key = f"raw/documents/{claim_id}/{filename}"
    content = b"This is a tracer bullet."

    try:
        # 1. Upload
        upload_test_file(s3, RAW_BUCKET, key, content)

        # 2. Verify Clean Bucket
        if not wait_for_clean_object(s3, CLEAN_BUCKET, claim_id):
            sys.exit(1)

        # 3. Verify DynamoDB
        if not wait_for_dynamo_item(dynamodb, CLAIMS_TABLE, claim_id):
            sys.exit(1)

        print("\nSUCCESS: Phase 1 Ingestion Tracer Bullet verified.")
        sys.exit(0)

    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
