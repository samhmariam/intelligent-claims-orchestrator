# OpenTelemetry Instrumentation Guide for ICPA

## Overview

This guide explains how to implement OpenTelemetry (OTel) instrumentation across the Intelligent Claims Processing Agent (ICPA) to achieve end-to-end distributed tracing and observability.

**Why OpenTelemetry?**
- **Vendor Neutrality:** Works with AWS X-Ray, CloudWatch, and third-party tools
- **Auto-Instrumentation:** Minimal code changes for Lambda, HTTP clients, AWS SDK
- **Context Propagation:** Traces flow across Step Functions → Lambda → Bedrock → DynamoDB
- **Structured Logging:** Correlate logs with traces using `trace_id` and `span_id`

---

## Architecture: Tracing Flow

```
API Gateway (trace_id generated)
    ↓
Step Functions (propagates trace context)
    ↓
Lambda: DocumentProcessor (creates span)
    ↓ (calls AWS SDK with trace context)
S3 PutObject (segment recorded)
    ↓
Lambda: TextractHandler (creates span)
    ↓
Textract AnalyzeDocument (segment recorded)
    ↓
Lambda: FraudAgentWrapper (creates span)
    ↓
Bedrock InvokeAgent (segment recorded)
    ↓
DynamoDB PutItem (segment recorded)
```

**Key Concept:** Each AWS service creates a **segment** (parent span), and each Lambda function creates **subsegments** (child spans). OpenTelemetry auto-instrumentation handles context propagation.

---

## Implementation Guide

### 1. Install AWS Distro for OpenTelemetry (ADOT)

**For Lambda Functions:**

Use the **ADOT Lambda Layer** (managed by AWS):

```python
# In Terraform/CloudFormation, add layer to Lambda function
resource "aws_lambda_function" "fraud_agent_wrapper" {
  function_name = "FraudAgentWrapper"
  runtime       = "python3.11"
  handler       = "index.handler"
  
  layers = [
    # ADOT Python Lambda Layer (us-east-1)
    "arn:aws:lambda:us-east-1:901920570463:layer:aws-otel-python-amd64-ver-1-20-0:3"
  ]
  
  environment {
    variables = {
      AWS_LAMBDA_EXEC_WRAPPER = "/opt/otel-instrument"
      OTEL_SERVICE_NAME       = "fraud-agent-wrapper"
      OTEL_TRACES_SAMPLER     = "xray"  # Use X-Ray sampling rules
      OTEL_PROPAGATORS        = "xray"  # AWS X-Ray trace context format
      OTEL_EXPORTER_OTLP_PROTOCOL = "http/protobuf"
    }
  }
}
```

**Layer ARNs by Region:**
- `us-east-1`: `arn:aws:lambda:us-east-1:901920570463:layer:aws-otel-python-amd64-ver-1-20-0:3`
- `us-west-2`: `arn:aws:lambda:us-west-2:901920570463:layer:aws-otel-python-amd64-ver-1-20-0:3`

