from __future__ import annotations

import json
from typing import Any, Dict, Optional

import boto3

from icpa.logging_utils import log_json
from icpa.otel import annotate_span, start_span


_sfn = boto3.client("stepfunctions")


def handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    claim_id = event.get("claim_id")
    decision = event.get("decision")
    task_token = event.get("task_token") or event.get("taskToken")
    correlation_id = event.get("correlation_id")

    if not task_token:
        raise ValueError(
            f"Missing task_token for claim_id={claim_id}, correlation_id={correlation_id}"
        )

    annotate_span({"claim_id": claim_id, "decision": decision})
    with start_span("hitl_callback", {"claim_id": claim_id}):
        payload: Dict[str, Optional[str]] = {"decision": decision}
        if claim_id:
            payload["claim_id"] = claim_id
        _sfn.send_task_success(task_token=task_token, output=json.dumps(payload))

    log_json("hitl_task_completed", claim_id=claim_id, decision=decision)
    return {"status": "ok", "claim_id": claim_id, "decision": decision}
