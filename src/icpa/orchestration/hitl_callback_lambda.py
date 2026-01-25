from __future__ import annotations

import base64
import json
from typing import Any, Dict, Tuple

import boto3

from icpa.db_client import DatabaseClient
from icpa.logging_utils import log_json
from icpa.otel import annotate_span, start_span


_sfn = boto3.client("stepfunctions")

_ALLOWED_DECISIONS = {"APPROVE", "DENY", "FLAGGED"}

def _extract_request_fields(event: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    if "body" not in event:
        return event, "event"

    body = event.get("body")
    if body is None:
        query = event.get("queryStringParameters")
        if isinstance(query, dict):
            return query, "query"
        return event, "event"

    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8")

    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            query = event.get("queryStringParameters")
            if isinstance(query, dict):
                return query, "query"
            return event, "event"
    if not isinstance(body, dict):
        return event, "event"
    return body, "body"


def handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    payload, source = _extract_request_fields(event)
    claim_id = payload.get("claim_id")
    decision = payload.get("decision")
    correlation_id = payload.get("correlation_id") or event.get("correlation_id")

    if not claim_id:
        log_json(
            "hitl_callback_missing_claim_id",
            source=source,
            correlation_id=correlation_id,
        )
        raise ValueError(f"Missing claim_id from {source} for correlation_id={correlation_id}")

    db = DatabaseClient()
    claim = None
    if db.claims_table:
        response = db.claims_table.get_item(
            Key={"PK": f"CLAIM#{claim_id}", "SK": "META"}
        )
        claim = response.get("Item")
    if not claim:
        raise ValueError(f"Claim not found for claim_id={claim_id}, correlation_id={correlation_id}")

    task_token = claim.get("task_token")
    if not task_token:
        raise ValueError(f"Missing task_token for claim_id={claim_id}, correlation_id={correlation_id}")

    decision_value = str(decision).upper() if decision is not None else None
    if decision_value not in _ALLOWED_DECISIONS:
        raise ValueError(
            f"Invalid decision for claim_id={claim_id}, correlation_id={correlation_id}"
        )

    annotate_span({"claim_id": claim_id, "decision": decision})
    with start_span("hitl_callback", {"claim_id": claim_id}):
        payload: Dict[str, Any] = {"decision": decision_value}
        if claim_id:
            payload["claim_id"] = claim_id
        _sfn.send_task_success(taskToken=task_token, output=json.dumps(payload))

    log_json("hitl_task_completed", claim_id=claim_id, decision=decision_value)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {"status": "ok", "claim_id": claim_id, "decision": decision_value}
        ),
    }
