import boto3
import sys
import os
import time
import uuid
import json
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

def generate_test_image(text):
    """Generates a PNG image with the given text."""
    # Create white image
    img = Image.new('RGB', (800, 600), color='white')
    d = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except IOError:
        font = ImageFont.load_default()

    d.text((50, 50), text, fill=(0, 0, 0), font=font)
    
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def upload_test_file(s3, bucket, key, content):
    print(f"Uploading to {bucket}/{key}...")
    s3.put_object(Bucket=bucket, Key=key, Body=content)
    return True

def wait_for_dynamo_status(dynamodb, table_name, claim_id, expected_status='EXTRACTED', timeout=90):
    print(f"Polling {table_name} for CLAIM#{claim_id} status={expected_status}...")
    table = dynamodb.Table(table_name)
    start_time = time.time()
    while time.time() - start_time < timeout:
        resp = table.get_item(Key={'PK': f"CLAIM#{claim_id}", 'SK': 'META'})
        item = resp.get('Item', {})
        status = item.get('status')
        if status == expected_status:
            print(f"[OK] Status is {status}")
            return item
        elif status:
            print(f"[INFO] Current status: {status}")
        time.sleep(5)
    print(f"[FAIL] Timeout or wrong status in {table_name}")
    return None

def verify_s3_object(s3, bucket, key, must_contain=None):
    print(f"Checking {bucket}/{key}...")
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
        body = resp['Body'].read().decode('utf-8')
        if must_contain:
            if must_contain in body:
                print(f"[OK] Found expected content: '{must_contain}'")
                return True
            else:
                print(f"[FAIL] Content missing '{must_contain}'. Body preview: {body[:100]}")
                return False
        return True
    except Exception as e:
        print(f"[FAIL] Object missing or error: {e}")
        return False

from boto3.dynamodb.conditions import Key

def wait_for_claim_id(dynamodb, table_name, external_id, timeout=60):
    print(f"Resolving External ID '{external_id}' in {table_name}...")
    table = dynamodb.Table(table_name)
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # Query GSI
        resp = table.query(
            IndexName='ExternalIdIndex',
            KeyConditionExpression=Key('external_id').eq(external_id)
        )
        items = resp.get('Items', [])
        if items:
            claim_id = items[0]['claim_id']
            status = items[0].get('status')
            print(f"[OK] Found Context: {external_id} -> {claim_id} (Status: {status})")
            return claim_id
        time.sleep(2)
        
    print(f"[FAIL] Could not resolve External ID {external_id}")
    return None

def verify_s3_metadata(s3, bucket, key, expected_external_id):
    print(f"Checking Metadata for {bucket}/{key}...")
    try:
        resp = s3.head_object(Bucket=bucket, Key=key)
        metadata = resp.get('Metadata', {})
        external_id = metadata.get('external-id')
        
        if external_id == expected_external_id:
            print(f"[OK] Metadata 'external-id' matches: {external_id}")
            return True
        else:
            print(f"[FAIL] Metadata mismatch. Expected {expected_external_id}, got {external_id}. All Meta: {metadata}")
            return False
    except Exception as e:
        print(f"[FAIL] Error checking metadata: {e}")
        return False

def run_verification(s3, dynamodb, clean_bucket, quarantine_bucket, claims_table, filename, content, data_type_name="Image", external_id_prefix="CLM-TEST"):
    # Generate unique External ID for this run, but normalized
    ram_suffix = str(uuid.uuid4())[:8].upper()
    external_id = f"{external_id_prefix}-{ram_suffix}"
    
    print(f"\n--- Verifying {data_type_name} ({filename}) | External ID: {external_id} ---")
    
    # 1. Upload Clean File (Trigger) using External ID path
    # Path: raw/documents/<external_id>/<filename>
    key = f"raw/documents/{external_id}/{filename}"
    upload_test_file(s3, "icpa-raw-intake", key, content) # Note: Need RAW bucket name passed in or hardcoded

    # 2. Resolve Claim UUID via GSI
    claim_id = wait_for_claim_id(dynamodb, claims_table, external_id)
    if not claim_id:
        return False

    # 3. Verify DynamoDB Status (EXTRACTED)
    # Re-use existing wait logic using the resolved claim_id
    item = wait_for_dynamo_status(dynamodb, claims_table, claim_id, 'EXTRACTED')
    if not item:
        return False
        
    # Verify Metadata logic
    meta = item.get('extraction_metadata', {})
    print(f"Metadata: {meta}")
    print(f"Extractor Used: {meta.get('extractor')}")

    # 4. Verify Clean Extract
    doc_id = item.get('latest_doc_id') # Get actual doc_id (newly generated) from DynamoDB item
    if not doc_id:
        print("[FAIL] 'latest_doc_id' not found in DynamoDB item.")
        return False

    # Check S3 Metadata on the Clean Document
    clean_key = f"{claim_id}/doc_id={doc_id}/{filename}"
    if not verify_s3_metadata(s3, clean_bucket, clean_key, external_id):
        return False

    extract_key = f"{claim_id}/extracts/{doc_id}.txt"
    if not verify_s3_object(s3, clean_bucket, extract_key):
        return False
        
    # Check redaction only for the generated PNG which we know has PHI
    if data_type_name == "Image (PHI)":
         if not verify_s3_object(s3, clean_bucket, extract_key, must_contain="[REDACTED:NAME]"):
             return False

    # 5. Verify Quarantine Audit (Raw)
    audit_key = f"phi-audit/{claim_id}/{doc_id}.json"
    if not verify_s3_object(s3, quarantine_bucket, audit_key):
         return False
    
    print(f"[SUCCESS] {data_type_name} Verified.")
    return True

def main():
    session = boto3.Session(region_name='us-east-1')
    s3 = session.client('s3')
    dynamodb = session.resource('dynamodb')

    # Config
    CLEAN_BUCKET = "icpa-clean-data"
    QUARANTINE_BUCKET = "icpa-quarantine"
    CLAIMS_TABLE = "ICPA_Claims"
    
    print("=== Phase 2.5 Verification: Context Propagation ===")

    # Test 1: Generated PNG with PHI
    print("\nGenerating Test Image (PNG)...")
    png_content = generate_test_image("Medical Record.\nPatient Name: John Doe.\nDiagnosis: Flu.")
    # Passing RAW BUCKET is needed for upload fn, but run_verification takes s3, dyn, clean, quar, table...
    # Updating run_verification signature implies I need to pass raw bucket name too or hardcode it inside.
    # The snippet above hardcoded "icpa-raw-intake" inside run_verification for simplicity/safety.

    if not run_verification(s3, dynamodb, CLEAN_BUCKET, QUARANTINE_BUCKET, CLAIMS_TABLE, "medical_record.png", png_content, "Image (PHI)"):
        sys.exit(1)

    # Test 2: PDF (Upload local file)
    pdf_path = r"test-data\claims\CLM-000001\raw\documents\INVOICE.pdf"
    if os.path.exists(pdf_path):
        print("\nLoading Test PDF...")
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
        if not run_verification(s3, dynamodb, CLEAN_BUCKET, QUARANTINE_BUCKET, CLAIMS_TABLE, "invoice.pdf", pdf_content, "PDF"):
            sys.exit(1)
    else:
        print(f"\n[WARN] PDF file not found at {pdf_path}. Skipping PDF test.")

    print("\nOVERALL SUCCESS: Context Propagation verified.")
    sys.exit(0)

if __name__ == "__main__":
    main()
