# Runbook: Textract Empty Results

**Severity:** HIGH

## Detection
- CloudWatch metric: low or zero extracted text length
- Step Functions state `textract_result` outputs `status=EXTRACTED` with empty text
- Increased `com.icpa.ingestion.failed` events for schema errors

## Immediate Actions
1. Check Textract job status in CloudWatch logs for the extraction Lambda.
2. Verify S3 object integrity (correct key, size, and MIME type).
3. Trigger fallback to DetectDocumentText (already implemented) and reprocess the document.

## Recovery
- Re-run extraction for affected documents via a re-drive queue or manual invocation.
- If empty results persist, quarantine the document and notify HITL.

## Validation
- Confirm extracted text length > minimum threshold.
- Confirm PHI detection runs on extracted text.

## Prevention
- Validate MIME type and document integrity at ingestion.
- Add alert on repeated empty extraction for a claim_id.
