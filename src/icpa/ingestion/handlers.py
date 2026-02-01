import os
import json
import boto3
import botocore
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

from boto3.dynamodb.conditions import Key

@tracer.capture_method
def get_or_create_claim_id(external_id: str) -> str:
    """
    Atomic mapping of external_id -> claim_id.
    Uses a dedicated MAPPING# item with ConditionExpression to prevent race conditions.
    """
    table = dynamodb.Table(CLAIMS_TABLE)
    mapping_pk = f"MAPPING#{external_id}"
    
    # 1. Try to create new mapping (Atomic)
    new_claim_id = str(uuid.uuid4())
    # Removed CLM- special case to enforce UUID-only schema
    # This prevents split-brain schema issues in Phase 6
        
    timestamp = datetime.now(timezone.utc).isoformat()
    
    try:
        table.put_item(
            Item={
                'PK': mapping_pk,
                'SK': 'META',
                'claim_id': new_claim_id,
                'external_id': external_id,
                'created_at': timestamp,
                'ttl': int(datetime.now(timezone.utc).timestamp()) + (365*24*60*60)
            },
            ConditionExpression='attribute_not_exists(PK)'
        )
        logger.info(f"Atomic Create: Mapped {external_id} -> {new_claim_id}")
        return new_claim_id
        
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            # Race lost or already exists - Retrieve existing
            logger.info(f"Mapping exists for {external_id}. Fetching...")
            resp = table.get_item(Key={'PK': mapping_pk, 'SK': 'META'})
            existing = resp.get('Item', {})
            if 'claim_id' in existing:
                 return existing['claim_id']
            else:
                 raise Exception(f"Corrupt mapping record for {external_id}")
        else:
            raise e

@tracer.capture_method
def update_claim_record(claim_id: str, external_id: str, filename: str, channel: str):
    """
    Updates the main CLAIM record with the new file and checks packet completeness.
    """
    table = dynamodb.Table(CLAIMS_TABLE)
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Update documents list and metadata
    # Changed from ADD (set) to list_append (list) for better compatibility
    
    try:
        resp = table.update_item(
            Key={'PK': f"CLAIM#{claim_id}", 'SK': 'META'},
            UpdateExpression="SET received_documents = list_append(if_not_exists(received_documents, :empty_list), :f), external_id = :e, #s = if_not_exists(#s, :status), updated_at = :t, channel = :c",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':f': [filename],  # List with single filename
                ':empty_list': [],  # Empty list for initialization
                ':e': external_id,
                ':status': 'INTAKE',
                ':t': timestamp,
                ':c': channel
            },
            ReturnValues="ALL_NEW"
        )
        
        attributes = resp.get('Attributes', {})
        docs = set(attributes.get('received_documents', []))  # Convert list to set for compatibility
        
        return docs
    except Exception as e:
        logger.exception("Failed to update claim record")
        raise e

import boto3
sfn = boto3.client('stepfunctions')
STATE_MACHINE_ARN = os.environ.get('STATE_MACHINE_ARN')

@tracer.capture_method
def check_and_trigger_orchestration(claim_uuid: str, documents: set):
    """
    Triggers Step Function if packet is complete.
    Idempotency: Uses claim_uuid as Execution Name.
    """
    # Logic: Trigger if 'FNOL.pdf' AND 'INVOICE.pdf' are present
    # OR if we have significant data.
    # For Golden Set: We have 12 files. 
    # Let's just ALWAYS try to trigger if FNOL is present, rely on SF Idempotency to ensure singleton.
    
    # Check for critical docs
    # Convert set to list for checking
    doc_list = list(documents)
    has_fnol = any("FNOL" in d for d in doc_list)
    has_invoice = any("INVOICE" in d for d in doc_list)
    
    if has_fnol or has_invoice or len(doc_list) >= 4:
        logger.info(f"Packet critical mass reached ({len(doc_list)} docs). Attempting Orchestration...")
        
        if not STATE_MACHINE_ARN:
            logger.warning("STATE_MACHINE_ARN not set. Skipping trigger.")
            return

        # "World-Class" Singleton Pattern
        # Only ONE execution per Claim UUID active at a time to prevent race conditions.
        # Wait state in SF handles the buffering of multiple files.
        # This guarantees 13 uploads -> 1 Execution.
        execution_name = claim_uuid
            
        try:
            sfn.start_execution(
                stateMachineArn=STATE_MACHINE_ARN,
                name=execution_name, 
                input=json.dumps({
                    "claim_uuid": claim_uuid,
                    "reason": "Packet Update"
                })
            )
            logger.info(f"Started Singleton Execution for {claim_uuid}")
        except sfn.exceptions.ExecutionAlreadyExists:
            logger.info(f"Execution already running for {claim_uuid}. Idempotency active.")
        except Exception as e:
            logger.error(f"Failed to trigger SF: {e}")

@logger.inject_lambda_context(log_event=True)
@metrics.log_metrics(capture_cold_start_metric=True)
@tracer.capture_lambda_handler
# @idempotent(persistence_store=persistence_layer) # Disable automatic powertools idempotency to handle Atomic Logic manually
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
        # process_record logic integrated here for flow control
        logger.info(f"Processing object: {bucket_name}/{object_key}")
        
        # 1. Parse Key
        # Updated Format: <external_id>/raw/documents/<filename>
        parts = object_key.split('/')
        if len(parts) >= 4 and parts[1] == 'raw':
             raw_external_id = parts[0]
             channel = parts[2]
             filename = parts[-1]
        elif len(parts) >= 3 and parts[0] == 'raw':
             # Legacy
             channel = parts[1]
             raw_external_id = parts[2]
             filename = parts[-1]
        else:
             raw_external_id = str(uuid.uuid4())
             channel = "unknown"
             filename = os.path.basename(object_key)

        external_id = raw_external_id.strip().upper()
        tracer.put_annotation(key="external_id", value=external_id)

        # 2. Atomic Mapping (Fix Race Condition)
        claim_id = get_or_create_claim_id(external_id)
        tracer.put_annotation(key="claim_id", value=claim_id)
        logger.info(f"Atomic Mapping: {external_id} → {claim_id}")

        # 3. Copy to Clean Bucket
        doc_id = str(uuid.uuid4())
        dest_key = f"{claim_id}/doc_id={doc_id}/{filename}"
        s3.copy_object(
            CopySource={'Bucket': bucket_name, 'Key': object_key},
            Bucket=CLEAN_BUCKET,
            Key=dest_key,
            MetadataDirective='REPLACE',
            Metadata={'external-id': external_id, 'original-key': object_key},
            Tagging=f"icpa:claim_uuid={claim_id}&icpa:external_id={external_id}"
        )
        logger.info(f"Copied to {CLEAN_BUCKET}/{dest_key}")

        # 4. Collector & Trigger (Fix Orchestration)
        current_docs = update_claim_record(claim_id, external_id, filename, channel)
        check_and_trigger_orchestration(claim_id, current_docs)
        
        return {"status": "success", "claim_id": claim_id}

    except Exception as e:
        logger.exception("Failed to process event")
        raise e
