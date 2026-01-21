# Task 3.2: Implement data security and privacy controls

## Scenario

Build a secure document analysis system that:

- Extracts information from financial documents.
- Detects and masks PII/sensitive information.
- Uses Amazon Bedrock to analyze and summarize documents.
- Implements comprehensive security controls.
- Provides monitoring and auditing capabilities.

## Prerequisites

- AWS account with appropriate permissions.
- Knowledge of AWS services.
- Familiarity with Python programming.
- Understanding of security concepts.

## Part 1: Setting up a protected environment

**Objective:** Create a secure network environment for your Amazon Bedrock deployment.

**Tasks:**
- Create a VPC with private and public subnets.
- Set up VPC endpoints for Amazon Bedrock and related services.
- Configure security groups and network ACLs.
- Create IAM roles and policies with least privilege permissions.
- Implement CloudWatch monitoring for API calls and data access.

**Sample code: Create a VPC endpoint for Amazon Bedrock**

```python
import boto3
from botocore.exceptions import ClientError

def create_bedrock_vpc_endpoint(vpc_id, subnet_ids, security_group_ids):
    ec2_client = boto3.client("ec2")

    try:
        response = ec2_client.create_vpc_endpoint(
            VpcEndpointType="Interface",
            VpcId=vpc_id,
            ServiceName="com.amazonaws.us-east-1.bedrock-runtime",
            SubnetIds=subnet_ids,
            SecurityGroupIds=security_group_ids,
            PrivateDnsEnabled=True,
        )
        print(f"VPC Endpoint created: {response['VpcEndpoint']['VpcEndpointId']}")
        return response["VpcEndpoint"]["VpcEndpointId"]
    except ClientError as e:
        print(f"Error creating VPC endpoint: {e}")
        return None
```

## Part 2: Implement data privacy controls

**Objective:** Develop mechanisms to detect and protect sensitive information.

**Tasks:**
- Set up Amazon Comprehend for PII detection.
- Configure Amazon Macie to scan S3 buckets for sensitive data.
- Implement S3 Lifecycle policies for data retention.
- Create data masking functions for sensitive information.
- Set up encryption for data at rest and in transit.

**Sample code: PII detection and masking with Amazon Comprehend**

```python
import boto3

def detect_pii(text):
    comprehend = boto3.client("comprehend")

    try:
        response = comprehend.detect_pii_entities(Text=text, LanguageCode="en")
        pii_entities = response["Entities"]
        print(f"Found {len(pii_entities)} PII entities")
        return pii_entities
    except Exception as e:
        print(f"Error detecting PII: {e}")
        return []

def mask_pii(text, pii_entities):
    masked_text = text
    sorted_entities = sorted(pii_entities, key=lambda x: x["BeginOffset"], reverse=True)

    for entity in sorted_entities:
        begin = entity["BeginOffset"]
        end = entity["EndOffset"]
        entity_type = entity["Type"]
        masked_text = masked_text[:begin] + f"[{entity_type}]" + masked_text[end:]

    return masked_text
```

## Part 3: Configure Amazon Bedrock Guardrails

**Objective:** Set up and configure Amazon Bedrock Guardrails to enforce security policies.

**Tasks:**
- Create a guardrails policy with content filtering.
- Configure denied topics for financial advice and legal advice.
- Set up sensitive information filters.
- Implement word filters for specific terms.
- Test and refine guardrails in monitor mode before enforcement.

**Sample code: Create and apply Bedrock Guardrails**

```python
import boto3
import json

def create_bedrock_guardrail():
    bedrock = boto3.client("bedrock")

    guardrail_config = {
        "name": "FinancialDocumentGuardrail",
        "description": "Guardrail for financial document processing",
        "contentPolicy": {
            "filters": [
                {
                    "type": "SENSITIVE_INFORMATION",
                    "config": {
                        "piiEntities": ["SSN", "CREDIT_CARD", "BANK_ACCOUNT_NUMBER"],
                    },
                },
                {
                    "type": "CONTENT",
                    "config": {
                        "contentTypes": ["HATE_SPEECH", "INSULTS", "SEXUAL"],
                    },
                },
            ],
            "deniedTopics": [
                {
                    "name": "Financial_Advice",
                    "definition": "Providing specific financial investment advice",
                    "examples": ["You should invest in", "Buy this stock"],
                }
            ],
        },
    }

    try:
        response = bedrock.create_guardrail(guardrailConfig=json.dumps(guardrail_config))
        print(f"Guardrail created: {response['guardrailId']}")
        return response["guardrailId"]
    except Exception as e:
        print(f"Error creating guardrail: {e}")
        return None

def apply_guardrail_to_model(guardrail_id, model_id):
    bedrock = boto3.client("bedrock-runtime")

    try:
        response = bedrock.invoke_model_with_response_stream(
            modelId=model_id,
            body=json.dumps({
                "prompt": "Analyze this financial document",
                "max_tokens": 500,
            }),
            contentType="application/json",
            accept="application/json",
            guardrailConfig={
                "guardrailId": guardrail_id,
                "guardrailVersion": "DRAFT",
            },
        )
        return response
    except Exception as e:
        print(f"Error applying guardrail: {e}")
        return None
```

## Part 4: Implement secure document processing

**Objective:** Create a secure pipeline for document processing with Amazon Bedrock.

**Tasks:**
- Set up S3 buckets with appropriate security controls.
- Create Lambda functions for document processing with VPC configuration.
- Implement PII detection and masking before model invocation.
- Configure Amazon Bedrock for secure document analysis.
- Implement post-processing to ensure no sensitive data is exposed.

**Sample code: Secure document processing Lambda**

