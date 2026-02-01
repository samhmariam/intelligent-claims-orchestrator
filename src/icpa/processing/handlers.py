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

def select_textract_features(bucket: str, key: str, filename: str) -> Tuple[str, List[str]]:
    """
    Intelligently selects Textract API and features based on document type.
    PHASE 1 OPTIMIZATION: Routes photos to DetectDocumentText (98% cost reduction).
    
    Returns: (api_method, feature_types)
    """
    filename_lower = filename.lower()
    
    # CRITICAL: Photos/Images - highest impact optimization
    # Golden Set: IMG_01.jpg to IMG_08.jpg (bumper damage, VIN plates)
    # Cost: $0.0015 vs $0.065 (98% savings)
    if any(ext in filename_lower for ext in ['.jpg', '.jpeg', '.png', '.heic', '.gif']):
        logger.info(f"Photo detected: {filename} → DetectDocumentText ($0.0015)")
        metrics.add_metric(
            name="TextractAPISelection",
            unit=MetricUnit.Count,
            value=1
        )
        return 'detect_document_text', []
    
    # Invoices/Receipts - tables only (no forms)
    # Cost: $0.015 vs $0.065 (77% savings)
    if 'invoice' in filename_lower or 'receipt' in filename_lower:
        logger.info(f"Invoice detected: {filename} → AnalyzeDocument(TABLES)")
        metrics.add_metric(
            name="TextractAPISelection",
            unit=MetricUnit.Count,
            value=1
        )
        return 'analyze_document', ['TABLES']
    
    # FNOL forms - forms only (no tables typically)
    # Cost: $0.050 vs $0.065 (23% savings)
    if 'fnol' in filename_lower or 'claim_form' in filename_lower:
        logger.info(f"Form detected: {filename} → AnalyzeDocument(FORMS)")
        metrics.add_metric(
            name="TextractAPISelection",
            unit=MetricUnit.Count,
            value=1
        )
        return 'analyze_document', ['FORMS']
    
    # Police reports, adjuster notes - likely complex multi-page PDFs
    # Keep both features for comprehensive extraction
    if 'police' in filename_lower or 'adjuster' in filename_lower or 'report' in filename_lower:
        logger.info(f"Complex document: {filename} → AnalyzeDocument(TABLES+FORMS)")
        metrics.add_metric(
            name="TextractAPISelection",
            unit=MetricUnit.Count,
            value=1
        )
        return 'analyze_document', ['TABLES', 'FORMS']
    
    # Plain text documents
    if any(ext in filename_lower for ext in ['.txt']):
        logger.info(f"Text file: {filename} → DetectDocumentText")
        return 'detect_document_text', []
    
    # Default: Use both features (conservative)
    logger.info(f"Default routing: {filename} → AnalyzeDocument(TABLES+FORMS)")
    metrics.add_metric(
        name="TextractAPISelection",
        unit=MetricUnit.Count,
        value=1
    )
    return 'analyze_document', ['TABLES', 'FORMS']

def get_text_from_textract(bucket: str, key: str) -> Tuple[str, Dict, str, float]:
    """
    Extracts text using intelligent API selection.
    PHASE 1 OPTIMIZATION: Routes to appropriate Textract API based on document type.
    
    Returns: (FullText, RawResponse, ExtractorType, Confidence)
    """
    logger.info(f"Extracting text from {bucket}/{key}")
    
    # Extract filename for routing decision
    filename = key.split('/')[-1]
    
    # PHASE 1: Intelligent feature selection
    api_method, features = select_textract_features(bucket, key, filename)
    
    extractor_type = f"TEXTRACT_SYNC_{api_method.upper()}"
    confidence = 0.0
    raw_response = {}
    full_text = ""

    try:
        if api_method == 'detect_document_text':
            # Cheapest option: $0.0015 per page
            response = textract.detect_document_text(
                Document={'S3Object': {'Bucket': bucket, 'Name': key}}
            )
            extractor_type = "TEXTRACT_SYNC_DETECT_TEXT"
            raw_response = response
            
            blocks = response.get('Blocks', [])
            lines = [b['Text'] for b in blocks if b['BlockType'] == 'LINE']
            full_text = "\n".join(lines)
            
            if lines:
                conf_sum = sum([b['Confidence'] for b in blocks if b['BlockType'] == 'LINE'])
                confidence = conf_sum / len(lines)
                
        else:  # analyze_document
            # Structured extraction with selected features
            response = textract.analyze_document(
                Document={'S3Object': {'Bucket': bucket, 'Name': key}},
                FeatureTypes=features
            )
            extractor_type = f"TEXTRACT_SYNC_ANALYZE_{'_'.join(features)}"
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
        extractor_type = "TEXTRACT_SYNC_DETECT_TEXT_FALLBACK"
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
    
    # PHASE 1: Track cost metrics
    metrics.add_metric(
        name="TextractExtraction",
        unit=MetricUnit.Count,
        value=1
    )
            
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

