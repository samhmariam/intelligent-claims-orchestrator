from __future__ import annotations

import json
import os
from typing import Any, Dict

import boto3

from icpa.logging_utils import log_json
from icpa.otel import start_span


_s3 = boto3.client("s3")


def handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    claim_id = event.get("claim_id")
    clean_bucket = os.environ["CLEAN_BUCKET"]

    with start_span("summarize_claim", {"claim_id": claim_id}):
        summary = _summarize(event)
        key = f"{claim_id}/summaries/{claim_id}.txt"
        _s3.put_object(Bucket=clean_bucket, Key=key, Body=summary.encode("utf-8"), ContentType="text/plain")

    log_json("summary_written", claim_id=claim_id, s3_key=key)
    return {"summary": summary}


def _summarize(claim: Dict[str, Any]) -> str:
    policy_number = claim.get("policy_number", "")
    incident_date = claim.get("incident_date", "")
    claim_amount = claim.get("claim_amount", "")
    policy_state = claim.get("policy_state", "")
    description = claim.get("description", "")
    document_count = len(claim.get("documents", []))

    payload = {
        "policy_number": policy_number,
        "incident_date": incident_date,
        "claim_amount": claim_amount,
        "policy_state": policy_state,
        "document_count": document_count,
        "description": description,
    }
    return json.dumps(payload, ensure_ascii=False)
