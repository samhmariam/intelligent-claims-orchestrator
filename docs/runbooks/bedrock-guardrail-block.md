# Runbook: Bedrock Guardrail Block

**Severity:** HIGH

## Detection
- Step Functions choice state routes to HITL on decision `BLOCKED`.
- CloudWatch logs show guardrail block signal from Bedrock Agent Runtime.

## Immediate Actions
1. Route claim to HITL queue (already configured in state machine).
2. Capture the blocked prompt/response metadata in audit logs (no PHI in logs).

## Recovery
- Human reviewer completes adjudication and resumes workflow.
- If repeated blocks, review prompt version in SSM and adjust guardrail configuration.

## Validation
- Confirm HITL decision recorded and workflow completed.
- Confirm guardrail block rate returns to normal baseline.

## Prevention
- Tighten prompt formats to enforce JSON-only outputs.
- Add regression tests for known trigger patterns.
