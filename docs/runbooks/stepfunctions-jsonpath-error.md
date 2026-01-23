# Runbook: Step Functions JSONPath Error

**Severity:** HIGH

## Detection
- State machine execution fails with JSONPath error.
- CloudWatch logs show `States.JsonPathMatchFailure`.

## Immediate Actions
1. Inspect execution input and state definitions for missing fields.
2. Validate inputs against canonical Claim schema.

## Recovery
- Re-run execution with corrected input payload.
- Roll back to last known-good ASL if recent change introduced the error.

## Validation
- Confirm all Choice states evaluate successfully.
- Confirm no failures in ErrorHandlingState for JSONPath issues.

## Prevention
- Maintain state machine unit tests for required fields.
- Add schema validation step before state machine execution.
