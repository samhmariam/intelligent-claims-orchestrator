import os
import boto3
import time
from decimal import Decimal
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError
from icpa.logging_utils import log_json

class DatabaseClient:
    def __init__(self, region_name: str = "us-east-1"):
        self.dynamodb = boto3.resource("dynamodb", region_name=region_name)
        
        self.claims_table_name = os.environ.get("CLAIMS_TABLE")
        self.idempotency_table_name = os.environ.get("IDEMPOTENCY_TABLE")
        self.evaluation_table_name = os.environ.get("EVALUATION_TABLE")

        self.claims_table = self.dynamodb.Table(self.claims_table_name) if self.claims_table_name else None
        self.idempotency_table = self.dynamodb.Table(self.idempotency_table_name) if self.idempotency_table_name else None
        self.evaluation_table = self.dynamodb.Table(self.evaluation_table_name) if self.evaluation_table_name else None

    def save_claim_state(self, claim_id: str, state: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Updates the current state of the claim.
        PK: CLAIM#<claim_id>
        SK: META
        """
        if not self.claims_table:
            log_json("db_client_missing_table", table="claims")
            return

        item = {
            "PK": f"CLAIM#{claim_id}",
            "SK": "META",
            "state": state,
            "updated_at": int(time.time()),
        }
        if metadata:
            item.update(metadata)

        try:
            self.claims_table.put_item(Item=item)
            log_json("db_save_claim_state", claim_id=claim_id, state=state)
        except ClientError as e:
            log_json("db_error_save_claim_state", error=str(e), claim_id=claim_id)
            raise

    def log_audit_entry(self, claim_id: str, step_id: str, details: Dict[str, Any]) -> None:
        """
        Logs an execution step for audit purposes.
        PK: CLAIM#<claim_id>
        SK: STEP#<step_id>
        """
        if not self.claims_table:
            log_json("db_client_missing_table", table="claims")
            return

        item = {
            "PK": f"CLAIM#{claim_id}",
            "SK": f"STEP#{step_id}",
            "timestamp": int(time.time()),
            "details": details
        }

        try:
            self.claims_table.put_item(Item=item)
            log_json("db_log_audit", claim_id=claim_id, step_id=step_id)
        except ClientError as e:
            log_json("db_error_log_audit", error=str(e), claim_id=claim_id)
            # Non-blocking error for audit logs
            pass

    def check_idempotency(self, req_hash: str, ttl_seconds: int = 3600) -> bool:
        """
        Checks if a request has already been processed. Returns True if New (not seen), False if Duplicate.
        PK: REQ#<req_hash>
        """
        if not self.idempotency_table:
            log_json("db_client_missing_table", table="idempotency")
            # Fail open if table missing? or closed? Let's say we process if DB is missing to avoid blocking.
            return True

        now = int(time.time())
        item = {
            "PK": f"REQ#{req_hash}",
            "expires_at": now + ttl_seconds,
            "created_at": now
        }

        try:
            self.idempotency_table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(PK)"
            )
            return True # New request
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return False # Duplicate
            log_json("db_error_idempotency", error=str(e), req_hash=req_hash)
            raise

    def save_evaluation(self, job_id: str, claim_id: str, result: Dict[str, Any]) -> None:
        """
        Saves evaluation results.
        PK: EVAL#<job_id>
        SK: CASE#<claim_id>
        """
        if not self.evaluation_table:
            log_json("db_client_missing_table", table="evaluation")
            return

        item = {
            "PK": f"EVAL#{job_id}",
            "SK": f"CASE#{claim_id}",
            "result": _to_dynamo_compatible(result),
            "timestamp": int(time.time())
        }

        try:
            self.evaluation_table.put_item(Item=item)
            log_json("db_save_evaluation", job_id=job_id, claim_id=claim_id)
        except ClientError as e:
            log_json("db_error_save_evaluation", error=str(e), job_id=job_id)
            raise


def _to_dynamo_compatible(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamo_compatible(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_dynamo_compatible(item) for item in value]
    return value
