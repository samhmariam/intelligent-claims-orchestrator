from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import boto3
from botocore.client import BaseClient

from icpa.constants import MIN_TEXT_LENGTH
from icpa.logging_utils import log_json
from icpa.otel import annotate_span, start_span
from icpa.db_client import DatabaseClient


@dataclass(frozen=True)
class EnvConfig:
    raw_bucket: str
    clean_bucket: str
    quarantine_bucket: str
    transcribe_output_bucket: str
    textract_role_arn: Optional[str]
    textract_sns_topic_arn: Optional[str]
    phi_threshold: float
    region: str


DOC_TYPE_ENUM = {
    "FNOL_FORM",
    "DAMAGE_PHOTO",
    "POLICE_REPORT",
    "ESTIMATE",
    "AUDIO_STATEMENT",
}

MIME_TYPE_ENUM = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "audio/wav",
}


def _env() -> EnvConfig:
    return EnvConfig(
        raw_bucket=os.environ["RAW_BUCKET"],
        clean_bucket=os.environ["CLEAN_BUCKET"],
        quarantine_bucket=os.environ["QUARANTINE_BUCKET"],
        transcribe_output_bucket=os.environ.get("TRANSCRIBE_OUTPUT_BUCKET", os.environ["CLEAN_BUCKET"]),
        textract_role_arn=os.environ.get("TEXTRACT_ROLE_ARN"),
        textract_sns_topic_arn=os.environ.get("TEXTRACT_SNS_TOPIC_ARN"),
        phi_threshold=float(os.environ.get("PHI_CONFIDENCE_THRESHOLD", "0.90")),
        region=os.environ.get("AWS_REGION", "us-east-1"),
    )


def _clients() -> Dict[str, BaseClient]:
    return {
        "s3": boto3.client("s3"),
        "textract": boto3.client("textract"),
        "transcribe": boto3.client("transcribe"),
        "comprehend_medical": boto3.client("comprehendmedical"),
        "events": boto3.client("events"),
    }


def _get_doc_type_and_channel(s3_client: BaseClient, bucket: str, key: str) -> Tuple[Optional[str], Optional[str]]:
    response = s3_client.head_object(Bucket=bucket, Key=key)
    metadata = response.get("Metadata", {})
    doc_type = metadata.get("doc_type")
    channel = metadata.get("channel")
    return doc_type, channel


def _copy_to_clean(s3_client: BaseClient, source_bucket: str, source_key: str, clean_bucket: str, claim_id: str, doc_id: str) -> str:
    filename = source_key.split("/")[-1]
    clean_key = f"{claim_id}/doc_id={doc_id}/{filename}"
    s3_client.copy_object(
        Bucket=clean_bucket,
        Key=clean_key,
        CopySource={"Bucket": source_bucket, "Key": source_key},
    )
    return f"s3://{clean_bucket}/{clean_key}"


def _write_extract(s3_client: BaseClient, clean_bucket: str, claim_id: str, doc_id: str, text: str) -> str:
    extract_key = f"{claim_id}/extracts/{doc_id}.txt"
    s3_client.put_object(
        Bucket=clean_bucket,
        Key=extract_key,
        Body=text.encode("utf-8"),
        ContentType="text/plain",
    )
    return f"s3://{clean_bucket}/{extract_key}"


def _chunk_text(text: str, size: int = 18_000, overlap: int = 2_000) -> Iterable[str]:
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _phi_detected(comprehend_client: BaseClient, text: str, threshold: float) -> bool:
    for chunk in _chunk_text(text):
        response = comprehend_client.detect_phi(Text=chunk)
        entities = response.get("Entities", [])
        for entity in entities:
            if entity.get("Score", 0.0) >= threshold:
                return True
    return False


def _emit_failure(events_client: BaseClient, claim_id: str, error_code: str, s3_uri: str) -> None:
    events_client.put_events(
        Entries=[
            {
                "Source": "com.icpa.ingestion",
                "DetailType": "com.icpa.ingestion.failed",
                "Detail": json.dumps(
                    {
                        "error_code": error_code,
                        "s3_key": s3_uri,
                        "claim_id": claim_id,
                    }
                ),
            }
        ]
    )


def _quarantine_object(s3_client: BaseClient, quarantine_bucket: str, s3_uri: str, reason: str) -> str:
    match = re.match(r"s3://([^/]+)/(.+)", s3_uri)
    if not match:
        return s3_uri
    source_bucket, source_key = match.group(1), match.group(2)
    filename = source_key.split("/")[-1]
    target_key = f"{reason}/{source_key}"
    s3_client.copy_object(
        Bucket=quarantine_bucket,
        Key=target_key,
        CopySource={"Bucket": source_bucket, "Key": source_key},
    )
    s3_client.delete_object(Bucket=source_bucket, Key=source_key)
    return f"s3://{quarantine_bucket}/{target_key}"


