# Test Report (Security, Privacy, GenAI Safety)

**Date:** 2026-01-23
**Phase:** TEST (IN_PROGRESS)

## Scope
- Security & compliance validation (IAM least privilege, lifecycle/TTL)
- GenAI safety (bias, prompt-injection handling, guardrail routing)
- Orchestration behavior (ASL checks)
- Golden set DecisionAccuracy check

## Tests Implemented (Deterministic)
- Ingestion fallback logic and PHI detection chunking (unit)
- State machine structure, retry policy, and guardrail routing (unit)
- Agent wrapper JSON parsing and prompt versioning (unit)
- GenAI safety checks (bias proxy: router ignores policy_state; prompt-injection rejection)
- Golden set DecisionAccuracy ≥ 90% (fixture-based)

## AWS-Native Validation (Manual Execution Required)
- IAM least privilege checks via [scripts/iam_least_privilege_check.py](../scripts/iam_least_privilege_check.py)
- PHI/PII detection recall tests using Comprehend Medical (requires test corpus in S3)
- End-to-end workflow run in non-prod (Step Functions + Bedrock Agents)

## Findings
- No high-risk findings detected in static unit checks.
- Guardrail decision path (BLOCKED → HITL) is defined in ASL.

## Coverage Gaps / Edge Cases
- IAM policy scope validation is environment-dependent and must be run post-deploy.
- PHI recall tests require a curated PHI corpus and live Comprehend Medical calls.
- E2E tests with real Bedrock agents are not executed in this workspace.

## Release Gate Status
- **Fail** until manual AWS-native tests are executed and recorded:
  - IAM least privilege
  - PHI detection recall (100% detection of test entities)
  - Full E2E claim lifecycle in non-prod

## Artifacts
- Unit tests: [tests](../tests)
- Fixtures: [tests/fixtures/golden_set_results.json](../tests/fixtures/golden_set_results.json)
