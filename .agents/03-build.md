# Build Agent

## Role
**Data Scientist (AWS-only):** Implements and tunes ML workflows, prompt/model evaluation, and integrations with AWS AI services; ensures model-related pipelines run on AWS only.

## Purpose
Implement features end-to-end following the approved design, including code, configuration, and documentation updates.

## When to Use
- After design approval
- For refactors or new components

## Inputs
- Design artifacts
- Existing codebase patterns
- Required tests and acceptance criteria

## Outputs
- Code changes with minimal diffs
- Updated configs/migrations
- Developer-facing docs or notes
- Implemented retry/backoff and error taxonomy handling
- Implemented prompt/model versioning hooks
- **OpenTelemetry instrumentation for observability**

## Guardrails
- Follow repo conventions and existing patterns.
- Prefer small, reversible changes.
- Add tests alongside code when feasible.
- Enforce data-retention and lifecycle policies in storage paths.
- **Instrument all Lambda functions with ADOT (AWS Distro for OpenTelemetry).**

## Checklist
- [ ] Implemented changes per design
- [ ] Updated configuration and wiring
- [ ] Added or updated tests
- [ ] Ensured backwards compatibility where required
- [ ] **Added OpenTelemetry tracing with required annotations**
- [ ] **Implemented structured logging with trace_id correlation**

---

## Code Quality Gates

### Mandatory Checks (Block PR Merge)
- [ ] **Pylint score ≥ 8.0** (run: `pylint src/ --fail-under=8.0`)
- [ ] **Type hints on all public functions** (run: `mypy src/ --strict`)
- [ ] **No hardcoded secrets** (scan: `git-secrets --scan` or `trufflehog`)
- [ ] **Unit test coverage ≥ 85%** (run: `pytest --cov=src --cov-report=term --cov-fail-under=85`)
- [ ] **Security scan passes** (run: `bandit -r src/` for Python, `checkov` for IaC)

### Code Style
- **Logging:** Use structured JSON format (CloudWatch Logs Insights compatible)
  ```python
  import json
  import logging
  
  logger = logging.getLogger()
  logger.setLevel(logging.INFO)
  
  def log_structured(level, message, **kwargs):
      log_entry = {
          "timestamp": datetime.utcnow().isoformat(),
          "level": level,
          "message": message,
          **kwargs
      }
      logger.log(getattr(logging, level), json.dumps(log_entry))
  
  # Usage
  log_structured("INFO", "Processing claim", claim_id="abc-123", agent_type="FRAUD")
  ```

- **Error Messages:** Always include `claim_id` and `correlation_id`
  ```python
  raise ValueError(
      f"Invalid claim schema for claim_id={claim_id}, "
      f"correlation_id={correlation_id}: {validation_error}"
  )
  ```

- **Constants:** Use UPPER_CASE for constants, define in `src/constants.py`
  ```python
  # src/constants.py
  FRAUD_SCORE_THRESHOLD = 0.70
  HITL_CLAIM_AMOUNT_THRESHOLD = 10000.00
  BEDROCK_MAX_RETRIES = 3
  BEDROCK_RETRY_BACKOFF_MULTIPLIER = 2.0
  ```

---

## Prompt Versioning

### Storage in SSM Parameter Store

All prompts MUST be stored in AWS Systems Manager Parameter Store with semantic versioning.

**Naming Convention:**
```
/icpa/prompts/{agent_name}/v{MAJOR}.{MINOR}.{PATCH}
```

**Example:**
```bash
# Fraud Agent prompt v1.2.3
aws ssm put-parameter \
  --name "/icpa/prompts/fraud_agent/v1.2.3" \
  --value "You are a fraud detection agent..." \
  --type "String" \
  --description "Fraud agent prompt with updated CoT instructions" \
  --tags "Key=Version,Value=1.2.3" "Key=Agent,Value=FraudAgent"

# Create alias pointing to latest
aws ssm put-parameter \
  --name "/icpa/prompts/fraud_agent/latest" \
  --value "v1.2.3" \
  --type "String" \
  --overwrite
```

### Lambda Retrieval Pattern

