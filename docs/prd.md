# Intelligent Claims Processing Agent (ICPA) - Product Requirements Document

## Table of Contents
- [Intelligent Claims Processing Agent (ICPA) - Product Requirements Document](#intelligent-claims-processing-agent-icpa---product-requirements-document)
  - [Table of Contents](#table-of-contents)
  - [1. Product Overview](#1-product-overview)
  - [2. System Contracts \& Canonical Models (REQUIRED)](#2-system-contracts--canonical-models-required)
    - [2.1. Canonical Data Schemas](#21-canonical-data-schemas)
    - [2.2. Persistence Model](#22-persistence-model)
  - [3. Target Goals \& Success Metrics](#3-target-goals--success-metrics)
  - [4. Functional Requirements \& Phased Implementation](#4-functional-requirements--phased-implementation)
    - [4.0. Testing Strategy](#40-testing-strategy)
      - [4.0.1. Test Pyramid](#401-test-pyramid)
      - [4.0.2. Test Requirements by Phase](#402-test-requirements-by-phase)
      - [4.0.3. Load \& Performance Testing](#403-load--performance-testing)
      - [4.0.4. Chaos Testing](#404-chaos-testing)
      - [4.0.5. Security \& Compliance Testing](#405-security--compliance-testing)
      - [4.0.6. Golden Set Management](#406-golden-set-management)
    - [4.1. Phase 1: Infrastructure \& Secure Environment](#41-phase-1-infrastructure--secure-environment)
    - [4.2. Phase 2: Multimodal Ingestion \& Data Sanitation](#42-phase-2-multimodal-ingestion--data-sanitation)
    - [4.3. Phase 3: Agentic Orchestration (The "Brain")](#43-phase-3-agentic-orchestration-the-brain)
    - [4.4. Phase 4: Safety, Governance \& HITL](#44-phase-4-safety-governance--hitl)
    - [4.5. Phase 5: Optimization \& Cost Control](#45-phase-5-optimization--cost-control)
    - [4.6. Phase 6: Observability, Evaluation \& Logs](#46-phase-6-observability-evaluation--logs)
  - [5. Operational, Security \& Compliance Requirements](#5-operational-security--compliance-requirements)
    - [5.1. Acceptance Criteria \& Non-Functional Targets](#51-acceptance-criteria--non-functional-targets)
    - [5.2. Error Taxonomy \& Retry Policy](#52-error-taxonomy--retry-policy)
    - [5.3. Data Retention \& Lifecycle](#53-data-retention--lifecycle)
    - [5.4. IAM \& Access Boundaries](#54-iam--access-boundaries)
    - [5.5. Model \& Prompt Governance](#55-model--prompt-governance)
    - [5.6. Observability Contract](#56-observability-contract)
      - [5.6.1. Metrics Dashboard Specification](#561-metrics-dashboard-specification)
      - [5.6.2. Custom CloudWatch Metrics](#562-custom-cloudwatch-metrics)
      - [5.6.3. X-Ray Tracing Requirements](#563-x-ray-tracing-requirements)
    - [5.7. Cost \& Sustainability Controls](#57-cost--sustainability-controls)
    - [5.8. DR/HA Expectations](#58-drha-expectations)
    - [5.9. Compliance Mapping](#59-compliance-mapping)
    - [5.10. External API Interface Contracts](#510-external-api-interface-contracts)
  - [6. Release Readiness \& Gating](#6-release-readiness--gating)
    - [6.1. Pre-Production Checklist](#61-pre-production-checklist)
      - [6.1.1. Functional Quality Gates](#611-functional-quality-gates)
      - [6.1.2. Security \& Compliance Gates](#612-security--compliance-gates)
      - [6.1.3. Operational Readiness Gates](#613-operational-readiness-gates)
      - [6.1.4. Documentation Gates](#614-documentation-gates)
      - [6.1.5. Deployment Checklist](#615-deployment-checklist)
    - [6.2. Release Approval Workflow](#62-release-approval-workflow)
    - [6.3. Post-Deployment Validation](#63-post-deployment-validation)
    - [6.4. Rollback Criteria (Automatic)](#64-rollback-criteria-automatic)
    - [6.5. Version Pinning Policy](#65-version-pinning-policy)
    - [6.6. Evaluation Gating](#66-evaluation-gating)

---

## 1. Product Overview
- **Project Name:** Intelligent Claims Processing Agent (ICPA)
- **Industry:** Insurance / Financial Services
- **Vision:** To automate the end-to-end insurance claims lifecycle—from intake to adjudication—using a multi-agent orchestration pattern that ensures high accuracy, regulatory compliance, and significant operational ROI.
- **Architecture Style:** Event-Driven, Serverless, Agentic (ReAct + Workflow Orchestration).

## 2. System Contracts & Canonical Models (REQUIRED)

### 2.1. Canonical Data Schemas
All agents must adhere to these JSON schemas.

**A. Claim Object (Canonical)**
```json
{
  "claim_id": "UUID (v4)",
  "policy_number": "String (Top-Level/S3 Key)",
  "incident_date": "ISO-8601 Date",
  "claim_amount": "Decimal (GBP)",
  "policy_state": "Enum [London, Birmingham, Leeds, Glasgow, Sheffield, Bristol, Edinburgh, Manchester, Cardiff, Newcastle]",
  "description": "String (Sanitized)",
  "documents": ["List<ClaimDocument>"],
  "status": "Enum [INTAKE, PROCESSING, FLAGGED, APPROVED, DENIED]"
}
```

**B. ClaimDocument Schema**
```json
{
  "doc_id": "UUID",
  "doc_type": "Enum [FNOL_FORM, DAMAGE_PHOTO, POLICE_REPORT, ESTIMATE, AUDIO_STATEMENT]",
  "storage_pointer": "s3://clean-bucket/<claim_id>/doc_id=<doc_id>/filename.ext",
  "mime_type": "String [application/pdf, image/jpeg, audio/wav]",
  "page_count": "Integer"
}
```

**C. DocumentExtract Contract**
```json
{
  "claim_id": "UUID",
  "doc_id": "UUID",
  "extracted_text_s3_uri": "s3://clean-bucket/<claim_id>/extracts/<doc_id>.txt",
  "extractor": "Enum [TEXTRACT_ASYNC, TEXTRACT_SYNC, TRANSCRIBE]",
  "confidence": "Float (Avg Confidence)",
  "created_at": "ISO-8601 Timestamp"
}
```

**D. SourcePointer Schema**
```json
{
  "source_type": "Enum [POLICY_PDF, CLAIM_DOC, KNOWLEDGE_CHUNK]",
  "s3_uri": "String (Full S3 URI)",
  "page_num": "Integer (1-based) [Nullable]",
  "chunk_id": "String (VectorDB ID) [Nullable]",
  "char_start": "Integer [Nullable]",
  "char_end": "Integer [Nullable]",
  "sha256": "String (Content Hash)"
}
```
**SourcePointer Field Requirements (by `source_type`):**
- **POLICY_PDF / CLAIM_DOC:** `s3_uri` required; `page_num` required; `chunk_id`, `char_start`, `char_end` MUST be null.
- **KNOWLEDGE_CHUNK:** `chunk_id`, `char_start`, `char_end` required; `page_num` MUST be null; `s3_uri` required (points to originating doc or KB export).

**E. AgentResult Schema**
```json
{
  "agent_id": "Enum [FRAUD_AGENT, ADJ_AGENT, POLICY_ROUTER]",
  "decision": "Enum [CONTINUE, STOP, HITL, APPROVE, DENY, BLOCKED]",
  "confidence_score": "Float (0.0 - 1.0)",
  "rationale": "String (CoT Summary)",
  "cited_evidence": ["List<SourcePointer>"],
  "structured_findings": {
    "fraud_score": "Float",
    "payout_amount": "Decimal (GBP) [Nullable]",
    "denial_reason_code": "String [Nullable]"
  }
}
```

### 2.2. Persistence Model
**System of Record: Amazon DynamoDB**

| Table Name | Partition Key (PK) | Sort Key (SK) | TTL | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `ICPA_Claims` | `CLAIM#<claim_id>` | `META` | `ttl` | Core claim state & metadata. |
| `ICPA_Claims` | `CLAIM#<claim_id>` | `STEP#<wf_step_id>` | `ttl` | Audit trail of step executions. |
| `ICPA_Idempotency` | `REQ#<canonical_req_hash>` | - | `expires_at` | 24hr cache of API responses. |
| `ICPA_Evaluation` | `EVAL#<job_id>` | `CASE#<claim_id>` | `ttl` | Evaluation results per test case. |

**Idempotency Key Construction:** 
`canonical_req_hash` := `SHA256("CLAIM#" + claim_id + "#STEP#" + step_name + "#HASH#" + SHA256(canonical_json(input)))`

## 3. Target Goals & Success Metrics
*(Unchanged from previous version)* -> See Section 5.6 for Observability Contracts.

## 4. Functional Requirements & Phased Implementation

### 4.0. Testing Strategy

#### 4.0.1. Test Pyramid
All phases must implement testing according to this distribution:

- **Unit Tests (70%):** Individual Lambda functions, schema validators, utility modules
  - **Coverage Target:** ≥ 85% line coverage
  - **Framework:** pytest with pytest-cov
  - **Scope:** Pure functions, business logic, data transformations
  - **Example:** Test `validate_claim_schema()` with valid/invalid inputs

- **Integration Tests (20%):** Component interactions with mocked external services
  - **Coverage Target:** All Step Functions state transitions
  - **Framework:** moto for AWS service mocks, pytest-mock
  - **Scope:** Lambda → DynamoDB, Lambda → S3, Step Functions workflows
  - **Example:** Test Step Functions workflow with mocked Bedrock agent responses

- **End-to-End Tests (10%):** Full claim lifecycle in non-production environment
  - **Coverage Target:** All golden set scenarios (100 cases)
  - **Framework:** behave (BDD) or pytest with fixtures
  - **Scope:** Complete workflow from ingestion → adjudication → persistence
  - **Example:** Submit claim via API Gateway, verify DynamoDB final state

#### 4.0.2. Test Requirements by Phase

**Phase 1 (Infrastructure):**
- [ ] VPC endpoint connectivity tests (can reach Bedrock, Textract, etc.)
- [ ] KMS key policy validation (verify `kms:ViaService` conditions)
- [ ] Security group rules (deny all inbound except required)
- [ ] CloudFormation/CDK stack deployment smoke tests

**Phase 2 (Ingestion):**
- [ ] Textract extraction accuracy (compare against ground truth for 10 sample PDFs)
- [ ] PHI detection recall test (100% of test PHI entities detected with >0.90 confidence)
- [ ] Glue Data Quality rule validation (schema violations correctly identified)
- [ ] Quarantine bucket routing (PHI documents moved to correct S3 prefix)

**Phase 3 (Orchestration):**
- [ ] State machine transition tests (all Choice conditions exercised)
- [ ] Fraud score thresholds (>0.70 correctly routes to HITL)
- [ ] Agent Lambda wrapper parsing (AgentResult JSON correctly extracted)
- [ ] Idempotency validation (duplicate requests return cached response)

**Phase 4 (HITL & Safety):**
- [ ] SNS notification payload structure (claim_id present)
- [ ] API Gateway IAM auth (unauthorized requests return 403)
- [ ] Task token resumption (SendTaskSuccess correctly resumes workflow)
- [ ] Guardrail blocking (high-risk inputs trigger HITL)

**Phase 5 (Optimization):**
- [ ] Model routing logic (complexity classifier correctly assigns LOW/HIGH)
- [ ] Cost per claim validation (average ≤ £0.45 for 100-claim batch)
- [ ] SSM parameter retrieval (model map retrieved and parsed correctly)

**Phase 6 (Evaluation):**
- [ ] DecisionAccuracy calculation (match expected_decision with tolerance)
- [ ] Judge LLM agreement (factual_accuracy scores ≥ 7/10 for 90% of cases)
- [ ] Golden set versioning (v1.0 → v1.1 backward compatible)
- [ ] Evaluation metrics persistence (results stored in DynamoDB)

#### 4.0.3. Load & Performance Testing

**Load Test Requirements:**
- **Sustained Load:** 50 claims/minute for 30 minutes
- **Burst Load:** 200 claims/minute for 5 minutes
- **Latency Target:** P95 end-to-end ≤ 120s (non-HITL path)
- **Error Rate:** < 2% for workflow failures

**Tools:**
- **Artillery** or **Locust** for API load generation
- **CloudWatch Contributor Insights** for identifying hot partitions
- **X-Ray Service Map** for latency bottleneck analysis

**Test Scenarios:**
```json
{
  "scenarios": [
    {
      "name": "baseline",
      "claims_per_min": 50,
      "duration_min": 30,
      "claim_types": ["LOW_COMPLEXITY", "HIGH_COMPLEXITY"],
      "distribution": [0.7, 0.3]
    },
    {
      "name": "burst",
      "claims_per_min": 200,
      "duration_min": 5,
      "claim_types": ["LOW_COMPLEXITY"],
      "distribution": [1.0]
    }
  ]
}
```

#### 4.0.4. Chaos Testing

**Fault Injection Scenarios:**
- **VPC Endpoint Failure:** Simulate `bedrock-runtime` endpoint unavailable (expect: Lambda retries → ERROR state)
- **Bedrock Throttling:** Inject `ThrottlingException` (expect: exponential backoff → success after 3 retries)
- **DynamoDB Hot Partition:** Concentrate writes on single partition key (expect: adaptive capacity engaged)
- **S3 Eventual Consistency:** Delay S3 object availability (expect: Lambda retry with backoff)

**Tools:**
- **AWS Fault Injection Simulator (FIS)** for managed chaos experiments
- **Lambda Layer** with custom throttling/failure injection
- **Step Functions error injection** via Task.catch testing

#### 4.0.5. Security & Compliance Testing

**Mandatory Security Tests:**
- [ ] **IAM Least Privilege:** Attempt cross-bucket S3 access (expect: AccessDenied)
- [ ] **API Gateway IAM Auth:** Submit request without signature (expect: 403 Forbidden)
- [ ] **PHI Leakage Prevention:** Verify no PHI in CloudWatch Logs (scan with regex)
- [ ] **Encryption at Rest:** Query S3 object metadata for `x-amz-server-side-encryption: aws:kms`
- [ ] **TLS Version:** Attempt connection with TLS 1.1 (expect: handshake failure)
- [ ] **KMS Key Policy:** Attempt direct KMS decrypt outside VPC (expect: denied by `kms:ViaService`)

**Compliance Validation:**
- **Data Retention:** Verify S3 lifecycle policies delete objects after 30/180/365 days
- **Audit Trail:** Confirm CloudTrail logs all API calls with user identity
- **Access Logging:** Verify S3 access logs enabled for all buckets

**Tools:**
- **Prowler** or **ScoutSuite** for automated security scanning
- **AWS Config Rules** for continuous compliance monitoring
- **IAM Access Analyzer** for unintended external access detection

#### 4.0.6. Golden Set Management

**Golden Set Schema:**
```json
{
  "version": "1.0",
  "created_at": "2025-01-01T00:00:00Z",
  "cases": [
    {
      "case_id": "GS-001",
      "claim_fixture": { /* Canonical Claim Object */ },
      "expected_decision": "APPROVE",
      "expected_payout": 1500.00,
      "rationale": "Valid claim with complete documentation",
      "tags": ["LOW_COMPLEXITY", "AUTO_APPROVE"]
    }
  ]
}
```

**Versioning Policy:**
- **v1.0 (Baseline):** 100 cases covering common scenarios
- **v1.1 (Edge Cases):** Add 20 adversarial cases (e.g., fraudulent patterns)
- **v1.2 (Regression):** Add cases from production incidents
- **Backward Compatibility:** New versions must pass all prior version tests

**Storage Location:** `s3://evaluation-bucket/golden-set/v{MAJOR}.{MINOR}/cases.jsonl`

### 4.1. Phase 1: Infrastructure & Secure Environment
**Definition of Done:** Terraform/CDK creates V1 infrastructure with passing security checks.

- **Requirement 1.1 (Region & Network):** 
    - **Region:** `us-east-1` (Primary).
    - **VPC Contract:** 
        - CIDR: `10.0.0.0/16`.
        - Subnets: Private Isolated (App Layer) x 3 AZs.
        - **Placement:** All workflow compute (Lambda/Glue) runs in Private Subnets; all AWS API calls use VPC endpoints; no NAT.
        - **Egress:** NO NAT Gateways allowed.
    - **Endpoint Matrix (Interface VPC Endpoints Required):**
        - `com.amazonaws.us-east-1.bedrock` (Control Plane)
        - `com.amazonaws.us-east-1.bedrock-runtime` (Inference)
        - `com.amazonaws.us-east-1.bedrock-agent` (Agents & Knowledge Bases)
        - `com.amazonaws.us-east-1.bedrock-agent-runtime` (Agent Runtime)
        - `com.amazonaws.us-east-1.textract`
        - `com.amazonaws.us-east-1.transcribe`
        - `com.amazonaws.us-east-1.comprehend`
        - `com.amazonaws.us-east-1.comprehendmedical`
        - `com.amazonaws.us-east-1.states`
        - `com.amazonaws.us-east-1.sns`
        - `com.amazonaws.us-east-1.ssm`
        - `com.amazonaws.us-east-1.execute-api` (For Private API Gateway)
        - `com.amazonaws.us-east-1.logs`
        - `com.amazonaws.us-east-1.xray`
        - `com.amazonaws.us-east-1.s3` (Gateway)
        - `com.amazonaws.us-east-1.dynamodb` (Gateway)

- **Requirement 1.2 (Security Enforcement):**
    - **TLS Policy:** Enforce **TLS 1.2+** on all ALB/API Listeners.
    - **KMS Policy:** `kms:ViaService` conditions for S3/DynamoDB restricted to specified VPC Endpoints. If the intent is “only usable via our VPC endpoints,” enforce with `aws:sourceVpce` (and/or `aws:sourceVpc`) conditions in the key policy.

### 4.2. Phase 2: Multimodal Ingestion & Data Sanitation
**Definition of Done:** Pipeline ingests, extracts txt, detects PHI, quarantines PHI content, and validates Schema.

**Event Envelopes (Internal):**
- `com.icpa.ingestion.received` (S3 intake event)
- `com.icpa.ingestion.extracted` (extraction completed)
- `com.icpa.ingestion.failed` (schema or PHI quarantine)

- **Requirement 2.1 (Ingestion Contract):**
    - **Inputs:** PDF (Max 10MB), JPG (Max 5MB), WAV (Audio, Max 2min).
    - **S3 Key Convention:**
        - Raw: `s3://raw-bucket/<claim_id>/source=<channel>/<filename>`
        - Clean: `s3://clean-bucket/<claim_id>/doc_id=<uuid>/<filename>`

- **Requirement 2.2 (Multimodal Processing & Extraction):**
    - **Extraction Contract (`DocumentExtract`):** All texts must be extracted to `s3://clean-bucket/<claim_id>/extracts/<doc_id>.txt` (UTF-8).
    - **Audio Path (Transcribe):** 
        - Call `StartTranscriptionJob` -> Output JSON to S3.
        - **Follow-up:** Lambda trigger parses JSON, extracts `"results.transcripts[0].transcript"`, and writes to `<doc_id>.txt`.
    - **Textract Strategy:** 
      - **PDFs:** Use `StartDocumentAnalysis` (Async API) with `FeatureTypes: ["FORMS", "TABLES"]`.
      - **Images:** Use `AnalyzeDocument` (Sync API) with `FeatureTypes: ["FORMS", "TABLES"]`.
      - **Fallback:** If analysis returns empty/near-empty text, call `DetectDocumentText` and use its output.
    - **PHI Detection (Chunking):** 
        - **Rule:** Comprehend Medical `DetectPHI` accepts max 20,000 bytes.
        - **Action:** Split `<doc_id>.txt` into 18KB overlapping chunks (2KB overlap) before calling `DetectPHI`.
    - **Action:** If *any* PHI entity is detected with Confidence > 0.90 -> Move document to `s3://quarantine-bucket/phi-review/` and trigger manual review.

**Implementation Guidance (from AWS Snippets):**
> **Glue Data Quality:** Use `awsglue.data_quality.DataQualityRule`.
> ```python
> rules = [
>     DataQualityRule.is_complete("claim_id"),
>     DataQualityRule.column_values_match_pattern("mime_type", "^(application/pdf|image/jpeg|audio/wav)$"),
>     DataQualityRule.column_values_match_pattern("storage_pointer", "^s3://clean-bucket/.*")
> ]
> ```
> **PHI Redaction:** Use `Comprehend.detect_pii_entities` for PII and `ComprehendMedical.detect_phi` for PHI. Ensure text is chunked (<20KB) with 10% overlap to avoid losing context at boundaries.

- **Requirement 2.3 (Validation & Failure):**
    - **Tool:** AWS Glue Data Quality.
  - **Ruleset (minimum checks):**
    - Required fields present: `claim_id`, `doc_id`, `doc_type`, `storage_pointer`, `mime_type`, `page_count`.
    - `doc_type` in enum `[FNOL_FORM, DAMAGE_PHOTO, POLICE_REPORT, ESTIMATE, AUDIO_STATEMENT]`.
    - `mime_type` in enum `[application/pdf, image/jpeg, audio/wav]`.
    - `storage_pointer` starts with `s3://clean-bucket/`.
    - `page_count` is integer and >= 1.
    - `claim_id` and `doc_id` are UUID v4 format.
  - **Failure Policy:** 
    - Schema Violation -> Move to `s3://quarantine-bucket/schema-error/`.
    - Emit EventBridge event: `com.icpa.ingestion.failed` with payload `{ "error_code": "SCHEMA_VIOLATION", "s3_key": "..." }`.

### 4.3. Phase 3: Agentic Orchestration (The "Brain")
**Definition of Done:** Step Function executes valid state transitions using Lambda-wrapped Agents.

**Event Envelopes (Internal):**
- `com.icpa.orchestration.start` (triggered after successful ingestion/extraction)

**Model Tiering (Sustainability/Cost):**
- **Classification/low-complexity:** Claude Haiku
- **Adjudication/high-complexity:** Claude Sonnet
- **Routing:** Lightweight complexity classifier determines model choice prior to Bedrock invocation.

- **Requirement 3.1 (State Machine ASL):**
  - **Query Language:** State machine uses **JSONPath** (not JSONata). All `.$` selectors are JSONPath.
```json
{
  "StartAt": "GenerateClaimSummary",
  "States": {
    "GenerateClaimSummary": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": { "FunctionName": "${SummarizationLambdaArn}", "Payload.$": "$" },
      "ResultSelector": { "claim_summary_text.$": "$.Payload.summary" },
      "ResultPath": "$.claim_summary",
      "Next": "RouteClaim",
      "Retry": [ { "ErrorEquals": ["Lambda.TooManyRequestsException"], "IntervalSeconds": 2, "MaxAttempts": 3, "BackoffRate": 2.0 } ]
    },
    "RouteClaim": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": { 
        "FunctionName": "${RouterLambdaArn}", 
        "Payload": { 
          "claim_id.$": "$.claim_id",
          "claim_amount.$": "$.claim_amount", 
          "policy_state.$": "$.policy_state"
        } 
      },
      "ResultSelector": { "target_agent.$": "$.Payload.target_agent", "reason.$": "$.Payload.reason" },
      "ResultPath": "$.router_output",
      "Next": "AgentRouter"
    },
    "AgentRouter": {
      "Type": "Choice",
      "Choices": [
        { "Variable": "$.router_output.target_agent", "StringEquals": "HITL", "Next": "HumanReview" }
      ],
      "Default": "FraudAgent"
    },
    "FraudAgent": { 
      "Type": "Task", 
      "Resource": "arn:aws:states:::lambda:invoke", 
      "Parameters": {
         "FunctionName": "${InvokeFraudAgentLambdaArn}",
         "Payload": { "session_id.$": "$.claim_id", "input_text.$": "$.claim_summary.claim_summary_text" }
      },
      "ResultSelector": { "agent_result.$": "$.Payload" },
      "ResultPath": "$.fraud_result",
      "Next": "FraudCheck",
      "Catch": [ { "ErrorEquals": ["States.ALL"], "Next": "ErrorHandlingState" } ] 
    },
    "FraudCheck": {
      "Type": "Choice",
      "Choices": [
        { "Variable": "$.fraud_result.agent_result.decision", "StringEquals": "STOP", "Next": "RejectClaim" },
        { "NumericGreaterThan": 0.70, "Variable": "$.fraud_result.agent_result.structured_findings.fraud_score", "Next": "HumanReview" }
      ],
      "Default": "AdjudicationAgent"
    },
    "AdjudicationAgent": { 
      "Type": "Task", 
      "Resource": "arn:aws:states:::lambda:invoke", 
      "Parameters": {
         "FunctionName": "${InvokeAdjAgentLambdaArn}",
         "Payload": { "session_id.$": "$.claim_id", "input_text.$": "$.claim_summary.claim_summary_text" }
      },
      "ResultSelector": { "agent_result.$": "$.Payload" },
      "ResultPath": "$.agent_result",
      "Next": "EvaluateResult",
      "Catch": [ { "ErrorEquals": ["States.ALL"], "Next": "ErrorHandlingState" } ] 
    },
    "EvaluateResult": { 
      "Type": "Choice", 
      "Choices": [
        { "Variable": "$.agent_result.agent_result.decision", "StringEquals": "STOP", "Next": "RejectClaim" },
        { "Variable": "$.agent_result.agent_result.decision", "StringEquals": "DENY", "Next": "RejectClaim" },
        { "Variable": "$.agent_result.agent_result.decision", "StringEquals": "BLOCKED", "Next": "HumanReview" },
        { "Variable": "$.agent_result.agent_result.decision", "StringEquals": "APPROVE", "Next": "FinalizeClaim" }
      ],
      "Default": "HumanReview" 
    },
    "HumanReview": { 
      "Type": "Task", 
      "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken", 
      "Parameters": { "FunctionName": "${NotificationLambdaArn}", "Payload": { "taskToken.$": "$$.Task.Token", "claim_id.$": "$.claim_id" } },
      "ResultPath": "$.human_decision",
      "Next": "HumanDecisionChoice" 
    },
    "HumanDecisionChoice": {
      "Type": "Choice",
      "Choices": [
        { "Variable": "$.human_decision.decision", "StringEquals": "DENY", "Next": "RejectClaim" }
      ],
      "Default": "FinalizeClaim"
    },
    "RejectClaim": { "Type": "Fail", "Cause": "Claim Rejected or Denied" },
    "ErrorHandlingState": { "Type": "Fail", "Cause": "Workflow Error" },
    "FinalizeClaim": { "Type": "Succeed" }
  }
}
```

- **Requirement 3.2 (Router Logic):**
    - **Logic:** Calls `RouterLambda` to check if `claim_amount > $10,000`. If YES -> HITL. Else -> Default to `FraudAgent`.
    - **Fraud Check:** Executed by `FraudAgent` (Bedrock). `FraudCheck` Choice State evaluates the returned `fraud_score` > 0.70.
  - **Summary Persistence:** `SummarizationLambda` must write the summary text to `s3://clean-bucket/<claim_id>/summaries/<claim_id>.txt` (UTF-8) before the workflow proceeds.

- **Requirement 3.3 (Agent Lambda Wrappers):**
    - **Contract:** All Agents are wrapped in a Lambda Layer that:
        1. Calls `bedrock-agent-runtime.invoke_agent`.
        2. Accumulates trace chunks.
        3. Parses the final "Completion" string into the canonical `AgentResult` JSON.
        4. Returns the clean JSON object to Step Functions.

**Implementation Guidance (from AWS Snippets):**
> **Session Management:** Use `bedrock_agent_runtime.create_session` to generate a session ID (if not mapped to `claim_id`) to maintain conversation context.
> **Memory:** Enable `SESSION_MEMORY` in the Agent definition to allow multi-turn reasoning on the `claim_summary`.
> **Lambda Wrapper:** Use `botocore` for `invoke_agent`. Handle the event stream:
> ```python
> for event in response['completion']:
>     if 'chunk' in event:
>         text += event['chunk']['bytes'].decode('utf-8')
> ```

### 4.4. Phase 4: Safety, Governance & HITL
**Definition of Done:** HITL API Auth defined and Notifier working without NAT.

- **Requirement 4.1 (HITL Mechanism):**
    - **Triggers:** 
        1. `ClaimAmount > $10k` (Router).
        2. `FraudScore > 0.70` (FraudCheck Choice).
        3. `Guardrail Block` (EvaluateResult Choice).
    - **Notification:** Send message to **SNS Topic** `ClaimsReviewTeam` -> **AWS Chatbot** (Slack).
    - **Notification Payload (SNS Message JSON):**
        ```json
        {
          "claim_id": "<claim_id>",
          "decision_endpoint": "https://<private-api-id>.execute-api.us-east-1.amazonaws.com/review/approve",
          "instructions": "Review claim and submit APPROVE, DENY, or FLAGGED using IAM-authenticated POST to /review/approve with claim_id + decision.",
          "summary_s3_uri": "s3://clean-bucket/<claim_id>/summaries/<claim_id>.txt"
        }
        ```
    - **Reviewer Action:** Human reviewer assumes the `ClaimsReviewerRole` and uses the internal review script/CLI to submit `POST /review/approve` with body `{ "claim_id": "...", "decision": "APPROVE|DENY|FLAGGED" }`.
    - **Resumption API:**
        - **Endpoint:** API Gateway Private `POST /review/approve`.
        - **Auth:** IAM-Auth.
        - **Handler (`ApprovalHandlerLambda`):**
            - **Input:** `{ "claim_id": "...", "decision": "APPROVE|DENY|FLAGGED" }`.
            - **Logic:** Looks up the task token by `claim_id`, then calls `SendTaskSuccess` with `{"decision": decision}`.

- **Requirement 4.2 (Guardrails - Security & RAI):**
    - **Prompt Injection:** Block inputs containing "Ignore previous instructions", "System override", or known jailbreak patterns (High strictness).
    - **Content Policy:** Block "Financial Advice", "Medical Diagnosis", "Hate Speech", "Sexual Content" (High filters).
    - **PII/PHI Enforce:** Ensure Guardrails redact any leaked PII in agent outputs as a final defense layer.
    - **Intervention:** Return `BLOCKED` to Step Function (Mapped to `HumanReview` path).

**Implementation Guidance (from AWS Snippets):**
> **Safety Filter Class:** Implement a standardized `InputSafetyFilter` class.
> ```python
> class InputSafetyFilter:
>     def filter_input(self, user_input):
>         response = bedrock.apply_guardrail(guardrailIdentifier=self.id, ...)
>         if json.loads(response["output"])["blocked"]:
>             return { "is_safe": False, "reason": result["blockReasons"] }
> ```
> **Defense in Depth:** Use `Comprehend.detect_sentiment` in the `ContentAnalyzer` Lambda to flag "High Risk" emotional content (e.g., negative sentiment + keywords) even if Guardrails pass.

### 4.5. Phase 5: Optimization & Cost Control
- **Requirement 5.1 (Routing & Config):**
    - **Classifier Output:** `{"complexity": "LOW|HIGH", "confidence": 0.0-1.0}`.
    - **Model Map:** Retrieve from **SSM Parameter Store** (via `vpce-ssm`).

### 4.6. Phase 6: Observability, Evaluation & Logs
**Definition of Done:** Single, consistent Evaluation Schema and Metrics.

- **Requirement 6.1 (Golden Set Contract):**
    - **Location:** `s3://evaluation-bucket/golden-set/v1/cases.jsonl`
    - **Schema:** 
    ```json
    { 
      "claim_fixture": { 
        "policy_number": "POL-123456", 
        "incident_date": "2024-01-01", 
        "claim_amount": 1500.00,
        "policy_state": "London",
        "description": "...", 
        "documents": [],
        "status": "INTAKE" 
      },
      "expected_decision": "APPROVE|DENY", 
      "expected_payout": 1500.00 
    }
    ```

- **Requirement 6.2 (Judge & Metrics):**
    - **Metric:** `DecisionAccuracy`.
        - Rule: Match if `decision == expected_decision`.
        - If `APPROVED`, check `payout` (found in `structured_findings.payout_amount`) within +/- 5% tolerance.
    - **Judge Schema (Canonical):**
        ```json
        { 
          "factual_accuracy": 1-10, 
          "policy_adherence": 1-10, 
          "bias_check_pass": "Boolean",
          "final_verdict": "PASS|FAIL", 
          "explanation": "String" 
        }
        ```
    - **Storage:** Arguments and Results stored in `ICPA_Evaluation` DynamoDB Table.
    - **Bias Testing:** Evaluate all "DENY" decisions for correlation with protected attributes (simulated in Test Set via `policy_state` or `demographic_proxy`). Report Disparate Impact Ratio if > 1.2.

**Implementation Guidance (from AWS Snippets):**
> **Quality Evaluator:** Implement an "LLM-as-a-Judge" class (`QualityEvaluator`).
> **Prompt Structure:**
> ```text
> You are an expert evaluator. Rate the response on:
> 1. Factual Accuracy (1-10)
> 2. Policy Adherence (1-10)
> Reference Info: {golden_set_ground_truth}
> Output JSON: { "factual_accuracy": <score>, ... }
> ```
> **Weighting:** Calculate overall score with higher weights on `Factual Accuracy` and `Policy Adherence` (e.g., 2x multiplier).

## 5. Operational, Security & Compliance Requirements

### 5.1. Acceptance Criteria & Non-Functional Targets
- **Latency:** P95 end-to-end claim processing <= 120 seconds for non-HITL paths.
- **Throughput:** Sustained 50 claims/minute with burst to 200/minute.
- **Accuracy:** `DecisionAccuracy` >= 90% on golden set v1.
- **Availability:** 99.9% monthly for workflow orchestration path.
- **Cost:** <= $0.45 per claim average (non-HITL path).

### 5.2. Error Taxonomy & Retry Policy
- **Categories:** `TRANSIENT`, `THROTTLE`, `INVALID_INPUT`, `ACCESS_DENIED`, `INTERNAL`.
- **Retries:**
  - `TRANSIENT`/`THROTTLE`: exponential backoff, max 3 retries.
  - `INVALID_INPUT`/`ACCESS_DENIED`: no retry; move to quarantine + emit failure event.
  - `INTERNAL`: 1 retry; then fail to `ErrorHandlingState`.

### 5.3. Data Retention & Lifecycle
- **Raw bucket:** 30 days then delete.
- **Clean bucket:** 180 days then delete.
- **Quarantine bucket:** 365 days then delete.
- **DynamoDB TTL:** 365 days for `ICPA_Claims` and `ICPA_Evaluation` unless legal hold applied.
- **Logs:** CloudWatch retention 90 days; X-Ray traces 30 days.

### 5.4. IAM & Access Boundaries
- **Principle:** Least privilege for every Lambda and API.
- **Roles:**
  - `ClaimsReviewerRole` can call `POST /review/approve` only.
  - Agent Lambdas can access only their required S3 prefixes and specific AWS APIs.
- **No cross-account access** unless explicitly approved.

### 5.5. Model & Prompt Governance
- **Version pinning:** Bedrock model IDs must be explicit and versioned.
- **Prompt versioning:** Prompts stored in SSM with semantic version tags.
- **Evaluation gating:** Release requires passing golden set thresholds in Section 6.
- **Rollback:** Prior prompt/model versions must be stored and reversible.

### 5.6. Observability Contract
- **Required metrics:**
  - `ClaimsProcessed`, `ClaimsHITL`, `ClaimsDenied`, `ClaimsApproved` (count)
  - `WorkflowLatencyP95`, `AgentLatencyP95` (ms)
  - `PHIQuarantineCount`, `SchemaViolationCount`
  - `InputTokenCount`, `OutputTokenCount` (Bedrock usage per agent)
- **Alarms:**
  - `WorkflowLatencyP95` > 120s for 5 minutes
  - `ErrorHandlingState` rate > 2% in 15 minutes

#### 5.6.1. Metrics Dashboard Specification

**CloudWatch Dashboard Name:** `ICPA-Production-Overview`

**Required Panels (Layout 3x2 grid):**

1. **Claim Flow Funnel (Stacked Area Chart)**
   - **Metrics:** 
     - `ClaimsIngested` (count, sum)
     - `ClaimsProcessing` (count, sum)
     - `ClaimsApproved` (count, sum)
     - `ClaimsDenied` (count, sum)
   - **Period:** 5 minutes
   - **Color Scheme:** Blue → Green (approved), Red (denied)
   - **Y-Axis:** Count per time bucket
   - **Annotations:** Mark HITL handoffs

2. **Agent Performance (Line Chart - Multi-Series)**
   - **Metrics:**
     - `FraudAgentLatency` (ms, P50/P95/P99)
     - `AdjudicationAgentLatency` (ms, P50/P95/P99)
   - **Period:** 1 minute
   - **Threshold Lines:** 
     - P95 target = 30s (horizontal red line)
     - P99 max = 60s (horizontal orange line)
   - **Stat:** Percentile

3. **Error Rates by Type (Bar Chart)**
   - **Metrics:**
     - `ErrorsByType` (count, sum)
     - **Dimensions:** `error_type` [TRANSIENT, THROTTLE, INVALID_INPUT, ACCESS_DENIED, INTERNAL]
   - **Period:** 5 minutes
   - **Sort:** Descending by count
   - **Alarm Overlay:** Show alarm threshold (2% of total)

4. **Daily Cost by Service (Stacked Bar Chart)**
   - **Metrics:**
     - `CostByService` (GBP, sum)
     - **Dimensions:** `service` [Lambda, Bedrock, Textract, S3, StepFunctions, DynamoDB]
   - **Period:** 1 day
   - **Goal Line:** £0.45 × daily claim volume (horizontal green line)
   - **Data Source:** AWS Cost Explorer API

5. **HITL Queue Depth (Gauge)**
   - **Metric:** `HITLQueueDepth` (count, max)
   - **Period:** 1 minute
   - **Ranges:**
     - 0-10: Green (healthy)
     - 11-50: Yellow (elevated)
     - 51+: Red (critical backlog)
   - **Alarm:** > 50 for 15 minutes → SNS notification

6. **PHI Quarantine Rate (Single Value + Sparkline)**
   - **Metric:** `PHIQuarantineRate` (percent, average)
   - **Formula:** `(PHIQuarantineCount / ClaimsProcessed) * 100`
   - **Period:** 1 hour
   - **Sparkline:** Last 24 hours
   - **Alarm:** > 10% triggers security review

**Dashboard Refresh Rate:** 1 minute (auto-refresh)

**Access Control:** IAM policy restricts to `ICPAOperationsRole` and `ICPAReadOnlyRole`

#### 5.6.2. Custom CloudWatch Metrics

**Namespace:** `ICPA/Production`

**Metric Dimensions:**
```python
{
  "Namespace": "ICPA/Production",
  "MetricData": [
    {
      "MetricName": "ClaimProcessingLatency",
      "Value": latency_ms,
      "Unit": "Milliseconds",
      "Timestamp": timestamp,
      "Dimensions": [
        {"Name": "ClaimType", "Value": "LOW_COMPLEXITY"},
        {"Name": "AgentType", "Value": "FraudAgent"},
        {"Name": "Region", "Value": "us-east-1"}
      ]
    }
  ]
}
```

**Embedded Metric Format (EMF) in Logs:**
```json
{
  "_aws": {
    "Timestamp": 1641234567890,
    "CloudWatchMetrics": [
      {
        "Namespace": "ICPA/Production",
        "Dimensions": [["ClaimType", "AgentType"]],
        "Metrics": [
          {"Name": "ClaimProcessingLatency", "Unit": "Milliseconds"}
        ]
      }
    ]
  },
  "ClaimType": "LOW_COMPLEXITY",
  "AgentType": "FraudAgent",
  "ClaimProcessingLatency": 2850,
  "claim_id": "abc-123",
  "correlation_id": "xyz-789"
}
```

#### 5.6.3. X-Ray Tracing Requirements

**Trace Segments:**
- **Ingestion:** API Gateway → Lambda (DocumentProcessor) → S3
- **Extraction:** Lambda (TextractHandler) → Textract → S3
- **Orchestration:** Step Functions → Lambda (AgentWrapper) → Bedrock Agent Runtime
- **HITL:** Lambda (NotificationHandler) → SNS → API Gateway (Callback)

**Trace Annotations (Required):**
```python
{
  "claim_id": "UUID",
  "policy_number": "String",
  "agent_type": "Enum [FRAUD, ADJUDICATION, ROUTER]",
  "model_id": "String (e.g., anthropic.claude-3-sonnet-v1:0)",
  "decision": "Enum [APPROVE, DENY, HITL, BLOCKED]",
  "cost_estimate_gbp": "Float"
}
```

**Trace Metadata (Optional):**
```python
{
  "claim_amount": 1500.00,
  "document_count": 3,
  "fraud_score": 0.23,
  "payout_amount": 1425.00
}
```

**Sampling Rule:**
```json
{
  "version": 2,
  "rules": [
    {
      "description": "Trace all HITL claims",
      "priority": 1,
      "fixed_rate": 1.0,
      "reservoir_size": 100,
      "attributes": {
        "decision": ["HITL"]
      }
    },
    {
      "description": "Sample 10% of normal claims",
      "priority": 100,
      "fixed_rate": 0.1,
      "reservoir_size": 10
    }
  ],
  "default": {
    "fixed_rate": 0.05,
    "reservoir_size": 1
  }
}
```

### 5.7. Cost & Sustainability Controls
- **AWS Budgets:** monthly budget with 80%/100% alerts.
- **Per-claim ceiling:** fail-safe alert if average > $0.45 for 24h window.
- **Model tiering:** allow fallback to lower-cost models (e.g., Haiku) for non-critical steps (Sustainability: use lighter models to reduce carbon footprint).
- **Token Efficiency:** Monitor `OutputTokenCount` / `InputTokenCount` ratio; optimize prompts to reduce input overhead.

### 5.8. DR/HA Expectations
- **Multi-AZ:** all Lambdas and storage are Multi-AZ by default.
- **RPO/RTO:** RPO <= 24h, RTO <= 4h for critical workflows.
- **Backups:** S3 versioning enabled for clean/quarantine buckets; DynamoDB PITR enabled.

### 5.9. Compliance Mapping
- **Applicable frameworks:** HIPAA, GLBA (as applicable by policy).
- **Controls:**
  - **Encryption:** S3 SSE-KMS and DynamoDB KMS encryption.
  - **Network isolation:** VPC endpoints only; no NAT; `kms:ViaService` + `aws:sourceVpce` enforced for key usage.
  - **Retention (HIPAA/GLBA):** S3 lifecycle policies (Raw 30d, Clean 180d, Quarantine 365d) and DynamoDB TTL enforce data minimization.
  - **PHI handling (HIPAA):** Comprehend Medical detection with quarantine routing; PHI content isolated before orchestration.
- **Audit evidence:** S3 access logs, CloudTrail, and evaluation results retained.

### 5.10. External API Interface Contracts
- **Inbound:** only Private API Gateway `POST /review/approve` with IAM auth.
- **Rate limits:** 50 req/min per reviewer role.
- **Request/Response:** request body `{ "claim_id": "...", "decision": "APPROVE|DENY|FLAGGED" }`, response `{ "status": "OK" }`.

---

## 6. Release Readiness & Gating

Before any deployment to **Staging** or **Production**, the following gates MUST be satisfied:

### 6.1. Pre-Production Checklist

#### 6.1.1. Functional Quality Gates
- [ ] **Golden Set Accuracy:** DecisionAccuracy ≥ 90% on golden set v{CURRENT}
- [ ] **Unit Test Coverage:** ≥ 85% line coverage across all Lambda functions
- [ ] **Integration Tests:** All Step Functions state transitions pass
- [ ] **E2E Test Suite:** 100% pass rate on staging environment (minimum 10 end-to-end scenarios)
- [ ] **Load Test:** Sustained 50 claims/min for 30 minutes with P95 latency < 120s
- [ ] **Chaos Test:** Bedrock throttling simulation passes with < 2% error rate

#### 6.1.2. Security & Compliance Gates
- [ ] **Security Scan:** Prowler/Checkov scan passes with zero HIGH or CRITICAL findings
- [ ] **IAM Access Analyzer:** No unintended external access detected
- [ ] **Secrets Validation:** No hardcoded credentials in code (automated scan via git-secrets)
- [ ] **Encryption Audit:** All S3 buckets and DynamoDB tables use KMS encryption
- [ ] **Compliance Sign-Off:** Legal/Privacy team approval documented in Jira ticket
- [ ] **PHI Detection Recall:** 100% of test PHI entities detected in golden set

#### 6.1.3. Operational Readiness Gates
- [ ] **DR Drill:** Disaster recovery procedure tested within last 30 days (RPO/RTO targets met)
- [ ] **Runbook Validation:** All critical incident runbooks tested in non-prod environment
- [ ] **Monitoring Coverage:** CloudWatch dashboards created with all required panels (Section 5.6.1)
- [ ] **Alarms Configured:** All critical alarms (latency, error rate, HITL queue) active with SNS routing
- [ ] **Cost Budget:** Finance approval for projected monthly spend (attach cost forecast)
- [ ] **On-Call Rotation:** PagerDuty schedule staffed for 7 days post-deployment

#### 6.1.4. Documentation Gates
- [ ] **README Updated:** Reflects all architectural changes and new dependencies
- [ ] **ADR Created:** Architecture Decision Record for major design changes (if applicable)
- [ ] **PRD Synchronized:** docs/prd.md reflects current system behavior
- [ ] **Runbooks Updated:** Incident response procedures include new failure modes
- [ ] **API Documentation:** OpenAPI spec for `/review/approve` endpoint current

#### 6.1.5. Deployment Checklist
- [ ] **Rollback Plan:** Documented procedure to revert to prior version (< 15 minutes)
- [ ] **Feature Flags:** New functionality behind AppConfig flags (if applicable)
- [ ] **Blue/Green Setup:** Deployment pipeline configured for zero-downtime cutover
- [ ] **Canary Duration:** 10% traffic for 1 hour before full rollout
- [ ] **Health Check:** `/health` endpoint returns 200 OK with version metadata
- [ ] **Post-Deploy Validation:** Smoke tests run automatically after deployment

### 6.2. Release Approval Workflow

**Gatekeeper Roles:**

| Gate | Approver | Criteria | SLA |
|------|----------|----------|-----|
| **Functional Quality** | Tech Lead | All tests pass + golden set ≥ 90% | 1 business day |
| **Security** | Security Engineer | Prowler scan clean + IAM review | 2 business days |
| **Compliance** | Compliance Officer | Legal/Privacy sign-off | 3 business days |
| **Cost** | Finance DRI | Budget approval for forecast spend | 1 business day |
| **Operations** | DevOps Manager | DR drill + monitoring validated | 1 business day |

**Approval Process:**
1. **Developer** completes all checklist items and creates Jira release ticket
2. **Build Agent** runs automated gate validations (tests, scans, coverage)
3. **Review Agent** performs code review and verifies non-automated gates
4. **Gatekeepers** provide sign-off in Jira (async approval within SLA)
5. **Deploy & Maintain Agent** executes deployment with manual approval for Production

**Emergency Hotfix Path:**
- **Criteria:** P0 outage or critical security vulnerability
- **Approval:** Tech Lead + On-Call Manager (verbal approval acceptable)
- **Process:** Deploy to Prod, then complete checklist within 24 hours (retroactive compliance)

### 6.3. Post-Deployment Validation

**Immediate (< 5 minutes post-deploy):**
- [ ] Step Functions execution succeeds for synthetic test claim
- [ ] CloudWatch metrics show `ClaimsProcessed` incrementing
- [ ] No ERROR logs in CloudWatch Logs Insights for new deployment version
- [ ] X-Ray Service Map shows all expected service connections

**Short-Term (1 hour post-deploy):**
- [ ] Canary metrics (P95 latency, error rate) within 5% of baseline
- [ ] No increase in `ErrorHandlingState` invocations
- [ ] HITL queue depth stable (no unexpected backlog)
- [ ] Cost per claim within expected range ($0.40 - $0.50)

**Long-Term (24 hours post-deploy):**
- [ ] Golden set re-run shows no accuracy regression
- [ ] Production DecisionAccuracy ≥ 90% (sampled from live claims)
- [ ] No P1/P0 incidents raised
- [ ] Customer feedback (if applicable) does not indicate degradation

### 6.4. Rollback Criteria (Automatic)

**Trigger automatic rollback if:**
- `ErrorHandlingState` rate > 5% for 10 minutes
- `WorkflowLatencyP95` > 180s for 15 minutes (50% degradation)
- `PHIQuarantineRate` > 20% (indicating detection false positives)
- CloudWatch Alarm: `CriticalFailureRate` in ALARM state

**Rollback Procedure:**
1. CodeDeploy automatically reverts to previous green deployment
2. Step Functions state machine updated to prior version ARN
3. Lambda function aliases switched to previous version
4. SNS notification sent to #icpa-oncall with rollback details
5. Post-rollback validation runs (same as 6.3 Immediate checks)

### 6.5. Version Pinning Policy

**Model Versions:**
- **Storage:** SSM Parameter Store `/icpa/models/{agent_name}/version`
- **Format:** `anthropic.claude-3-sonnet-20240229-v1:0` (explicit version, no wildcards)
- **Approval:** Any model version change requires golden set re-validation
- **Rollback:** Prior model versions retained in SSM with `_previous` suffix

**Prompt Versions:**
- **Storage:** SSM Parameter Store `/icpa/prompts/{agent_name}/v{MAJOR}.{MINOR}.{PATCH}`
- **Semantic Versioning:**
  - MAJOR: Instruction format change (e.g., tool schema update)
  - MINOR: Phrasing change affecting outputs
  - PATCH: Typo fix or clarification
- **Alias:** `/icpa/prompts/{agent_name}/latest` points to active version
- **Audit Trail:** DynamoDB table `ICPA_PromptVersions` logs all updates with approver identity

**Infrastructure Versions:**
- **IaC:** Terraform/CDK stack versions tagged in Git (e.g., `v1.2.3`)
- **Release Notes:** Each version includes changelog with breaking changes highlighted
- **Deprecation:** 30-day notice for any resource deletion (e.g., SSM parameter removal)

### 6.6. Evaluation Gating

**Continuous Evaluation:**
- **Schedule:** Golden set evaluation runs nightly at 2 AM UTC
- **Alerting:** If DecisionAccuracy drops below 88% (2% buffer), SNS alert to #icpa-dev
- **Root Cause Analysis:** If below 85% for 3 consecutive days, mandatory RCA meeting

**Pre-Release Evaluation:**
- **Baseline:** Run golden set on current production version (establish baseline)
- **Candidate:** Run golden set on new deployment candidate
- **Comparison:** DecisionAccuracy must not regress by > 1 percentage point
- **Edge Cases:** New golden set cases added for any production incident root causes

**A/B Testing (for model changes):**
- **Setup:** Route 10% of claims to new model version for 7 days
- **Metrics:** Compare DecisionAccuracy, latency, cost per claim
- **Decision Rule:** Promote to 100% only if all metrics neutral or better

---
