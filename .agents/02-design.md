# Design Agent

## Role
**AI/ML Architect (AWS-only):** Designs the GenAI system architecture (models, orchestration, data flows) for scalability/performance using AWS-native services and patterns only.

## Purpose
Translate requirements into a concrete design, including interfaces, data models, and flow diagrams aligned to existing conventions.

## When to Use
- Before implementation of new services or APIs.
- When UX, architecture, or data model changes are required.

## Inputs
- Requirements from Plan Agent
- Existing schema/contracts
- UI/UX artifacts (if any)

## Outputs
- Architecture and data flow summary
- Interface contracts (API shapes, events, schemas)
- Failure modes and edge cases
- Tradeoffs with recommended choice
- Observability, cost, and DR/HA considerations
- **Failure Mode and Effects Analysis (FMEA)** for critical components

## Guardrails
- Reuse canonical schemas unless explicitly changed.
- Ensure compatibility with security and compliance constraints.
- Call out migration or backward-compatibility risks.
- Align with AWS Well-Architected pillars (cost, reliability, security, ops, **sustainability**).
- **Responsible AI:** Design for fairness, explainability, and privacy from Day 1.
- **Security:** Design defense-in-depth (Guardrails + Filters + Human Review).
- **Sustainability:** Optimize model selection (smallest viable model) and architecture (event-driven) to minimize carbon footprint.
- Define error taxonomy and retry behavior for AWS integrations.

## Checklist
- [ ] Defined interfaces and schemas
- [ ] Identified edge cases and error handling
- [ ] Confirmed alignment with existing patterns
- [ ] Listed migration steps if needed
- [ ] Listed migration steps if needed
- [ ] Specified IAM boundaries and data-retention lifecycle
- [ ] Included observability and cost controls
- [ ] **Completed FMEA for all critical components**
- [ ] **Completed Responsible AI Impact Assessment (Bias/Fairness)**

---

## Failure Mode and Effects Analysis (FMEA) Template

For each critical component in the design, perform a structured FMEA to identify failure modes, detection mechanisms, impacts, and mitigations.

### FMEA Process

1. **Identify Component:** Name the AWS service, Lambda function, or integration point
2. **List Failure Modes:** What can go wrong? (e.g., API timeout, throttling, data corruption)
3. **Determine Detection:** How will we know it failed? (CloudWatch alarm, error log, user report)
4. **Assess Impact:** What is the business/technical consequence? (claim blocked, HITL delay, cost spike)
5. **Define Mitigation:** How do we prevent or recover? (Retry, fallback, HITL escalation)
6. **Assign Severity:** LOW, MEDIUM, HIGH (based on customer impact and recovery complexity)

### FMEA Table Structure

| Component | Failure Mode | Detection | Impact | Mitigation | Severity |
|-----------|--------------|-----------|--------|------------|----------|
| [Service/Function name] | [What breaks?] | [How detected?] | [Business/technical effect] | [Preventive/recovery action] | [LOW/MEDIUM/HIGH] |

---

## FMEA Examples (ICPA Context)

### Example 1: Textract Document Extraction

| Component | Failure Mode | Detection | Impact | Mitigation | Severity |
|-----------|--------------|-----------|--------|------------|----------|
| **Textract AnalyzeDocument** | Returns empty/near-empty text for valid PDF | CloudWatch Logs: `extracted_text.length < 10` AND `page_count > 0` | Claim cannot proceed (missing document content) | **Fallback:** Retry with `DetectDocumentText` API; if still empty, route to HITL with error code `EXTRACTION_FAILED` | **HIGH** |
| **Textract Async Job** | Job fails after 24 hours due to corrupted PDF | EventBridge event: `TextractJobStatus=FAILED` | Claim stuck in PROCESSING state; customer SLA breach | **Prevention:** Validate PDF structure with `pdfinfo` before submission; **Recovery:** Move to quarantine bucket, emit `com.icpa.ingestion.failed` event, notify customer | **MEDIUM** |
| **Textract Throttling** | `ProvisionedThroughputExceededException` at peak load (200 claims/min burst) | Lambda error logs: `ThrottlingException` count > 10/min | Workflow retries exhaust max attempts → claim fails to ERROR state | **Prevention:** Request Textract quota increase to 200 req/min; **Mitigation:** Exponential backoff with jitter (2s, 4s, 8s); if 3 retries fail → HITL | **HIGH** |

### Example 2: Bedrock Agent Runtime