def _extract_text_from_blocks(blocks: List[Dict[str, Any]]) -> Tuple[str, int]:
    lines = [block["Text"] for block in blocks if block.get("BlockType") == "LINE" and "Text" in block]
    page_count = len({block.get("Page") for block in blocks if block.get("Page")})
    return "\n".join(lines).strip(), max(page_count, 1)


def ingestion_handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    config = _env()
    clients = _clients()
    s3_client = clients["s3"]
    db = DatabaseClient(region_name=config.region)

    results: List[Dict[str, Any]] = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        claim_id = key.split("/")[0]
        doc_id = str(uuid.uuid4())
        annotate_span({"claim_id": claim_id, "s3_key": key})
        
        db.save_claim_state(claim_id, "INTAKE")

        with start_span("ingestion_start", {"claim_id": claim_id}):
            head_doc_type, channel = _get_doc_type_and_channel(s3_client, bucket, key)
            doc_type = head_doc_type if head_doc_type in DOC_TYPE_ENUM else None
            mime_type = record.get("s3", {}).get("object", {}).get("contentType") or _guess_mime_type(key)

            if doc_type is None or mime_type not in MIME_TYPE_ENUM:
                s3_uri = f"s3://{bucket}/{key}"
                quarantined = _quarantine_object(s3_client, config.quarantine_bucket, s3_uri, "schema-error")
                _emit_failure(clients["events"], claim_id, "SCHEMA_VIOLATION", quarantined)
                log_json("schema_violation", claim_id=claim_id, s3_uri=s3_uri)
                results.append({"status": "QUARANTINED", "claim_id": claim_id, "doc_id": doc_id})
                continue

            clean_uri = _copy_to_clean(s3_client, bucket, key, config.clean_bucket, claim_id, doc_id)

            if mime_type == "application/pdf":
                job_tag = f"claim_id={claim_id};doc_id={doc_id};clean_uri={clean_uri}"
                params: Dict[str, Any] = {
                    "DocumentLocation": {"S3Object": {"Bucket": bucket, "Name": key}},
                    "FeatureTypes": ["FORMS", "TABLES"],
                    "JobTag": job_tag,
                }
                if config.textract_role_arn and config.textract_sns_topic_arn:
                    params["NotificationChannel"] = {
                        "RoleArn": config.textract_role_arn,
                        "SNSTopicArn": config.textract_sns_topic_arn,
                    }
                response = clients["textract"].start_document_analysis(**params)
                results.append(
                    {
                        "status": "STARTED",
                        "claim_id": claim_id,
                        "doc_id": doc_id,
                        "job_id": response["JobId"],
                        "channel": channel,
                        "clean_uri": clean_uri,
                    }
                )
                continue

            if mime_type in {"image/jpeg", "image/jpg"}:
                text, page_count = _analyze_image(clients["textract"], bucket, key)
                extract_uri = _write_extract(s3_client, config.clean_bucket, claim_id, doc_id, text)
                if _phi_detected(clients["comprehend_medical"], text, config.phi_threshold):
                    _quarantine_object(s3_client, config.quarantine_bucket, clean_uri, "phi-review")
                    quarantined = _quarantine_object(s3_client, config.quarantine_bucket, extract_uri, "phi-review")
                    _emit_failure(clients["events"], claim_id, "PHI_DETECTED", quarantined)
                    results.append({"status": "QUARANTINED", "claim_id": claim_id, "doc_id": doc_id})
                    continue
                results.append(
                    {
                        "status": "EXTRACTED",
                        "claim_id": claim_id,
                        "doc_id": doc_id,
                        "extract_uri": extract_uri,
                        "page_count": page_count,
                    }
                )
                continue

            if mime_type == "audio/wav":
                transcribe_job_name = f"{claim_id}-{doc_id}-{int(time.time())}"
                filename = key.split("/")[-1]
                output_key = f"transcribe/{claim_id}/{doc_id}/{filename}.json"
                clients["transcribe"].start_transcription_job(
                    TranscriptionJobName=transcribe_job_name,
                    LanguageCode="en-US",
                    Media={"MediaFileUri": f"s3://{bucket}/{key}"},
                    OutputBucketName=config.transcribe_output_bucket,
                    OutputKey=output_key,
                )
                results.append({"status": "STARTED", "claim_id": claim_id, "doc_id": doc_id, "job": transcribe_job_name})
                continue

    return {"results": results}


def _analyze_image(textract_client: BaseClient, bucket: str, key: str) -> Tuple[str, int]:
    response = textract_client.analyze_document(
        Document={"S3Object": {"Bucket": bucket, "Name": key}},
        FeatureTypes=["FORMS", "TABLES"],
    )
    text, page_count = _extract_text_from_blocks(response.get("Blocks", []))
    if len(text) < MIN_TEXT_LENGTH:
        response = textract_client.detect_document_text(Document={"S3Object": {"Bucket": bucket, "Name": key}})
        text, page_count = _extract_text_from_blocks(response.get("Blocks", []))
    return text, page_count


