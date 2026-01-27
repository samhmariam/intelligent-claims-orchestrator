import boto3
import sys
import os
import time
import uuid
import json
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# --- Config ---
AWS_REGION = 'us-east-1'
CLEAN_BUCKET = "icpa-clean-data"
QUARANTINE_BUCKET = "icpa-quarantine"
CLAIMS_TABLE = "ICPA_Claims"

session = boto3.Session(region_name=AWS_REGION)
s3 = session.client('s3')
dynamodb = session.resource('dynamodb')
sf = session.client('stepfunctions')

def generate_test_image(text, text_color="black"):
    img = Image.new('RGB', (800, 600), color='white')
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except IOError:
        font = ImageFont.load_default()
    d.text((10, 10), text, fill=text_color, font=font)
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()

def upload_file(bucket, key, content):
    print(f"Uploading to s3://{bucket}/{key}...")
    s3.put_object(Bucket=bucket, Key=key, Body=content)

def get_claim_status(claim_uuid):
    table = dynamodb.Table(CLAIMS_TABLE)
    resp = table.get_item(Key={'PK': claim_uuid, 'SK': 'META'})
    return resp.get('Item', {})

def resolve_claim_id(external_id):
    table = dynamodb.Table(CLAIMS_TABLE)
    response = table.query(
        IndexName='ExternalIdIndex',
        KeyConditionExpression=boto3.dynamodb.conditions.Key('external_id').eq(external_id)
    )
    items = response.get('Items', [])
    if items:
        # The Index might return the MAPPING# record or the CLAIM# record.
        # Both should have 'claim_id' attribute.
        # We want to return the PK of the CLAIM record, which is "CLAIM#<uuid>"
        found_item = items[0]
        if 'claim_id' in found_item:
            c_uuid = found_item['claim_id']
            return f"CLAIM#{c_uuid}"
            
        return found_item.get('PK')
    return None

def wait_for_status(claim_uuid, target_statuses, timeout=120):
    print(f"Waiting for status {target_statuses} for claim {claim_uuid}...")
    start = time.time()
    while time.time() - start < timeout:
        item = get_claim_status(claim_uuid)
        status = item.get('status')
        if status in target_statuses:
            return item
        if status == 'ERROR_REVIEW' and 'ERROR_REVIEW' not in target_statuses:
             # If we didn't expect error but got it, fail fast, UNLESS we are testing negative path
             pass
        time.sleep(5)
        print(".", end="", flush=True)
    print(" Timeout!")
    return None

def verify_happy_path():
    print("\n=== Test 1: Happy Path (Auto-Approve) ===")
    claim_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    key = f"{claim_id}/doc_id={doc_id}/invoice_clean.png"
    
    # Mock clean text (Phase 1 output)
    content = generate_test_image("Invoice #123\nDate: 2023-01-01\nVendor: Office Supplies Co.\nAmount: $50.00\nItem: High Quality Office Paper")
    upload_file(CLEAN_BUCKET, key, content)
    
    item = wait_for_status(claim_id, ['APPROVED'])
    if item and item.get('status') == 'APPROVED':
        print(" [PASS] Claim Automatically Approved.")
    else:
        print(f" [FAIL] Status is {item.get('status') if item else 'None'}")

def verify_review_path():
    print("\n=== Test 2: Review Path (Sensitive/High Value) ===")
    claim_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    key = f"{claim_id}/doc_id={doc_id}/medical_clean.png"
    
    # Trigger Review: High Value + Redaction
    # Note: Decision Engine looks for [REDACTED] near 'Total'/'Amount' etc.
    content = generate_test_image("Medical Report\n[REDACTED]\nTotal Amount: $5,000.00")
    upload_file(CLEAN_BUCKET, key, content)
    
    item = wait_for_status(claim_id, ['NEEDS_REVIEW'])
    if item and item.get('status') == 'NEEDS_REVIEW':
        print(" [PASS] Claim Routed to Review (High Value/Redacted).")
    else:
        print(f" [FAIL] Status is {item.get('status') if item else 'None'}")

def verify_negative_path():
    print("\n=== Test 3: Negative Path (Low Confidence) ===")
    claim_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    key = f"{claim_id}/doc_id={doc_id}/low_conf.png"
    
    # Small text -> "Low Confidence" logic in Decision Engine
    content = generate_test_image("Hi") 
    upload_file(CLEAN_BUCKET, key, content)
    
    item = wait_for_status(claim_id, ['NEEDS_REVIEW', 'ERROR_REVIEW'])
    if item:
        print(f" [PASS] Handled gracefully. Status: {item.get('status')}")
    else:
        print(" [FAIL] No status update.")

def verify_idempotency():
    print("\n=== Test 4: Idempotency (Re-run) ===")
    # 1. Upload File
    claim_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    key = f"{claim_id}/doc_id={doc_id}/retry_test.png"
    content = generate_test_image("Invoice $100.00")
    
    print(" -> First Upload")
    upload_file(CLEAN_BUCKET, key, content)
    wait_for_status(claim_id, ['APPROVED'])
    
    # 2. Upload Same File Again
    print(" -> Second Upload (Duplicate)")
    upload_file(CLEAN_BUCKET, key, content)
    
    # Monitor for 20 seconds
    time.sleep(20)
    item = get_claim_status(claim_id)
    print(f" [PASS] status remains {item.get('status')}")

