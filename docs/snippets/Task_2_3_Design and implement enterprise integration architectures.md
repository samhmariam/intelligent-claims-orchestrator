# Enterprise Integration Architectures

## Project Architecture

### Objective

- Design and implement enterprise integration architectures that include:
  - API Gateway for centralized access control.
  - Event-driven integration patterns.
  - Secure access frameworks.
  - Cross-environment data handling.
  - CI/CD pipeline for deployment.

---

## Project Components

1. **API-Based Integration Layer**:
   - Centralized access point for foundation model capabilities.
   - Simulates integration with legacy systems.

2. **Event-Driven Processing System**:
   - Enables asynchronous communication between components.

3. **Secure Access Framework**:
   - Ensures secure and authorized access to resources.

4. **Cross-Environment Data Handling**:
   - Facilitates seamless data flow across environments.

5. **CI/CD Pipeline for Deployment**:
   - Automates deployment and integration processes.

---

## Component 1: API-Based Integration Layer

### Objective

- Create an API Gateway that serves as a central access point for foundation model capabilities.

### Implementation

#### Step 1.1: Create an API Gateway

```bash
# Create an API Gateway
aws apigateway create-rest-api --name "GenAI-Integration-Gateway" --description "Enterprise GenAI Integration Gateway"

# Get the API ID for use in subsequent commands
API_ID=$(aws apigateway get-rest-apis --query "items[?name=='GenAI-Integration-Gateway'].id" --output text)

# Create a resource
PARENT_ID=$(aws apigateway get-resources --rest-api-id $API_ID --query "items[0].id" --output text)
aws apigateway create-resource --rest-api-id $API_ID --parent-id $PARENT_ID --path-part "generate"

# Get the resource ID
RESOURCE_ID=$(aws apigateway get-resources --rest-api-id $API_ID --query "items[?pathPart=='generate'].id" --output text)

# Create a POST method
aws apigateway put-method --rest-api-id $API_ID --resource-id $RESOURCE_ID --http-method POST --authorization-type "COGNITO_USER_POOLS" --authorizer-id $AUTHORIZER_ID
```

#### Step 1.2: Create a Lambda Function for API Processing

Create a file named `api_processor.py`:

```python
import json
import boto3
import os
import logging
import uuid

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients
bedrock_runtime = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['REQUEST_TABLE'])

def lambda_handler(event, context):
    """
    Process API requests and route to appropriate foundation models
    """
    try:
        # Extract request body
        body = json.loads(event['body']) if isinstance(event.get('body'), str) else event.get('body', {})
        
        # Extract request parameters
        prompt = body.get('prompt', '')
        model_id = body.get('model', 'anthropic.claude-v2')
        department = body.get('department', 'general')
        request_type = body.get('type', 'text-generation')
        
        # Log request for auditing
        request_id = str(uuid.uuid4())
        user_id = event['requestContext']['authorizer']['claims']['sub']
        
        # Store request in DynamoDB for tracking
        table.put_item(
            Item={
                'requestId': request_id,
                'userId': user_id,
                'department': department,
                'modelId': model_id,
                'requestType': request_type,
                'timestamp': int(context.timestamp),
                'prompt': prompt
            }
        )
        
        # Process based on request type
        if request_type == 'text-generation':
            response = invoke_text_model(prompt, model_id)
        elif request_type == 'image-generation':
            response = invoke_image_model(prompt)
        else:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Unsupported request type'})
            }
        
        # Return successful response
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'requestId': request_id,
                'result': response,
                'model': model_id
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def invoke_text_model(prompt, model_id):
    """
    Invoke a text generation foundation model
    """
    if model_id.startswith('anthropic'):
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
                "max_tokens_to_sample": 500,
                "temperature": 0.7,
                "top_p": 0.9,
            })
        )
        response_body = json.loads(response['body'].read())
        return response_body.get('completion', '')
    
    elif model_id.startswith('amazon'):
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                "inputText": prompt
            })
        )
        response_body = json.loads(response['body'].read())
        return response_body.get('results', [{}])[0].get('outputText', '')
    
    else:
        raise ValueError(f"Unsupported model ID: {model_id}")

def invoke_image_model(prompt):
    """
    Invoke an image generation model (placeholder)
    """
    # In a real implementation, this would call an image generation model
    return f"Image generation requested for prompt: {prompt}"
```