def textract_result_handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    config = _env()
    clients = _clients()
    s3_client = clients["s3"]
    textract_client = clients["textract"]

    job_id = _get_textract_job_id(event)
    job_tag = _get_textract_job_tag(event)
    claim_id, doc_id, clean_uri = _parse_job_tag(job_tag)

    with start_span("textract_result", {"claim_id": claim_id, "job_id": job_id}):
        blocks: List[Dict[str, Any]] = []
        next_token: Optional[str] = None
        while True:
            args = {"JobId": job_id}
            if next_token:
                args["NextToken"] = next_token
            response = textract_client.get_document_analysis(**args)
            blocks.extend(response.get("Blocks", []))
            next_token = response.get("NextToken")
            if not next_token:
                break

        text, page_count = _extract_text_from_blocks(blocks)
        if len(text) < MIN_TEXT_LENGTH and clean_uri:
            fallback = textract_client.detect_document_text(
                Document={"S3Object": {"Bucket": config.clean_bucket, "Name": _s3_key_from_uri(clean_uri)}}
            )
            text, page_count = _extract_text_from_blocks(fallback.get("Blocks", []))

        extract_uri = _write_extract(s3_client, config.clean_bucket, claim_id, doc_id, text)
        if _phi_detected(clients["comprehend_medical"], text, config.phi_threshold):
            _quarantine_object(s3_client, config.quarantine_bucket, clean_uri, "phi-review")
            quarantined = _quarantine_object(s3_client, config.quarantine_bucket, extract_uri, "phi-review")
            _emit_failure(clients["events"], claim_id, "PHI_DETECTED", quarantined)
            return {"status": "QUARANTINED", "claim_id": claim_id, "doc_id": doc_id}

        return {
            "status": "EXTRACTED",
            "claim_id": claim_id,
            "doc_id": doc_id,
            "extract_uri": extract_uri,
            "page_count": page_count,
        }


def transcribe_postprocess_handler(event: Dict[str, Any], _: Any) -> Dict[str, Any]:
    config = _env()
    clients = _clients()
    s3_client = clients["s3"]

    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = record["s3"]["object"]["key"]
    claim_id, doc_id, filename = _parse_transcribe_key(key)

    response = s3_client.get_object(Bucket=bucket, Key=key)
    payload = json.loads(response["Body"].read().decode("utf-8"))
    transcript = payload.get("results", {}).get("transcripts", [{}])[0].get("transcript", "")

    extract_uri = _write_extract(s3_client, config.clean_bucket, claim_id, doc_id, transcript)
    if _phi_detected(clients["comprehend_medical"], transcript, config.phi_threshold):
        cleaned_uri = f"s3://{config.clean_bucket}/{claim_id}/doc_id={doc_id}/{filename}"
        _quarantine_object(s3_client, config.quarantine_bucket, cleaned_uri, "phi-review")
        quarantined = _quarantine_object(s3_client, config.quarantine_bucket, extract_uri, "phi-review")
        _emit_failure(clients["events"], claim_id, "PHI_DETECTED", quarantined)
        return {"status": "QUARANTINED", "claim_id": claim_id, "doc_id": doc_id}

    return {"status": "EXTRACTED", "claim_id": claim_id, "doc_id": doc_id, "extract_uri": extract_uri}


def _get_textract_job_id(event: Dict[str, Any]) -> str:
    detail = event.get("detail", {})
    return detail.get("JobId") or event.get("JobId") or event.get("jobId")


def _get_textract_job_tag(event: Dict[str, Any]) -> str:
    detail = event.get("detail", {})
    return detail.get("JobTag") or event.get("JobTag") or event.get("jobTag", "")


def _parse_job_tag(job_tag: str) -> Tuple[str, str, str]:
    parts = dict(item.split("=", 1) for item in job_tag.split(";") if "=" in item)
    return parts.get("claim_id", ""), parts.get("doc_id", ""), parts.get("clean_uri", "")


def _parse_transcribe_key(key: str) -> Tuple[str, str, str]:
    match = re.search(r"transcribe/([^/]+)/([^/]+)/(.+)\.json", key)
    if not match:
        return "", "", ""
    return match.group(1), match.group(2), match.group(3)


def _guess_mime_type(key: str) -> str:
    lowered = key.lower()
    if lowered.endswith(".pdf"):
        return "application/pdf"
    if lowered.endswith(".jpg") or lowered.endswith(".jpeg"):
        return "image/jpeg"
    if lowered.endswith(".wav"):
        return "audio/wav"
    return "application/octet-stream"


def _s3_key_from_uri(s3_uri: str) -> str:
    match = re.match(r"s3://[^/]+/(.+)", s3_uri)
    return match.group(1) if match else ""