# PHASE 1 OPTIMIZATION: Caching Layer (99% development cost reduction)
def get_cached_extraction(doc_id: str) -> Dict | None:
    """
    Check if extraction already exists in cache.
    PHASE 1: Uses DOC#<doc_id> pattern for deduplication.
    
    Returns cached extraction data or None if not found.
    """
    table = dynamodb.Table(CLAIMS_TABLE)
    
    try:
        response = table.get_item(
            Key={'PK': f'DOC#{doc_id}', 'SK': 'EXTRACT'}
        )
        
        item = response.get('Item')
        if item and 'extracted_text_s3_uri' in item:
            # Verify S3 object still exists
            try:
                extract_key = item['extracted_text_s3_uri'].replace(f's3://{CLEAN_BUCKET}/', '')
                s3.head_object(
                    Bucket=CLEAN_BUCKET,
                    Key=extract_key
                )
                logger.info(f"✅ Cache HIT for {doc_id}")
                metrics.add_metric(
                    name="TextractCacheHit",
                    unit=MetricUnit.Count,
                    value=1
                )
                return item
            except s3.exceptions.NoSuchKey:
                logger.warning(f"Cached S3 object missing for {doc_id}. Cache invalidated.")
                metrics.add_metric(
                    name="TextractCacheMiss",
                    unit=MetricUnit.Count,
                    value=1
                )
        
        logger.info(f"Cache MISS for {doc_id}")
        metrics.add_metric(
            name="TextractCacheMiss",
            unit=MetricUnit.Count,
            value=1
        )
        return None
    except Exception as e:
        logger.error(f"Cache lookup failed for {doc_id}: {e}")
        return None

def cache_extraction_result(doc_id: str, claim_id: str, extraction_data: Dict):
    """
    Store extraction result with 30-day TTL.
    PHASE 1: Allows iteration on downstream logic without re-running OCR.
    
    TTL: 30 days for development (allows extensive iteration on Decision Engine/Context Assembler)
    """
    table = dynamodb.Table(CLAIMS_TABLE)
    timestamp = datetime.now(timezone.utc)
    
    # TTL: 30 days (2,592,000 seconds)
    # This allows developers to iterate on Decision Engine and Context Assembler
    # without paying for OCR on the same Golden Set documents repeatedly
    ttl_timestamp = int(timestamp.timestamp()) + (30 * 24 * 60 * 60)
    
    try:
        table.put_item(
            Item={
                'PK': f'DOC#{doc_id}',
                'SK': 'EXTRACT',
                'claim_id': claim_id,
                'extracted_text_s3_uri': extraction_data['s3_uri'],
                'extractor_type': extraction_data['extractor'],
                'confidence': str(extraction_data['confidence']),
                'cached_at': timestamp.isoformat(),
                'ttl': ttl_timestamp  # DynamoDB will auto-delete after 30 days
            }
        )
        logger.info(f"Cached extraction for {doc_id} (TTL: 30 days)")
        metrics.add_metric(
            name="TextractCacheSave",
            unit=MetricUnit.Count,
            value=1
        )
    except Exception as e:
        logger.error(f"Failed to cache extraction for {doc_id}: {e}")
        # Non-fatal: continue processing even if cache save fails


@tracer.capture_method
def process_document(bucket: str, key: str) -> Dict:
    """
    Core orchestration for a single document.
    PHASE 1: Integrated caching layer for 99% development cost reduction.
    """
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

    # PHASE 1: Check cache first
    cached = get_cached_extraction(doc_id)
    if cached:
        logger.info(f"Using cached extraction for {doc_id} (Textract cost saved!)")
        # Return cached result in expected format
        extract_key = cached['extracted_text_s3_uri'].replace(f's3://{CLEAN_BUCKET}/', '')
        return {
            "claim_uuid": claim_id,
            "doc_id": doc_id,
            "status": "EXTRACTED",
            "s3_location": {
                "bucket": CLEAN_BUCKET,
                "key": extract_key
            },
            "metadata": {
                "confidence": float(cached.get('confidence', 0.0)),
                "extractor": cached.get('extractor_type', 'CACHED'),
                "external_id": "CACHED",
                "cached": True,
                "cached_at": cached.get('cached_at')
            }
        }

    # 1. Get S3 Metadata (Context Propagation)
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        s3_metadata = head.get('Metadata', {})
        external_id = s3_metadata.get('external-id', 'UNKNOWN')
    except Exception as e:
        logger.warning(f"Failed to retrieve head_object: {e}")
        external_id = "UNKNOWN"

    
    # 2. Extract (PHASE 1: Intelligent routing applied here)
    text, raw_json, extractor, confidence = get_text_from_textract(bucket, key)
    
    # 3. Redact
    redacted_text = redact_phi(text)
    
    # 4. Persist
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
    
    # PHASE 1: Cache the extraction result
    cache_extraction_result(doc_id, claim_id, {
        's3_uri': f's3://{CLEAN_BUCKET}/{extract_key}',
        'extractor': extractor,
        'confidence': confidence
    })
    
    # 5. Update Database
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