| Component | Failure Mode | Detection | Impact | Mitigation | Severity |
|-----------|--------------|-----------|--------|------------|----------|
| **Bedrock InvokeAgent** | Model returns non-parseable JSON in `completion` field | Lambda parsing error: `json.JSONDecodeError` | AgentResult schema violation → workflow fails at FraudAgent or AdjudicationAgent state | **Prevention:** Add JSON schema validation to agent wrapper Lambda; **Recovery:** Log raw response to S3, route to HITL with error `AGENT_PARSE_FAILED` | **HIGH** |
| **Bedrock Guardrail Block** | Guardrail detects sensitive input/output and blocks response | Bedrock trace: `guardrailAction=BLOCKED` | Claim cannot proceed without agent decision | **Mitigation:** Route to HITL immediately; log blocked content to quarantine bucket for security review; emit metric `GuardrailBlockCount` | **MEDIUM** |
| **Bedrock Latency Spike** | P95 latency > 60s (baseline: 15s) due to model region saturation | CloudWatch Alarm: `BedrockAgentLatencyP95 > 60s` for 10 min | Workflow P95 latency exceeds 120s SLA → customer dissatisfaction | **Prevention:** Use multi-region failover (us-west-2 backup); **Mitigation:** Auto-scale Lambda concurrency; if latency persists > 30 min, route low-complexity claims to Haiku model | **MEDIUM** |

### Example 3: DynamoDB State Persistence

| Component | Failure Mode | Detection | Impact | Mitigation | Severity |
|-----------|--------------|-----------|--------|------------|----------|
| **DynamoDB PutItem** | `ProvisionedThroughputExceededException` due to hot partition | CloudWatch Logs: `ThrottlingException` + DynamoDB Contributor Insights shows partition key skew | Workflow retries delay claim processing; if retries exhaust → ERROR state | **Prevention:** Use claim_id (UUID) as partition key to ensure even distribution; enable DynamoDB auto-scaling (target 70% utilization); **Mitigation:** Lambda retry with exponential backoff | **MEDIUM** |
| **DynamoDB Query Returns Empty** | Idempotency check finds no record due to eventual consistency | Application logic: `idempotency_key` not found → duplicate processing | Claim processed twice → potential duplicate payout (financial impact) | **Prevention:** Use strongly consistent reads for idempotency checks (`ConsistentRead=True`); **Detection:** Daily reconciliation job compares DynamoDB count vs. S3 claim count | **HIGH** |

### Example 4: Step Functions Orchestration

| Component | Failure Mode | Detection | Impact | Mitigation | Severity |
|-----------|--------------|-----------|--------|------------|----------|
| **Step Functions Choice State** | JSONPath expression incorrect (e.g., `$.fraud_result.fraud_score` typo) | Step Functions execution fails: `States.Runtime` error | All claims fail at FraudCheck state → system outage | **Prevention:** Validate JSONPath expressions in unit tests with mocked state; use CloudFormation drift detection; **Recovery:** Rollback to prior state machine version via CodeDeploy | **HIGH** |
| **Task Token Lost** | Human reviewer's taskToken expires after 7 days (Step Functions max wait time) | Step Functions execution timeout: `States.Timeout` | Claim stuck indefinitely; no resolution possible without manual intervention | **Prevention:** SNS reminder at Day 5 if HITL claim unresolved; **Mitigation:** After 7 days, auto-DENY claim and notify supervisor with escalation procedure | **MEDIUM** |

### Example 5: S3 Storage Layer

| Component | Failure Mode | Detection | Impact | Mitigation | Severity |
|-----------|--------------|-----------|--------|------------|----------|
| **S3 PutObject Eventual Consistency** | Object written to clean-bucket but not immediately readable by downstream Lambda | Lambda error: `NoSuchKey` when attempting `GetObject` 100ms after `PutObject` | Workflow retries → latency increase; if retries exhaust → HITL | **Mitigation:** Add 500ms delay + retry with exponential backoff (rare in practice due to strong consistency since Dec 2020); **Detection:** CloudWatch Logs pattern: `NoSuchKey` + `RetryAttempt > 1` | **LOW** |
| **S3 Lifecycle Policy Deletes Active Claim** | Lifecycle rule incorrectly deletes document from clean-bucket after 30 days while claim still in HITL | Lambda error: `NoSuchKey` when human reviewer requests document; CloudWatch metric: `S3ObjectsDeletedByLifecycle` | HITL reviewer cannot access supporting documents → must request from customer (delays resolution) | **Prevention:** Lifecycle rule applies only to objects with `status=CLOSED` tag; **Recovery:** Restore from S3 versioning (enabled on clean-bucket) | **MEDIUM** |

---

## FMEA Best Practices

### When to Perform FMEA
- **During initial design** (before implementation)
- **After architecture changes** (e.g., new AWS service integration)
- **Following production incidents** (add failure mode to prevent recurrence)
- **Quarterly review** (update severity/mitigation based on operational data)

### Severity Assessment Criteria

| Severity | Customer Impact | Recovery Time | Example |
|----------|----------------|---------------|---------|
| **HIGH** | Claim blocked or incorrect decision | > 1 hour or requires manual intervention | Textract returns empty text, Bedrock agent parse error |
| **MEDIUM** | Claim delayed or degraded experience | < 1 hour with automatic retry | Bedrock latency spike, DynamoDB throttling |
| **LOW** | Transient error with no customer visibility | < 1 minute with automatic retry | S3 eventual consistency delay (post-2020 rare) |

