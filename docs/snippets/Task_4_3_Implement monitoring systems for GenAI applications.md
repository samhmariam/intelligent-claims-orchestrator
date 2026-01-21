# Task 4.3: Implement monitoring systems for GenAI applications

## Prerequisites

- AWS account with appropriate permissions.
- Basic knowledge of Python programming.
- Familiarity with AWS services (Amazon Bedrock, CloudWatch, Lambda, etc.).
- Understanding of foundation models and generative AI concepts.

## Project architecture

```text
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Customer Support   │────▶│  Request Router     │────▶│  Amazon Bedrock     │
│  Application        │     │  (Lambda)           │     │  Foundation Models  │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
         │                           │                           │
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Comprehensive Monitoring System                       │
├─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│ Operational     │ Performance     │ Quality         │ Business Impact │
│ Metrics         │ Tracing         │ Monitoring      │ Metrics         │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
         │                 │                 │                 │
         └─────────────────┼─────────────────┼─────────────────┘
                           │                 │
                           ▼                 ▼
                  ┌─────────────────┐ ┌─────────────────┐
                  │ CloudWatch      │ │ QuickSight      │
                  │ Dashboards      │ │ Visualizations  │
                  └─────────────────┘ └─────────────────┘
```

## Module 1: Set up holistic observability

### Step 1: Create a CloudWatch Metrics Publisher for Operational Metrics

First, let's create a function to publish operational metrics to CloudWatch:

```python
import boto3
import time
import json
import uuid
from datetime import datetime
from typing import Dict, List, Any

class GenAIMetricsPublisher:
    """Class for publishing GenAI-specific metrics to CloudWatch"""
    
    def __init__(self, namespace="GenAICustomerSupport"):
        """Initialize the metrics publisher"""
        self.cloudwatch = boto3.client('cloudwatch')
        self.namespace = namespace
    
    def publish_operational_metrics(self, metrics_data: Dict[str, Any]) -> bool:
        """
        Publish operational metrics to CloudWatch.
        
        Args:
            metrics_data: Dictionary containing operational metrics
            
        Returns:
            Boolean indicating success or failure
        """
        try:
            metric_data = []
            
            # Process each metric in the data
            for metric_name, metric_value in metrics_data.items():
                # Skip if the metric value is not a number
                if not isinstance(metric_value, (int, float)):
                    continue
                
                # Add dimensions if available
                dimensions = []
                if "dimensions" in metrics_data and isinstance(metrics_data["dimensions"], dict):
                    for dim_name, dim_value in metrics_data["dimensions"].items():
                        dimensions.append({
                            'Name': dim_name,
                            'Value': str(dim_value)
                        })
                
                # Create the metric data point
                metric_data.append({
                    'MetricName': metric_name,
                    'Dimensions': dimensions,
                    'Value': float(metric_value),
                    'Unit': metrics_data.get(f"{metric_name}_unit", "None"),
                    'Timestamp': datetime.utcnow()
                })
            
            # Publish metrics in batches (maximum 20 per request)
            batch_size = 20
            for i in range(0, len(metric_data), batch_size):
                batch = metric_data[i:i + batch_size]
                self.cloudwatch.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=batch
                )
            
            return True
        except Exception as e:
            print(f"Error publishing operational metrics: {e}")
            return False
    
    def track_request(self, 
                     request_id: str, 
                     model_id: str, 
                     prompt_tokens: int, 
                     completion_tokens: int, 
                     latency_ms: float,
                     error_occurred: bool = False) -> bool:
        """
        Track a single model request with key metrics.
        
        Args:
            request_id: Unique identifier for the request
            model_id: The model ID used
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            latency_ms: Request latency in milliseconds
            error_occurred: Whether an error occurred
            
        Returns:
            Boolean indicating success or failure
        """
        try:
            # Create dimensions for this request
            dimensions = [
                {'Name': 'ModelId', 'Value': model_id},
                {'Name': 'RequestId', 'Value': request_id}
            ]
            
            # Create metric data
            metric_data = [
                {
                    'MetricName': 'PromptTokens',
                    'Dimensions': dimensions,
                    'Value': prompt_tokens,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'CompletionTokens',
                    'Dimensions': dimensions,
                    'Value': completion_tokens,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'TotalTokens',
                    'Dimensions': dimensions,
                    'Value': prompt_tokens + completion_tokens,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'Latency',
                    'Dimensions': dimensions,
                    'Value': latency_ms,
                    'Unit': 'Milliseconds',
                    'Timestamp': datetime.utcnow()
                }
            ]
            
            # Add error metric if an error occurred
            if error_occurred:
                metric_data.append({
                    'MetricName': 'ErrorCount',
                    'Dimensions': dimensions,
                    'Value': 1,
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                })
            
            # Publish metrics
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=metric_data
            )
            
            return True
        except Exception as e:
            print(f"Error tracking request: {e}")
            return False

# Test the metrics publisher
def test_metrics_publisher():
    publisher = GenAIMetricsPublisher()
    
    # Test publishing operational metrics
    metrics_data = {
        "RequestCount": 1,
        "SuccessCount": 1,
        "PromptTokens": 100,
        "CompletionTokens": 200,
        "TotalTokens": 300,
        "Latency": 1200.5,
        "dimensions": {
            "ModelId": "anthropic.claude-v2",
            "QueryType": "customer_support"
        }
    }
    
    success = publisher.publish_operational_metrics(metrics_data)
    print(f"Published operational metrics: {success}")
    
    # Test tracking a single request
    request_id = str(uuid.uuid4())
    success = publisher.track_request(
        request_id=request_id,
        model_id="anthropic.claude-v2",
        prompt_tokens=100,
        completion_tokens=200,
        latency_ms=1200.5
    )
    print(f"Tracked request {request_id}: {success}")

if __name__ == "__main__":
    test_metrics_publisher()
```

