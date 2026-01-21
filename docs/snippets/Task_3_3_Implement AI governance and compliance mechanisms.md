# Task 3.3: Implement AI governance and compliance mechanisms

## Prerequisites

- AWS account with appropriate permissions.
- Basic knowledge of Python programming.
- Familiarity with AWS services (SageMaker, Glue, CloudWatch, etc.).
- Understanding of foundation models and generative AI concepts.

## Project architecture

Build a governance framework for a text generation application using Amazon Bedrock, with comprehensive compliance and monitoring capabilities:

```text
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Data Management    │     │  Model Governance   │     │  Monitoring & Audit │
│  ----------------   │     │  ----------------   │     │  ----------------   │
│  - AWS Glue         │────▶│  - SageMaker        │────▶│  - CloudWatch       │
│  - S3 with Metadata │     │  - Model Cards      │     │  - EventBridge      │
│  - Lake Formation   │     │  - Bedrock          │     │  - CloudTrail       │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
           │                           │                           │
           ▼                           ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Governance Dashboard (QuickSight)                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module 1: Set up data governance and lineage tracking

**Objective:** Implement comprehensive data tracking and lineage for foundation model training data.

**Tasks:**
- Create S3 buckets with metadata tagging.
- Configure AWS Glue for data lineage tracking.
- Set up AWS Lake Formation for data access control.

**Create S3 buckets with metadata tagging**

```python
import boto3
import json
from datetime import datetime

def setup_s3_buckets():
    s3_client = boto3.client('s3')
    
    try:
        bucket_name = f'fm-training-data-{boto3.client("sts").get_caller_identity()["Account"]}'
        
        s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': 'us-west-2'}
        )
        print(f"Created bucket: {bucket_name}")
        
        s3_client.put_bucket_tagging(
            Bucket=bucket_name,
            Tagging={
                'TagSet': [
                    {'Key': 'Project', 'Value': 'FM-Governance'},
                    {'Key': 'DataClassification', 'Value': 'Confidential'},
                    {'Key': 'Compliance', 'Value': 'GDPR,HIPAA'},
                    {'Key': 'Owner', 'Value': 'ml-team@example.com'},
                    {'Key': 'CostCenter', 'Value': 'ML-Research'}
                ]
            }
        )
        print(f"Applied tags to bucket: {bucket_name}")
        
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        print("Enabled versioning")
        
        s3_client.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                'Rules': [
                    {
                        'ApplyServerSideEncryptionByDefault': {
                            'SSEAlgorithm': 'aws:kms',
                            'KMSMasterKeyID': 'alias/aws/s3'
                        }
                    }
                ]
            }
        )
        print("Enabled encryption")
        
        return bucket_name
    except Exception as e:
        print(f"Error setting up S3 bucket: {e}")
        return None
```

**Configure AWS Glue for data lineage tracking**

```python
def setup_glue_lineage():
    glue_client = boto3.client('glue')
    
    try:
        database_name = 'fm_training_data'
        glue_client.create_database(
            DatabaseInput={
                'Name': database_name,
                'Description': 'Database for foundation model training data',
                'Parameters': {
                    'classification': 'training-data',
                    'project': 'fm-governance'
                }
            }
        )
        print(f"Created Glue database: {database_name}")
        
        crawler_name = 'fm-training-data-crawler'
        s3_target = f's3://fm-training-data-{boto3.client("sts").get_caller_identity()["Account"]}/training-data/'
        
        glue_client.create_crawler(
            Name=crawler_name,
            Role=f'arn:aws:iam::{boto3.client("sts").get_caller_identity()["Account"]}:role/GlueServiceRole',
            DatabaseName=database_name,
            Description='Crawler for foundation model training data',
            Targets={'S3Targets': [{'Path': s3_target}]},
            SchemaChangePolicy={
                'UpdateBehavior': 'UPDATE_IN_DATABASE',
                'DeleteBehavior': 'LOG'
            },
            LineageConfiguration={'CrawlerLineageSettings': 'ENABLE'}
        )
        print(f"Created Glue crawler: {crawler_name}")
        
        glue_client.start_crawler(Name=crawler_name)
        print(f"Started crawler: {crawler_name}")
        
        return database_name
    except Exception as e:
        print(f"Error setting up Glue lineage: {e}")
        return None
