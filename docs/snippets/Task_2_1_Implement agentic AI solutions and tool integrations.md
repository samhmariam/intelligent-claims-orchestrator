# Intelligent Customer Support System

## Scenario

### Objective

- Build an intelligent customer support system that:
  - Uses multiple specialized agents to handle different types of support requests.
  - Maintains conversation context across interactions.
  - Implements safeguards to ensure appropriate responses.
  - Coordinates between different foundation models for optimal performance.
  - Incorporates human review for sensitive actions.
  - Integrates with external tools for enhanced capabilities.

---

## Part 1: Set up the Amazon Bedrock Agent with Memory Management

### Step 1: Create Bedrock Agent

#### Code Example

```python
import boto3
import json
from botocore.exceptions import ClientError

# Initialize Bedrock client
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime')

def create_agent_session():
    """Create a new session for the Bedrock Agent"""
    try:
        response = bedrock_agent_runtime.create_session(
            agentId='your-agent-id',
            agentAliasId='your-agent-alias-id',
            sessionConfiguration={
                'enableTrace': True
            }
        )
        return response['sessionId']
    except ClientError as e:
        print(f"Error creating session: {e}")
        return None

def invoke_agent_with_memory(session_id, user_input):
    """Invoke the agent with memory of previous interactions"""
    try:
        response = bedrock_agent_runtime.invoke_agent(
            agentId='your-agent-id',
            agentAliasId='your-agent-alias-id',
            sessionId=session_id,
            inputText=user_input
        )
        
        # Process the streaming response
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    # Decode and print text response
                    text = chunk['bytes'].decode('utf-8')
                    print(text, end='')
        
        return response
    except ClientError as e:
        print(f"Error invoking agent: {e}")
        return None

# Usage example
session_id = create_agent_session()
if session_id:
    # First interaction
    invoke_agent_with_memory(session_id, "My internet connection is slow")
    
    # Second interaction - agent will remember previous context
    invoke_agent_with_memory(session_id, "What troubleshooting steps should I try?")
```

#### Agent Definition JSON

```json
{
  "agentName": "CustomerSupportAgent",
  "agentResourceRoleArn": "arn:aws:iam::123456789012:role/BedrockAgentRole",
  "foundationModel": "anthropic.claude-3-sonnet-20240229-v1:0",
  "instruction": "You are a customer support agent for an internet service provider. Help customers troubleshoot their issues by asking clarifying questions and providing step-by-step solutions.",
  "memoryConfiguration": {
    "enableMemory": true,
    "memoryType": "SESSION_MEMORY"
  }
}
```

---

## Part 2: Implement ReAct pattern with Step Functions

### Step 1: Create a Step Functions workflow

#### Workflow Definition

```json
{
  "Comment": "ReAct Pattern Implementation for Customer Support",
  "StartAt": "ParseUserRequest",
  "States": {
    "ParseUserRequest": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:ParseUserRequestFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "DetermineAction"
    },
    "DetermineAction": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:DetermineActionFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "ActionChoice"
    },
    "ActionChoice": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.actionType",
          "StringEquals": "troubleshoot",
          "Next": "TroubleshootingAction"
        },
        {
          "Variable": "$.actionType",
          "StringEquals": "billing",
          "Next": "BillingAction"
        },
        {
          "Variable": "$.actionType",
          "StringEquals": "escalate",
          "Next": "EscalateAction"
        }
      ],
      "Default": "GenerateResponse"
    },
    "TroubleshootingAction": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:TroubleshootingFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "ReasonAboutResults"
    },
    "BillingAction": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:BillingFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "ReasonAboutResults"
    },
    "EscalateAction": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:EscalateFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "ReasonAboutResults"
    },
    "ReasonAboutResults": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:ReasoningFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "NeedMoreActions"
    },
    "NeedMoreActions": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.needMoreActions",
          "BooleanEquals": true,
          "Next": "DetermineAction"
        }
      ],
      "Default": "GenerateResponse"
    },
    "GenerateResponse": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:GenerateResponseFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "End": true
    }
  }
}
```

