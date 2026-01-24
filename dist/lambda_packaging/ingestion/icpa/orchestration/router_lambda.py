from __future__ import annotations

from typing import Any, Dict

from icpa.constants import HITL_CLAIM_AMOUNT_THRESHOLD
from icpa.logging_utils import log_json
from icpa.otel import start_span


def handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    claim_id = event.get("claim_id")
    claim_amount = float(event.get("claim_amount", 0))

    with start_span("route_claim", {"claim_id": claim_id, "claim_amount": claim_amount}):
        if claim_amount > HITL_CLAIM_AMOUNT_THRESHOLD:
            log_json("router_hitl", claim_id=claim_id, claim_amount=claim_amount)
            return {"target_agent": "HITL", "reason": "AMOUNT_OVER_THRESHOLD"}

        return {"target_agent": "FRAUD_AGENT", "reason": "DEFAULT"}
