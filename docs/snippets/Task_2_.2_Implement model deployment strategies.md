# Multi-Tier Customer Support AI System

## Scenario

### Objective

- Build a multi-tier customer support AI system that:
  - Handles routine queries with efficient, smaller models.
  - Escalates complex issues to more powerful models.
  - Optimizes for both performance and cost.
  - Implements various deployment patterns.

---

## Part 1: On-Demand Lambda Deployment

### Step 1: Set Up IAM Role

- Create an IAM role with the following permissions:
  - `bedrock:InvokeModel`
  - `logs:CreateLogGroup`
  - `logs:CreateLogStream`
  - `logs:PutLogEvents`

### Step 2: Create Lambda Function

#### Code Example

```python
import json
import boto3
import os

# Initialize Bedrock client
bedrock_runtime = boto3.client('bedrock-runtime')

# Define model parameters
MODEL_ID = 'anthropic.claude-instant-v1'  # Smaller, more efficient model for routine queries

def lambda_handler(event, context):
    """
    Lambda function to handle customer support queries using Amazon Bedrock
    """
    try:
        # Extract query from event
        query = event.get('query', '')
        if not query:
            return {
                'statusCode': 400,
                'body': json.dumps('No query provided')
            }
        
        # Prepare prompt for customer support context
        prompt = f"""
        You are a helpful customer support assistant for a cloud computing company.
        Please respond to the following customer query concisely and accurately.
        
        Customer query: {query}
        """
        
        # Invoke Bedrock model
        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                "prompt": prompt,
                "max_tokens_to_sample": 300,
                "temperature": 0.4,
                "top_p": 0.9,
            })
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        model_response = response_body.get('completion', '')
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'query': query,
                'response': model_response
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error processing request: {str(e)}')
        }
```

### Step 3: Configure Lambda Settings

- **Memory**: 256 MB
- **Timeout**: 30 seconds
- **Environment Variables**:
  - `MODEL_ID`: `anthropic.claude-instant-v1`

### Step 4: Create API Gateway Endpoint

- Create a new REST API
- Create a resource `/query`
- Add a POST method that integrates with your Lambda function
- Deploy the API to a new stage (e.g., "dev")

### Step 5: Test the Deployment

- Use the following command:

```bash
curl -X POST \
  https://your-api-id.execute-api.region.amazonaws.com/dev/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "How do I reset my password?"}'
```

---

## Part 2: Provisioned Throughput Configuration

### Objective

- Set up Amazon Bedrock with provisioned throughput for handling consistent traffic with predictable latency.

### Step 1: Create Provisioned Throughput

- Use AWS CLI or console to create provisioned throughput for a more powerful model:

```bash
aws bedrock create-provisioned-model-throughput \
  --model-id anthropic.claude-v2 \
  --provisioned-model-name "customer-support-advanced" \
  --model-units 1
```

### Step 2: Lambda Function

#### Code Example

```python
import json
import boto3
import os
import time

# Initialize Bedrock client
bedrock_runtime = boto3.client('bedrock-runtime')

# Define provisioned throughput ARN
PROVISIONED_MODEL_ARN = os.environ['PROVISIONED_MODEL_ARN']

def lambda_handler(event, context):
    """
    Lambda function to handle complex customer support queries using provisioned throughput
    """
    try:
        # Extract query from event
        query = event.get('query', '')
        if not query:
            return {
                'statusCode': 400,
                'body': json.dumps('No query provided')
            }
        
        # Prepare prompt for complex customer support context
        prompt = f"""
        You are an advanced customer support assistant for a cloud computing company.
        Please provide a detailed and helpful response to the following complex customer query.
        Include specific steps, documentation references, and best practices where applicable.
        
        Customer query: {query}
        """
        
        # Start timing for latency measurement
        start_time = time.time()
        
        # Invoke Bedrock model with provisioned throughput
        response = bedrock_runtime.invoke_model(
            modelId=PROVISIONED_MODEL_ARN,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                "prompt": prompt,
                "max_tokens_to_sample": 1000,
                "temperature": 0.2,
                "top_p": 0.9,
            })
        )
        
        # Calculate latency
        latency = time.time() - start_time
        
        # Parse response
        response_body = json.loads(response['body'].read())
        model_response = response_body.get('completion', '')
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'query': query,
                'response': model_response,
                'latency_seconds': latency
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error processing request: {str(e)}')
        }
```

