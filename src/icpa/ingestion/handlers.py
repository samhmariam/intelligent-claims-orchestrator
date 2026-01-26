import os
import json
import boto3
import urllib.parse
import uuid
import logging
from datetime import datetime, timezone

from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.utilities.idempotency import (
    DynamoDBPersistenceLayer, idempotent
)
from aws_lambda_powertools.utilities.data_classes import (
    event_source, EventBridgeEvent
)
from aws_lambda_powertools.metrics import MetricUnit

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="ICPA/Production")

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

CLEAN_BUCKET = os.environ.get('CLEAN_BUCKET_NAME')
CLAIMS_TABLE = os.environ.get('CLAIMS_TABLE_NAME')
IDEMPOTENCY_TABLE = os.environ.get('IDEMPOTENCY_TABLE_NAME', 'ICPA_Idempotency')

# Idempotency Config
persistence_layer = DynamoDBPersistenceLayer(table_name=IDEMPOTENCY_TABLE, key_attr="PK")

@tracer.capture_method
def process_record(bucket: str, key: str) -> str:
    """Core logic to process a single S3 object."""
    logger.info(f"Processing object: {bucket}/{key}")
    
    # Extract claim_id from Key
    # Expected Format: raw/documents/<claim_id>/<filename>
    #               or raw/photos/<claim_id>/<filename>
    parts = key.split('/')
    if len(parts) >= 3:
        # parts[0] = "raw"
        # parts[1] = "documents" or "photos"
        # parts[2] = claim_id
        # parts[3] = filename
        channel = parts[1]
        claim_id = parts[2]
        filename = parts[-1]
    else:
        # Fallback (legacy format support or root upload)
        claim_id = str(uuid.uuid4())
        filename = os.path.basename(key)
        logger.warning(f"Could not extract claim_id from key {key}. Generated {claim_id}.")

    # Annotate Trace
    tracer.put_annotation(key="claim_id", value=claim_id)
    
    doc_id = str(uuid.uuid4())
    
    # 1. Copy to Clean Bucket
    dest_key = f"{claim_id}/doc_id={doc_id}/{filename}"
    
    logger.info(f"Copying to {CLEAN_BUCKET}/{dest_key}")
    
    s3.copy_object(
        CopySource={'Bucket': bucket, 'Key': key},
        Bucket=CLEAN_BUCKET,
        Key=dest_key
    )

    # 2. Write to DynamoDB
    logger.info(f"Writing Claim {claim_id} to {CLAIMS_TABLE}")
    
    table = dynamodb.Table(CLAIMS_TABLE)
    timestamp = datetime.now(timezone.utc).isoformat()
    
    item = {
        'PK': f"CLAIM#{claim_id}",
        'SK': 'META',
        'claim_id': claim_id,
        'status': 'INTAKE',
        'created_at': timestamp,
        'latest_doc_id': doc_id,
        'channel': channel,
        'ttl': int(datetime.now(timezone.utc).timestamp()) + (365*24*60*60)
    }
    
    table.put_item(Item=item)
    
    # 3. Metrics
    metrics.add_metric(name="ClaimsIngested", unit=MetricUnit.Count, value=1)
    
    return claim_id


@logger.inject_lambda_context(log_event=True)
@metrics.log_metrics(capture_cold_start_metric=True)
@tracer.capture_lambda_handler
@idempotent(persistence_store=persistence_layer)
@event_source(data_class=EventBridgeEvent)
def ingestion_handler(event: EventBridgeEvent, context):
    """
    Triggers on EventBridge Event (S3 Object Created).
    """
    # EventBridge 'detail' contains the S3 info
    detail = event.detail
    bucket_name = detail.get('bucket', {}).get('name')
    object_key = detail.get('object', {}).get('key')
    
    if not bucket_name or not object_key:
        logger.error("Event missing bucket or object key.")
        return {"status": "skipped", "reason": "missing_data"}

    # URL Decode key
    object_key = urllib.parse.unquote_plus(object_key)
    
    try:
        claim_id = process_record(bucket_name, object_key)
        return {"status": "success", "claim_id": claim_id}
    except Exception as e:
        logger.exception("Failed to process event")
        raise e  # Raise to trigger DLQ via Lambda destination or built-in retry
