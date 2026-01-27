import os
import json
import boto3
import urllib.parse
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Tuple

from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.utilities.data_classes import (
    event_source, EventBridgeEvent
)
from aws_lambda_powertools.metrics import MetricUnit

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="ICPA/Production")

# Clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
textract = boto3.client('textract')
comprehend_med = boto3.client('comprehendmedical')
events = boto3.client('events')

# Config
CLEAN_BUCKET = os.environ.get('CLEAN_BUCKET_NAME')
QUARANTINE_BUCKET = os.environ.get('QUARANTINE_BUCKET_NAME')
CLAIMS_TABLE = os.environ.get('CLAIMS_TABLE_NAME')
CHUNK_SIZE = 18000 # ~18KB to stay under 20KB limit
CHUNK_OVERLAP = 2000

def get_text_from_textract(bucket: str, key: str) -> Tuple[str, Dict, str, float]:
    """
    Tries AnalyzeDocument, falls back to DetectDocumentText.
    Returns: (FullText, RawResponse, ExtractorType, Confidence)
    """
    logger.info(f"Extracting text from {bucket}/{key}")
    
    extractor_type = "TEXTRACT_SYNC_ANALYZE_DOC"
    confidence = 0.0
    raw_response = {}
    full_text = ""

    try:
        # Attempt 1: Analyze Document (Tables/Forms) - Better for structured data
        response = textract.analyze_document(
            Document={'S3Object': {'Bucket': bucket, 'Name': key}},
            FeatureTypes=['TABLES', 'FORMS']
        )
        raw_response = response
        
        # Aggregate text
        blocks = response.get('Blocks', [])
        lines = [b['Text'] for b in blocks if b['BlockType'] == 'LINE']
        full_text = "\n".join(lines)
        
        # Calculate avg confidence of lines
        if lines:
            conf_sum = sum([b['Confidence'] for b in blocks if b['BlockType'] == 'LINE'])
            confidence = conf_sum / len(lines)
        
        # Fallback Trigger: Empty text or very low confidence
        if not full_text.strip() or confidence < 50.0:
            logger.warning(f"AnalyzeDocument result poor (Conf: {confidence}). Falling back to DetectDocumentText.")
            raise Exception("Fallback Required")
            
    except Exception as e:
        logger.info(f"Fallback to DetectDocumentText due to: {str(e)}")
        # Attempt 2: Detect Document Text (Raw OCR)
        extractor_type = "TEXTRACT_SYNC_DETECT_TEXT"
        response = textract.detect_document_text(
            Document={'S3Object': {'Bucket': bucket, 'Name': key}}
        )
        raw_response = response
        
        blocks = response.get('Blocks', [])
        lines = [b['Text'] for b in blocks if b['BlockType'] == 'LINE']
        full_text = "\n".join(lines)
        
        if lines:
            conf_sum = sum([b['Confidence'] for b in blocks if b['BlockType'] == 'LINE'])
            confidence = conf_sum / len(lines)
            
    return full_text, raw_response, extractor_type, confidence

def chunk_text(text: str, chunk_size: int, overlap: int) -> List[Tuple[int, str]]:
    """
    Splits text into chunks with overlap.
    Returns list of (start_index, chunk_text).
    """
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end]
        chunks.append((start, chunk))
        
        if end == text_len:
            break
            
        start = end - overlap
        
    return chunks

def redact_phi(text: str) -> str:
    """
    Uses Comprehend Medical to detect and redact PHI.
    Handles chunking for large documents.
    """
    if not text:
        return text

    # Identify all PHI entities across chunks
    entities_found = []
    
    chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
    
    for offset, chunk in chunks:
        try:
            resp = comprehend_med.detect_phi(Text=chunk)
            for entity in resp.get('Entities', []):
                # Adjust positions to absolute original text
                abs_begin = offset + entity['BeginOffset']
                abs_end = offset + entity['EndOffset']
                
                entities_found.append({
                    'BeginOffset': abs_begin,
                    'EndOffset': abs_end,
                    'Type': entity['Type'],
                    'Text': entity['Text'] # For debug/logging if needed
                })
        except Exception as e:
            logger.error(f"Comprehend Medical failed on chunk: {e}")
            raise e

    # Deduplicate entities (due to overlap) logic could be complex. 
    # Simplest approach: Sort by start offset and merge overlapping intervals.
    # However, simpler for redaction: Sort descending by offset and replace.
    # We must handle overlaps carefully. If we blindly replace, we might mess up.
    
    # 1. Sort by BeginOffset Descending
    entities_found.sort(key=lambda x: x['BeginOffset'], reverse=True)
    
    # 2. Filter/Merge overlaps (Basic Approach: If current end > prev begin (since reverse), skip or merge).
    # Since we are modifying strings, strict coordinate handling is needed.
    # Let's use a simpler approach: Just collect all ranges to redact, merge them, then apply.
    
    ranges = []
    for e in entities_found:
        ranges.append((e['BeginOffset'], e['EndOffset'], e['Type']))
    
    # Sort Ascending to merge
    ranges.sort(key=lambda x: x[0])
    
    merged = []
    if ranges:
        curr_start, curr_end, curr_type = ranges[0]
        for i in range(1, len(ranges)):
            next_start, next_end, next_type = ranges[i]
            if next_start < curr_end: # Overlap
                curr_end = max(curr_end, next_end)
                # Keep type as first found or generic
            else:
                merged.append((curr_start, curr_end, curr_type))
                curr_start, curr_end, curr_type = next_start, next_end, next_type
        merged.append((curr_start, curr_end, curr_type))
    
    # 3. Apply Redaction (Bottom-Up)
    redacted_text = text
    for start, end, entity_type in reversed(merged):
        replacement = f"[REDACTED:{entity_type}]"
        redacted_text = redacted_text[:start] + replacement + redacted_text[end:]
        
    return redacted_text

