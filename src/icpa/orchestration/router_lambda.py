from __future__ import annotations

from typing import Any, Dict

from icpa.constants import HITL_CLAIM_AMOUNT_THRESHOLD
from icpa.logging_utils import log_json
from icpa.otel import start_span
from icpa.db_client import DatabaseClient


def _parse_claim_amount(raw_amount: Any) -> float:
    if raw_amount is None:
        return 0.0
    if isinstance(raw_amount, str):
        trimmed = raw_amount.strip()
        if not trimmed:
            return 0.0
        return float(trimmed)
    return float(raw_amount)


def handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    db = DatabaseClient()
    claim_id = event.get("claim_id")
    claim_amount = _parse_claim_amount(event.get("claim_amount"))

    with start_span("route_claim", {"claim_id": claim_id, "claim_amount": claim_amount}):
        if claim_amount > HITL_CLAIM_AMOUNT_THRESHOLD:
            log_json("router_hitl", claim_id=claim_id, claim_amount=claim_amount)
            db.save_claim_state(claim_id, "PROCESSING", {"sub_state": "ROUTED_TO_HITL"})
            return {"target_agent": "HITL", "reason": "AMOUNT_OVER_THRESHOLD"}

        db.save_claim_state(claim_id, "PROCESSING", {"sub_state": "ROUTED_TO_FRAUD_AGENT"})
        return {"target_agent": "FRAUD_AGENT", "reason": "DEFAULT"}
