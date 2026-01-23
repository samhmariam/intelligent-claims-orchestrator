# Review Report (AWS Well-Architected)

**Date:** 2026-01-23
**Phase:** REVIEW (IN_PROGRESS)

## Scope
- Requirements: [docs/prd.md](docs/prd.md)
- Design: [docs/design-architecture.md](docs/design-architecture.md)
- Code: [src/icpa](src/icpa)
- Tests: [docs/test-report.md](docs/test-report.md), [tests](tests)

## Summary
Overall alignment with the event-driven serverless design is strong, with clear ingestion/orchestration pipelines and structured observability hooks. Security, reliability, and compliance require additional AWS-native validation and IaC enforcement before release.

## Component Coverage
- **Ingestion:** PHI quarantine logic present; lifecycle policies defined but not validated in AWS.
- **Extraction:** Textract async + DetectDocumentText fallback present; empty-text handling still requires E2E validation.
- **Orchestration:** ASL choice states and guardrail routing are defined; retries present but DLQ wiring is not evidenced.

## Findings (by Severity)

### Critical
- **Release gate not met for security/PHI recall/E2E.** Test report explicitly marks release as **Fail** pending IAM least-privilege validation, PHI recall tests, and full E2E workflow. See [docs/test-report.md](docs/test-report.md).

### Warning
- **VPC endpoint enforcement not evidenced in IaC.** No stack wiring shown to bind Lambda/Step Functions/Bedrock calls to VPC endpoints or to enforce `kms:ViaService` with `aws:sourceVpce`. Requires IaC validation. Impact: compliance and data exfiltration risk.
- **Latency/cost NFR evidence missing.** Test report has no load or cost validation; P95 ≤ 120s and ≤ £0.45/claim not demonstrated. Impact: NFRs unverified.

### Advisory
- **Textract PDF fallback path uses DetectDocumentText only.** PRD suggests async → sync → detect for PDFs; Textract sync does not support PDFs. Current implementation is the correct AWS constraint; document this exception in design/test notes.
- **DecisionAccuracy check is fixture-based.** Current test uses local fixture results; needs real golden set evaluation run in AWS to confirm ≥ 90%.
- **IAM least-privilege check is partial.** Script only checks for `AdministratorAccess`; does not assert least-privilege scope. Consider IAM Access Analyzer findings and policy simulation in AWS.

## Well-Architected Alignment
- **Operational Excellence:** ADOT hooks present; requires deployment of dashboards and alarms per PRD.
- **Security:** PHI quarantine logic implemented; IAM and VPC endpoint enforcement still pending.
- **Reliability:** Step Functions retries exist; failure paths in ASL and FMEA are partially addressed, but no DLQ wiring shown.
- **Performance Efficiency:** Model tiering strategy exists (Haiku/Sonnet); no empirical latency tests.
- **Cost Optimization:** Cost controls referenced but not validated; no CloudWatch cost dashboard deployment evidence.
- **Sustainability:** Tiered model selection supports lower token usage; needs routing classifier implementation evidence.

## Required Fixes Before Deploy
1. Validate IAM least privilege for all Lambdas and Bedrock invocation roles in AWS.
2. Run PHI detection recall tests (100% on test corpus) using Comprehend Medical.
3. Execute E2E workflow in non-prod with Step Functions (happy path + FMEA failure paths).
4. Provide NFR evidence for latency/cost (load tests + cost-per-claim calc).
5. Add IaC wiring to private subnets + VPC endpoints and KMS policies.

## Recommendation
Proceed to DOCUMENT/DEPLOY only after the above items are closed with evidence recorded in the test report.

## Well-Architected Sign-off
**Status:** NOT APPROVED. Security and operational gates remain open (see Critical/Warning findings).