```

**Set up AWS Lake Formation for data access control**

```python
def setup_lake_formation():
    lakeformation_client = boto3.client('lakeformation')
    
    try:
        database_name = 'fm_training_data'
        
        lakeformation_client.put_data_lake_settings(
            DataLakeSettings={
                'DataLakeAdmins': [
                    {'DataLakePrincipalIdentifier': f'arn:aws:iam::{boto3.client("sts").get_caller_identity()["Account"]}:role/DataLakeAdmin'}
                ],
                'CreateDatabaseDefaultPermissions': [],
                'CreateTableDefaultPermissions': []
            }
        )
        print("Configured Lake Formation settings")
        
        lakeformation_client.grant_permissions(
            Principal={'DataLakePrincipalIdentifier': f'arn:aws:iam::{boto3.client("sts").get_caller_identity()["Account"]}:role/MLEngineerRole'},
            Resource={
                'Database': {'Name': database_name}
            },
            Permissions=['DESCRIBE', 'ALTER', 'CREATE_TABLE']
        )
        print(f"Granted permissions for database: {database_name}")
        
        return True
    except Exception as e:
        print(f"Error setting up Lake Formation: {e}")
        return False
```

## Module 2: Implement model governance and documentation

**Objective:** Create comprehensive model documentation and governance controls.

**Tasks:**
- Create SageMaker Model Cards for model documentation.
- Configure Amazon Bedrock with guardrails.
- Implement model versioning and approval workflows.

**Create SageMaker Model Cards**

```python
import time

def create_model_card():
    sagemaker_client = boto3.client('sagemaker')
    
    try:
        model_card_name = f'fm-governance-card-{int(time.time())}'
        
        model_card_content = {
            "model_overview": {
                "model_id": "anthropic.claude-v2",
                "model_name": "Claude v2",
                "model_description": "Foundation model for text generation with governance controls",
                "model_version": "2.0",
                "model_creator": "Anthropic",
                "problem_type": "Text Generation"
            },
            "intended_uses": {
                "purpose_of_model": "Text generation for internal business applications",
                "intended_uses": "Document summarization, content creation, Q&A systems",
                "out_of_scope_use_cases": "Medical diagnosis, legal advice, financial trading decisions"
            },
            "business_details": {
                "business_problem": "Automate content generation while maintaining compliance",
                "business_stakeholders": "ML Team, Legal, Compliance",
                "line_of_business": "Enterprise AI"
            },
            "training_details": {
                "training_data": "Proprietary training data from S3",
                "training_methodology": "Pre-trained foundation model with fine-tuning"
            },
            "evaluation_details": {
                "evaluation_datasets": ["validation-dataset-v1"],
                "quantitative_analysis": {
                    "performance_metrics": [
                        {"name": "BLEU Score", "value": 0.85},
                        {"name": "Perplexity", "value": 12.3},
                        {"name": "Bias Score", "value": 0.15}
                    ]
                }
            },
            "additional_information": {
                "ethical_considerations": "Model has been tested for bias and fairness",
                "caveats_and_recommendations": "Should not be used for sensitive decision-making without human review"
            }
        }
        
        response = sagemaker_client.create_model_card(
            ModelCardName=model_card_name,
            ModelCardStatus='Draft',
            Content=json.dumps(model_card_content),
            SecurityConfig={'KmsKeyId': 'alias/aws/sagemaker'}
        )
        
        model_card_arn = response['ModelCardArn']
        print(f"Created model card: {model_card_name}")
        print(f"ARN: {model_card_arn}")
        
        sagemaker_client.update_model_card(
            ModelCardName=model_card_name,
            ModelCardStatus='Approved'
        )
        print("Updated model card status to Approved")
        
        return model_card_name
    except Exception as e:
        print(f"Error creating model card: {e}")
        return None