### Step 3: Create CloudWatch Dashboard for Monitoring

- Create a CloudWatch dashboard to monitor:
  - Invocation counts
  - Latency metrics
  - Error rates
  - Provisioned throughput utilization

```bash
aws cloudwatch put-dashboard \
  --dashboard-name "BedrokProvisionedThroughputMonitoring" \
  --dashboard-body file://dashboard.json
```

Where `dashboard.json` contains:

```json
{
  "widgets": [
    {
      "type": "metric",
      "x": 0,
      "y": 0,
      "width": 12,
      "height": 6,
      "properties": {
        "metrics": [
          [ "AWS/Lambda", "Duration", "FunctionName", "customer-support-advanced-lambda" ]
        ],
        "view": "timeSeries",
        "stacked": false,
        "region": "us-east-1",
        "title": "Lambda Duration",
        "period": 300
      }
    },
    {
      "type": "metric",
      "x": 12,
      "y": 0,
      "width": 12,
      "height": 6,
      "properties": {
        "metrics": [
          [ "AWS/Lambda", "Invocations", "FunctionName", "customer-support-advanced-lambda" ]
        ],
        "view": "timeSeries",
        "stacked": false,
        "region": "us-east-1",
        "title": "Lambda Invocations",
        "period": 300
      }
    }
  ]
}
```

---

## Part 3: Container-Based Deployment with Memory Optimization

### Objective

- Deploy a foundation model using SageMaker with container optimizations for memory and GPU utilization.

### Step 1: Create a Dockerfile for Optimized Container

```dockerfile
FROM nvidia/cuda:11.8.0-base-ubuntu20.04

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch and Transformers
RUN pip3 install --no-cache-dir \
    torch==2.0.1 \
    transformers==4.31.0 \
    accelerate==0.21.0 \
    bitsandbytes==0.40.2 \
    flask \
    gunicorn \
    boto3

# Set up working directory
WORKDIR /app

# Copy model serving code
COPY serve.py /app/
COPY model_utils.py /app/

# Set up environment variables for memory optimization
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128

# Expose port for SageMaker
EXPOSE 8080

# Command to run the server
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "300", "serve:app"]
```

### Step 2: Create Model Serving Code with Memory Optimizations

#### Code Example: `model_utils.py`

```python
import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from accelerate import init_empty_weights
import gc

class OptimizedModel:
    def __init__(self, model_id="meta-llama/Llama-2-7b-chat-hf"):
        self.model_id = model_id
        self.model = None
        self.tokenizer = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.is_loaded = False
    
    def load_model(self):
        """Load model with memory optimizations"""
        if self.is_loaded:
            return
        
        print(f"Loading model {self.model_id}...")
        
        # Clear CUDA cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        
        # Load model with 8-bit quantization for memory efficiency
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            device_map="auto",
            load_in_8bit=True,  # Use 8-bit quantization
            torch_dtype=torch.float16  # Use half precision
        )
        
        self.is_loaded = True
        print("Model loaded successfully")
    
    def generate_response(self, prompt, max_tokens=512):
        """Generate response with memory-efficient inference"""
        if not self.is_loaded:
            self.load_model()
        
        # Tokenize input
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        
        # Generate with memory-efficient settings
        with torch.no_grad():
            # Use efficient attention implementation
            outputs = self.model.generate(
                inputs["input_ids"],
                max_new_tokens=max_tokens,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                use_cache=True,  # Enable KV caching
                attention_mask=inputs["attention_mask"]
            )
        
        # Decode and return response
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Return just the generated part (not the input prompt)
        return response[len(self.tokenizer.decode(inputs["input_ids"][0], skip_special_tokens=True)):]
```

#### Code Example: `serve.py`