@tracer.capture_method
def process_document(bucket: str, key: str) -> Dict:
    """Core orchestration for a single document."""
    logger.info(f"Processing {bucket}/{key}")
    
    # Parse Path: <claim_id>/doc_id=<doc_id>/<filename>
    # Note: Phase 1 output is exactly this structure in Clean bucket.
    parts = key.split('/')
    if len(parts) >= 3 and "doc_id=" in parts[1]:
        claim_id = parts[0]
        doc_id = parts[1].split('=')[1]
        filename = parts[-1]
        
        tracer.put_annotation(key="claim_id", value=claim_id)
        tracer.put_annotation(key="doc_id", value=doc_id)
    else:
        logger.warning(f"Invalid key structure: {key}. Skipping.")
        cid = parts[0] if parts else "UNKNOWN"
        return {"status": "skipped", "debug_key": key, "debug_parts": parts, "claim_uuid": cid}

    # 1. Get S3 Metadata (Context Propagation)
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        s3_metadata = head.get('Metadata', {})
        external_id = s3_metadata.get('external-id', 'UNKNOWN')
    except Exception as e:
        logger.warning(f"Failed to retrieve head_object: {e}")
        external_id = "UNKNOWN"

    
    # 2. Extract
    text, raw_json, extractor, confidence = get_text_from_textract(bucket, key)
    
    # 2. Redact
    redacted_text = redact_phi(text)
    
    # 3. Persist
    # A. Raw JSON to Quarantine (Audit)
    audit_key = f"phi-audit/{claim_id}/{doc_id}.json"
    s3.put_object(
        Bucket=QUARANTINE_BUCKET,
        Key=audit_key,
        Body=json.dumps(raw_json)
    )
    
    # B. Redacted Text to Clean
    extract_key = f"{claim_id}/extracts/{doc_id}.txt"
    s3.put_object(
        Bucket=CLEAN_BUCKET,
        Key=extract_key,
        Body=redacted_text,
        Metadata={'external-id': external_id}
    )
    
    # 4. Update Database
    table = dynamodb.Table(CLAIMS_TABLE)
    timestamp = datetime.now(timezone.utc).isoformat()
    
    table.update_item(
        Key={'PK': f"CLAIM#{claim_id}", 'SK': 'META'},
        UpdateExpression="SET #s = :s, extraction_metadata = :m, updated_at = :t",
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':s': 'EXTRACTED',
            ':m': {
                'extractor': extractor,
                'confidence': str(confidence),
                'created_at': timestamp,
                'audit_loc': f"s3://{QUARANTINE_BUCKET}/{audit_key}",
                'extract_loc': f"s3://{CLEAN_BUCKET}/{extract_key}"
            },
            ':t': timestamp
        }
    )
    
    metrics.add_metric(name="DocumentsExtracted", unit=MetricUnit.Count, value=1)
    
    # 5. Return Output for Step Function
    return {
        "claim_uuid": claim_id, 
        "doc_id": doc_id, 
        "status": "EXTRACTED",
        "s3_location": {
            "bucket": CLEAN_BUCKET,
            "key": extract_key
        },
        "metadata": {
            "confidence": confidence,
            "extractor": extractor,
            "external_id": external_id
        }
    }

@logger.inject_lambda_context(log_event=True)
@metrics.log_metrics(capture_cold_start_metric=True)
@tracer.capture_lambda_handler
def processing_handler(event, context):
    """
    Orchestrates Extraction & Redaction for a Check Packet (Batch).
    Input: {"claim_uuid": "...", ...}
    """
    claim_uuid = event.get('claim_uuid')
    
    if not claim_uuid:
        # Fallback for legacy EventBridge (if any) or error
        logger.warning(f"No claim_uuid in event: {event}. Checking legacy detail.")
        if 'detail' in event:
             # Support legacy path for backward compat if needed, or just fail
             # For now, let's just error/skip to enforce new pattern
             return {"status": "skipped", "reason": "legacy_event_not_supported"}
        return {"status": "failed", "reason": "missing_claim_uuid"}

    tracer.put_annotation(key="claim_id", value=claim_uuid)
    logger.info(f"Starting Batch Processing for Claim {claim_uuid}")
    
    # 1. List Documents in Clean Bucket (Prefix: <claim_uuid>/)
    # We look for "doc_id=" keys to differentiate from "extracts/" or "metadata/"
    # Pattern: <claim_uuid>/doc_id=<doc_id>/<filename>
    
    try:
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=CLEAN_BUCKET, Prefix=f"{claim_uuid}/")
        
        processed_count = 0
        errors = []
        
        for page in pages:
            for obj in page.get('Contents', []):
                key = obj['Key']
                # Filter for source documents (exclude extracts/ etc)
                if "/doc_id=" in key and not key.endswith("/"): 
                    try:
                        process_document(CLEAN_BUCKET, key)
                        processed_count += 1
                    except Exception as e:
                        logger.error(f"Failed to process {key}: {e}")
                        errors.append(key)
        
        status = "EXTRACTED" if processed_count > 0 else "EMPTY"
        if errors:
            status = "PARTIAL_ERROR"
            
        return {
            "claim_uuid": claim_uuid,
            "status": status,
            "processed_count": processed_count,
            "error_count": len(errors)
        }
        
    except Exception as e:
        logger.exception("Batch Processing Failed")
        raise e
