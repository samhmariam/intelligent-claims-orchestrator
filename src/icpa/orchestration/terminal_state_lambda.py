from __future__ import annotations

from typing import Any, Dict, Optional

from icpa.db_client import DatabaseClient
from icpa.logging_utils import log_json
from icpa.otel import annotate_span, start_span


_DECISION_TO_STATE = {
    "APPROVE": "APPROVED",
    "APPROVED": "APPROVED",
    "DENY": "DENIED",
    "DENIED": "DENIED",
    "REJECT": "DENIED",
    "REJECTED": "DENIED",
    "FLAG": "FLAGGED",
    "FLAGGED": "FLAGGED",
}


def _resolve_state(decision: Optional[str], explicit_state: Optional[str]) -> str:
    if explicit_state:
        return explicit_state
    normalized = (decision or "").strip().upper()
    return _DECISION_TO_STATE.get(normalized, "APPROVED")


def handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    claim_id = event.get("claim_id")
    decision = event.get("decision")
    correlation_id = event.get("correlation_id")
    if not claim_id:
        raise ValueError(
            f"Missing claim_id for correlation_id={correlation_id}"
        )

    state = _resolve_state(decision, event.get("state"))
    db = DatabaseClient()

    annotate_span({"claim_id": claim_id, "decision": decision, "state": state})
    with start_span("persist_terminal_state", {"claim_id": claim_id, "state": state}):
        metadata = {"decision": decision} if decision else None
        db.save_claim_state(claim_id, state, metadata)

    log_json("claim_terminal_state_persisted", claim_id=claim_id, state=state, decision=decision)
    return {"claim_id": claim_id, "state": state, "decision": decision}