#### Step 1.3: Create a legacy system simulator

Create a file named `legacy_system_simulator.py`:

```python
import json
import boto3
import os
import logging
import csv
import io
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3 = boto3.client('s3')
bucket_name = os.environ['DATA_BUCKET']

def lambda_handler(event, context):
    """
    Simulate a legacy system that processes CSV data and requests AI analysis
    """
    try:
        # Get the file from the event
        file_key = event['Records'][0]['s3']['object']['key']
        
        # Download the CSV file
        response = s3.get_object(Bucket=bucket_name, Key=file_key)
        csv_content = response['Body'].read().decode('utf-8')
        
        # Process the CSV data
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        records = list(csv_reader)
        
        # Generate summary request for AI analysis
        summary_request = {
            'prompt': f"Analyze the following {len(records)} records and provide insights: {json.dumps(records[:10])}...",
            'model': 'anthropic.claude-v2',
            'department': 'finance',
            'type': 'text-generation'
        }
        
        # Call the API Gateway (in a real scenario)
        # Here we'll just log the request
        logger.info(f"Legacy system would send request: {json.dumps(summary_request)}")
        
        # Store the processed result
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        processed_key = f"processed/{os.path.basename(file_key)}-{timestamp}.json"
        
        s3.put_object(
            Bucket=bucket_name,
            Key=processed_key,
            Body=json.dumps({
                'source_file': file_key,
                'record_count': len(records),
                'processed_timestamp': timestamp,
                'ai_request': summary_request
            }),
            ContentType='application/json'
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f"Processed {len(records)} records from {file_key}",
                'output_file': processed_key
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing legacy data: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

#### Step 1.4: Create CloudFormation template for API integration layer

Create a file named `api_integration_layer.yaml`:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Enterprise GenAI Integration Gateway - API Integration Layer'

Parameters:
  DataBucketName:
    Type: String
    Default: 'genai-enterprise-data'
    Description: 'S3 bucket for storing data'

Resources:
  # DynamoDB Table for Request Tracking
  RequestTrackingTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: GenAI-Request-Tracking
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: requestId
          AttributeType: S
        - AttributeName: userId
          AttributeType: S
      KeySchema:
        - AttributeName: requestId
          KeyType: HASH
      GlobalSecondaryIndexes:
        - IndexName: UserIdIndex
          KeySchema:
            - AttributeName: userId
              KeyType: HASH
          Projection:
            ProjectionType: ALL

  # S3 Bucket for Data Storage
  DataBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Ref DataBucketName
      VersioningConfiguration:
        Status: Enabled
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256

  # IAM Role for API Processor Lambda
  ApiProcessorRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: 'sts:AssumeRole'
      ManagedPolicyArns:
        - 'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
      Policies:
        - PolicyName: BedrockAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - 'bedrock:InvokeModel'
                Resource: '*'
        - PolicyName: DynamoDBAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - 'dynamodb:PutItem'
                Resource: !GetAtt RequestTrackingTable.Arn

  # IAM Role for Legacy System Simulator Lambda
  LegacySystemRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: 'sts:AssumeRole'
      ManagedPolicyArns:
        - 'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
      Policies:
        - PolicyName: S3Access
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - 's3:GetObject'
                  - 's3:PutObject'
                Resource: 
                  - !Sub '${DataBucket.Arn}/*'

  # Lambda Function for API Processing
  ApiProcessorFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: GenAI-API-Processor
      Handler: index.lambda_handler
      Role: !GetAtt ApiProcessorRole.Arn
      Runtime: python3.9
      Timeout: 30
      MemorySize: 256
      Environment:
        Variables:
          REQUEST_TABLE: !Ref RequestTrackingTable
      Code:
        ZipFile: |
          # Code from api_processor.py

  # Lambda Function for Legacy System Simulator
  LegacySystemFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: GenAI-Legacy-System-Simulator
      Handler: index.lambda_handler
      Role: !GetAtt LegacySystemRole.Arn
      Runtime: python3.9
      Timeout: 30
      MemorySize: 256
      Environment:
        Variables:
          DATA_BUCKET: !Ref DataBucketName
      Code:
        ZipFile: |
          # Code from legacy_system_simulator.py

  # S3 Event Notification for Legacy System
  LegacySystemEventNotification:
    Type: AWS::S3::BucketNotification
    Properties:
      Bucket: !Ref DataBucket
      LambdaConfigurations:
        - Event: 's3:ObjectCreated:*'
          Filter:
            S3Key:
              Suffix: '.csv'
          Function: !GetAtt LegacySystemFunction.Arn

  # Lambda Permission for S3 Invocation
  LegacySystemPermission:
    Type: AWS::Lambda::Permission
    Properties:
      Action: 'lambda:InvokeFunction'
      FunctionName: !Ref LegacySystemFunction
      Principal: 's3.amazonaws.com'
      SourceAccount: !Ref 'AWS::AccountId'
      SourceArn: !GetAtt DataBucket.Arn

Outputs:
  ApiProcessorFunctionArn:
    Description: 'ARN of the API Processor Lambda Function'
    Value: !GetAtt ApiProcessorFunction.Arn
  
  RequestTrackingTableName:
    Description: 'Name of the DynamoDB Request Tracking Table'
    Value: !Ref RequestTrackingTable
  
  DataBucketName:
    Description: 'Name of the S3 Data Bucket'
    Value: !Ref DataBucket
```