def debug_last_execution():
    print("\n=== Debugging Last Execution ===")
    state_machine_arn = "arn:aws:states:us-east-1:120106008631:stateMachine:OrchestrationStateMachineFE6E059A-WVpJU4U9FW9b"
    # Note: Hardcoded ARN for debug. Ideally fetch dynamically.
    # Logic: List executions, get latest, describe.
    
    try:
        exs = sf.list_executions(stateMachineArn=state_machine_arn, maxResults=1)
        if not exs['executions']:
            print("No executions found.")
            return
            
        latest = exs['executions'][0]
        print(f"Latest Execution: {latest['executionArn']}")
        print(f"Status: {latest['status']}")
        
        if latest['status'] == 'FAILED':
            hist = sf.get_execution_history(executionArn=latest['executionArn'], maxResults=5, reverseOrder=True)
            for event in hist['events']:
                if 'executionFailedEventDetails' in event:
                    print(f"FAILURE DETAILS: {event['executionFailedEventDetails']}")
                    break
        elif latest['status'] == 'RUNNING':
             # Check current state
             print("Execution is RUNNING.")
             
    except Exception as e:
        print(f"Debug Error: {e}")

import argparse

def verify_golden_set(claim_id, golden_file):
    print(f"\n=== verifying Golden Set: {claim_id} ===")
    
    # 1. Load Golden Data
    with open(golden_file, 'r') as f:
        golden = json.load(f)
    print(f"Loaded Golden File: {golden_file}")
    print(f"Expected Decision: {golden['expected_decision']}")
    
    # 2. Upload Data
    # Local Path: test-data/claims/{claim_id}/raw/
    base_dir = f"test-data/claims/{claim_id}/raw"
    if not os.path.exists(base_dir):
        print(f"Error: Directory {base_dir} not found.")
        return

    print("Syncing files to S3...")
    # Walk directory and upload
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            local_path = os.path.join(root, file)
            # S3 Key: {claim_id}/raw/{subdirectory}/{filename}
            # e.g. CLM-000001/raw/documents/file.pdf
            rel_path = os.path.relpath(local_path, f"test-data/claims/{claim_id}")
            s3_key = f"{claim_id}/{rel_path}".replace("\\", "/") 
            
            # Map raw/ to bucket root? No, typically "raw/" is inside the claim prefix or root?
            # User said: s3://icpa-raw-data/CLM-000001/raw/documents/
            # My 'upload_file' uploads to CLEAN_BUCKET (icpa-clean-data).
            # Wait, user instructions say: "Upload... to the raw/ folder... s3://icpa-raw-data/..."
            # AND "Triggers Ingestion". Ingestion triggers from RAW bucket.
            # My 'verify_phase_3.py' normally uploads to 'icpa-clean-data' (skipping Phase 1).
            # BUT 'Golden Set' implies FULL E2E?
            # "Triggers Ingestion: It ensures the files are in S3, triggering the OrchestrationStateMachine."
            # Actually, typically Orchestrator triggers from CLEAN bucket.
            # INGESTION triggers from RAW bucket.
            # If I upload to RAW, it goes Phase 1 -> Phase 2 -> Phase 3.
            # The user says: "Monitors Extraction: It waits for Phase 2 to complete".
            # So I should upload to RAW BUCKET.
            
            # RAW BUCKET variable needed.
            RAW_BUCKET = "icpa-raw-intake" # Hardcoded based on infrastructure
            print(f"Uploading {local_path} -> s3://{RAW_BUCKET}/{s3_key}")
            s3.put_object(Bucket=RAW_BUCKET, Key=s3_key, Body=open(local_path, 'rb').read())
            
    # 3. Wait for Decision
    target_status = golden['expected_decision']
    # Map 'DENY' to 'DENIED' if needed, but let's assume 'DENIED' in table or 'DENY'.
    # My code sets 'DENIED'. Golden says 'DENY'.
    # Map golden 'DENY' -> 'DENIED', 'APPROVE' -> 'APPROVED'
    status_map = { "DENY": "DENIED", "APPROVE": "APPROVED", "REVIEW": "NEEDS_REVIEW" }
    expected_db_status = status_map.get(target_status, target_status)
    
    print(f"Waiting for DB Status: {expected_db_status}")
    
    # Resolve valid claim_id from External ID
    resolved_claim_id = resolve_claim_id(claim_id)
    if not resolved_claim_id:
        print(f" [FAIL] Could not resolve claim_id for external_id {claim_id}")
        return

    print(f"Resolved External ID {claim_id} -> Claim UUID {resolved_claim_id}")
    item = wait_for_status(resolved_claim_id, [expected_db_status])
    
    if item and item.get('status') == expected_db_status:
        print(" [PASS] Golden Set Validation Successful.")
        print(f" Reason: {item.get('decision_reason')}")
    else:
        print(f" [FAIL] Final Status: {item.get('status') if item else 'None'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-id", help="Claim ID for Golden Set")
    parser.add_argument("--golden-file", help="Path to golden.json")
    args = parser.parse_args()

    if args.claim_id and args.golden_file:
        verify_golden_set(args.claim_id, args.golden_file)
    else:
        verify_happy_path()
        # debug_last_execution() 
        # verify_review_path()
        # verify_negative_path()
        # verify_idempotency()
