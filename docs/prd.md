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