---

## Part 3: Implement Safeguarded AI Workflows

### Step 1: Add Safeguards to Workflow

#### Lambda Function with Timeout Mechanism

```python
import boto3
import json
import time
import threading
import signal

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Function execution timed out")

def lambda_handler(event, context):
    # Set a timeout that's shorter than Lambda's timeout
    # to ensure we can handle it gracefully
    max_execution_time = 10  # seconds
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(max_execution_time)
    
    try:
        # Initialize Bedrock client
        bedrock = boto3.client('bedrock-runtime')
        
        # Extract user input
        user_input = event.get('userInput', '')
        
        # Invoke the model with safeguards
        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-sonnet-20240229-v1:0',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "messages": [
                    {
                        "role": "user",
                        "content": user_input
                    }
                ],
                "temperature": 0.2,  # Lower temperature for more controlled outputs
                "top_p": 0.9
            })
        )
        
        response_body = json.loads(response['body'].read().decode())
        model_response = response_body['content'][0]['text']
        
        # Turn off the alarm
        signal.alarm(0)
        
        return {
            "statusCode": 200,
            "body": model_response
        }
        
    except TimeoutError:
        # Handle timeout gracefully
        return {
            "statusCode": 408,
            "body": "The model is taking too long to respond. Please try a simpler query."
        }
    except Exception as e:
        # Handle other exceptions
        signal.alarm(0)  # Turn off alarm
        return {
            "statusCode": 500,
            "body": f"An error occurred: {str(e)}"
        }
```

#### Circuit Breaker Implementation

```python
import boto3
import json
import os
from datetime import datetime, timedelta
import time

# Use DynamoDB to track error rates
dynamodb = boto3.resource('dynamodb')
circuit_breaker_table = dynamodb.Table(os.environ['CIRCUIT_BREAKER_TABLE'])

def lambda_handler(event, context):
    service_name = event.get('serviceName', 'default-service')
    
    # Check if circuit is open (service disabled due to errors)
    circuit_status = get_circuit_status(service_name)
    
    if circuit_status['status'] == 'OPEN':
        # Circuit is open, check if we should try again
        if datetime.now() >= circuit_status['reset_time']:
            # Try half-open state
            update_circuit_status(service_name, 'HALF-OPEN')
        else:
            # Still in cool-down period, use fallback
            return invoke_fallback_service(event)
    
    # Circuit is CLOSED or HALF-OPEN, try the primary service
    try:
        # Call the primary service (e.g., Bedrock model)
        bedrock = boto3.client('bedrock-runtime')
        response = bedrock.invoke_model(
            modelId=event.get('modelId', 'anthropic.claude-3-sonnet-20240229-v1:0'),
            contentType='application/json',
            accept='application/json',
            body=json.dumps(event.get('requestBody', {}))
        )
        
        # If we get here in HALF-OPEN state, close the circuit
        if circuit_status['status'] == 'HALF-OPEN':
            update_circuit_status(service_name, 'CLOSED')
        
        # Record successful call
        record_call_result(service_name, True)
        
        return {
            "statusCode": 200,
            "body": json.loads(response['body'].read().decode())
        }
        
    except Exception as e:
        # Record failed call
        record_call_result(service_name, False)
        
        # Check if we need to open the circuit
        error_rate = get_error_rate(service_name)
        if error_rate > 0.5:  # 50% error rate threshold
            # Open the circuit
            reset_time = datetime.now() + timedelta(minutes=5)  # 5-minute cool-down
            update_circuit_status(service_name, 'OPEN', reset_time)
        
        # Use fallback for this request
        return invoke_fallback_service(event)

def get_circuit_status(service_name):
    try:
        response = circuit_breaker_table.get_item(
            Key={'serviceName': service_name}
        )
        if 'Item' in response:
            item = response['Item']
            return {
                'status': item.get('circuitStatus', 'CLOSED'),
                'reset_time': datetime.fromisoformat(item.get('resetTime', datetime.now().isoformat()))
            }
        return {'status': 'CLOSED', 'reset_time': datetime.now()}
    except Exception:
        return {'status': 'CLOSED', 'reset_time': datetime.now()}

def update_circuit_status(service_name, status, reset_time=None):
    try:
        item = {
            'serviceName': service_name,
            'circuitStatus': status,
            'lastUpdated': datetime.now().isoformat()
        }
        if reset_time:
            item['resetTime'] = reset_time.isoformat()
        
        circuit_breaker_table.put_item(Item=item)
    except Exception as e:
        print(f"Error updating circuit status: {e}")

def record_call_result(service_name, success):
    # Record call results for error rate calculation
    timestamp = int(time.time())
    try:
        circuit_breaker_table.update_item(
            Key={'serviceName': service_name},
            UpdateExpression="SET calls = if_not_exists(calls, :empty_list) + :call",
            ExpressionAttributeValues={
                ':empty_list': [],
                ':call': [{
                    'timestamp': timestamp,
                    'success': success
                }]
            }
        )
    except Exception as e:
        print(f"Error recording call result: {e}")

def get_error_rate(service_name):
    try:
        response = circuit_breaker_table.get_item(
            Key={'serviceName': service_name}
        )
        
        if 'Item' not in response or 'calls' not in response['Item']:
            return 0.0
        
        # Consider only calls in the last 5 minutes
        calls = response['Item']['calls']
        current_time = int(time.time())
        recent_calls = [call for call in calls if current_time - call['timestamp'] < 300]
        
        if not recent_calls:
            return 0.0
        
        # Calculate error rate
        failures = sum(1 for call in recent_calls if not call['success'])
        return failures / len(recent_calls)
    except Exception:
        return 0.0

def invoke_fallback_service(event):
    # Implement fallback logic here (e.g., use a simpler model or canned responses)
    return {
        "statusCode": 200,
        "body": {
            "message": "Using fallback service due to primary service issues",
            "fallbackResponse": "I apologize, but our advanced AI service is currently experiencing issues. Here's a basic response to your query..."
        }
    }
```

