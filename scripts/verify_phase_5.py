import boto3
import json
import uuid
import time
import argparse
import os
from datetime import datetime

# Config
EVENT_BUS_NAME = "ICPA_EventBus"
CLAIMS_TABLE = "ICPA_Claims"
RAW_BUCKET = "icpa-raw-intake"
CLEAN_BUCKET = "icpa-clean-data"
SOURCE = "com.icpa.orchestration"

events = boto3.client('events')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(CLAIMS_TABLE)
s3 = boto3.client('s3')

def resolve_claim_id(external_id):
    """
    Query GSI to find the canonical internal UUID for a given external_id.
    """
    try:
        resp = table.query(
            IndexName='ExternalIdIndex',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('external_id').eq(external_id)
        )
        items = resp.get('Items', [])
        if items:
            # Format: CLAIM#<uuid>
            return items[0].get('PK')
        return None
    except Exception as e:
        print(f"Error resolving ID: {e}")
        return None

def upload_test_data(claim_id):
    """Uploads raw files to act as the trigger/data source."""
    base_dir = f"test-data/claims/{claim_id}/raw"
    if not os.path.exists(base_dir):
        print(f"[WARNING] Test data directory {base_dir} not found. Skipping upload.")
        return

    print(f"Syncing raw files for {claim_id}...")
    count = 0
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            local_path = os.path.join(root, file)
            rel_path = os.path.relpath(local_path, base_dir)
            # S3 Key: <claim_id>/raw/...
            s3_key = f"{claim_id}/raw/{rel_path}".replace("\\", "/")
            
            s3.put_object(Bucket=RAW_BUCKET, Key=s3_key, Body=open(local_path, 'rb').read())
            count += 1
            
    print(f" -> Uploaded {count} files.")

def wait_for_processing(claim_id):
    """Waits for the claim to be processed (Context Bundle created)."""
    print(f"Waiting for processing of {claim_id}...")
    
    # 1. Resolve UUID (if claim_id is external like CLM-000001)
    resolved_uuid = None
    if claim_id.startswith("CLM-"):
        for i in range(12):
            pk = resolve_claim_id(claim_id)
            if pk:
                resolved_uuid = pk.replace("CLAIM#", "")
                break
            time.sleep(5)
            print(".", end="", flush=True)
        if not resolved_uuid:
            print("\n[FAIL] Could not resolve UUID from External ID.")
            return None
    else:
        resolved_uuid = claim_id 

    # 2. Wait for Context Bundle
    bundle_key = f"{resolved_uuid}/context/context_bundle.json"
    print(f"\nPolling for bundle: s3://{CLEAN_BUCKET}/{bundle_key}")
    
    for i in range(30): # 2.5 mins
        try:
            s3.head_object(Bucket=CLEAN_BUCKET, Key=bundle_key)
            print("[SUCCESS] Context Bundle found. Pipeline Check passed.")
            return resolved_uuid
        except:
            time.sleep(5)
            print(".", end="", flush=True)
            
    print("\n[WARNING] Context Bundle not found. Payout verification might fail/be meaningless.")
    return resolved_uuid

def cleanup_claim(claim_uuid):
    """Deletes the mock claim meta to prevent clutter (skips persistent IDs)."""
    if claim_uuid and (claim_uuid.startswith("CLM-") or claim_uuid.startswith("TEST-PERSIST")):
        print(f"Skipping cleanup for persistent claim {claim_uuid}")
        return
        
    print(f"Cleaning up {claim_uuid}...")
    try:
        table.delete_item(Key={'PK': f"CLAIM#{claim_uuid}", 'SK': 'META'})
    except Exception as e:
        print(f"Cleanup failed: {e}")

