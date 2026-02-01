"""
API Lambda Handlers for HITL Dashboard
Provides endpoints for claim retrieval and manual overrides
"""
import json
import os
import boto3
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3.dynamodb.conditions import Key

logger = Logger()
tracer = Tracer()

dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
events_client = boto3.client('events')

CLAIMS_TABLE_NAME = os.environ.get('CLAIMS_TABLE_NAME', 'ICPA_Claims')
CLEAN_BUCKET_NAME = os.environ.get('CLEAN_BUCKET_NAME', 'icpa-clean-data')
EVENT_BUS_NAME = os.environ.get('EVENT_BUS_NAME', 'ICPA_EventBus')

claims_table = dynamodb.Table(CLAIMS_TABLE_NAME)


def _cors_headers() -> Dict[str, str]:
    """Return CORS headers for API responses"""
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Format API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': _cors_headers(),
        'body': json.dumps(body, default=str)
    }


def _generate_presigned_url(bucket: str, key: str, expiration: int = 3600) -> str:
    """Generate S3 presigned URL for secure document access"""
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for {key}: {str(e)}")
        return ""


@tracer.capture_method
def _resolve_external_id(external_id: str) -> Optional[str]:
    """
    Resolve external_id to internal claim_uuid using ExternalIdIndex GSI
    
    Args:
        external_id: External claim ID (e.g., CLM-000001)
        
    Returns:
        claim_uuid if found, None otherwise
    """
    try:
        response = claims_table.query(
            IndexName='ExternalIdIndex',
            KeyConditionExpression=Key('external_id').eq(external_id),
            ProjectionExpression='claim_id',
            Limit=1
        )
        
        if response['Items']:
            # claim_id in DynamoDB is the UUID
            return response['Items'][0].get('claim_id')
        
        return None
    except Exception as e:
        logger.error(f"Failed to resolve external_id {external_id}: {str(e)}")
        return None