#### IAM Policy for Resource Boundaries

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": [
        "arn:aws:bedrock:*:*:model/anthropic.claude-3-sonnet-20240229-v1:0"
      ],
      "Condition": {
        "StringEquals": {
          "aws:ResourceAccount": "${AWS::AccountId}"
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "*",
      "Condition": {
        "NumericLessThan": {
          "bedrock:MaxTokens": "2000"
        },
        "NumericLessThanEquals": {
          "bedrock:Temperature": "0.5"
        }
      }
    }
  ]
}
```

---

## Part 4: Model Coordination System

### Step 1: Create a System that Coordinates Multiple Foundation Models

#### Code Example

```python
import boto3
import json
import os

# Initialize clients
bedrock = boto3.client('bedrock-runtime')
lambda_client = boto3.client('lambda')

def lambda_handler(event, context):
    """
    Model coordination system that selects the appropriate model based on the task
    """
    user_input = event.get('userInput', '')
    task_type = determine_task_type(user_input)
    
    # Select model based on task type
    if task_type == 'classification':
        result = invoke_classification_model(user_input)
    elif task_type == 'generation':
        result = invoke_generation_model(user_input)
    elif task_type == 'qa':
        result = invoke_qa_model(user_input)
    else:
        # Default to general purpose model
        result = invoke_general_model(user_input)
    
    return {
        'statusCode': 200,
        'body': result
    }

