from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from icpa.logging_utils import log_json
from icpa.otel import annotate_span, start_span
from icpa.db_client import DatabaseClient


_bedrock_runtime = boto3.client("bedrock-agent-runtime")
_ssm = boto3.client("ssm")

_ALLOWED_DECISIONS = {"CONTINUE", "STOP", "HITL", "APPROVE", "DENY", "BLOCKED", "FLAGGED"}

def _safe_snippet(text: str, max_len: int = 200) -> str:
    snippet = text[:max_len]
    return re.sub(r"[A-Za-z0-9]", "x", snippet)


def _normalize_agent_result(result: Dict[str, Any], agent_type: Optional[str]) -> Dict[str, Any]:
    normalized = dict(result)
    decision = normalized.get("decision")
    if not decision:
        if agent_type and agent_type.upper().startswith("FRAUD"):
            normalized["decision"] = "CONTINUE"
        else:
            normalized["decision"] = "BLOCKED"

    if agent_type and agent_type.upper().startswith("FRAUD"):
        findings = normalized.get("structured_findings")
        if not isinstance(findings, dict):
            findings = {}
            normalized["structured_findings"] = findings
        if "fraud_score" not in findings:
            confidence = normalized.get("confidence")
            findings["fraud_score"] = float(confidence) if isinstance(confidence, (int, float)) else 0.0

    return normalized


def _normalize_agent_name(agent_name: str) -> str:
    name = agent_name.strip()
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    return name.lower().replace(" ", "_").replace("-", "_")


def _get_prompt(agent_name: Optional[str], version: str) -> Optional[str]:
    if not agent_name:
        return None
    candidates = [agent_name, _normalize_agent_name(agent_name)]
    tried = set()
    last_error: ClientError | None = None

    for candidate in candidates:
        if candidate in tried:
            continue
        tried.add(candidate)
        try:
            if version == "latest":
                latest_param = f"/icpa/prompts/{candidate}/latest"
                latest_response = _ssm.get_parameter(Name=latest_param, WithDecryption=False)
                resolved_version = latest_response["Parameter"]["Value"]
                param_name = f"/icpa/prompts/{candidate}/{resolved_version}"
            else:
                param_name = f"/icpa/prompts/{candidate}/{version}"
            response = _ssm.get_parameter(Name=param_name, WithDecryption=False)
            return response["Parameter"]["Value"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ParameterNotFound":
                raise
            last_error = exc

    if last_error:
        raise last_error
    return None


def _parse_agent_result(text: str) -> Dict[str, Any]:
    candidates = []
    for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL):
        candidates.append(match.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("Agent output JSON is not an object")

    raise ValueError("Agent output does not contain JSON")

def _validate_agent_result(result: Dict[str, Any]) -> None:
    decision = result.get("decision")
    if not isinstance(decision, str):
        raise ValueError("Agent output missing decision")
    if decision.upper() not in _ALLOWED_DECISIONS:
        raise ValueError("Agent output has invalid decision")
    findings = result.get("structured_findings")
    if findings is not None and not isinstance(findings, dict):
        raise ValueError("Agent output structured_findings must be object")


def _invoke_agent(agent_id: str, agent_alias_id: str, session_id: str, input_text: str) -> str:
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
    return completion_text


def handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    agent_id = os.environ["BEDROCK_AGENT_ID"]
    agent_alias_id = os.environ["BEDROCK_AGENT_ALIAS_ID"]
    agent_name = os.environ.get("AGENT_NAME")
    prompt_version = os.environ.get("PROMPT_VERSION", "latest")
    agent_type = os.environ.get("AGENT_TYPE", agent_name)
    model_id = os.environ.get("MODEL_ID")
    parse_retries = int(os.environ.get("AGENT_PARSE_RETRIES", "1"))
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

        last_error: Exception | None = None
        completion_text = ""
        for attempt in range(parse_retries + 1):
            completion_text = _invoke_agent(agent_id, agent_alias_id, session_id, input_text)
            try:
                result = _parse_agent_result(completion_text)
                result = _normalize_agent_result(result, agent_type)
                _validate_agent_result(result)
                if result.get("decision") and isinstance(result["decision"], str):
                    result["decision"] = result["decision"].upper()
                last_error = None
                break
            except ValueError as exc:
                last_error = exc
                log_json(
                    "agent_output_parse_failed",
                    claim_id=claim_id,
                    agent_type=agent_type,
                    output_length=len(completion_text),
                    output_snippet=_safe_snippet(completion_text),
                    attempt=attempt + 1,
                )
                if attempt >= parse_retries:
                    break
                log_json(
                    "agent_output_retry",
                    claim_id=claim_id,
                    agent_type=agent_type,
                    attempt=attempt + 1,
                )
        if last_error:
            fallback: Dict[str, Any]
            if agent_type and agent_type.upper().startswith("FRAUD"):
                fallback = {"decision": "CONTINUE", "structured_findings": {"fraud_score": 1.0}}
            else:
                fallback = {"decision": "BLOCKED"}
            log_json(
                "agent_output_fallback_hitl",
                claim_id=claim_id,
                agent_type=agent_type,
                reason=str(last_error),
            )
            result = fallback

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