---

## Component 2: Event-Driven Processing System

### Objective

- Create an event-driven architecture using EventBridge to process events from various sources and trigger appropriate AI workflows.

### Implementation

#### Step 2.1: Create an EventBridge rule and target

```bash
# Create an EventBridge rule
aws events put-rule \
    --name "GenAI-ProcessingEvents" \
    --event-pattern "{\"source\":[\"com.enterprise.application\"],\"detail-type\":[\"DocumentUploaded\",\"CustomerInteraction\",\"DataAnalysisRequest\"]}"

# Create a Lambda function for event processing
aws lambda create-function \
    --function-name GenAI-EventProcessor \
    --runtime python3.9 \
    --role $LAMBDA_EXECUTION_ROLE \
    --handler index.lambda_handler \
    --zip-file fileb://event_processor.zip

# Add the Lambda function as a target for the EventBridge rule
aws events put-targets \
    --rule "GenAI-ProcessingEvents" \
    --targets "Id"="1","Arn"="$LAMBDA_FUNCTION_ARN"
```

#### Step 2.2: Create an Event processor Lambda function

Create a file named `event_processor.py`:

```python
import json
import boto3
import os
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients
bedrock_runtime = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['EVENT_TABLE'])

def lambda_handler(event, context):
    """
    Process events from EventBridge and trigger appropriate AI workflows
    """
    try:
        # Log the incoming event
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Extract event details
        detail_type = event.get('detail-type', '')
        source = event.get('source', '')
        detail = event.get('detail', {})
        
        # Store the event in DynamoDB
        event_id = detail.get('id', datetime.now().isoformat())
        table.put_item(
            Item={
                'eventId': event_id,
                'source': source,
                'detailType': detail_type,
                'timestamp': event.get('time', datetime.now().isoformat()),
                'detail': detail
            }
        )
        
        # Process based on event type
        if detail_type == 'DocumentUploaded':
            response = process_document_upload(detail)
        elif detail_type == 'CustomerInteraction':
            response = process_customer_interaction(detail)
        elif detail_type == 'DataAnalysisRequest':
            response = process_data_analysis(detail)
        else:
            logger.warning(f"Unsupported event type: {detail_type}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f"Unsupported event type: {detail_type}"})
            }
        
        # Return successful response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'eventId': event_id,
                'result': response
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def process_document_upload(detail):
    """
    Process document upload events
    """
    document_type = detail.get('documentType', '')
    content = detail.get('content', '')
    
    # Generate a prompt based on document type
    if document_type == 'contract':
        prompt = f"Analyze this contract and extract key terms, parties, and obligations: {content[:1000]}..."
    elif document_type == 'report':
        prompt = f"Summarize the main findings of this report: {content[:1000]}..."
    else:
        prompt = f"Analyze this document and provide key insights: {content[:1000]}..."
    
    # Invoke foundation model
    response = bedrock_runtime.invoke_model(
        modelId='anthropic.claude-v2',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
            "max_tokens_to_sample": 1000,
            "temperature": 0.2,
            "top_p": 0.9,
        })
    )
    
    response_body = json.loads(response['body'].read())
    return {
        'documentType': document_type,
        'analysis': response_body.get('completion', '')
    }

def process_customer_interaction(detail):
    """
    Process customer interaction events
    """
    interaction_type = detail.get('interactionType', '')
    customer_id = detail.get('customerId', '')
    content = detail.get('content', '')
    
    # Generate a prompt based on interaction type
    if interaction_type == 'complaint':
        prompt = f"Analyze this customer complaint and suggest a response: {content}"
    elif interaction_type == 'inquiry':
        prompt = f"Generate a helpful response to this customer inquiry: {content}"
    else:
        prompt = f"Analyze this customer interaction and provide insights: {content}"
    
    # Invoke foundation model
    response = bedrock_runtime.invoke_model(
        modelId='anthropic.claude-v2',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
            "max_tokens_to_sample": 800,
            "temperature": 0.4,
            "top_p": 0.9,
        })
    )
    
    response_body = json.loads(response['body'].read())
    return {
        'interactionType': interaction_type,
        'customerId': customer_id,
        'suggestedResponse': response_body.get('completion', '')
    }

def process_data_analysis(detail):
    """
    Process data analysis requests
    """
    analysis_type = detail.get('analysisType', '')
    data_source = detail.get('dataSource', '')
    parameters = detail.get('parameters', {})
    
    # In a real implementation, this would fetch data from the specified source
    # For this example, we'll simulate with a placeholder
    
    # Generate a prompt based on analysis type
    prompt = f"Perform {analysis_type} analysis on data from {data_source} with parameters {json.dumps(parameters)}"
    
    # Invoke foundation model
    response = bedrock_runtime.invoke_model(
        modelId='anthropic.claude-v2',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
            "max_tokens_to_sample": 1200,
            "temperature": 0.2,
            "top_p": 0.9,
        })
    )
    
    response_body = json.loads(response['body'].read())
    return {
        'analysisType': analysis_type,
        'dataSource': data_source,
        'results': response_body.get('completion', '')
    }
```