```python
import boto3
import os

ssm = boto3.client('ssm')

def get_prompt(agent_name: str, version: str = "latest") -> str:
    """Retrieve prompt from SSM Parameter Store.
    
    Args:
        agent_name: e.g., "fraud_agent", "adjudication_agent"
        version: Semantic version (e.g., "v1.2.3") or "latest"
    
    Returns:
        Prompt text as string
    
    Raises:
        ParameterNotFound: If prompt version doesn't exist
    """
    if version == "latest":
        # First, resolve latest pointer
        latest_param = f"/icpa/prompts/{agent_name}/latest"
        response = ssm.get_parameter(Name=latest_param)
        resolved_version = response['Parameter']['Value']
        param_name = f"/icpa/prompts/{agent_name}/{resolved_version}"
    else:
        param_name = f"/icpa/prompts/{agent_name}/{version}"
    
    response = ssm.get_parameter(Name=param_name, WithDecryption=False)
    return response['Parameter']['Value']


# Usage in Lambda
AGENT_NAME = os.environ.get('AGENT_NAME', 'fraud_agent')
PROMPT_VERSION = os.environ.get('PROMPT_VERSION', 'latest')

def handler(event, context):
    prompt = get_prompt(AGENT_NAME, PROMPT_VERSION)
    # Use prompt for Bedrock InvokeAgent or InvokeModel
    ...
```

### Semantic Versioning Rules

- **MAJOR:** Instruction format change (e.g., tool schema update, output format change)
  - Example: `v1.0.0` → `v2.0.0` (changed from JSON output to XML)
  - **Requires:** Golden set re-evaluation and approval from Review Agent

- **MINOR:** Phrasing change affecting outputs (e.g., added CoT instructions, new examples)
  - Example: `v1.2.3` → `v1.3.0` (added "explain your reasoning step-by-step")
  - **Requires:** A/B test with 10% traffic for 7 days

- **PATCH:** Typo fix or clarification (no expected behavior change)
  - Example: `v1.2.3` → `v1.2.4` (fixed spelling error in example)
  - **Requires:** Code review only (no re-evaluation needed)

---

## OpenTelemetry Instrumentation

### Required Setup for All Lambda Functions

**1. Add ADOT Lambda Layer**

In your IaC (Terraform/CloudFormation):

```hcl
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
      OTEL_TRACES_SAMPLER     = "xray"
      OTEL_PROPAGATORS        = "xray"
    }
  }
}
```

**2. Add Required IAM Permissions**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords"
      ],
      "Resource": "*"
    }
  ]
}
```

**3. Create Custom Spans for Business Logic**

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def handler(event, context):
    claim_id = event.get('claim_id')
    
    # Create custom span
    with tracer.start_as_current_span("parse_claim_summary") as span:
        # Add required annotations (per PRD Section 7.6.3)
        span.set_attribute("claim.id", claim_id)
        span.set_attribute("claim.amount", event.get('claim_amount'))
        span.set_attribute("claim.policy_state", event.get('policy_state'))
        
        summary_text = parse_summary(event)
        span.set_attribute("summary.length", len(summary_text))
    
    # Call Bedrock (auto-instrumented)
    with tracer.start_as_current_span("invoke_bedrock_agent") as span:
        span.set_attribute("agent.type", "FRAUD")
        span.set_attribute("model.id", "anthropic.claude-3-sonnet-v1:0")
        
        result = invoke_bedrock(claim_id, summary_text)
        
        span.set_attribute("agent.decision", result['decision'])
        span.set_attribute("agent.confidence", result['confidence_score'])
    
    return result
```

**4. Correlate Logs with Traces**

```python
import logging
import json
from opentelemetry import trace

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    current_span = trace.get_current_span()
    span_context = current_span.get_span_context()
    
    trace_id = format(span_context.trace_id, '032x')
    span_id = format(span_context.span_id, '016x')
    
    # Log with trace context
    log_entry = {
        "timestamp": context.request_id,
        "level": "INFO",
        "message": "Processing claim",
        "claim_id": event.get('claim_id'),
        "trace_id": trace_id,
        "span_id": span_id,
        "function_name": context.function_name
    }
    
    logger.info(json.dumps(log_entry))
```

**📖 Full Guide:** [docs/observability/opentelemetry-guide.md](../docs/observability/opentelemetry-guide.md)

---

## Model Versioning

### Bedrock Model ID Pinning

**NEVER use wildcards or "latest" tags in production.**

**❌ Bad (unpredictable behavior):**
```python
model_id = "anthropic.claude-3-sonnet"  # Resolves to latest version
```

**✅ Good (explicit version):**
```python
model_id = "anthropic.claude-3-sonnet-20240229-v1:0"  # Pinned to specific release
```

### Model Version Management

Store model IDs in SSM Parameter Store:

```bash
aws ssm put-parameter \
  --name "/icpa/models/fraud_agent/model_id" \
  --value "anthropic.claude-3-sonnet-20240229-v1:0" \
  --type "String" \
  --description "Fraud agent Bedrock model ID"
```

Lambda retrieval:

```python
def get_model_id(agent_name: str) -> str:
    param_name = f"/icpa/models/{agent_name}/model_id"
    response = ssm.get_parameter(Name=param_name)
    return response['Parameter']['Value']
```

### Model Upgrade Process

