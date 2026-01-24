from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import boto3

from icpa.logging_utils import log_json
from icpa.otel import annotate_span, start_span
from icpa.db_client import DatabaseClient


_bedrock_runtime = boto3.client("bedrock-agent-runtime")
_ssm = boto3.client("ssm")


def _get_prompt(agent_name: Optional[str], version: str) -> Optional[str]:
    if not agent_name:
        return None
    if version == "latest":
        latest_param = f"/icpa/prompts/{agent_name}/latest"
        latest_response = _ssm.get_parameter(Name=latest_param, WithDecryption=False)
        resolved_version = latest_response["Parameter"]["Value"]
        param_name = f"/icpa/prompts/{agent_name}/{resolved_version}"
    else:
        param_name = f"/icpa/prompts/{agent_name}/{version}"
    response = _ssm.get_parameter(Name=param_name, WithDecryption=False)
    return response["Parameter"]["Value"]


def _parse_agent_result(text: str) -> Dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Agent output does not contain JSON")
    return json.loads(text[start : end + 1])


def handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    agent_id = os.environ["BEDROCK_AGENT_ID"]
    agent_alias_id = os.environ["BEDROCK_AGENT_ALIAS_ID"]
    agent_name = os.environ.get("AGENT_NAME")
    prompt_version = os.environ.get("PROMPT_VERSION", "latest")
    agent_type = os.environ.get("AGENT_TYPE", agent_name)
    model_id = os.environ.get("MODEL_ID")
    db = DatabaseClient()

    claim_id = event.get("claim_id")
    session_id = event.get("session_id") or claim_id
    input_text = event.get("input_text", "")
    prompt = _get_prompt(agent_name, prompt_version)
    if prompt:
        input_text = f"{prompt}\n\n{input_text}"

    annotate_span(
        {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "session_id": session_id,
            "claim_id": claim_id,
            "model_id": model_id,
        }
    )

    with start_span(
        "bedrock.invoke_agent",
        {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "session_id": session_id,
            "claim_id": claim_id,
            "model_id": model_id,
        },
    ):
        db.log_audit_entry(
            claim_id=claim_id,
            step_id=f"agent_start_{agent_name}",
            details={"agent_id": agent_id, "input_text_length": len(input_text)}
        )
        
        response = _bedrock_runtime.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias_id,
            sessionId=session_id,
            inputText=input_text,
        )

        completion_text = ""
        for event_item in response.get("completion", []):
            if "chunk" in event_item:
                completion_text += event_item["chunk"]["bytes"].decode("utf-8")

        result = _parse_agent_result(completion_text)
        annotate_span({"decision": result.get("decision")})

        db.log_audit_entry(
            claim_id=claim_id,
            step_id=f"agent_end_{agent_name}",
            details={"decision": result.get("decision")}
        )

        if "structured_findings" in result:
             # Assume job_id is just session_id for simplicity, or generate new UUID
             db.save_evaluation(job_id=session_id, claim_id=claim_id, result=result["structured_findings"])

    log_json(
        "bedrock_agent_result",
        agent_id=agent_id,
        agent_type=agent_type,
        model_id=model_id,
        session_id=session_id,
        claim_id=claim_id,
        decision=result.get("decision"),
    )
    return result