### Step 2: Implement Performance Tracing with X-Ray

Let's create a function to trace performance across the application:

```python
import boto3
import json
import time
import os
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core import patch_all

# Patch all supported libraries for X-Ray tracing
patch_all()

class GenAIPerformanceTracer:
    """Class for tracing performance of GenAI applications"""
    
    def __init__(self):
        """Initialize the performance tracer"""
        # Configure X-Ray
        if not xray_recorder.is_disabled():
            xray_recorder.configure(
                service='GenAICustomerSupport',
                sampling=True,
                context_missing='LOG_ERROR'
            )
    
    def trace_request(self, func):
        """
        Decorator to trace a function execution with X-Ray.
        
        Args:
            func: The function to trace
            
        Returns:
            Wrapped function with tracing
        """
        def wrapper(*args, **kwargs):
            # Start a segment
            segment_name = func.__name__
            
            # Get the request ID if available
            request_id = kwargs.get('request_id', 'unknown')
            
            # Start a subsegment for this function
            subsegment = xray_recorder.begin_subsegment(segment_name)
            
            try:
                # Add request metadata
                if subsegment:
                    subsegment.put_annotation('request_id', request_id)
                    
                    # Add any model ID if available
                    model_id = kwargs.get('model_id')
                    if model_id:
                        subsegment.put_annotation('model_id', model_id)
                
                # Execute the function
                start_time = time.time()
                result = func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000  # Convert to ms
                
                # Add execution time metadata
                if subsegment:
                    subsegment.put_metadata('execution_time_ms', execution_time)
                    
                    # Add result metadata (be careful with large responses)
                    if isinstance(result, dict) and 'response' in result:
                        # Truncate response if needed to avoid large metadata
                        response_preview = result['response'][:500] + '...' if len(result['response']) > 500 else result['response']
                        subsegment.put_metadata('response_preview', response_preview)
                
                return result
            except Exception as e:
                # Record the error
                if subsegment:
                    subsegment.add_exception(e, stack=True)
                raise
            finally:
                # Close the subsegment
                xray_recorder.end_subsegment()
        
        return wrapper
    
    def trace_bedrock_request(self, model_id, prompt, response, latency_ms, metadata=None):
        """
        Create a trace for a Bedrock model request.
        
        Args:
            model_id: The model ID used
            prompt: The prompt sent to the model
            response: The response from the model
            latency_ms: Request latency in milliseconds
            metadata: Additional metadata to include in the trace
            
        Returns:
            None
        """
        subsegment = xray_recorder.begin_subsegment('bedrock_model_invocation')
        
        try:
            if subsegment:
                # Add basic annotations
                subsegment.put_annotation('model_id', model_id)
                subsegment.put_annotation('latency_ms', latency_ms)
                
                # Add prompt and response as metadata (truncated to avoid large traces)
                prompt_preview = prompt[:500] + '...' if len(prompt) > 500 else prompt
                response_preview = response[:500] + '...' if len(response) > 500 else response
                
                subsegment.put_metadata('prompt', prompt_preview)
                subsegment.put_metadata('response', response_preview)
                
                # Add additional metadata if provided
                if metadata:
                    for key, value in metadata.items():
                        subsegment.put_metadata(key, value)
        finally:
            xray_recorder.end_subsegment()

# Example usage
@xray_recorder.capture('example_function')
def example_traced_function(request_id, model_id, prompt):
    tracer = GenAIPerformanceTracer()
    
    # Simulate model invocation
    start_time = time.time()
    time.sleep(1)  # Simulate processing time
    response = f"This is a simulated response for prompt: {prompt[:20]}..."
    latency_ms = (time.time() - start_time) * 1000
    
    # Trace the Bedrock request
    tracer.trace_bedrock_request(
        model_id=model_id,
        prompt=prompt,
        response=response,
        latency_ms=latency_ms,
        metadata={
            'prompt_tokens': len(prompt.split()),
            'completion_tokens': len(response.split())
        }
    )
    
    return {
        'request_id': request_id,
        'model_id': model_id,
        'response': response,
        'latency_ms': latency_ms
    }

# Test the performance tracer
def test_performance_tracer():
    request_id = str(uuid.uuid4())
    model_id = "anthropic.claude-v2"
    prompt = "How can I reset my AWS account password?"
    
    tracer = GenAIPerformanceTracer()
    traced_function = tracer.trace_request(example_traced_function)
    
    result = traced_function(request_id=request_id, model_id=model_id, prompt=prompt)
    print(f"Traced function result: {result}")

if __name__ == "__main__":
    test_performance_tracer()
```