Latest versions: [AWS OTel Lambda Layers](https://aws-otel.github.io/docs/getting-started/lambda/lambda-python)

### 2. Configure Environment Variables

**Required for All Lambda Functions:**

```bash
# Enable ADOT auto-instrumentation wrapper
AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument

# Service name (appears in X-Ray Service Map)
OTEL_SERVICE_NAME=fraud-agent-wrapper

# Use AWS X-Ray as the tracing backend
OTEL_TRACES_SAMPLER=xray
OTEL_PROPAGATORS=xray

# Sampling rules (defined in X-Ray console)
# - 100% of HITL claims
# - 10% of standard claims
# - 5% default sampling
```

**Optional (for debugging):**

```bash
# Log level for ADOT instrumentation
OTEL_LOG_LEVEL=INFO  # Options: DEBUG, INFO, WARN, ERROR

# Disable specific auto-instrumentations (if needed)
OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=urllib3,requests
```

### 3. Manual Instrumentation (Custom Spans)

**For Business Logic Spans:**

```python
import boto3
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

# Get the current tracer
tracer = trace.get_tracer(__name__)

def handler(event, context):
    # Auto-instrumented by ADOT layer (Lambda invocation span)
    
    claim_id = event.get('claim_id')
    
    # Create custom span for business logic
    with tracer.start_as_current_span("parse_claim_summary") as span:
        # Add structured attributes
        span.set_attribute("claim.id", claim_id)
        span.set_attribute("claim.amount", event.get('claim_amount'))
        span.set_attribute("claim.policy_state", event.get('policy_state'))
        
        try:
            summary_text = parse_summary(event)
            span.set_attribute("summary.length", len(summary_text))
            
        except Exception as e:
            # Record exception in span
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
    
    # Call Bedrock (auto-instrumented by ADOT)
    with tracer.start_as_current_span("invoke_bedrock_agent") as span:
        span.set_attribute("agent.type", "FRAUD")
        span.set_attribute("model.id", "anthropic.claude-3-sonnet-v1:0")
        
        bedrock = boto3.client('bedrock-agent-runtime')
        response = bedrock.invoke_agent(
            agentId=FRAUD_AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=claim_id,
            inputText=summary_text
        )
        
        # Extract result (auto-creates subsegment for boto3 call)
        agent_result = parse_agent_response(response)
        
        span.set_attribute("agent.decision", agent_result['decision'])
        span.set_attribute("agent.confidence", agent_result['confidence_score'])
        span.set_attribute("agent.fraud_score", agent_result.get('fraud_score', 0))
    
    return agent_result


def parse_summary(event):
    """Parse claim summary from event."""
    # Business logic here
    return event.get('claim_summary', {}).get('claim_summary_text', '')


def parse_agent_response(response):
    """Parse Bedrock agent response into AgentResult schema."""
    # Extract completion from streaming response
    completion_text = ""
    for event in response['completion']:
        if 'chunk' in event:
            chunk = event['chunk']
            if 'bytes' in chunk:
                completion_text += chunk['bytes'].decode('utf-8')
    
    # Parse JSON from completion
    import json
    return json.loads(completion_text)
```

### 4. Structured Logging with Trace Context

**Correlate Logs with Traces:**

```python
import logging
import json
from opentelemetry import trace

# Configure structured JSON logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    # Get current span context
    current_span = trace.get_current_span()
    span_context = current_span.get_span_context()
    
    # Extract trace_id and span_id
    trace_id = format(span_context.trace_id, '032x')  # 32-char hex
    span_id = format(span_context.span_id, '016x')    # 16-char hex
    
    # Log with structured format (CloudWatch Logs Insights compatible)
    log_entry = {
        "timestamp": context.request_id,
        "level": "INFO",
        "message": "Processing claim",
        "claim_id": event.get('claim_id'),
        "trace_id": trace_id,
        "span_id": span_id,
        "correlation_id": event.get('correlation_id'),
        "function_name": context.function_name,
        "function_version": context.function_version,
        "memory_limit_mb": context.memory_limit_in_mb,
        "request_id": context.request_id
    }
    
    logger.info(json.dumps(log_entry))
    
    # CloudWatch Logs Insights query to find related logs:
    # fields @timestamp, message, claim_id
    # | filter trace_id = "abc123..."
    # | sort @timestamp desc
```

### 5. Custom Metrics via Embedded Metric Format (EMF)

**Publish CloudWatch Metrics from Logs:**

```python
import json

def publish_metrics(claim_id, agent_type, latency_ms, decision):
    """Publish custom metrics using EMF (no boto3 calls required)."""
    
    # EMF log entry (automatically parsed by CloudWatch)
    emf_log = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": "ICPA/Production",
                    "Dimensions": [["AgentType", "Decision"]],
                    "Metrics": [
                        {"Name": "AgentLatency", "Unit": "Milliseconds"},
                        {"Name": "ClaimProcessed", "Unit": "Count"}
                    ]
                }
            ]
        },
        "AgentType": agent_type,
        "Decision": decision,
        "AgentLatency": latency_ms,
        "ClaimProcessed": 1,
        "claim_id": claim_id
    }
    
    # Print to stdout (CloudWatch agent ingests as metric)
    print(json.dumps(emf_log))
```

### 6. X-Ray Sampling Rules

**Configure in X-Ray Console:**

```json
{
  "version": 2,
  "rules": [
    {
      "description": "Trace all HITL claims (high value)",
      "service_name": "*",
      "http_method": "*",
      "url_path": "*",
      "fixed_rate": 1.0,
      "reservoir_size": 100,
      "priority": 1,
      "attributes": {
        "decision": ["HITL"]
      }
    },
    {
      "description": "Trace all fraud score > 0.70",
      "service_name": "fraud-agent-wrapper",
      "http_method": "*",
      "url_path": "*",
      "fixed_rate": 1.0,
      "reservoir_size": 50,
      "priority": 2,
      "attributes": {
        "fraud_score": [{"numeric": [">=", 0.70]}]
      }
    },
    {
      "description": "Sample 10% of normal claims",
      "service_name": "*",
      "http_method": "*",
      "url_path": "*",
      "fixed_rate": 0.1,
      "reservoir_size": 10,
      "priority": 100
    }
  ],
  "default": {
    "fixed_rate": 0.05,
    "reservoir_size": 1
  }
}
```

### 7. X-Ray Trace Annotations (Required Fields)

**Standard Annotations for All Traces:**

```python
from aws_xray_sdk.core import xray_recorder

# Add annotations (indexed, searchable in X-Ray console)
xray_recorder.put_annotation("claim_id", claim_id)
xray_recorder.put_annotation("policy_number", policy_number)
xray_recorder.put_annotation("agent_type", "FRAUD")
xray_recorder.put_annotation("decision", "APPROVE")
xray_recorder.put_annotation("model_id", "anthropic.claude-3-sonnet-v1:0")

# Add metadata (not indexed, for context only)
xray_recorder.put_metadata("claim_amount", 1500.00)
xray_recorder.put_metadata("fraud_score", 0.23)
xray_recorder.put_metadata("payout_amount", 1425.00)
xray_recorder.put_metadata("document_count", 3)
```

**Required Annotations (per PRD Section 7.6.3):**
- `claim_id` (UUID)
- `policy_number` (String)
- `agent_type` (Enum: FRAUD, ADJUDICATION, ROUTER)
- `model_id` (String: e.g., anthropic.claude-3-sonnet-v1:0)
- `decision` (Enum: APPROVE, DENY, HITL, BLOCKED)
- `cost_estimate_usd` (Float)

---

## Querying Traces

### CloudWatch Logs Insights

**Find all logs for a specific claim:**

```sql
fields @timestamp, @message, level, trace_id, span_id
| filter claim_id = "abc-123-def-456"
| sort @timestamp desc
| limit 100
```

**Find errors with trace context:**

```sql
fields @timestamp, @message, trace_id, function_name
| filter level = "ERROR"
| stats count() by trace_id
| sort count desc
```

### X-Ray Console

**Find traces with high fraud scores:**

```
annotation.fraud_score >= 0.70
```

**Find traces routed to HITL:**

```
annotation.decision = "HITL"
```

**Find slow traces (> 120s):**

```
responsetime > 120
```

---

## Testing OpenTelemetry Setup

### 1. Unit Test with Mock Tracer

```python
import unittest
from unittest.mock import Mock, patch
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

class TestTracingIntegration(unittest.TestCase):
    def setUp(self):
        # Create in-memory exporter for testing
        self.exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        trace.set_tracer_provider(provider)
    
    def test_claim_processing_creates_spans(self):
        # Import your handler
        from fraud_agent_wrapper import handler
        
        # Invoke handler with test event
        event = {
            "claim_id": "test-123",
            "claim_amount": 1500.00,
            "claim_summary": {"claim_summary_text": "Test claim"}
        }
        context = Mock()
        
        handler(event, context)
        
        # Verify spans were created
        spans = self.exporter.get_finished_spans()
        self.assertGreater(len(spans), 0)
        
        # Verify required attributes
        root_span = spans[0]
        self.assertEqual(root_span.attributes.get("claim.id"), "test-123")
        self.assertEqual(root_span.attributes.get("agent.type"), "FRAUD")
```

### 2. Integration Test with X-Ray

```python
import boto3
import time
from aws_xray_sdk.core import xray_recorder

def test_end_to_end_trace():
    """Submit a test claim and verify trace appears in X-Ray."""
    
    # Start trace
    xray_recorder.begin_segment('test-claim-submission')
    
    try:
        # Invoke Step Functions
        sfn = boto3.client('stepfunctions')
        response = sfn.start_execution(
            stateMachineArn='arn:aws:states:us-east-1:123456789012:stateMachine:ICPA-Workflow',
            input='{"claim_id": "test-e2e-123", "claim_amount": 500.00}'
        )
        
        execution_arn = response['executionArn']
        trace_id = xray_recorder.current_segment().trace_id
        
        print(f"Execution ARN: {execution_arn}")
        print(f"Trace ID: {trace_id}")
        
        # Wait for execution to complete (max 2 minutes)
        for _ in range(24):  # 24 * 5s = 120s
            time.sleep(5)
            status = sfn.describe_execution(executionArn=execution_arn)
            if status['status'] in ['SUCCEEDED', 'FAILED']:
                break
        
        # Query X-Ray for trace
        xray = boto3.client('xray')
        time.sleep(10)  # Wait for X-Ray indexing
        
        traces = xray.get_trace_summaries(
            StartTime=time.time() - 300,  # Last 5 minutes
            EndTime=time.time(),
            FilterExpression=f'annotation.claim_id = "test-e2e-123"'
        )
        
        assert len(traces['TraceSummaries']) > 0, "Trace not found in X-Ray"
        print(f"✅ Trace found: {traces['TraceSummaries'][0]['Id']}")
        
    finally:
        xray_recorder.end_segment()
```

---

## Cost Considerations

**X-Ray Pricing (as of 2025):**
- **Trace Recording:** $5 per 1 million traces recorded
- **Trace Retrieval:** $0.50 per 1 million traces retrieved
- **Trace Scan:** $0.50 per 1 million traces scanned

**Estimated Monthly Cost for ICPA:**
- 2.16M claims/month × 10% sampling = 216K traces recorded = **$1.08/month**
- 100K trace retrievals (for debugging) = **$0.05/month**
- **Total: ~$1.13/month** (negligible compared to $432/month Step Functions cost)

**Cost Optimization:**
- Use sampling rules (10% for normal claims, 100% for HITL)
- Disable tracing in non-prod environments if not needed
- Set X-Ray trace retention to 30 days (default; sufficient for most debugging)

---

## Troubleshooting

### Issue: Traces Not Appearing in X-Ray

**Symptoms:** Lambda executes successfully but no traces in X-Ray console.

**Checklist:**
- [ ] ADOT Lambda layer added to function
- [ ] `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument` environment variable set
- [ ] Lambda execution role has `xray:PutTraceSegments` and `xray:PutTelemetryRecords` permissions
- [ ] VPC endpoint for X-Ray exists (if Lambda in VPC): `com.amazonaws.us-east-1.xray`
- [ ] Wait 30 seconds after execution (X-Ray indexing delay)

**Debug Steps:**
1. Check CloudWatch Logs for ADOT errors: `fields @message | filter @message like /otel/`
2. Verify IAM permissions: `aws iam simulate-principal-policy --policy-source-arn <role-arn> --action-names xray:PutTraceSegments`
3. Test X-Ray connectivity: `aws xray put-trace-segments --trace-segment-documents '[{"trace_id": "1-..."}]'`

### Issue: Broken Trace Chain (Gaps in Service Map)

**Symptoms:** Some services appear disconnected in X-Ray Service Map.

**Root Cause:** Trace context not propagated between services.

**Fix:**
- Ensure `OTEL_PROPAGATORS=xray` for all Lambda functions
- For Step Functions: enable X-Ray tracing on state machine (`"TracingConfiguration": {"Enabled": true}`)
- For HTTP calls: pass `X-Amzn-Trace-Id` header manually if client library doesn't auto-propagate

```python
import requests
from aws_xray_sdk.core import xray_recorder

# Get current trace context
trace_id = xray_recorder.current_segment().trace_id
parent_id = xray_recorder.current_segment().id

# Add to HTTP headers
headers = {
    "X-Amzn-Trace-Id": f"Root={trace_id};Parent={parent_id};Sampled=1"
}

response = requests.post("https://api.example.com/endpoint", headers=headers)
```

---

## References

- [AWS Distro for OpenTelemetry (ADOT) Documentation](https://aws-otel.github.io/)
- [ADOT Lambda Layers](https://aws-otel.github.io/docs/getting-started/lambda)
- [X-Ray Developer Guide](https://docs.aws.amazon.com/xray/latest/devguide/)
- [CloudWatch Embedded Metric Format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html)
- [PRD Section 7.6.3: X-Ray Tracing Requirements](../prd.md#763-x-ray-tracing-requirements)