```python
from flask import Flask, request, jsonify
import os
import json
from model_utils import OptimizedModel

# Initialize Flask app
app = Flask(__name__)

# Initialize model (lazy loading)
model = None

@app.route('/ping', methods=['GET'])
def ping():
    """SageMaker health check endpoint"""
    return "", 200

@app.route('/invocations', methods=['POST'])
def invoke():
    """SageMaker invocation endpoint"""
    global model
    
    # Lazy load model on first request
    if model is None:
        model = OptimizedModel(model_id=os.environ.get('MODEL_ID', 'meta-llama/Llama-2-7b-chat-hf'))
    
    # Parse request data
    if request.content_type == 'application/json':
        data = json.loads(request.data.decode('utf-8'))
        prompt = data.get('prompt', '')
        max_tokens = data.get('max_tokens', 512)
    else:
        return jsonify(error="This predictor only supports application/json input"), 415
    
    # Generate response
    try:
        response = model.generate_response(prompt, max_tokens)
        return jsonify({"response": response})
    except Exception as e:
        return jsonify(error=str(e)), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

### Step 3: Build and Push Docker Image

```bash
# Build the Docker image
docker build -t customer-support-llm .

# Create ECR repository
aws ecr create-repository --repository-name customer-support-llm

# Tag and push the image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin {account-id}.dkr.ecr.us-east-1.amazonaws.com
docker tag customer-support-llm:latest {account-id}.dkr.ecr.us-east-1.amazonaws.com/customer-support-llm:latest
docker push {account-id}.dkr.ecr.us-east-1.amazonaws.com/customer-support-llm:latest
```

### Step 4: Deploy Model to SageMaker

#### Code Example: `deploy_to_sagemaker.py`

```python
import boto3
import json
import time

# Initialize SageMaker client
sagemaker_client = boto3.client('sagemaker')
runtime_client = boto3.client('sagemaker-runtime')

# Define model parameters
model_name = 'customer-support-llm'
image_uri = '{account-id}.dkr.ecr.us-east-1.amazonaws.com/customer-support-llm:latest'
role_arn = 'arn:aws:iam::{account-id}:role/SageMakerExecutionRole'
instance_type = 'ml.g5.2xlarge'  # GPU instance optimized for LLMs

# Create model in SageMaker
print("Creating model...")
response = sagemaker_client.create_model(
    ModelName=model_name,
    PrimaryContainer={
        'Image': image_uri,
        'Environment': {
            'MODEL_ID': 'meta-llama/Llama-2-7b-chat-hf',
            'PYTORCH_CUDA_ALLOC_CONF': 'max_split_size_mb:128'
        }
    },
    ExecutionRoleArn=role_arn
)

# Create endpoint configuration with memory optimization
print("Creating endpoint configuration...")
response = sagemaker_client.create_endpoint_config(
    EndpointConfigName=model_name + '-config',
    ProductionVariants=[
        {
            'VariantName': 'default',
            'ModelName': model_name,
            'InstanceType': instance_type,
            'InitialInstanceCount': 1,
            'ContainerStartupHealthCheckTimeoutInSeconds': 600,  # Allow time for model loading
            'ModelDataDownloadTimeoutInSeconds': 900
        }
    ]
)

# Create endpoint
print("Creating endpoint... This may take 10-15 minutes...")
response = sagemaker_client.create_endpoint(
    EndpointName=model_name + '-endpoint',
    EndpointConfigName=model_name + '-config'
)

# Wait for endpoint to be in service
print("Waiting for endpoint to be ready...")
waiter = sagemaker_client.get_waiter('endpoint_in_service')
waiter.wait(EndpointName=model_name + '-endpoint')

print(f"Endpoint {model_name}-endpoint is ready!")

# Test the endpoint
print("Testing the endpoint...")
response = runtime_client.invoke_endpoint(
    EndpointName=model_name + '-endpoint',
    ContentType='application/json',
    Body=json.dumps({
        'prompt': 'How do I troubleshoot high latency in my cloud application?',
        'max_tokens': 256
    })
)

result = json.loads(response['Body'].read().decode())
print("Response from model:")
print(result['response'])
```

---

## Part 4: Model Cascading Implementation

### Objective

- Implement an API-based model cascading system that routes queries to appropriate models based on complexity.

### Step 1: Create a Model Router Lambda Function

#### Code Example

```python
import json
import boto3
import os
import re
import time