```

**Configure Amazon Bedrock with guardrails**

```python
def setup_bedrock_guardrails():
    bedrock_client = boto3.client('bedrock')
    
    try:
        guardrail_name = f'fm-governance-guardrail-{int(time.time())}'
        
        response = bedrock_client.create_guardrail(
            name=guardrail_name,
            description='Guardrail for foundation model governance',
            blockedInputMessaging={
                'messageForUser': 'Your input contains content that violates our usage policies.'
            },
            blockedOutputsMessaging={
                'messageForUser': 'The model\'s response contains content that violates our usage policies.'
            },
            contentPolicy={
                'filters': [
                    {
                        'type': 'TOPIC',
                        'topics': [
                            {'name': 'Violence', 'type': 'DENY'},
                            {'name': 'FinancialAdvice', 'type': 'DENY'},
                            {'name': 'LegalAdvice', 'type': 'DENY'},
                            {'name': 'MedicalAdvice', 'type': 'DENY'}
                        ]
                    },
                    {
                        'type': 'SENSITIVE_INFORMATION',
                        'sensitiveInformationTypes': [
                            {'name': 'SSN', 'type': 'MASK'},
                            {'name': 'EMAIL', 'type': 'MASK'},
                            {'name': 'PHONE_NUMBER', 'type': 'MASK'},
                            {'name': 'CREDIT_CARD', 'type': 'MASK'}
                        ]
                    },
                    {
                        'type': 'WORD',
                        'words': [
                            {'text': 'confidential', 'type': 'MASK'},
                            {'text': 'proprietary', 'type': 'MASK'}
                        ]
                    }
                ]
            }
        )
        
        guardrail_id = response['guardrailId']
        print(f"Created guardrail: {guardrail_name}")
        print(f"ID: {guardrail_id}")
        
        response = bedrock_client.create_guardrail_version(
            guardrailId=guardrail_id,
            description='Initial version'
        )
        
        guardrail_version = response['guardrailVersion']
        print(f"Created guardrail version: {guardrail_version}")
        
        return guardrail_id
    except Exception as e:
        print(f"Error setting up Bedrock guardrails: {e}")
        return None
```

## Module 3: Implement continuous monitoring and alerting

**Objective:** Set up comprehensive monitoring and alerting for foundation model governance.

**Tasks:**
- Configure CloudWatch metrics and alarms.
- Create custom metrics for model usage and compliance.
- Set up alarms for policy violations and anomalous behavior.
- Set up EventBridge for automated remediation.

**Configure CloudWatch metrics and alarms**

```python
def setup_cloudwatch_monitoring():
    cloudwatch_client = boto3.client("cloudwatch")

    try:
        dashboard_name = "FM-Governance-Dashboard"
        dashboard_body = {
            "widgets": [
                {
                    "type": "metric",
                    "x": 0,
                    "y": 0,
                    "width": 12,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            ["Custom/FMGovernance", "PolicyViolations", "ModelId", "anthropic.claude-v2"],
                            ["Custom/FMGovernance", "GuardrailBlocks", "ModelId", "anthropic.claude-v2"],
                        ],
                        "view": "timeSeries",
                        "stacked": False,
                        "region": "us-west-2",
                        "title": "Policy Violations and Guardrail Blocks",
                        "period": 300,
                    },
                },
                {
                    "type": "metric",
                    "x": 0,
                    "y": 6,
                    "width": 12,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            ["Custom/FMGovernance", "PIIDetections", "ModelId", "anthropic.claude-v2"],
                            ["Custom/FMGovernance", "TokenRedactions", "ModelId", "anthropic.claude-v2"],
                        ],
                        "view": "timeSeries",
                        "stacked": False,
                        "region": "us-west-2",
                        "title": "PII Detections and Token Redactions",
                        "period": 300,
                    },
                },
                {
                    "type": "metric",
                    "x": 12,
                    "y": 0,
                    "width": 12,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            ["Custom/FMGovernance", "ModelInvocations", "ModelId", "anthropic.claude-v2"],
                        ],
                        "view": "timeSeries",
                        "stacked": False,
                        "region": "us-west-2",
                        "title": "Model Invocations",
                        "period": 300,
                    },
                },
                {
                    "type": "metric",
                    "x": 12,
                    "y": 6,
                    "width": 12,
                    "height": 6,
                    "properties": {
                        "metrics": [
                            ["Custom/FMGovernance", "BiasDrift", "ModelId", "anthropic.claude-v2"],
                        ],
                        "view": "timeSeries",
                        "stacked": False,
                        "region": "us-west-2",
                        "title": "Bias Drift Metric",
                        "period": 3600,
                    },
                },
            ]
        }

        cloudwatch_client.put_dashboard(
            DashboardName=dashboard_name,
            DashboardBody=json.dumps(dashboard_body),
        )
        print(f"Created CloudWatch dashboard: {dashboard_name}")

        cloudwatch_client.put_metric_alarm(
            AlarmName="FM-Policy-Violations-Alarm",
            ComparisonOperator="GreaterThanThreshold",
            EvaluationPeriods=1,
            MetricName="PolicyViolations",
            Namespace="Custom/FMGovernance",
            Period=300,
            Statistic="Sum",
            Threshold=5.0,
            ActionsEnabled=True,
            AlarmDescription="Alarm when policy violations exceed threshold",
            Dimensions=[
                {"Name": "ModelId", "Value": "anthropic.claude-v2"},
            ],
            AlarmActions=[
                f"arn:aws:sns:us-west-2:{boto3.client('sts').get_caller_identity()['Account']}:FM-Governance-Alerts",
            ],
        )
        print("Created alarm for policy violations")

        cloudwatch_client.put_metric_alarm(
            AlarmName="FM-Bias-Drift-Alarm",
            ComparisonOperator="GreaterThanThreshold",
            EvaluationPeriods=3,
            MetricName="BiasDrift",
            Namespace="Custom/FMGovernance",
            Period=3600,
            Statistic="Average",
            Threshold=0.2,
            ActionsEnabled=True,
            AlarmDescription="Alarm when bias drift exceeds threshold",
            Dimensions=[
                {"Name": "ModelId", "Value": "anthropic.claude-v2"},
            ],
            AlarmActions=[
                f"arn:aws:sns:us-west-2:{boto3.client('sts').get_caller_identity()['Account']}:FM-Governance-Alerts",
            ],
        )
        print("Created alarm for bias drift")

        return dashboard_name
    except Exception as e:
        print(f"Error setting up CloudWatch monitoring: {e}")
        return None
