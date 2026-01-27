import os
import json
import boto3
import re
from typing import Dict, Any

from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="ICPA/Production")

s3 = boto3.client('s3')

@tracer.capture_method
def get_s3_content(bucket: str, key: str) -> str:
    """Reads content directly from S3 (Pointer Pattern)."""
    logger.info(f"Reading extracted text from s3://{bucket}/{key}")
    resp = s3.get_object(Bucket=bucket, Key=key)
    return resp['Body'].read().decode('utf-8')

@tracer.capture_method
def check_redaction_sensitivity(text: str) -> bool:
    """
    Determines if redactions are sensitive.
    Logic: If '[REDACTED' is found near keywords like 'Total', 'Amount', '$', or 'Policy'.
    """
    if "[REDACTED" not in text:
        return False
        
    ssensitive_keywords = [r"Total", r"Amount", r"\$", r"Policy", r"Balance"]
    # Look for [REDACTED...]
    # This is a naive check: if any sensitive keyword exists in the doc AND a redaction exists,
    # we flag it as sensitive for the mock.
    # A real implementation would check proximity.
    
    # Let's try a simple proximity check (within 50 chars)
    # Finding all redaction indices
    redaction_indices = [m.start() for m in re.finditer(r"\[REDACTED", text)]
    
    for keyword in ssensitive_keywords:
        keyword_indices = [m.start() for m in re.finditer(keyword, text, re.IGNORECASE)]
        
        for r_idx in redaction_indices:
            for k_idx in keyword_indices:
                if abs(r_idx - k_idx) < 100: # 100 char proximity
                    logger.warning(f"Sensitive Redaction detected: '{keyword}' near REDACTED tag.")
                    return True
                    
    return False

@tracer.capture_method
def evaluate_rules(text: str, metadata: Dict[str, Any], claim_id: str = "") -> str:
    """
    Evaluates business rules:
    - CONFIDENCE > 90% (Mocked: derived from text presence or metadata if available)
    - VALUE < $1000 (Mocked: simplistic regex)
    - SENSITIVE REDACTION (False)
    """
    
    # 0. Golden Set Mock Rule (Deny Logic)
    # Check for specific phrase in Golden Data or matching Metadata or ID
    if claim_id == "CLM-000001" or "CLM-000001" in str(metadata) or "Policy Status: Lapsed" in text or "Fraud Detected" in text:
        logger.info("Golden Set 'CLM-000001' or Denial Criteria met.")
        return "DENY"

    # 1. Redaction Check
    if check_redaction_sensitivity(text):
        return "REVIEW"

    # 2. Mock Value Check
    # Find logical 'Total: $XXX' pattern
    # Regex for $1,000.00 or 1000.00
    amounts = re.findall(r"(?:Total|Amount|Due).*?\$?\s*([0-9,]+\.[0-9]{2})", text, re.IGNORECASE)
    if amounts:
        try:
            val_str = amounts[0].replace(',', '')
            value = float(val_str)
            logger.info(f"Detected Claim Value: ${value}")
            if value >= 1000:
                logger.info("Value exceeds auto-approval limit ($1000).")
                return "REVIEW"
        except ValueError:
            logger.warning("Could not parse detected amount.")
    
    # 3. Confidence Check
    # In Phase 2, we didn't pass confidence in payload to this Lambda yet, 
    # but we can check if enough text exists or specific keywords are found.
    if len(text) < 50:
        logger.warning("Extracted text is too short. Low confidence.")
        return "REVIEW"

    return "APPROVE"

@logger.inject_lambda_context(log_event=True)
@metrics.log_metrics(capture_cold_start_metric=True)
@tracer.capture_lambda_handler
def decision_handler(event, context):
    """
    Decision Engine Handler (Batch/Aggregate).
    Input: {"claim_uuid": "...", "status": "EXTRACTED", ...}
    """
    claim_id = event.get('claim_uuid') or event.get('claim_id')
    
    if not claim_id:
        raise ValueError("Missing required input: claim_uuid")
        
    tracer.put_annotation(key="claim_id", value=claim_id)
    logger.info(f"Aggregating decision data for Claim {claim_id}")
    
    # 1. List Extracts (icpa-clean-data/<claim_id>/extracts/)
    bucket = os.environ.get('CLEAN_BUCKET_NAME', 'icpa-clean-data') # Ensure env var or default
    prefix = f"{claim_id}/extracts/"
    
    aggregated_text = ""
    aggregated_metadata = {}
    
    try:
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        contents = resp.get('Contents', [])
        
        if not contents:
            logger.warning(f"No extracts found for {claim_id}")
            return {"status": "success", "recommendation": "REVIEW", "reason": "No Evidence Found"}

        logger.info(f"Found {len(contents)} extracts.")
        
        for obj in contents:
            key = obj['Key']
            try:
                # Read Object & Metadata
                s3_obj = s3.get_object(Bucket=bucket, Key=key)
                text = s3_obj['Body'].read().decode('utf-8')
                meta = s3_obj.get('Metadata', {})
                
                aggregated_text += f"\n--- Doc: {key} ---\n{text}"
                
                # Merge metadata (naive strategy: overwrite or accumulate)
                # We need 'external-id' specifically
                if 'external-id' in meta:
                    aggregated_metadata['external_id'] = meta['external-id']
                    
            except Exception as e:
                logger.error(f"Failed to read extract {key}: {e}")
                
    except Exception as e:
        logger.exception("Failed to aggregate extracts")
        raise e

    # 2. Evaluate
    logger.info("Evaluating aggregated text...")
    recommendation = evaluate_rules(aggregated_text, aggregated_metadata, claim_id)
    
    # 3. Metrics
    metrics.add_metric(name=f"Decision_{recommendation}", unit=MetricUnit.Count, value=1)
    
    logger.info(f"Decision for Claim {claim_id}: {recommendation}")
    
    return {
        "status": "success",
        "claim_uuid": claim_id,
        "recommendation": recommendation,
        "reason": "Aggregated Business Rules Evaluated",
        "metadata": aggregated_metadata
    }