# Initialize clients
bedrock_runtime = boto3.client('bedrock-runtime')
sagemaker_runtime = boto3.client('sagemaker-runtime')
lambda_client = boto3.client('lambda')

# Define model configurations
SIMPLE_MODEL_ID = 'anthropic.claude-instant-v1'  # Fast, efficient model for simple queries
ADVANCED_MODEL_ARN = os.environ['PROVISIONED_MODEL_ARN']  # Provisioned throughput model
SAGEMAKER_ENDPOINT = os.environ['SAGEMAKER_ENDPOINT']  # Custom deployed model

def lambda_handler(event, context):
    """
    Model router that implements cascading based on query complexity
    """
    try:
        # Extract query from event
        query = event.get('query', '')
        if not query:
            return {
                'statusCode': 400,
                'body': json.dumps('No query provided')
            }
        
        # Step 1: Determine query complexity
        complexity_score = analyze_query_complexity(query)
        
        # Step 2: Route to appropriate model based on complexity
        if complexity_score < 3:  # Simple query
            print(f"Routing simple query (score: {complexity_score}) to {SIMPLE_MODEL_ID}")
            response = invoke_simple_model(query)
        elif complexity_score < 7:  # Moderately complex query
            print(f"Routing moderate query (score: {complexity_score}) to provisioned throughput model")
            response = invoke_advanced_model(query)
        else:  # Very complex query
            print(f"Routing complex query (score: {complexity_score}) to SageMaker custom model")
            response = invoke_sagemaker_model(query)
        
        # Add metadata to response
        response['complexity_score'] = complexity_score
        
        return {
            'statusCode': 200,
            'body': json.dumps(response)
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error processing request: {str(e)}')
        }

def analyze_query_complexity(query):
    """
    Analyze query complexity using heuristics
    Returns a score from 1-10 (simple to complex)
    """
    # Initialize base complexity
    complexity = 1
    
    # Length-based complexity
    words = query.split()
    if len(words) > 50:
        complexity += 3
    elif len(words) > 20:
        complexity += 1
    
    # Technical term complexity
    technical_terms = [
        'configuration', 'architecture', 'infrastructure', 'deployment',
        'security', 'performance', 'optimization', 'troubleshoot',
        'database', 'network', 'authentication', 'authorization'
    ]
    
    for term in technical_terms:
        if term.lower() in query.lower():
            complexity += 0.5
    
    # Question complexity
    if '?' in query:
        # Multiple questions increase complexity
        complexity += query.count('?') * 0.5
    
    # Check for complex requests
    complex_patterns = [
        r'compare .+ and',
        r'difference between',
        r'step[s]? to',
        r'how (can|do) i',
        r'best practice',
        r'optimize',
        r'troubleshoot'
    ]
    
    for pattern in complex_patterns:
        if re.search(pattern, query.lower()):
            complexity += 1
    
    # Cap at 10
    return min(10, complexity)

def invoke_simple_model(query):
    """Invoke the simple model for routine queries"""
    start_time = time.time()
    
    prompt = f"""
    You are a helpful customer support assistant. 
    Please respond to the following query concisely:
    
    {query}
    """
    
    response = bedrock_runtime.invoke_model(
        modelId=SIMPLE_MODEL_ID,
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            "prompt": prompt,
            "max_tokens_to_sample": 300,
            "temperature": 0.4,
        })
    )
    
    latency = time.time() - start_time
    response_body = json.loads(response['body'].read())
    
    return {
        'query': query,
        'response': response_body.get('completion', ''),
        'model_used': SIMPLE_MODEL_ID,
        'latency_seconds': latency
    }

def invoke_advanced_model(query):
    """Invoke the advanced model with provisioned throughput"""
    start_time = time.time()
    
    prompt = f"""
    You are an advanced customer support assistant.
    Please provide a detailed response to the following query:
    
    {query}
    """
    
    response = bedrock_runtime.invoke_model(
        modelId=ADVANCED_MODEL_ARN,
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            "prompt": prompt,
            "max_tokens_to_sample": 800,
            "temperature": 0.3,
        })
    )
    
    latency = time.time() - start_time
    response_body = json.loads(response['body'].read())
    
    return {
        'query': query,
        'response': response_body.get('completion', ''),
        'model_used': 'Provisioned Throughput Model',
        'latency_seconds': latency
    }