```python
import boto3
import json
import os
from urllib.parse import unquote_plus

def lambda_handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        s3_client = boto3.client("s3")
        download_path = f"/tmp/{os.path.basename(key)}"
        s3_client.download_file(bucket, key, download_path)

        with open(download_path, "r") as file:
            document_text = file.read()

        comprehend = boto3.client("comprehend")
        pii_response = comprehend.detect_pii_entities(Text=document_text, LanguageCode="en")

        masked_text = document_text
        for entity in sorted(pii_response["Entities"], key=lambda x: x["BeginOffset"], reverse=True):
            begin = entity["BeginOffset"]
            end = entity["EndOffset"]
            entity_type = entity["Type"]
            masked_text = masked_text[:begin] + f"[{entity_type}]" + masked_text[end:]

        bedrock = boto3.client("bedrock-runtime")
        guardrail_id = os.environ["GUARDRAIL_ID"]

        response = bedrock.invoke_model(
            modelId="anthropic.claude-v2",
            body=json.dumps({
                "prompt": f"Analyze this financial document and provide a summary: {masked_text}",
                "max_tokens": 1000,
            }),
            contentType="application/json",
            accept="application/json",
            guardrailConfig={
                "guardrailId": guardrail_id,
                "guardrailVersion": "DRAFT",
            },
        )

        bedrock_response = json.loads(response["body"].read())

        result_key = f"processed/{os.path.basename(key)}.json"
        s3_client.put_object(
            Bucket=bucket,
            Key=result_key,
            Body=json.dumps({
                "summary": bedrock_response["completion"],
                "processingMetadata": {
                    "piiDetected": len(pii_response["Entities"]) > 0,
                    "guardrailApplied": True,
                },
            }),
            ServerSideEncryption="aws:kms",
            SSEKMSKeyId=os.environ["KMS_KEY_ID"],
        )

        return {
            "statusCode": 200,
            "body": json.dumps("Document processed successfully"),
        }
```

## Part 5: Set up monitoring and auditing

**Objective:** Implement comprehensive monitoring and auditing for security compliance.

**Tasks:**
- Configure CloudTrail for API activity monitoring.
- Set up CloudWatch alarms for security events.
- Create dashboards for security monitoring.
- Implement automated notifications for security incidents.
- Set up regular security audit reports.

**Sample code: CloudWatch alarms for security events**

```python
import boto3

def create_security_alarms():
    cloudwatch = boto3.client("cloudwatch")

    try:
        cloudwatch.put_metric_alarm(
            AlarmName="UnauthorizedBedrockAPIAccess",
            ComparisonOperator="GreaterThanThreshold",
            EvaluationPeriods=1,
            MetricName="AccessDenied",
            Namespace="AWS/Bedrock",
            Period=300,
            Statistic="Sum",
            Threshold=0,
            ActionsEnabled=True,
            AlarmDescription="Alarm for unauthorized access attempts to Bedrock API",
            AlarmActions=[
                "arn:aws:sns:us-east-1:123456789012:SecurityAlerts",
            ],
            Dimensions=[
                {"Name": "Service", "Value": "Bedrock"},
            ],
        )
        print("Unauthorized access alarm created")

        cloudwatch.put_metric_alarm(
            AlarmName="PIIDetectionEvents",
            ComparisonOperator="GreaterThanThreshold",
            EvaluationPeriods=1,
            MetricName="PIIEntitiesDetected",
            Namespace="Custom/DocumentProcessing",
            Period=300,
            Statistic="Sum",
            Threshold=10,
            ActionsEnabled=True,
            AlarmDescription="Alarm for high number of PII entities detected",
            AlarmActions=[
                "arn:aws:sns:us-east-1:123456789012:SecurityAlerts",
            ],
        )
        print("PII detection alarm created")
        return True
    except Exception as e:
        print(f"Error creating alarms: {e}")
        return False
```

## Deliverables

### Secure AI environment
- VPC with private subnets and VPC endpoints.
- IAM roles with least privilege permissions.
- Network security controls.

### Privacy-preserving document processing system
- PII detection and masking pipeline.
- S3 buckets with appropriate security controls.
- Data retention policies.

### Amazon Bedrock with Guardrails
- Configured guardrails for content filtering.
- Sensitive information protection.
- Secure model invocation.

### Monitoring and auditing
- CloudWatch dashboards and alarms.
- CloudTrail logs for API activity.

Security incident response procedures

Documentation:

Architecture diagram

Security controls documentation

Implementation guide

Testing results

Architecture diagram

Here's a high-level architecture diagram of the secure document processing system:


┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ Input Bucket  │────▶│  Lambda VPC   │────▶│ Output Bucket │
└───────────────┘     │  Environment   │     └───────────────┘
                      └───────┬───────┘
                              │
┌───────────────┐     ┌──────▼────────┐     ┌───────────────┐
│   Amazon      │◀───▶│    Amazon     │◀───▶│    Amazon     │
│  Comprehend   │     │    Bedrock    │     │    Macie      │
└───────────────┘     └──────┬────────┘     └───────────────┘
                              │
┌───────────────┐     ┌──────▼────────┐     ┌───────────────┐
│    Amazon     │◀───▶│    Bedrock    │     │   CloudWatch  │
│  CloudTrail   │     │   Guardrails  │────▶│   Monitoring  │
└───────────────┘     └───────────────┘     └───────────────┘
Extension activities

Implement Fine-Grained Access Control:

Use AWS Lake Formation to provide granular data access controls

Create different access levels for various user roles

Add Real-time Monitoring:

Implement real-time monitoring of PII detection events

Create automated remediation workflows for security incidents

Enhance Privacy Controls:

Implement differential privacy techniques

Add anonymization strategies beyond simple masking

Compliance Reporting:

Create automated compliance reports

Implement continuous compliance monitoring