from __future__ import annotations

import json
import os
from typing import Any, Dict

import boto3

from icpa.logging_utils import log_json
from icpa.otel import start_span
from icpa.db_client import DatabaseClient


_sns = boto3.client("sns")


def handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    topic_arn = os.environ["HITL_TOPIC_ARN"]
    task_token = event.get("taskToken") or event.get("task_token")
    claim_id = event.get("claim_id")
    db = DatabaseClient()

    with start_span("hitl_notify", {"claim_id": claim_id}):
        payload = {
            "claim_id": claim_id,
        }
        db.save_claim_state(claim_id, "PENDING_REVIEW", {"task_token": task_token})
        _sns.publish(TopicArn=topic_arn, Message=json.dumps(payload))

    log_json("hitl_notified", claim_id=claim_id, topic_arn=topic_arn)
    return payload