def invoke_sagemaker_model(query):
    """Invoke the custom SageMaker model for complex queries"""
    start_time = time.time()
    
    response = sagemaker_runtime.invoke_endpoint(
        EndpointName=SAGEMAKER_ENDPOINT,
        ContentType='application/json',
        Body=json.dumps({
            'prompt': f"You are an expert customer support specialist. Provide a comprehensive answer to this complex query: {query}",
            'max_tokens': 1024
        })
    )
    
    latency = time.time() - start_time
    response_body = json.loads(response['Body'].read().decode())
    
    return {
        'query': query,
        'response': response_body.get('response', ''),
        'model_used': 'Custom SageMaker Model',
        'latency_seconds': latency
    }
```

### Step 2: Create a CloudFormation Template for the Complete System

- Create a file named `model-cascade-template.yaml`:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: 'Multi-tier Foundation Model Deployment for Customer Support'

Parameters:
  ProvisionedModelArn:
    Type: String
    Description: ARN of the provisioned throughput model
  
  SageMakerEndpoint:
    Type: String
    Description: Name of the SageMaker endpoint

Resources:
  # IAM Role for Lambda functions
  LambdaExecutionRole:
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
        - PolicyName: SageMakerInvoke
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - 'sagemaker:InvokeEndpoint'
                Resource: !Sub 'arn:aws:sagemaker:${AWS::Region}:${AWS::AccountId}:endpoint/${SageMakerEndpoint}'

  # Model Router Lambda Function
  ModelRouterFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: 'customer-support-model-router'
      Handler: 'index.lambda_handler'
      Role: !GetAtt LambdaExecutionRole.Arn
      Code:
        ZipFile: |
          # Code from the model router Lambda function above
      Runtime: 'python3.9'
      Timeout: 60
      MemorySize: 256
      Environment:
        Variables:
          PROVISIONED_MODEL_ARN: !Ref ProvisionedModelArn
          SAGEMAKER_ENDPOINT: !Ref SageMakerEndpoint

  # API Gateway for the model router
  ApiGateway:
    Type: AWS::ApiGateway::RestApi
    Properties:
      Name: 'CustomerSupportModelRouter'
      Description: 'API for the multi-tier customer support model router'

  ApiGatewayResource:
    Type: AWS::ApiGateway::Resource
    Properties:
      RestApiId: !Ref ApiGateway
      ParentId: !GetAtt ApiGateway.RootResourceId
      PathPart: 'query'

  ApiGatewayMethod:
    Type: AWS::ApiGateway::Method
    Properties:
      RestApiId: !Ref ApiGateway
      ResourceId: !Ref ApiGatewayResource
      HttpMethod: POST
      AuthorizationType: NONE
      Integration:
        Type: AWS_PROXY
        IntegrationHttpMethod: POST
        Uri: !Sub 'arn:aws:apigateway:${AWS::Region}:lambda:path/2015-03-31/functions/${ModelRouterFunction.Arn}/invocations'

  ApiGatewayDeployment:
    Type: AWS::ApiGateway::Deployment
    DependsOn: ApiGatewayMethod
    Properties:
      RestApiId: !Ref ApiGateway
      StageName: 'prod'

  # Lambda permission for API Gateway
  LambdaPermission:
    Type: AWS::Lambda::Permission
    Properties:
      Action: 'lambda:InvokeFunction'
      FunctionName: !Ref ModelRouterFunction
      Principal: 'apigateway.amazonaws.com'
      SourceArn: !Sub 'arn:aws:execute-api:${AWS::Region}:${AWS::AccountId}:*/*/*'
```

---

## Deliverables

1. **Working Multi-Tier Customer Support AI System**:
   - Includes on-demand Lambda deployment for routine queries.

2. **Documentation**:
   - Clear instructions and code examples.

3. **Test Results**:
   - Demonstrate system performance and cost optimization.

4. **Analysis**:
   - Iterative improvements made during development.