### Step 3: Create a Business Impact Metrics Tracker

Let's implement a system to track business impact metrics:

```python
class BusinessImpactTracker:
    """Class for tracking business impact metrics for GenAI applications"""
    
    def __init__(self, namespace="GenAIBusinessImpact"):
        """Initialize the business impact tracker"""
        self.cloudwatch = boto3.client('cloudwatch')
        self.namespace = namespace
    
    def track_user_satisfaction(self, 
                               conversation_id: str, 
                               rating: int, 
                               feedback: str = None,
                               metadata: Dict[str, Any] = None) -> bool:
        """
        Track user satisfaction metrics.
        
        Args:
            conversation_id: Unique identifier for the conversation
            rating: User rating (1-5)
            feedback: Optional user feedback text
            metadata: Additional metadata about the conversation
            
        Returns:
            Boolean indicating success or failure
        """
        try:
            # Validate rating
            if not isinstance(rating, int) or rating < 1 or rating > 5:
                print("Rating must be an integer between 1 and 5")
                return False
            
            # Create dimensions
            dimensions = [
                {'Name': 'ConversationId', 'Value': conversation_id}
            ]
            
            # Add additional dimensions from metadata
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, (str, int, float, bool)):
                        dimensions.append({
                            'Name': key,
                            'Value': str(value)
                        })
            
            # Create metric data
            metric_data = [
                {
                    'MetricName': 'UserSatisfactionRating',
                    'Dimensions': dimensions,
                    'Value': float(rating),
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow()
                }
            ]
            
            # Publish metrics
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=metric_data
            )
            
            # Store feedback text in CloudWatch Logs if provided
            if feedback:
                logs_client = boto3.client('logs')
                log_group_name = f"/genai/{self.namespace}/UserFeedback"
                
                # Create log group if it doesn't exist
                try:
                    logs_client.create_log_group(logGroupName=log_group_name)
                except logs_client.exceptions.ResourceAlreadyExistsException:
                    pass
                
                # Create log stream if it doesn't exist
                log_stream_name = datetime.utcnow().strftime('%Y/%m/%d')
                try:
                    logs_client.create_log_stream(
                        logGroupName=log_group_name,
                        logStreamName=log_stream_name
                    )
                except logs_client.exceptions.ResourceAlreadyExistsException:
                    pass
                
                # Log the feedback
                logs_client.put_log_events(
                    logGroupName=log_group_name,
                    logStreamName=log_stream_name,
                    logEvents=[
                        {
                            'timestamp': int(datetime.utcnow().timestamp() * 1000),
                            'message': json.dumps({
                                'conversation_id': conversation_id,
                                'rating': rating,
                                'feedback': feedback,
                                'metadata': metadata or {}
                            })
                        }
                    ]
                )
            
            return True
        except Exception as e:
            print(f"Error tracking user satisfaction: {e}")
            return False
    
    def track_business_metrics(self, 
                              metric_name: str, 
                              value: float,
                              dimensions: Dict[str, str] = None) -> bool:
        """
        Track custom business metrics.
        
        Args:
            metric_name: Name of the business metric
            value: Value of the metric
            dimensions: Dictionary of dimension name-value pairs
            
        Returns:
            Boolean indicating success or failure
        """
        try:
            # Create dimensions
            dimension_list = []
            if dimensions:
                for key, value in dimensions.items():
                    dimension_list.append({
                        'Name': key,
                        'Value': str(value)
                    })
            
            # Create metric data
            metric_data = [
                {
                    'MetricName': metric_name,
                    'Dimensions': dimension_list,
                    'Value': float(value),
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow()
                }
            ]
            
            # Publish metrics
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=metric_data
            )
            
            return True
        except Exception as e:
            print(f"Error tracking business metric: {e}")
            return False

# Test the business impact tracker
def test_business_impact_tracker():
    tracker = BusinessImpactTracker()
    
    # Test tracking user satisfaction
    conversation_id = str(uuid.uuid4())
    success = tracker.track_user_satisfaction(
        conversation_id=conversation_id,
        rating=4,
        feedback="The AI was very helpful in resolving my AWS password reset issue.",
        metadata={
            "QueryType": "password_reset",
            "ModelId": "anthropic.claude-v2",
            "UserType": "new_customer"
        }
    )
    print(f"Tracked user satisfaction: {success}")
    
    # Test tracking business metrics
    success = tracker.track_business_metrics(
        metric_name="IssueResolutionRate",
        value=0.85,
        dimensions={
            "QueryType": "password_reset",
            "ModelId": "anthropic.claude-v2"
        }
    )
    print(f"Tracked business metric: {success}")
    
    success = tracker.track_business_metrics(
        metric_name="TimeToResolution",
        value=120,  # seconds
        dimensions={
            "QueryType": "password_reset",
            "ModelId": "anthropic.claude-v2"
        }
    )
    print(f"Tracked business metric: {success}")

if __name__ == "__main__":
    test_business_impact_tracker()
```