@tracer.capture_method
def _get_claim_record(claim_uuid: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full claim record from DynamoDB
    
    Args:
        claim_uuid: Internal claim UUID
        
    Returns:
        Claim record if found, None otherwise
    """
    try:
        response = claims_table.get_item(
            Key={
                'PK': f'CLAIM#{claim_uuid}',
                'SK': 'META'
            }
        )
        
        return response.get('Item')
    except Exception as e:
        logger.error(f"Failed to fetch claim {claim_uuid}: {str(e)}")
        return None


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def get_claim_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    GET /claims/{external_id}
    
    Retrieves claim data with presigned URLs for documents
    """
    try:
        # Extract external_id from path parameters
        external_id = event.get('pathParameters', {}).get('external_id')
        
        if not external_id:
            return _response(400, {'error': 'Missing external_id parameter'})
        
        logger.info(f"Fetching claim: {external_id}")
        
        # Step 1: Resolve external_id to UUID
        claim_uuid = _resolve_external_id(external_id)
        
        if not claim_uuid:
            return _response(404, {'error': f'Claim not found: {external_id}'})
        
        # Step 2: Fetch full claim record
        claim_record = _get_claim_record(claim_uuid)
        
        if not claim_record:
            return _response(404, {'error': f'Claim record not found for UUID: {claim_uuid}'})
        
        # Step 3: Generate presigned URLs for context bundle
        context_bundle_key = claim_record.get('context_bundle_s3_key')
        context_bundle_url = ""
        
        if context_bundle_key:
            context_bundle_url = _generate_presigned_url(CLEAN_BUCKET_NAME, context_bundle_key)
        
        # Step 4: Generate presigned URLs for all received documents
        received_documents = claim_record.get('received_documents', [])
        document_urls = []
        
        for idx, doc in enumerate(received_documents):
            # Handle both string (S3 key) and dict formats
            if isinstance(doc, str):
                # Simple S3 key format
                s3_key = doc
                presigned_url = _generate_presigned_url(CLEAN_BUCKET_NAME, s3_key)
                document_urls.append({
                    'document_id': f'doc-{idx}',
                    'document_type': 'unknown',
                    'url': presigned_url,
                    's3_key': s3_key
                })
            elif isinstance(doc, dict):
                # Dictionary format with metadata
                s3_key = doc.get('s3_key')
                if s3_key:
                    presigned_url = _generate_presigned_url(CLEAN_BUCKET_NAME, s3_key)
                    document_urls.append({
                        'document_id': doc.get('document_id', f'doc-{idx}'),
                        'document_type': doc.get('document_type', 'unknown'),
                        'url': presigned_url,
                        'uploaded_at': doc.get('uploaded_at'),
                        's3_key': s3_key
                    })
        
        # Step 5: Build response payload
        response_data = {
            'claim_uuid': claim_uuid,
            'external_id': external_id,
            'status': claim_record.get('status'),
            'recommendation': claim_record.get('recommendation'),
            'decision_reason': claim_record.get('decision_reason'),
            'payout_gbp': claim_record.get('payout_gbp', 0.0),
            'fraud_score': claim_record.get('fraud_score'),
            'context_bundle_url': context_bundle_url,
            'received_documents': document_urls,
            'created_at': claim_record.get('created_at'),
            'updated_at': claim_record.get('updated_at'),
            # Audit trail fields (if present)
            'manual_reviewer_id': claim_record.get('manual_reviewer_id'),
            'override_timestamp': claim_record.get('override_timestamp'),
            'override_justification': claim_record.get('override_justification'),
            'ai_agreement_flag': claim_record.get('ai_agreement_flag')
        }
        
        logger.info(f"Successfully retrieved claim {external_id}")
        return _response(200, response_data)
        
    except Exception as e:
        logger.exception(f"Error in get_claim_handler: {str(e)}")
        return _response(500, {'error': 'Internal server error'})


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def manual_override_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """
    POST /claims/{external_id}/override
    
    Processes manual override requests from adjusters
    
    Expected payload:
    {
        "action": "FORCE_APPROVE" | "CONFIRM_DENIAL",
        "manual_reviewer_id": "adjuster-001",
        "override_justification": "AI missed third-party liability clause",
        "payout_gbp_override": 849.52  # Optional, for FORCE_APPROVE
    }
    """
    try:
        # Extract external_id from path
        external_id = event.get('pathParameters', {}).get('external_id')
        
        if not external_id:
            return _response(400, {'error': 'Missing external_id parameter'})
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return _response(400, {'error': 'Invalid JSON payload'})
        
        # Validate required fields
        action = body.get('action')
        reviewer_id = body.get('manual_reviewer_id')
        justification = body.get('override_justification')
        payout_override = body.get('payout_gbp_override')
        
        if not action or action not in ['FORCE_APPROVE', 'CONFIRM_DENIAL']:
            return _response(400, {'error': 'Invalid action. Must be FORCE_APPROVE or CONFIRM_DENIAL'})
        
        if not reviewer_id:
            return _response(400, {'error': 'Missing required field: manual_reviewer_id'})
        
        if not justification or len(justification.strip()) < 10:
            return _response(400, {
                'error': 'Missing or insufficient override_justification. Must be at least 10 characters explaining why you disagree with the AI.'
            })
        
        logger.info(f"Processing override for {external_id}: {action} by {reviewer_id}")
        
        # Step 1: Resolve external_id to UUID
        claim_uuid = _resolve_external_id(external_id)
        
        if not claim_uuid:
            return _response(404, {'error': f'Claim not found: {external_id}'})
        
        # Step 2: Fetch current claim state
        claim_record = _get_claim_record(claim_uuid)
        
        if not claim_record:
            return _response(404, {'error': f'Claim record not found for UUID: {claim_uuid}'})
        
        # Step 3: Calculate ai_agreement_flag
        ai_recommendation = claim_record.get('recommendation', 'REVIEW')
        ai_agreement_flag = False
        
        if action == 'FORCE_APPROVE' and ai_recommendation == 'APPROVE':
            ai_agreement_flag = True
        elif action == 'CONFIRM_DENIAL' and ai_recommendation == 'DENY':
            ai_agreement_flag = True
        
        # Step 4: Determine new status and payout
        if action == 'FORCE_APPROVE':
            new_status = 'APPROVED'
            # Use override payout if provided, otherwise use AI's recommendation
            payout_amount = Decimal(str(payout_override)) if payout_override is not None else Decimal(str(claim_record.get('payout_gbp', 0.0)))
        else:  # CONFIRM_DENIAL
            new_status = 'DENIED'
            payout_amount = Decimal('0.0')
        
        override_timestamp = datetime.now(timezone.utc).isoformat()
        
        # Step 5: Update DynamoDB with audit trail
        try:
            update_expression = "SET #status = :status, #manual_reviewer_id = :reviewer_id, #override_timestamp = :override_timestamp, #override_justification = :justification, #ai_agreement_flag = :ai_agreement_flag, #updated_at = :updated_at"
            
            expression_attribute_names = {
                '#status': 'status',
                '#manual_reviewer_id': 'manual_reviewer_id',
                '#override_timestamp': 'override_timestamp',
                '#override_justification': 'override_justification',
                '#ai_agreement_flag': 'ai_agreement_flag',
                '#updated_at': 'updated_at'
            }
            
            expression_attribute_values = {
                ':status': new_status,
                ':reviewer_id': reviewer_id,
                ':override_timestamp': override_timestamp,
                ':justification': justification,
                ':ai_agreement_flag': ai_agreement_flag,
                ':updated_at': override_timestamp
            }
            
            # Add payout_gbp_override if provided
            if payout_override is not None:
                update_expression += ", #payout_gbp_override = :payout_override"
                expression_attribute_names['#payout_gbp_override'] = 'payout_gbp_override'
                expression_attribute_values[':payout_override'] = payout_amount
            
            claims_table.update_item(
                Key={
                    'PK': f'CLAIM#{claim_uuid}',
                    'SK': 'META'
                },
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values
            )
            
            logger.info(f"Updated claim {external_id} with manual override")
            
        except Exception as e:
            logger.exception(f"Failed to update DynamoDB: {str(e)}")
            return _response(500, {'error': 'Failed to update claim record'})
        
        # Step 6: Emit EventBridge event for downstream processing
        try:
            event_detail = {
                'claim_uuid': claim_uuid,
                'external_id': external_id,
                'status': new_status,
                'reason': justification,
                'payout_gbp': float(payout_amount),  # Convert Decimal to float for JSON serialization
                'manual_reviewer_id': reviewer_id,
                'ai_agreement_flag': ai_agreement_flag,
                'context_s3_key': claim_record.get('context_bundle_s3_key', '')
            }
            
            events_client.put_events(
                Entries=[{
                    'Source': 'com.icpa.human_override',
                    'DetailType': 'ManualOverride',
                    'Detail': json.dumps(event_detail),
                    'EventBusName': EVENT_BUS_NAME
                }]
            )
            
            logger.info(f"Emitted human_override event for {external_id}")
            
        except Exception as e:
            logger.exception(f"Failed to emit EventBridge event: {str(e)}")
            # Don't fail the request, but log the error
        
        # Step 7: Return success response
        return _response(200, {
            'message': 'Override processed successfully',
            'claim_uuid': claim_uuid,
            'external_id': external_id,
            'new_status': new_status,
            'payout_gbp': payout_amount,
            'ai_agreement_flag': ai_agreement_flag,
            'override_timestamp': override_timestamp
        })
        
    except Exception as e:
        logger.exception(f"Error in manual_override_handler: {str(e)}")
        return _response(500, {'error': 'Internal server error'})
