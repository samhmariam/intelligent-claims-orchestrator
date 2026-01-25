# ICPA Architecture, Interfaces, and FMEA (Design)

**Role:** Design Agent (AWS-native AI/ML Architect)

## 1) Architecture & Data Flow (Event-Driven, Serverless)

**Core services (AWS-only, VPC endpoints, no NAT):**
- S3 (Raw/Clean/Quarantine/Evaluation)
- Lambda (ingestion, extraction post-processing, orchestration wrappers)
- Textract, Transcribe, Comprehend, Comprehend Medical
- Step Functions (orchestration)
- Bedrock (Agents + Runtime)
- DynamoDB (System of Record)
- EventBridge (routing, failure events)
- SNS (HITL)
- API Gateway (private)
- CloudWatch + X-Ray (observability)

**Flow (happy path):**
1. **Ingestion**: Claim docs uploaded to Raw bucket → S3 event → Ingestion Lambda.
2. **Extraction**:
   - PDF → Textract async; Image → Textract sync; Audio → Transcribe async.
   - Extraction output written to Clean bucket as `DocumentExtract` text.
3. **PHI Detection**: Comprehend Medical runs on extracted text chunks.
   - If PHI > 0.90 → move to Quarantine bucket and emit `com.icpa.ingestion.failed`.
4. **Validation**: Glue Data Quality validates DocumentExtract + ClaimDocument rules.
5. **Orchestration Start**: EventBridge emits `com.icpa.orchestration.start` to Step Functions.
6. **Agentic Orchestration**:
   - Step Functions invokes Lambda wrappers for Bedrock Agent Runtime.
   - Each agent returns `AgentResult` with `SourcePointer` evidence.
7. **Decision**:
   - If HITL → SNS notification with task token; resume via private API Gateway.
   - Else adjudicate and persist final state in DynamoDB.

**Flow (failure/exception path):**
- Extraction empty or low confidence → fallback Textract call; if still empty → quarantine (schema error) + EventBridge failure event.
- Bedrock guardrail block → HITL or deny based on policy.
- Step Functions task timeout → retry (exponential) then failure state with audit record.

## 2) Interface Contracts (Internal Events & APIs)

All payloads **MUST** conform to PRD canonical models (Claim, ClaimDocument, DocumentExtract, SourcePointer, AgentResult). Below are system-level envelopes that wrap those objects.

### 2.1 S3 Ingestion Event (from Raw Bucket)
```json
{
  "event_type": "com.icpa.ingestion.received",
  "event_version": "1.0",
  "timestamp": "2026-01-23T00:00:00Z",
  "claim_id": "<uuid>",
  "s3_uri": "s3://raw-bucket/<claim_id>/source=<channel>/<filename>",
  "doc_type": "FNOL_FORM",
  "mime_type": "application/pdf",
  "channel": "web|mobile|agent"
}
```

### 2.2 Extraction Completed Event
```json
{
  "event_type": "com.icpa.ingestion.extracted",
  "event_version": "1.0",
  "timestamp": "2026-01-23T00:00:00Z",
  "claim_id": "<uuid>",
  "document": {
    "doc_id": "<uuid>",
    "doc_type": "FNOL_FORM",
    "storage_pointer": "s3://clean-bucket/<claim_id>/doc_id=<doc_id>/filename.ext",
    "mime_type": "application/pdf",
    "page_count": 2
  },
  "extract": {
    "claim_id": "<uuid>",
    "doc_id": "<uuid>",
    "extracted_text_s3_uri": "s3://clean-bucket/<claim_id>/extracts/<doc_id>.txt",
    "extractor": "TEXTRACT_ASYNC",
    "confidence": 0.92,
    "created_at": "2026-01-23T00:00:00Z"
  }
}
```

### 2.3 PHI Detected Event (Quarantine)
```json
{
  "event_type": "com.icpa.ingestion.failed",
  "event_version": "1.0",
  "timestamp": "2026-01-23T00:00:00Z",
  "claim_id": "<uuid>",
  "error_code": "PHI_DETECTED",
  "s3_uri": "s3://quarantine-bucket/phi-review/<claim_id>/...",
  "confidence_threshold": 0.90
}
```