#### Step 2.3: Create a sample event publisher

Create a file named `event_publisher.py`:

```python
import json
import boto3
import uuid
import datetime
import random

# Initialize EventBridge client
events = boto3.client('events')

def publish_document_event():
    """
    Publish a sample document upload event
    """
    document_types = ['contract', 'report', 'policy', 'memo']
    document_type = random.choice(document_types)
    
    event = {
        'Source': 'com.enterprise.application',
        'DetailType': 'DocumentUploaded',
        'Time': datetime.datetime.now().isoformat(),
        'Detail': json.dumps({
            'id': str(uuid.uuid4()),
            'documentType': document_type,
            'uploadedBy': f'user-{random.randint(1000, 9999)}',
            'timestamp': datetime.datetime.now().isoformat(),
            'content': f"This is a sample {document_type} document content for testing purposes."
        })
    }
    
    response = events.put_events(Entries=[event])
    print(f"Published DocumentUploaded event: {response}")

def publish_customer_event():
    """
    Publish a sample customer interaction event
    """
    interaction_types = ['complaint', 'inquiry', 'feedback']
    interaction_type = random.choice(interaction_types)
    
    content_templates = {
        'complaint': "I've been having issues with your service for the past week. This is unacceptable.",
        'inquiry': "Can you provide more information about your premium subscription options?",
        'feedback': "I really enjoyed using your new feature. It has greatly improved my workflow."
    }
    
    event = {
        'Source': 'com.enterprise.application',
        'DetailType': 'CustomerInteraction',
        'Time': datetime.datetime.now().isoformat(),
        'Detail': json.dumps({
            'id': str(uuid.uuid4()),
            'interactionType': interaction_type,
            'customerId': f'cust-{random.randint(10000, 99999)}',
            'channel': random.choice(['email', 'chat', 'phone']),
            'timestamp': datetime.datetime.now().isoformat(),
            'content': content_templates[interaction_type]
        })
    }
    
    response = events.put_events(Entries=[event])
    print(f"Published CustomerInteraction event: {response}")

def publish_data_analysis_event():
    """
    Publish a sample data analysis request event
    """
    analysis_types = ['trend', 'anomaly', 'forecast', 'segment']
    analysis_type = random.choice(analysis_types)
    
    data_sources = ['sales_data', 'customer_metrics', 'product_performance', 'marketing_campaign']
    data_source = random.choice(data_sources)
    
    event = {
        'Source': 'com.enterprise.application',
        'DetailType': 'DataAnalysisRequest',
        'Time': datetime.datetime.now().isoformat(),
        'Detail': json.dumps({
            'id': str(uuid.uuid4()),
            'analysisType': analysis_type,
            'dataSource': data_source,
            'requestedBy': f'analyst-{random.randint(100, 999)}',
            'priority': random.choice(['high', 'medium', 'low']),
            'parameters': {
                'timeframe': random.choice(['daily', 'weekly', 'monthly']),
                'segments': random.sample(['region', 'product', 'customer_type', 'channel'], k=random.randint(1, 3))
            }
        })
    }
    
    response = events.put_events(Entries=[event])
    print(f"Published DataAnalysisRequest event: {response}")
```

