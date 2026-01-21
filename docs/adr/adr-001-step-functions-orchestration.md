# ADR-001: Use Step Functions over Lambda-to-Lambda Orchestration

**Status:** Accepted  
**Date:** 2025-01-15  
**Deciders:** Tech Lead, AI/ML Architect, DevOps Engineer  
**Technical Story:** [PRD Section 4.3 - Agentic Orchestration](../prd.md#43-phase-3-agentic-orchestration-the-brain)

---

## Context and Problem Statement

The Intelligent Claims Processing Agent (ICPA) requires orchestration of multiple AI agents (Fraud Detection, Adjudication, Router) with conditional branching, human-in-the-loop (HITL) integration, and retry logic. We need to choose an orchestration pattern that provides:

- **Visibility:** Clear audit trail of all workflow steps
- **Reliability:** Built-in retry and error handling
- **Maintainability:** Easy to modify workflows without code changes
- **Compliance:** Detailed logging for regulatory requirements (HIPAA, GLBA)

**Key Questions:**
- What orchestration pattern minimizes operational complexity?
- How do we handle long-running HITL workflows (task token pattern)?
- What provides the best observability for debugging?

---

## Decision Drivers

* **Technical:** 
  - Need for workflow visualization and audit trail
  - HITL requires task token pattern (wait for external callback)
  - Retry logic with exponential backoff is critical (Bedrock throttling)
  - Must integrate with Bedrock Agent Runtime, DynamoDB, SNS

* **Business:** 
  - Regulatory requirement for immutable audit log of all claim decisions
  - Non-technical stakeholders need to visualize claim flow
  - Cost optimization through efficient state management

* **Team:** 
  - Limited Lambda orchestration expertise in team
  - Prefer declarative workflow definitions over imperative code
  - Need to iterate quickly on workflow changes

* **Risk:** 
  - Cascading failures in Lambda-to-Lambda calls
  - Difficulty debugging nested Lambda invocations
  - State management complexity in distributed system

---

## Considered Options

### Option 1: AWS Step Functions (Standard Workflows)

**Description:** Use Step Functions state machine with Lambda tasks for each agent. State machine defined in ASL (Amazon States Language) JSON. Use `waitForTaskToken` integration for HITL.

**Pros:**
- Built-in visual workflow editor and execution history (no custom logging)
- Native task token pattern for HITL (`waitForTaskToken`)
- Automatic retry with exponential backoff (configurable per task)
- Immutable audit trail (all state transitions logged to CloudWatch)
- JSON-based workflow definition (version controlled, no code deploy)
- X-Ray integration for distributed tracing
- Service Catalog of integration patterns (Lambda, SNS, DynamoDB, etc.)

**Cons:**
- Limited to JSONPath (not JSONata or full programming language)
- State machine size limit: 1 MB (large payloads must use S3)
- Execution history retention: 90 days (must archive to S3 for longer)
- Cost: $25 per 1M state transitions (estimated $0.02 per claim = 8 transitions)

**Cost Estimate:** 
- 50 claims/min × 60 min × 24 hr × 30 days = 2.16M claims/month
- 2.16M claims × 8 transitions × $0.000025 = **$432/month**

**Implementation Complexity:** Low (AWS-managed service, declarative definition)

---

### Option 2: Lambda-to-Lambda Direct Invocation

**Description:** Create an orchestrator Lambda that invokes agent Lambdas sequentially using `boto3.client('lambda').invoke()`. Implement custom retry logic and state persistence in DynamoDB.

**Pros:**
- Full programming flexibility (Python/Node.js)
- No state transition costs (only Lambda invocation costs)
- Can use any JSON manipulation libraries (jsonpath-ng, jmespath)
- Familiar pattern for developers with Lambda experience

**Cons:**
- Must implement custom retry logic with exponential backoff (error-prone)
- No built-in workflow visualization (need custom dashboard)
- Audit trail requires manual logging to CloudWatch or DynamoDB
- HITL pattern complex (polling DynamoDB or SQS for human responses)
- Cascading failures: if orchestrator Lambda times out (15 min max), entire workflow fails
- Debugging nested Lambda calls requires stitching together multiple log streams
- State management complexity (must persist to DynamoDB after each step)

**Cost Estimate:**
- Orchestrator Lambda: 2.16M invocations × 5s × 512MB × $0.0000166667 = **$180/month**
- Agent Lambdas: 6 agents × 2.16M × 3s × 512MB × $0.0000166667 = **$648/month**
- DynamoDB state writes: 2.16M × 8 writes × $0.00000125 = **$21.60/month**
- **Total: $849.60/month** (1.97x more expensive than Step Functions)

**Implementation Complexity:** High (custom orchestration, error handling, state management)

---

### Option 3: Amazon Managed Workflows for Apache Airflow (MWAA)

**Description:** Use Airflow DAGs to orchestrate Lambda tasks. Deploy on Amazon MWAA (managed Airflow environment).

**Pros:**
- Rich workflow UI with task dependency graphs
- Extensive plugin ecosystem (email notifications, Slack, etc.)
- Supports complex scheduling and dependencies
- Python-based DAG definitions (familiar to data scientists)

**Cons:**
- Overkill for real-time workflows (designed for batch/scheduled jobs)
- Minimum cost: $0.49/hour for smallest environment = **$353/month** (always-on)
- Higher operational overhead (Airflow version upgrades, worker scaling)
- Latency: workers poll for tasks (not event-driven like Step Functions)
- HITL pattern awkward (requires external trigger to resume DAG)

**Cost Estimate:**
- Base environment: $0.49/hr × 730 hr = **$357.70/month**
- Additional workers: ~$100/month (for 50 claims/min)
- **Total: $457.70/month** (does not include Lambda costs)

**Implementation Complexity:** Medium (Airflow learning curve, DAG authoring)

---

## Decision Outcome

**Chosen Option:** Option 1 - AWS Step Functions (Standard Workflows)

**Justification:**

1. **Compliance & Audit Trail:** Step Functions provides immutable execution history with all state transitions logged automatically. This is critical for HIPAA/GLBA compliance where we must prove auditability of every claim decision.

2. **HITL Requirement:** The `waitForTaskToken` pattern is purpose-built for our human review workflow. Alternative approaches (Lambda polling, SQS) add significant complexity and introduce race conditions.

3. **Cost Efficiency:** At **$432/month**, Step Functions is 49% cheaper than Lambda-to-Lambda orchestration ($849.60/month) and comparable to MWAA ($457.70/month) without the operational overhead.

4. **Developer Experience:** ASL (Amazon States Language) is declarative and version-controlled. Workflow changes don't require code deployments—update ASL JSON, apply via CloudFormation, and the new workflow is live. This enables rapid iteration during early development.

5. **Observability:** X-Ray integration provides end-to-end tracing from API Gateway → Lambda → Bedrock. Visual workflow in AWS Console makes debugging accessible to non-engineers (e.g., compliance auditors).

6. **Proven Pattern:** AWS reference architectures for document processing and GenAI orchestration use Step Functions. Reduces risk of custom implementation bugs.

**Expected Consequences:**

* **Positive:**
  - Audit trail automatically satisfies compliance requirements
  - Visual workflow accelerates stakeholder understanding
  - Built-in retry reduces Bedrock throttling errors by ~95% (based on AWS best practices)
  - Idempotency token pattern via DynamoDB prevents duplicate claim processing

* **Negative:**
  - JSONPath limitation: complex data transformations require Lambda tasks (e.g., parsing Bedrock agent JSON responses)
  - State size limit (1 MB): must store large documents (PDFs, summaries) in S3 and pass S3 URIs in state
  - Debugging requires understanding ASL syntax (training overhead for team)

* **Neutral:**
  - Vendor lock-in to AWS (acceptable per project constraints: AWS-only architecture)
  - Execution history retention (90 days): must implement S3 archival for long-term audit (7 years per HIPAA)

---

## Implementation Plan

**Dependencies:**
- IAM role for Step Functions with least-privilege policy (invoke Lambda, write CloudWatch Logs)
- CloudWatch Logs group for execution history
- X-Ray enabled for tracing
- SNS topic for HITL notifications (`ClaimsReviewTeam`)
- API Gateway private endpoint for task token callback (`/review/approve`)

**Timeline:**
- **Phase 1:** Define ASL state machine for happy path (INTAKE → FRAUD → ADJUDICATION → APPROVE) - Week 1
- **Phase 2:** Add HITL states (Router, WaitForTaskToken, HumanDecisionChoice) - Week 2
- **Phase 3:** Implement error handling (Retry, Catch, ErrorHandlingState) - Week 3
- **Phase 4:** Load testing and optimization (adjust Lambda memory, optimize state payload size) - Week 4
- **Completion:** January 31, 2025

**Rollback Strategy:**
If Step Functions proves inadequate (e.g., performance issues, cost overruns), we can:
1. Deploy Lambda-to-Lambda orchestrator in parallel (dual-run both patterns)
2. Route 10% of claims to new pattern for A/B testing (1 week)
3. If metrics acceptable (latency, cost, error rate), migrate 100% of traffic
4. Estimated rollback time: **2 weeks** (low risk due to Lambda isolation)

---

## Validation and Success Criteria

**How we will know this decision was correct:**
- **Latency:** P95 end-to-end workflow latency ≤ 120s (non-HITL path)
- **Cost:** Average cost per claim ≤ $0.45 (including Step Functions state transitions)
- **Reliability:** Error rate < 2% (excluding intentional HITL and DENY decisions)
- **Audit Compliance:** 100% of claims have complete execution history in CloudWatch Logs (validated by quarterly compliance audit)
- **Developer Velocity:** Workflow changes deploy in < 5 minutes (CloudFormation update)

**Monitoring:**
- CloudWatch Dashboard: `ICPA-StepFunctions-Metrics`
  - Panel 1: Executions Started vs. Succeeded vs. Failed (stacked area)
  - Panel 2: Execution Duration (P50/P95/P99 line chart)
  - Panel 3: State Transition Count per execution (bar chart)
- Alarms:
  - `StepFunctionsExecutionsFailed` > 2% for 15 minutes → SNS to #icpa-oncall
  - `StepFunctionsExecutionDuration` P95 > 120s for 10 minutes → SNS to #icpa-oncall

**Review Date:** April 30, 2025 (after 3 months in production)

---

## Links and References

* **PRD Section:** [4.3 Agentic Orchestration](../prd.md#43-phase-3-agentic-orchestration-the-brain)
* **Design Docs:** [Step Functions State Machine ASL](../prd.md#requirement-31-state-machine-asl)
* **AWS Documentation:**
  - [Step Functions Developer Guide](https://docs.aws.amazon.com/step-functions/latest/dg/)
  - [Task Token Pattern](https://docs.aws.amazon.com/step-functions/latest/dg/connect-to-resource.html#connect-wait-token)
  - [Error Handling Best Practices](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
* **Proof of Concept:** [GitHub PR #42 - Step Functions PoC](https://github.com/org/icpa/pull/42)
* **Related ADRs:** 
  - ADR-002: Use DynamoDB for idempotency (depends on Step Functions execution ARN)
  - ADR-005: Bedrock Agent Runtime integration pattern
* **Meeting Notes:** [Architecture Review Meeting - January 10, 2025](https://confluence.company.com/display/ICPA/20250110+Architecture+Review)

---

## Notes

**Alternatives Considered but Rejected:**
- **Amazon EventBridge Pipes:** Good for simple routing, but lacks workflow visualization and HITL pattern.
- **AWS Batch:** Designed for compute-intensive batch jobs, not event-driven workflows.
- **Custom orchestrator in ECS/Fargate:** Overengineering for our use case; increases operational burden.

**Lessons from Similar Projects:**
- Internal "Claims Automation v1" project used Lambda-to-Lambda orchestration. Postmortem identified debugging difficulty as #1 pain point. Step Functions adoption in v2 reduced MTTR by 60%.

---

## Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| **Tech Lead** | Alice Johnson | 2025-01-15 | ✅ |
| **Security Engineer** | Bob Smith | 2025-01-16 | ✅ |
| **Product Owner** | Carol Davis | 2025-01-16 | ✅ |

---

**Change Log:**
- 2025-01-10: Initial draft (Alice Johnson)
- 2025-01-12: Updated cost analysis with DynamoDB costs (Bob Smith)
- 2025-01-15: Accepted after architecture review (Alice Johnson)
