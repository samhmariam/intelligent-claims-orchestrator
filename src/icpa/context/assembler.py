import os
import json
import boto3
import re
from typing import Dict, Any, List
from datetime import datetime
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="ICPA/Production")

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

class ContextAssembler:
    def __init__(self, bucket_name: str, claim_uuid: str, table_name: str):
        self.bucket_name = bucket_name
        self.claim_uuid = claim_uuid
        self.table = dynamodb.Table(table_name)
        self.extracts_prefix = f"{claim_uuid}/extracts/"
        self.context_prefix = f"{claim_uuid}/context/"
        self.docs = []
        self.metadata = {}
        
        # 1. Guardrail: Verify Prefix Exists (Fast Check)
        resp = s3.list_objects_v2(Bucket=bucket_name, Prefix=self.extracts_prefix, MaxKeys=1)
        if not resp.get('Contents'):
            msg = f"Guardrail: No extract objects found at {self.extracts_prefix}"
            logger.error(msg)
            raise ValueError(msg)

    def fetch_extracts(self, execution_start_time: str = None):
        """Fetches all text extracts from S3 and validates identity + freshness."""
        try:
            paginator = s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=self.extracts_prefix)
            
            # Parse execution time if provided (ISO 8601)
            exec_time = None
            if execution_start_time:
                try:
                    # Handle Z suffix manually if python < 3.7
                    if execution_start_time.endswith('Z'):
                        execution_start_time = execution_start_time[:-1] + '+00:00'
                    exec_time = datetime.fromisoformat(execution_start_time)
                except ValueError:
                    logger.warning(f"Could not parse execution_start_time: {execution_start_time}")
            
            for page in pages:
                if 'Contents' not in page: continue
                    
                for obj in page['Contents']:
                    key = obj['Key']
                    if key.endswith('/'): continue
                    
                    # Lifecycle Verification: Stale Check
                    if exec_time and obj['LastModified'] < exec_time:
                        logger.warning(f"Skipping stale extract {key} (Last Modified: {obj['LastModified']} < Execution Start: {exec_time})")
                        continue
                        
                    resp = s3.get_object(Bucket=self.bucket_name, Key=key)
                    text = resp['Body'].read().decode('utf-8')
                    meta = resp.get('Metadata', {})
                    
                    self.docs.append({
                        'key': key, 'text': text, 'metadata': meta,
                        'doc_id': key.split('/')[-1]
                    })
                    
                    if 'external-id' in meta:
                         self.metadata['external_id'] = meta['external-id']

            logger.info(f"Fetched {len(self.docs)} fresh documents.")
            
            # 2. Strict UUID Validation with DynamoDB
            # Ensure the claim_uuid we are processing matches the canonical ID for the external_id found in docs
            if 'external_id' in self.metadata:
                ext_id = self.metadata['external_id']
                # Query GSI to get canonical claim_id
                resp = self.table.query(
                    IndexName='ExternalIdIndex',
                    KeyConditionExpression=boto3.dynamodb.conditions.Key('external_id').eq(ext_id)
                )
                items = resp.get('Items', [])
                if items:
                    # GSI usually returns Mapping item or metadata item. 
                    # If it's the Mapping item, it points to CLAIM#uuid
                    canonical_id = items[0].get('claim_id') or items[0].get('PK')
                    canonical_uuid = canonical_id.replace("CLAIM#", "").replace("MAPPING#", "")
                    
                    if canonical_uuid != self.claim_uuid:
                         msg = f"Split-Brain Detected! Processing {self.claim_uuid} but canonical for {ext_id} is {canonical_uuid}"
                         logger.critical(msg)
                         raise ValueError(msg)
            
        except Exception as e:
            logger.exception("Failed to fetch/validate extracts")
            raise e

    def _extract_date(self, text: str) -> str:
        """Heuristic to find first date. Returns ISO YYYY-MM-DD or '9999-99-99' for sort."""
        # Try YYYY-MM-DD
        m1 = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        if m1: return m1.group(1)
        # Try DD/MM/YYYY
        m2 = re.search(r'(\d{2})/(\d{2})/(\d{4})', text)
        if m2: return f"{m2.group(3)}-{m2.group(2)}-{m2.group(1)}"
        return "9999-99-99"

    def create_timeline(self) -> List[Dict]:
        """Creates a chronologically sorted timeline."""
        timeline = []
        for doc in self.docs:
            date_str = self._extract_date(doc['text'])
            # Only add to timeline if meaningful? Or add all?
            # Add all for now, sort puts unknowns at end
            timeline.append({
                'date': date_str,
                'event': f"Document: {doc['doc_id']}",
                'source_doc_id': doc['doc_id']
            })
        
        # Sort by date
        timeline.sort(key=lambda x: x['date'])
        return timeline

    def check_min_viable_context(self) -> str:
        """Checks for FNOL and INVOICE."""
        text_blob = " ".join([d['text'].upper() for d in self.docs])
        has_fnol = "FNOL" in text_blob or "FIRST NOTIFICATION" in text_blob
        has_invoice = "INVOICE" in text_blob or "TOTAL" in text_blob
        
        if len(self.docs) < 2: return "INCOMPLETE"
        if has_fnol and has_invoice: return "COMPLETE"
        return "PARTIAL_CONTEXT"

    def optimize_bundle(self, full_bundle: Dict) -> Dict:
        """Optimizes bundle for token limits."""
        optimized = {
            "claim_uuid": full_bundle['claim_uuid'],
            "status": full_bundle['status'],
            "metadata": full_bundle['metadata'],
            "timeline": full_bundle['timeline'], 
            "documents": []
        }
        
        priority_order = ["FNOL", "INVOICE", "POLICE_REPORT", "ADJUSTER"]
        sorted_docs = sorted(self.docs, key=lambda d: next((i for i, k in enumerate(priority_order) if k in d['key'].upper()), 999))
        
        current_len = 0
        limit = 150000 # Increased limit since we have more memory, but Agent has token limit. Keep reasonable.
        
        for doc in sorted_docs:
            chunk = f"\n--- Document: {doc['doc_id']} ---\n{doc['text']}\n"
            if current_len + len(chunk) < limit:
                optimized['documents'].append({
                    'doc_id': doc['doc_id'],
                    'text': doc['text'], 
                    'metadata': doc['metadata']
                })
                current_len += len(chunk)

        return optimized

    def save_bundles(self):
        """Saves bundles to S3 and links to DynamoDB."""
        status = self.check_min_viable_context()
        timeline = self.create_timeline()
        
        full_bundle = {
            "claim_uuid": self.claim_uuid,
            "timestamp": datetime.utcnow().isoformat(),
            "status": status,
            "metadata": self.metadata,
            "timeline": timeline,
            "documents": self.docs,
            "total_docs": len(self.docs)
        }
        
        optimized_bundle = self.optimize_bundle(full_bundle)
        
        # S3 Paths
        full_key = f"{self.context_prefix}context_bundle.json"
        opt_key = f"{self.context_prefix}context_bundle_optimized.json"
        
        s3.put_object(Bucket=self.bucket_name, Key=full_key, Body=json.dumps(full_bundle), ContentType='application/json')
        s3.put_object(Bucket=self.bucket_name, Key=opt_key, Body=json.dumps(optimized_bundle), ContentType='application/json')
        
        # 3. Atomic Bundle Link in DynamoDB
        # Update the Claim Metadata record with the bundle location
        try:
             self.table.update_item(
                Key={'PK': f"CLAIM#{self.claim_uuid}", 'SK': 'META'},
                UpdateExpression="SET context_bundle_s3_key = :k, context_status = :s, updated_at = :t",
                ExpressionAttributeValues={
                    ':k': full_key,
                    ':s': status,
                    ':t': datetime.utcnow().isoformat()
                }
             )
             logger.info("Updated DynamoDB with bundle link.")
        except Exception as e:
            logger.error(f"Failed to link bundle in DynamoDB: {e}")
            # Non-fatal? The bundle exists in S3. But good to know.
        
        return optimized_bundle

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event, context):
    claim_uuid = event.get('claim_uuid')
    if not claim_uuid: raise ValueError("Missing claim_uuid")
        
    logger.info(f"Assembling context for {claim_uuid}")
    
    bucket = os.environ.get('CLEAN_BUCKET_NAME', 'icpa-clean-data')
    table_name = os.environ.get('CLAIMS_TABLE_NAME', 'ICPA_Claims')
    
    exec_start_time = event.get('execution_start_time')
    assembler = ContextAssembler(bucket, claim_uuid, table_name)
    assembler.fetch_extracts(execution_start_time=exec_start_time)
    optimized = assembler.save_bundles()
    
    return {
        "status": "success",
        "claim_uuid": claim_uuid,
        "context_status": optimized['status'],
        "bundle_s3_key": f"{assembler.context_prefix}context_bundle_optimized.json",
         "metadata": optimized['metadata']
    }