```

**Set up EventBridge for automated remediation**

```python
def setup_eventbridge_remediation():
    events_client = boto3.client("events")

    try:
        rule_name = "FM-Policy-Violation-Rule"
        events_client.put_rule(
            Name=rule_name,
            EventPattern=json.dumps(
                {
                    "source": ["aws.cloudwatch"],
                    "detail-type": ["CloudWatch Alarm State Change"],
                    "resources": [
                        f"arn:aws:cloudwatch:us-west-2:{boto3.client('sts').get_caller_identity()['Account']}:alarm:FM-Policy-Violations-Alarm"
                    ],
                    "detail": {"state": {"value": ["ALARM"]}},
                }
            ),
            State="ENABLED",
            Description="Rule to detect foundation model policy violations",
        )
        print(f"Created EventBridge rule: {rule_name}")

        lambda_function_name = "fm-governance-remediation"
        events_client.put_targets(
            Rule=rule_name,
            Targets=[
                {
                    "Id": "1",
                    "Arn": (
                        f"arn:aws:lambda:us-west-2:{boto3.client('sts').get_caller_identity()['Account']}:function:{lambda_function_name}"
                    ),
                }
            ],
        )
        print(f"Added Lambda target to rule: {rule_name}")

        lambda_code = """
import boto3
import json

def lambda_handler(event, context):
    print("Received event:", json.dumps(event))

    alarm_name = event["detail"]["alarmName"]
    alarm_state = event["detail"]["state"]["value"]

    print(f"Alarm {alarm_name} is in state {alarm_state}")

    if alarm_name == "FM-Policy-Violations-Alarm":
        sns_client = boto3.client("sns")
        sns_client.publish(
            TopicArn=(
                f"arn:aws:sns:us-west-2:{boto3.client('sts').get_caller_identity()['Account']}:FM-Governance-Alerts"
            ),
            Message=(
                "ALERT: Foundation Model policy violations detected. Implementing automatic remediation."
            ),
            Subject="Foundation Model Policy Violation Alert",
        )

        print("Implementing temporary access restrictions")
        print("Triggering investigation workflow")

    return {
        "statusCode": 200,
        "body": json.dumps("Remediation actions completed"),
    }
"""

        _ = lambda_code
        return True
    except Exception as e:
        print(f"Error setting up EventBridge remediation: {e}")
        return False
```