### 2.4 Orchestration Start Event
```json
{
  "event_type": "com.icpa.orchestration.start",
  "event_version": "1.0",
  "timestamp": "2026-01-23T00:00:00Z",
  "claim": { /* Canonical Claim Object */ }
}
```

### 2.5 Agent Invocation (Lambda → Bedrock Runtime)
```json
{
  "agent_id": "FRAUD_AGENT",
  "claim": { /* Canonical Claim Object */ },
  "context": {
    "documents": [ /* ClaimDocument[] */ ],
    "extracts": [ /* DocumentExtract[] */ ]
  }
}
```

### 2.6 Agent Result (Bedrock → Lambda → Step Functions)
```json
{ /* AgentResult (Canonical) */ }
```

### 2.7 HITL Request (SNS)
```json
{
  "event_type": "com.icpa.hitl.request",
  "event_version": "1.0",
  "timestamp": "2026-01-23T00:00:00Z",
  "claim_id": "<uuid>",
  "reason": "PHI_REVIEW|FRAUD_SCORE|GUARDRAIL_BLOCK",
  "summary": "short text"
}
```

### 2.8 HITL Response (Private API Gateway)
```json
{
  "claim_id": "<uuid>",
  "decision": "APPROVE|DENY|FLAGGED",
  "notes": "string"
}
```

### 2.9 Evaluation Job Request
```json
{
  "event_type": "com.icpa.evaluation.start",
  "event_version": "1.0",
  "timestamp": "2026-01-23T00:00:00Z",
  "golden_set_version": "1.0",
  "cases_s3_uri": "s3://evaluation-bucket/golden-set/v1.0/cases.jsonl"
}
```

## 3) FMEA (Critical Components)

| Component | Failure Mode | Detection | Impact | Mitigation | Severity |
|---|---|---|---|---|---|
| Textract | Empty or near-empty text | Low word count, confidence < 0.5 | Missed facts → wrong adjudication | Fallback to `DetectDocumentText`; quarantine if still empty | High |
| Textract | Async job timeout | Job status `FAILED` or time > timeout | Delayed workflow | Step Functions retry + DLQ; alert | Medium |
| Bedrock Agent Runtime | Non-parseable JSON | JSON schema validation failure | Orchestration stop | Retry with strict output prompt; fallback parser | High |
| Bedrock Agent Runtime | Guardrail block | Guardrail response signal | Halted or partial decision | Route to HITL; log event | High |
| Step Functions | JSONPath errors | State execution error | Workflow failure | Contract tests + schema validation before state execution | High |
| Step Functions | Task token timeout (HITL) | TaskTimedOut | Workflow stall | HITL SLA + reminder + auto-cancel path | Medium |

## 4) Observability & Cost

### 4.1 OpenTelemetry (ADOT) Strategy
- ADOT Lambda Layer on all Lambdas.
- Trace propagation: API Gateway → Lambda → Bedrock → DynamoDB.
- Structured logs with trace/span IDs.
- EMF custom metrics:
  - `ClaimsProcessed`, `ClaimsFailed`, `PHIRate`, `AvgAgentLatency`, `BedrockTokensUsed`, `TextractPagesProcessed`.

### 4.2 CloudWatch Dashboard Panels (per PRD)
- Claim Flow Funnel (INTAKE → PROCESSING → APPROVED/DENIED)
- Agent Latency (P50/P95/P99)
- Error Rates by Type
- Daily Cost by Service
- HITL Queue Depth
- PHI Quarantine Rate

### 4.3 Sustainability / Model Selection
- Use Claude Haiku for low-complexity classification.
- Use Claude Sonnet for complex adjudication and multi-document reasoning.
- Route by a lightweight complexity classifier to minimize carbon/cost.

## 5) Defense in Depth
- PHI detection + quarantine before orchestration.
- Guardrails on all agent invocations.
- HITL for: high fraud score, guardrail blocks, low confidence.
- KMS policies restricted to VPC endpoints.

