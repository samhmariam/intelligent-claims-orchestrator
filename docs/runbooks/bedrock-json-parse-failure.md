# Runbook: Bedrock Non-Parseable JSON

**Severity:** HIGH

## Detection
- Lambda wrapper throws JSON parse error for AgentResult.
- Step Functions state transitions to ErrorHandlingState.

## Immediate Actions
1. Inspect CloudWatch logs for raw completion text (redact PHI).
2. Retry with strict JSON-only prompt version from SSM.

## Recovery
- Route claim to HITL if retries fail.
- Roll back to last known-good prompt version.

## Validation
- Confirm AgentResult conforms to canonical schema.
- Confirm workflow resumes without ErrorHandlingState.

## Prevention
- Maintain schema validation in wrapper and unit tests.
- Add guardrails that enforce JSON outputs.