#### Step 2.4: Create a CloudFormation template for an event-driven system

Create a file named `event_driven_system.yaml`:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Enterprise GenAI Integration Gateway - Event-Driven Processing System'

Parameters:
  RequestTrackingTableName:
    Type: String
    Default: 'GenAI-Request-Tracking'
    Description: 'DynamoDB table for request tracking'

Resources:
  # DynamoDB Table for Event Tracking
  EventTrackingTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: GenAI-Event-Tracking
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: eventId
          AttributeType: S
        - AttributeName: source
          AttributeType: S
      KeySchema:
        - AttributeName: eventId
          KeyType: HASH
      GlobalSecondaryIndexes:
        - IndexName: SourceIndex
          KeySchema:
            - AttributeName: source
              KeyType: HASH
          Projection:
            ProjectionType: ALL

  # IAM Role for Event Processor Lambda
  EventProcessorRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: 'sts:AssumeRole'
      ManagedPolicyArns:
        - 'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
      Policies:
        - PolicyName: BedrockAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - 'bedrock:InvokeModel'
                Resource: '*'
        - PolicyName: DynamoDBAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - 'dynamodb:PutItem'
                Resource: !GetAtt RequestTrackingTable.Arn

  # Lambda Function for Event Processing
  EventProcessorFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: GenAI-EventProcessor
      Handler: index.lambda_handler
      Role: !GetAtt EventProcessorRole.Arn
      Runtime: python3.9
      Timeout: 30
      MemorySize: 256
      Environment:
        Variables:
          EVENT_TABLE: !Ref EventTrackingTable
      Code:
        ZipFile: |
          # Code from event_processor.py

  # EventBridge Rule for Processing Events
  ProcessingEventsRule:
    Type: AWS::Events::Rule
    Properties:
      Name: GenAI-ProcessingEvents
      EventPattern:
        source:
          - "com.enterprise.application"
        detail-type:
          - "DocumentUploaded"
          - "CustomerInteraction"
          - "DataAnalysisRequest"
      Targets:
        - Arn: !GetAtt EventProcessorFunction.Arn
          Id: "EventProcessorTarget"

Outputs:
  EventProcessorFunctionArn:
    Description: 'ARN of the Event Processor Lambda Function'
    Value: !GetAtt EventProcessorFunction.Arn
  
  EventTrackingTableName:
    Description: 'Name of the DynamoDB Event Tracking Table'
    Value: !Ref EventTrackingTable
```

---

## Deliverables

1. **Working Enterprise Integration Architecture**:
   - Includes API Gateway, Lambda functions, and secure data handling.

2. **Documentation**:
   - Clear instructions and code examples.

3. **Test Results**:
   - Demonstrate system performance and integration capabilities.

4. **Analysis**:
   - Iterative improvements made during development.