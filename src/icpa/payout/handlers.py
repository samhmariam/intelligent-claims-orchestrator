import os
import json
import boto3
from aws_lambda_powertools import Logger, Tracer

logger = Logger(service="payment-service")
tracer = Tracer(service="payment-service")

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('CLAIMS_TABLE_NAME', 'ICPA_Claims')
table = dynamodb.Table(table_name)

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event, context):
    """
    Payment Service Lambda.
    Triggered by EventBridge Rule on "ClaimDecision" where status="APPROVED".
    """
    logger.info("Received Payment Event", extra={"event": event})
    
    # EventBridge payload is in 'detail'
    detail = event.get('detail', {})
    claim_uuid = detail.get('claim_uuid')
    payout_gbp = detail.get('payout_gbp', 0.0)
    external_id = detail.get('external_id')
    
    if not claim_uuid:
        logger.error("Missing claim_uuid in event")
        return
        
    logger.info(f"Processing Payout for {claim_uuid} ({external_id})")
    
    # 1. Idempotency Check
    # Check if already paid
    try:
        resp = table.get_item(Key={'PK': f"CLAIM#{claim_uuid}", 'SK': 'META'})
        item = resp.get('Item', {})
        current_status = item.get('status')
        
        # Diagnostic: Check if context_bundle_s3_key exists BEFORE update
        context_key = item.get('context_bundle_s3_key')
        if context_key:
            logger.info(f"✓ Evidence Link Present: {context_key}")
        else:
            logger.warning(f"⚠ Evidence Link Missing: context_bundle_s3_key not found in record before payment")
        
        if current_status == 'CLOSED_PAID':
            logger.info(f"Claim {claim_uuid} is already CLOSED_PAID. Skipping duplicate payout.")
            return {"status": "SKIPPED", "reason": "Already Paid"}
            
    except Exception as e:
        logger.exception(f"Failed to check idempotency for {claim_uuid}")
        raise e

    # 2. Payout Validation (Sanity Check)
    # CRITICAL: Only pay if status is APPROVED/APPROVE
    event_status = detail.get('status', 'review').upper()
    
    # Ensure amount is positive AND status is APPROVED
    try:
        amount = float(payout_gbp)
        
        # LOGIC GUARD: Force zero payout for non-APPROVED claims
        if event_status not in ['APPROVED', 'APPROVE']:
            amount = 0.0  # Force zero payout for non-approved claims
            logger.warning(f"Logic Guard: Forcing payout to £0.0 for status {event_status} (was £{payout_gbp})")
        elif amount <= 0:
            logger.warning(f"Payout amount {amount} is non-positive. Flagging for manual review?")
    except (ValueError, TypeError):
        logger.error(f"Invalid payout amount: {payout_gbp}")
        amount = 0.0  # Safe default
        
    # 3. Execute Payment (Mock Banking API)
    # In reality, this would call Stripe Connect / BACS API
    logger.info(f"$$$ INITIATING BACS TRANSFER $$$")
    logger.info(f"Beneficiary: Policyholder for {external_id}")
    logger.info(f"Amount: £{amount:.2f}")
    logger.info(f"Reference: {claim_uuid}")
    logger.info(f"$$$ TRANSFER COMPLETE $$$")
    
    # 4. Update Status to CLOSED_PAID (Safe Update)
    # Use update_item to preserve Context Bundle link
    from datetime import datetime, timezone
    payout_date = datetime.now(timezone.utc).isoformat()
    
    try:
        table.update_item(
            Key={'PK': f"CLAIM#{claim_uuid}", 'SK': 'META'},
            UpdateExpression="SET #s = :s, payout_date = :d, final_payout_gbp = :a",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "CLOSED_PAID",
                ":d": payout_date, # Fixed: ISO Timestamp
                ":a": str(amount)
            }
        )
        logger.info(f"Claim {claim_uuid} marked as CLOSED_PAID")
        
    except Exception as e:
        logger.exception(f"Failed to update status for {claim_uuid}")
        raise e
        
    return {"status": "SUCCESS", "claim_uuid": claim_uuid, "amount": amount}