def verify_payout_scenario(external_id=None):
    """Scenario A: File Upload -> Wait -> Approve Event -> Payout Verification."""
    print("\n=== Scenario A: E2E Payout (Upload -> Process -> Payout) ===")
    
    target_id = external_id if external_id else f"TEST-{uuid.uuid4()}"
    
    # Step 1: Upload Data (Simulates Phase 1)
    upload_test_data(target_id)
    
    # Step 2: Wait for Pipeline (Simulates Phase 2-4)
    # This ensures the backend knows about the claim before we try to pay it.
    resolved_uuid = wait_for_processing(target_id)
    
    if not resolved_uuid:
        resolved_uuid = str(uuid.uuid4()) # Fallback for pure mock test
        print(f"Proceeding with Mock UUID {resolved_uuid}")

    # Ensure metadata exists (if pipeline failed or didn't run)
    # We update it to ensure 'status' is ready for transition
    print(f"Ensuring metadata for {resolved_uuid}...")
    table.put_item(Item={
        'PK': f"CLAIM#{resolved_uuid}",
        'SK': 'META',
        'claim_uuid': resolved_uuid,
        'external_id': target_id,
        'status': 'DECIDED', # Ready for final event
        'created_at': datetime.utcnow().isoformat()
    })

    try:
        # Step 3: Trigger Payout (Simulates Phase 5 Outcome)
        print(f"Emitting APPROVED event for {resolved_uuid}...")
        entry = {
            'Source': SOURCE,
            'DetailType': 'ClaimDecision',
            'Detail': json.dumps({
                "claim_uuid": resolved_uuid,
                "external_id": target_id,
                "status": "APPROVED",
                "reason": "E2E Verification Approval",
                "payout_gbp": 150.00
            }),
            'EventBusName': EVENT_BUS_NAME
        }
        
        resp = events.put_events(Entries=[entry])
        print(f"Event ID: {resp['Entries'][0]['EventId']}")
        
        # Step 4: Verify Result (Poll DB)
        print("Waiting for CLOSED_PAID status...")
        for i in range(12): # 60s
            resp = table.get_item(Key={'PK': f"CLAIM#{resolved_uuid}", 'SK': 'META'})
            item = resp.get('Item', {})
            status = item.get('status')
            
            if status == 'CLOSED_PAID':
                print(f"[PASS] Claim {resolved_uuid} ({target_id}) is CLOSED_PAID.")
                
                final_payout = item.get('final_payout_gbp')
                if str(final_payout).startswith("150"):
                     print(f"[PASS] Final Payout Matches: £{final_payout}")
                else:
                     print(f"[FAIL] Final Payout Mismatch: £{final_payout} != 150.00")
                return
            
            time.sleep(5)
            print(".", end="", flush=True)
            
        print(f"\n[FAIL] Claim status is {status}")
        
    finally:
        if resolved_uuid:
            cleanup_claim(resolved_uuid)

def verify_denied_logic_guard():
    """Scenario B: Logic Guard - DENIED claim with accidental payout amount."""
    print("\n=== Scenario B: Logic Guard (DENIED with Accidental Payout) ===")
    
    # Create a mock claim
    claim_uuid = str(uuid.uuid4())
    external_id = f"TEST-DENY-{uuid.uuid4().hex[:8]}"
    
    print(f"Creating mock claim {claim_uuid}...")
    table.put_item(Item={
        'PK': f"CLAIM#{claim_uuid}",
        'SK': 'META',
        'claim_uuid': claim_uuid,
        'external_id': external_id,
        'status': 'DECIDED',
        'context_bundle_s3_key': f's3://icpa-clean-data/{claim_uuid}/context/context_bundle.json',
        'created_at': datetime.utcnow().isoformat()
    })
    
    try:
        # Emit a DENIED event but 'accidentally' include a payout amount
        print(f"Emitting DENIED event with accidental payout £999.99...")
        entry = {
            'Source': SOURCE,
            'DetailType': 'ClaimDecision',
            'Detail': json.dumps({
                "claim_uuid": claim_uuid,
                "external_id": external_id,
                "status": "DENIED",
                "reason": "Fraudulent claim detected",
                "payout_gbp": 999.99  # Should be forced to 0.0 by logic guard
            }),
            'EventBusName': EVENT_BUS_NAME
        }
        
        resp = events.put_events(Entries=[entry])
        print(f"Event ID: {resp['Entries'][0]['EventId']}")
        
        # Wait and verify
        print("Waiting for payment processing...")
        time.sleep(10)  # Give Lambda time to process
        
        # Verify DB: final_payout should be 0.0
        resp = table.get_item(Key={'PK': f"CLAIM#{claim_uuid}", 'SK': 'META'})
        item = resp.get('Item', {})
        
        final_payout = item.get('final_payout_gbp', 'NOT_SET')
        context_key = item.get('context_bundle_s3_key')
        
        # Check payout
        if final_payout == "0.0" or final_payout == 0.0:
            print(f"[PASS] Logic Guard successfully zeroed the unauthorized payout (£{final_payout})")
        else:
            print(f"[FAIL] Logic Guard failed! Payout is £{final_payout} (expected £0.0)")
        
        # Check evidence link preservation
        if context_key:
            print(f"[PASS] Evidence Link preserved: {context_key}")
        else:
            print(f"[FAIL] Evidence Link missing after payment update")
            
    finally:
        cleanup_claim(claim_uuid)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-id", help="Claim ID to verify (e.g. CLM-000001)", default="CLM-000001")
    parser.add_argument("--test-logic-guard", action="store_true", help="Run negative test for DENIED claims")
    parser.add_argument("--all", action="store_true", help="Run all test scenarios")
    args = parser.parse_args()
    
    if args.all:
        verify_payout_scenario(args.claim_id)
        verify_denied_logic_guard()
    elif args.test_logic_guard:
        verify_denied_logic_guard()
    else:
        verify_payout_scenario(args.claim_id)