## Module 2: Implement comprehensive GenAI monitoring

### Step 1: Create a Token Usage Monitor

Let's implement a system to track token usage and detect anomalies:

```python
class TokenUsageMonitor:
    """Class for monitoring token usage in GenAI applications"""
    
    def __init__(self, namespace="GenAITokenUsage"):
        """Initialize the token usage monitor"""
        self.cloudwatch = boto3.client('cloudwatch')
        self.namespace = namespace
        self.token_history = {}  # In-memory cache of recent token usage
    
    def track_token_usage(self, 
                         model_id: str, 
                         prompt_tokens: int, 
                         completion_tokens: int,
                         metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Track token usage and detect anomalies.
        
        Args:
            model_id: The model ID used
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            metadata: Additional metadata about the request
            
        Returns:
            Dictionary with tracking results and anomaly detection
        """
        try:
            # Calculate total tokens
            total_tokens = prompt_tokens + completion_tokens
            
            # Create dimensions
            dimensions = [
                {'Name': 'ModelId', 'Value': model_id}
            ]
            
            # Add additional dimensions from metadata
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, (str, int, float, bool)):
                        dimensions.append({
                            'Name': key,
                            'Value': str(value)
                        })
            
            # Create metric data
            metric_data = [
                {
                    'MetricName': 'PromptTokens',
                    'Dimensions': dimensions,
                    'Value': float(prompt_tokens),
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'CompletionTokens',
                    'Dimensions': dimensions,
                    'Value': float(completion_tokens),
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'TotalTokens',
                    'Dimensions': dimensions,
                    'Value': float(total_tokens),
                    'Unit': 'Count',
                    'Timestamp': datetime.utcnow()
                }
            ]
            
            # Calculate token ratio (completion/prompt)
            if prompt_tokens > 0:
                token_ratio = completion_tokens / prompt_tokens
                metric_data.append({
                    'MetricName': 'TokenRatio',
                    'Dimensions': dimensions,
                    'Value': float(token_ratio),
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow()
                })
            
            # Publish metrics
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=metric_data
            )
            
            # Update token history for this model
            model_key = model_id
            if model_key not in self.token_history:
                self.token_history[model_key] = {
                    'prompt_tokens': [],
                    'completion_tokens': [],
                    'total_tokens': [],
                    'token_ratios': []
                }
            
            # Keep last 100 entries for each metric
            history = self.token_history[model_key]
            history['prompt_tokens'].append(prompt_tokens)
            history['completion_tokens'].append(completion_tokens)
            history['total_tokens'].append(total_tokens)
            if prompt_tokens > 0:
                history['token_ratios'].append(token_ratio)
            
            # Trim history if needed
            max_history = 100
            if len(history['prompt_tokens']) > max_history:
                history['prompt_tokens'] = history['prompt_tokens'][-max_history:]
                history['completion_tokens'] = history['completion_tokens'][-max_history:]
                history['total_tokens'] = history['total_tokens'][-max_history:]
                history['token_ratios'] = history['token_ratios'][-max_history:]
            
            # Detect anomalies if we have enough history
            anomalies = {}
            if len(history['total_tokens']) >= 10:
                # Calculate mean and standard deviation
                mean_total = sum(history['total_tokens']) / len(history['total_tokens'])
                std_total = (sum((x - mean_total) ** 2 for x in history['total_tokens']) / len(history['total_tokens'])) ** 0.5
                
                # Check if current usage is anomalous (> 2 standard deviations from mean)
                if abs(total_tokens - mean_total) > 2 * std_total:
                    anomalies['total_tokens'] = {
                        'current': total_tokens,
                        'mean': mean_total,
                        'std_dev': std_total,
                        'z_score': (total_tokens - mean_total) / std_total if std_total > 0 else 0
                    }
                    
                    # Log anomaly to CloudWatch
                    self.cloudwatch.put_metric_data(
                        Namespace=self.namespace,
                        MetricData=[
                            {
                                'MetricName': 'TokenUsageAnomaly',
                                'Dimensions': dimensions,
                                'Value': 1.0,
                                'Unit': 'Count',
                                'Timestamp': datetime.utcnow()
                            }
                        ]
                    )
            
            return {
                'tracked': True,
                'model_id': model_id,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'token_ratio': token_ratio if prompt_tokens > 0 else None,
                'anomalies': anomalies
            }
        except Exception as e:
            print(f"Error tracking token usage: {e}")
            return {
                'tracked': False,
                'error': str(e)
            }
    
    def get_token_usage_statistics(self, model_id: str) -> Dict[str, Any]:
        """
        Get token usage statistics for a model.
        
        Args:
            model_id: The model ID
            
        Returns:
            Dictionary with token usage statistics
        """
        model_key = model_id
        
        if model_key not in self.token_history or not self.token_history[model_key]['total_tokens']:
            return {
                'model_id': model_id,
                'statistics': None,
                'error': 'No history available for this model'
            }
        
        history = self.token_history[model_key]
        
        # Calculate statistics
        prompt_tokens = history['prompt_tokens']
        completion_tokens = history['completion_tokens']
        total_tokens = history['total_tokens']
        
        # Calculate averages
        request_count = history['request_count']
        avg_prompt_tokens = sum(prompt_tokens) / request_count if request_count > 0 else 0
        avg_completion_tokens = sum(completion_tokens) / request_count if request_count > 0 else 0
        avg_total_tokens = sum(total_tokens) / request_count if request_count > 0 else 0
        
        return {
            'model_id': model_id,
            'statistics': {
                'request_count': request_count,
                'total_prompt_tokens': sum(prompt_tokens),
                'total_completion_tokens': sum(completion_tokens),
                'total_tokens': sum(total_tokens),
                'avg_prompt_tokens': avg_prompt_tokens,
                'avg_completion_tokens': avg_completion_tokens,
                'avg_total_tokens': avg_total_tokens,
                'max_prompt_tokens': max(prompt_tokens) if prompt_tokens else 0,
                'max_completion_tokens': max(completion_tokens) if completion_tokens else 0,
                'max_total_tokens': max(total_tokens) if total_tokens else 0
            }
        }

# Test the token usage monitor
def test_token_usage_monitor():
    monitor = TokenUsageMonitor()
    
    # Simulate tracking multiple requests
    model_id = "anthropic.claude-v2"
    
    test_requests = [
        {"prompt_tokens": 100, "completion_tokens": 200},
        {"prompt_tokens": 150, "completion_tokens": 250},
        {"prompt_tokens": 120, "completion_tokens": 180},
        {"prompt_tokens": 200, "completion_tokens": 300},
    ]
    
    for i, req in enumerate(test_requests, 1):
        request_id = f"request-{i}"
        result = monitor.track_token_usage(
            request_id=request_id,
            model_id=model_id,
            prompt_tokens=req["prompt_tokens"],
            completion_tokens=req["completion_tokens"]
        )
        print(f"Tracked request {request_id}: {result['tracked']}")
    
    # Get statistics
    stats = monitor.get_token_usage_statistics(model_id)
    print(f"\nToken usage statistics for {model_id}:")
    print(json.dumps(stats, indent=2))

if __name__ == "__main__":
    test_token_usage_monitor()
```