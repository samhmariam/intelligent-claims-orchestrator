import boto3
import time
import uuid
import json
import os
import argparse
try:
    from scripts.verify_phase_3 import generate_test_image, upload_file, wait_for_status, CLEAN_BUCKET, CLAIMS_TABLE, resolve_claim_id
except ImportError:
    # Fallback if running from within scripts/ directory
    from verify_phase_3 import generate_test_image, upload_file, wait_for_status, CLEAN_BUCKET, CLAIMS_TABLE, resolve_claim_id

s3 = boto3.client('s3')

def verify_context_assembly(claim_id=None):
    if not claim_id:
        claim_id = str(uuid.uuid4())
        
    print(f"\n=== Verifying Phase 4: Context Assembly for {claim_id} ===")
    
    # 1. Upload Test Data (Raw Files)
    # Target: s3://icpa-raw-intake/<claim_id>/raw/...
    # Local: test-data/claims/<claim_id>/raw/
    RAW_BUCKET = "icpa-raw-intake"
    base_dir = f"test-data/claims/{claim_id}/raw"
    
    if not os.path.exists(base_dir):
        print(f"[ERROR] Test data not found at {base_dir}")
        return

    print("Syncing Raw files to S3 (Phase 1 Trigger)...")
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            local_path = os.path.join(root, file)
            # Rel path: documents/FNOL.pdf from CLM/raw/documents/FNOL.pdf
            rel_path = os.path.relpath(local_path, base_dir)
            # S3 Key: CLM-000001/raw/documents/FNOL.pdf
            s3_key = f"{claim_id}/raw/{rel_path}".replace("\\", "/")
            
            print(f" -> Uploading {local_path} to s3://{RAW_BUCKET}/{s3_key}")
            s3.put_object(Bucket=RAW_BUCKET, Key=s3_key, Body=open(local_path, 'rb').read())

    # 2. Resolve UUID
    print("Waiting for Ingestion to resolve Claim UUID...")
    resolved_uuid = None
    for i in range(12): # 60 seconds
        time.sleep(5)
        resolved_uuid = resolve_claim_id(claim_id)
        if resolved_uuid:
             # Returns CLAIM#<uuid>
             resolved_uuid = resolved_uuid.replace("CLAIM#", "")
             print(f" -> Resolved: {resolved_uuid}")
             break
        print(".", end="", flush=True)
        
    if not resolved_uuid:
        print("\n[FAIL] Could not resolve Claim UUID. Ingestion failed?")
        return

    # 3. Verify Bundle in S3 (Phase 4 Output)
    # The assembler runs AFTER extraction. Extraction takes time.
    bundle_key = f"{resolved_uuid}/context/context_bundle.json"
    print(f"Waiting for Context Bundle: s3://{CLEAN_BUCKET}/{bundle_key}...")
    
    bundle = None
    for i in range(30): # 2.5 minutes wait (Extraction can be slow)
        try:
            obj = s3.get_object(Bucket=CLEAN_BUCKET, Key=bundle_key)
            bundle = json.loads(obj['Body'].read())
            print("\n[SUCCESS] Bundle found.")
            break
        except s3.exceptions.NoSuchKey:
            time.sleep(5)
            print(".", end="", flush=True)
            
    if not bundle:
        print("\n[FAIL] Context Bundle not created in time.")
        return

    # 4. Validation Checks
    print("Validating Bundle Content...")
    status = bundle.get('status')
    timeline = bundle.get('timeline', [])
    docs = bundle.get('documents', [])
    
    print(f"Bundle Status: {status}")
    print(f"Timeline Events: {len(timeline)}")
    print(f"Documents: {len(docs)}")
    
    # Check Evidence Links
    has_links = any('source_doc_id' in event for event in timeline)
    print(f"Evidence Links Present: {has_links}")
    
    if len(docs) >= 2 and has_links:
        print("[PASS] Context Assembly Verified.")
    else:
        print("[FAIL] Bundle validation failed (Check document count or evidence links).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-id", help="Claim ID to verify", default="CLM-000001")
    args = parser.parse_args()

    verify_context_assembly(args.claim_id)