def determine_task_type(user_input):
    """
    Determine the type of task based on user input
    """
    # Use a lightweight model to classify the task
    response = bedrock.invoke_model(
        modelId='amazon.titan-text-express-v1',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            "inputText": f"Classify the following user request into one of these categories: classification, generation, qa, general.\n\nUser request: {user_input}\n\nCategory:",
            "textGenerationConfig": {
                "maxTokenCount": 10,
                "temperature": 0.0,
                "topP": 0.9
            }
        })
    )
    
    response_body = json.loads(response['body'].read().decode())
    task_type = response_body['results'][0]['outputText'].strip().lower()
    
    # Normalize the response
    if 'class' in task_type:
        return 'classification'
    elif 'gen' in task_type:
        return 'generation'
    elif 'qa' in task_type or 'question' in task_type:
        return 'qa'
    else:
        return 'general'

def invoke_classification_model(user_input):
    """
    Use a model optimized for classification tasks
    """
    response = bedrock.invoke_model(
        modelId='amazon.titan-text-express-v1',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            "inputText": user_input,
            "textGenerationConfig": {
                "maxTokenCount": 100,
                "temperature": 0.0,
                "topP": 0.9
            }
        })
    )
    
    return json.loads(response['body'].read().decode())

def invoke_generation_model(user_input):
    """
    Use a model optimized for creative generation
    """
    response = bedrock.invoke_model(
        modelId='anthropic.claude-3-sonnet-20240229-v1:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": user_input
                }
            ],
            "temperature": 0.7
        })
    )
    
    return json.loads(response['body'].read().decode())

def invoke_qa_model(user_input):
    """
    Use a model optimized for question answering
    """
    response = bedrock.invoke_model(
        modelId='anthropic.claude-3-haiku-20240307-v1:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [
                {
                    "role": "user",
                    "content": user_input
                }
            ],
            "temperature": 0.2
        })
    )
    
    return json.loads(response['body'].read().decode())

def invoke_general_model(user_input):
    """
    Use a general purpose model
    """
    response = bedrock.invoke_model(
        modelId='anthropic.claude-3-sonnet-20240229-v1:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "messages": [
                {
                    "role": "user",
                    "content": user_input
                }
            ],
            "temperature": 0.4
        })
    )
    
    return json.loads(response['body'].read().decode())
```

---

## Part 5: Collaborative AI System with Human-in-the-Loop

### Step 1: Create a Step Functions Workflow that Incorporates Human Review

#### Workflow Definition

```json
{
  "Comment": "Human-in-the-Loop AI Workflow",
  "StartAt": "GenerateInitialResponse",
  "States": {
    "GenerateInitialResponse": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:GenerateResponseFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "EvaluateConfidence"
    },
    "EvaluateConfidence": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:EvaluateConfidenceFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "ConfidenceCheck"
    },
    "ConfidenceCheck": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.confidence",
          "NumericGreaterThan": 0.9,
          "Next": "DeliverResponse"
        },
        {
          "Variable": "$.sensitivity",
          "StringEquals": "HIGH",
          "Next": "RequestHumanReview"
        }
      ],
      "Default": "RequestHumanReview"
    },
    "RequestHumanReview": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:CreateHumanTaskFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "WaitForHumanReview"
    },
    "WaitForHumanReview": {
      "Type": "Wait",
      "SecondsPath": "$.waitTime",
      "Next": "CheckHumanReviewStatus"
    },
    "CheckHumanReviewStatus": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:CheckHumanReviewStatusFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "IsReviewComplete"
    },
    "IsReviewComplete": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.reviewStatus",
          "StringEquals": "COMPLETED",
          "Next": "ProcessHumanFeedback"
        }
      ],
      "Default": "WaitForHumanReview"
    },
    "ProcessHumanFeedback": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:ProcessHumanFeedbackFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "Next": "DeliverResponse"
    },
    "DeliverResponse": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:DeliverResponseFunction",
        "Payload": {
          "input.$": "$"
        }
      },
      "End": true
    }
  }
}


```

---

## Deliverables

1. **Working Intelligent Customer Support System**:
   - Includes memory management, ReAct pattern, and safeguards.

2. **Documentation**:
   - Clear instructions and code examples.

3. **Test Results**:
   - Demonstrate system resilience and effectiveness.

4. **Analysis**:
   - Iterative improvements made during development.