1. **Proposal:** Tech Lead proposes new model version in ADR
2. **A/B Test:** Route 10% of claims to new model for 7 days
3. **Evaluation:** Compare DecisionAccuracy, latency, cost on golden set
4. **Approval:** If metrics neutral or better, Review Agent approves
5. **Deployment:** Update SSM parameter, redeploy Lambda (no code change)
6. **Rollback Plan:** Keep prior model ID in `/icpa/models/{agent_name}/previous`

---

## Error Handling & Retry Logic

### Error Taxonomy (per PRD Section 7.2)

Classify all errors into these categories:

| Error Category | Examples | Retry Policy |
|----------------|----------|--------------|
| `TRANSIENT` | Network timeout, S3 eventual consistency | 3 retries, exponential backoff (2s, 4s, 8s) |
| `THROTTLE` | Bedrock `ThrottlingException`, DynamoDB throttle | 3 retries, exponential backoff with jitter |
| `INVALID_INPUT` | Schema validation failure, malformed JSON | No retry; move to quarantine, emit failure event |
| `ACCESS_DENIED` | IAM permission error, KMS key access denied | No retry; alert security team |
| `INTERNAL` | Bedrock parse error, unexpected exception | 1 retry; if fails → HITL |

### Implementation Pattern

```python
import time
import random
from botocore.exceptions import ClientError

def invoke_with_retry(func, max_retries=3, base_delay=2.0, error_categories=None):
    """Generic retry wrapper with exponential backoff and jitter.
    
    Args:
        func: Callable to invoke
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        error_categories: Dict mapping error codes to categories
    
    Returns:
        Function result
    
    Raises:
        Exception if all retries exhausted
    """
    error_categories = error_categories or {
        "ThrottlingException": "THROTTLE",
        "TooManyRequestsException": "THROTTLE",
        "ServiceUnavailable": "TRANSIENT"
    }
    
    for attempt in range(max_retries + 1):
        try:
            return func()
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_category = error_categories.get(error_code, "INTERNAL")
            
            if error_category in ["INVALID_INPUT", "ACCESS_DENIED"]:
                # No retry for these categories
                raise
            
            if attempt == max_retries:
                # Exhausted retries
                raise
            
            # Calculate backoff with jitter
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(
                f"Retry attempt {attempt + 1}/{max_retries} after {delay:.2f}s "
                f"for error {error_code} (category: {error_category})"
            )
            time.sleep(delay)
    
    raise Exception("Unreachable code")


# Usage
result = invoke_with_retry(
    lambda: bedrock_client.invoke_agent(
        agentId=FRAUD_AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=claim_id,
        inputText=summary_text
    ),
    max_retries=3,
    base_delay=2.0
)
```

**Note:** Step Functions also has retry configuration (prefer that for Lambda tasks).

---

## Data Retention & Lifecycle

### S3 Lifecycle Policies

**Enforce in IaC (Terraform example):**

```hcl
resource "aws_s3_bucket_lifecycle_configuration" "clean_bucket" {
  bucket = aws_s3_bucket.clean_bucket.id
  
  rule {
    id     = "delete-after-180-days"
    status = "Enabled"
    
    expiration {
      days = 180
    }
    
    # Only apply to closed claims
    filter {
      tag {
        key   = "status"
        value = "CLOSED"
      }
    }
  }
}
```

**Lambda tagging pattern:**

```python
def tag_claim_closed(claim_id: str):
    """Tag all S3 objects for a closed claim."""
    s3 = boto3.client('s3')
    
    # List all objects for claim
    prefix = f"{claim_id}/"
    response = s3.list_objects_v2(Bucket=CLEAN_BUCKET, Prefix=prefix)
    
    for obj in response.get('Contents', []):
        s3.put_object_tagging(
            Bucket=CLEAN_BUCKET,
            Key=obj['Key'],
            Tagging={'TagSet': [{'Key': 'status', 'Value': 'CLOSED'}]}
        )
```

### DynamoDB TTL

**Enable TTL in IaC:**

```hcl
resource "aws_dynamodb_table" "icpa_claims" {
  name           = "ICPA_Claims"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "PK"
  range_key      = "SK"
  
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
  
  attribute {
    name = "PK"
    type = "S"
  }
  
  attribute {
    name = "SK"
    type = "S"
  }
}
```

**Set TTL in Lambda:**

```python
import time

def write_claim_to_dynamo(claim_id: str, claim_data: dict):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('ICPA_Claims')
    
    # Set TTL to 365 days from now
    ttl = int(time.time()) + (365 * 24 * 60 * 60)
    
    item = {
        'PK': f'CLAIM#{claim_id}',
        'SK': 'META',
        'ttl': ttl,  # DynamoDB will auto-delete after this timestamp
        **claim_data
    }
    
    table.put_item(Item=item)
```