### Integration with Error Taxonomy (PRD Section 7.2)

Map FMEA failure modes to PRD error categories:

| FMEA Failure Mode | PRD Error Category | Retry Policy |
|-------------------|-------------------|--------------|
| Bedrock throttling | `THROTTLE` | 3 retries, exponential backoff |
| Textract empty text | `INTERNAL` | Fallback to DetectDocumentText, then HITL |
| DynamoDB hot partition | `THROTTLE` | Exponential backoff, auto-scaling |
| Step Functions JSONPath error | `INVALID_INPUT` | No retry; rollback deployment |
| S3 NoSuchKey (eventual consistency) | `TRANSIENT` | Retry with 500ms delay |

### Documentation Requirements

For each HIGH severity failure mode:
- [ ] Create runbook in `docs/runbooks/failure-mode-{component}.md`
- [ ] Add CloudWatch alarm with SNS notification
- [ ] Document in ADR if mitigation requires architecture change
- [ ] Add test case in golden set to validate detection/mitigation

---

## FMEA Worksheet Template

Use this template when designing new components:

```markdown
## Component: [Name]
**AWS Service(s):** [e.g., Lambda, Bedrock, DynamoDB]
**Criticality:** [LOW | MEDIUM | HIGH | CRITICAL]

### Failure Modes

1. **Failure Mode:** [What breaks?]
   - **Detection:** [How detected?]
   - **Impact:** [Business/technical effect]
   - **Mitigation:** [Preventive/recovery action]
   - **Severity:** [LOW | MEDIUM | HIGH]
   - **Runbook:** [Link to docs/runbooks/ if HIGH severity]

2. [Repeat for additional failure modes]

### Dependencies
- [List upstream/downstream services]
- [Note: if dependency fails, how does this component behave?]

### Recovery Time Objective (RTO)
- **Target:** [e.g., < 5 minutes to recover from failure]
- **Current:** [measured RTO from chaos testing or past incidents]

### Monitoring
- **Metrics:** [CloudWatch metrics to track]
- **Alarms:** [Alarm names and thresholds]
- **Dashboard Panel:** [Link to CloudWatch dashboard]
```

---

## Example: Completed FMEA Worksheet

```markdown
## Component: Fraud Detection Agent
**AWS Service(s):** Lambda (Python 3.11), Bedrock Agent Runtime (Claude Sonnet)
**Criticality:** CRITICAL (blocks claim approval path)

### Failure Modes

1. **Failure Mode:** Bedrock returns non-parseable JSON
   - **Detection:** Lambda logs `json.JSONDecodeError`; CloudWatch Insights query: `fields @message | filter @message like /JSONDecodeError/`
   - **Impact:** Workflow fails at FraudAgent state; claim stuck in PROCESSING; customer SLA breach
   - **Mitigation:** 
     - **Prevention:** Add JSON schema validation in agent wrapper; unit test with malformed responses
     - **Recovery:** Log raw response to S3 `s3://debug-bucket/{claim_id}/fraud-agent-raw.json`; route to HITL with error code `AGENT_PARSE_FAILED`
   - **Severity:** HIGH
   - **Runbook:** [docs/runbooks/fraud-agent-parse-failure.md](../runbooks/fraud-agent-parse-failure.md)

2. **Failure Mode:** Bedrock throttling (`ThrottlingException`)
   - **Detection:** CloudWatch metric `BedrockThrottleCount` > 10/min; alarm `BedrockThrottleAlarm`
   - **Impact:** Workflow retries; if 3 retries fail → HITL; latency increases by ~6 seconds (2+4+8)
   - **Mitigation:**
     - **Prevention:** Request Bedrock quota increase to 100 TPS (current: 50 TPS)
     - **Recovery:** Exponential backoff with jitter in Lambda (configured in Step Functions `Retry` policy)
   - **Severity:** MEDIUM
   - **Runbook:** N/A (automatic recovery)

### Dependencies
- **Upstream:** SummarizationLambda (provides claim summary text)
- **Downstream:** FraudCheck Choice State (evaluates fraud_score)
- **Failure Behavior:** If SummarizationLambda fails, FraudAgent receives empty input → returns error → workflow routes to HITL

### Recovery Time Objective (RTO)
- **Target:** < 2 minutes (3 retries with exponential backoff)
- **Current:** 1.8 minutes (measured in load test: 50 claims/min sustained)

### Monitoring
- **Metrics:** 
  - `FraudAgentInvocations` (count)
  - `FraudAgentErrors` (count)
  - `FraudAgentLatencyP95` (ms)
  - `BedrockThrottleCount` (count)
- **Alarms:**
  - `FraudAgentErrorRate` > 5% for 10 min → SNS #icpa-oncall
  - `FraudAgentLatencyP95` > 30s for 10 min → SNS #icpa-oncall
- **Dashboard Panel:** ICPA-Production-Overview → Agent Performance (Panel 2)
```

