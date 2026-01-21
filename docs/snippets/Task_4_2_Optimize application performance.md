# Task 4.2: Optimize application performance

## Prerequisites

You'll need:

- AWS account with appropriate permissions.
- Basic knowledge of Python programming.
- Familiarity with AWS services (Amazon Bedrock, Lambda, DynamoDB, etc.).
- Understanding of foundation models and generative AI concepts.

## Project architecture

```text
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  API Gateway        │────▶│  Request Router     │────▶│  Query Preprocessor │
└─────────────────────┘     │  (Lambda)           │     │  (Lambda)           │
                            └─────────────────────┘     └─────────────────────┘
                                      │                           │
                                      ▼                           ▼
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Pre-computation    │◀───▶│  Model Selector     │◀───▶│  Knowledge Base     │
│  Cache (DynamoDB)   │     │  (Lambda)           │     │  (Vector DB)        │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                      │
                      ┌───────────────┼───────────────┐
                      ▼               ▼               ▼
         ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
         │ Fast Model      │ │ Standard Model  │ │ Advanced Model  │
         │ (Low Latency)   │ │ (Balanced)      │ │ (High Quality)  │
         └─────────────────┘ └─────────────────┘ └─────────────────┘
                      │               │               │
                      └───────────────┼───────────────┘
                                      ▼
                            ┌─────────────────────┐
                            │  Response           │
                            │  Optimization       │
                            └─────────────────────┘
                                      │
                                      ▼
                            ┌─────────────────────┐
                            │  Performance        │
                            │  Monitoring         │
                            └─────────────────────┘
```

## Part 1: Response AI system implementation

### Step 1: Set Up Response Streaming for Improved User Experience

First, let's implement response streaming to reduce perceived latency:

```python
import boto3
import json
import time
import os
from typing import Dict, List, Any, Generator

def stream_bedrock_response(prompt: str, model_id: str = "anthropic.claude-instant-v1") -> Generator[str, None, None]:
    """
    Stream responses from Amazon Bedrock to reduce perceived latency.
    
    Args:
        prompt: The user prompt
        model_id: The model ID to use
        
    Returns:
        Generator yielding response chunks
    """
    bedrock_runtime = boto3.client('bedrock-runtime')
    
    # Prepare the request based on model type
    if "anthropic" in model_id:
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "temperature": 0.7,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
    elif "amazon.titan" in model_id:
        request_body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 1000,
                "temperature": 0.7,
                "topP": 0.9
            }
        }
    else:
        # Default format for other models
        request_body = {
            "prompt": prompt,
            "max_tokens_to_sample": 1000,
            "temperature": 0.7,
            "top_p": 0.9
        }
    
    try:
        # Call the model with streaming enabled
        response = bedrock_runtime.invoke_model_with_response_stream(
            modelId=model_id,
            body=json.dumps(request_body)
        )
        
        # Process the streaming response
        stream = response.get('body')
        if stream:
            for event in stream:
                chunk = event.get('chunk')
                if chunk:
                    chunk_obj = json.loads(chunk.get('bytes').decode())
                    
                    # Extract the text based on model type
                    if "anthropic" in model_id:
                        if 'content' in chunk_obj and len(chunk_obj['content']) > 0:
                            content = chunk_obj['content'][0].get('text', '')
                            yield content
                    elif "amazon.titan" in model_id:
                        if 'outputText' in chunk_obj:
                            yield chunk_obj['outputText']
                    else:
                        if 'completion' in chunk_obj:
                            yield chunk_obj['completion']
        
    except Exception as e:
        yield f"Error streaming response: {str(e)}"

# Example usage (in a real application, this would be part of a web server)
def example_streaming_handler(prompt: str):
    print("Starting response streaming...")
    for chunk in stream_bedrock_response(prompt):
        print(chunk, end='', flush=True)
    print("\nStreaming complete.")

# Test the function
if __name__ == "__main__":
    test_prompt = "Explain how to optimize Amazon S3 performance in 5 steps."
    example_streaming_handler(test_prompt)
```

### Step 2: Implement Pre-computation for Common Queries

Let's create a system to pre-compute responses for common queries:

```python
import hashlib
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timedelta

class PrecomputationCache:
    """Class to manage pre-computation of common queries"""
    
    def __init__(self, table_name="CustomerSupportPrecomputedResponses"):
        """Initialize the cache with DynamoDB table"""
        self.dynamodb = boto3.resource('dynamodb')
        self.table_name = table_name
        self.ensure_table_exists()
        self.table = self.dynamodb.Table(table_name)
        
    def ensure_table_exists(self):
        """Create the DynamoDB table if it doesn't exist"""
        try:
            # Check if table exists
            client = boto3.client('dynamodb')
            client.describe_table(TableName=self.table_name)
        except client.exceptions.ResourceNotFoundException:
            # Create table if it doesn't exist
            self.dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {
                        'AttributeName': 'query_hash',
                        'KeyType': 'HASH'
                    }
                ],
                AttributeDefinitions=[
                    {
                        'AttributeName': 'query_hash',
                        'AttributeType': 'S'
                    }
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
            # Wait for table to be created
            waiter = client.get_waiter('table_exists')
            waiter.wait(TableName=self.table_name)
    
    def get_query_hash(self, query: str) -> str:
        """Generate a hash for the query"""
        # Normalize the query by lowercasing and removing extra whitespace
        normalized_query = " ".join(query.lower().split())
        return hashlib.md5(normalized_query.encode('utf-8')).hexdigest()
    
    def get_precomputed_response(self, query: str) -> Dict[str, Any]:
        """Get a precomputed response if it exists and is not expired"""
        query_hash = self.get_query_hash(query)
        
        try:
            response = self.table.get_item(Key={'query_hash': query_hash})
            
            if 'Item' in response:
                item = response['Item']
                # Check if the response is expired
                expiry_time = datetime.fromisoformat(item['expiry_time'])
                if datetime.now() < expiry_time:
                    return {
                        'found': True,
                        'response': item['response'],
                        'model_id': item['model_id'],
                        'created_at': item['created_at']
                    }
            
            return {'found': False}
        except Exception as e:
            print(f"Error retrieving precomputed response: {e}")
            return {'found': False, 'error': str(e)}
    
    def store_precomputed_response(self, query: str, response: str, model_id: str, ttl_days: int = 7) -> bool:
        """Store a precomputed response"""
        query_hash = self.get_query_hash(query)
        created_at = datetime.now().isoformat()
        expiry_time = (datetime.now() + timedelta(days=ttl_days)).isoformat()
        
        try:
            self.table.put_item(
                Item={
                    'query_hash': query_hash,
                    'query': query,
                    'response': response,
                    'model_id': model_id,
                    'created_at': created_at,
                    'expiry_time': expiry_time
                }
            )
            return True
        except Exception as e:
            print(f"Error storing precomputed response: {e}")
            return False
    
    def precompute_common_queries(self, common_queries: List[str], model_id: str) -> Dict[str, Any]:
        """Precompute responses for a list of common queries"""
        bedrock_runtime = boto3.client('bedrock-runtime')
        results = {
            'successful': 0,
            'failed': 0,
            'details': []
        }
        
        for query in common_queries:
            try:
                # Check if we already have a valid precomputed response
                existing = self.get_precomputed_response(query)
                if existing.get('found', False):
                    results['successful'] += 1
                    results['details'].append({
                        'query': query,
                        'status': 'already_exists',
                        'created_at': existing['created_at']
                    })
                    continue
                
                # Generate a new response
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "temperature": 0.2,  # Lower temperature for more consistent responses
                    "messages": [
                        {
                            "role": "user",
                            "content": query
                        }
                    ]
                }
                
                response = bedrock_runtime.invoke_model(
                    modelId=model_id,
                    body=json.dumps(request_body)
                )
                
                response_body = json.loads(response['body'].read())
                response_text = response_body['content'][0]['text']
                
                # Store the precomputed response
                success = self.store_precomputed_response(query, response_text, model_id)
                
                if success:
                    results['successful'] += 1
                    results['details'].append({
                        'query': query,
                        'status': 'computed_and_stored',
                        'created_at': datetime.now().isoformat()
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'query': query,
                        'status': 'failed_to_store'
                    })
                
                # Add a small delay to avoid rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'query': query,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return results

# Test the precomputation cache
def test_precomputation_cache():
    cache = PrecomputationCache()
    
    # List of common customer support queries about AWS services
    common_queries = [
        "What is Amazon S3?",
        "How do I create an EC2 instance?",
        "What is the difference between RDS and DynamoDB?",
        "How do I set up CloudFront?",
        "What is AWS Lambda?"
    ]
    
    # Precompute responses
    results = cache.precompute_common_queries(common_queries, "anthropic.claude-instant-v1")
    print(f"Precomputation results: {json.dumps(results, indent=2)}")
    
    # Test retrieving a precomputed response
    test_query = "What is Amazon S3?"
    result = cache.get_precomputed_response(test_query)
    
    if result.get('found', False):
        print(f"\nFound precomputed response for '{test_query}':")
        print(f"Model: {result['model_id']}")
        print(f"Created at: {result['created_at']}")
        print(f"Response: {result['response'][:100]}...")  # Show first 100 chars
    else:
        print(f"\nNo precomputed response found for '{test_query}'")

if __name__ == "__main__":
    test_precomputation_cache()
```

### Step 3: Implement Model Selection Based on Latency Requirements

Let's create a function to select models based on latency requirements:

```python
def select_model_for_latency(query: str, latency_requirement: str = "standard") -> Dict[str, Any]:
    """
    Select the appropriate model based on latency requirements.
    
    Args:
        query: The user query
        latency_requirement: The latency requirement (low, standard, or quality)
        
    Returns:
        Dictionary with selected model and parameters
    """
    # Define available models with their latency characteristics
    models = {
        "low_latency": {
            "model_id": "anthropic.claude-instant-v1",
            "avg_response_time": 0.5,  # seconds per request (approximate)
            "max_tokens": 500,
            "temperature": 0.4,
            "streaming": True
        },
        "standard": {
            "model_id": "anthropic.claude-v2",
            "avg_response_time": 1.2,  # seconds per request (approximate)
            "max_tokens": 1000,
            "temperature": 0.7,
            "streaming": True
        },
        "quality": {
            "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
            "avg_response_time": 2.5,  # seconds per request (approximate)
            "max_tokens": 2000,
            "temperature": 0.7,
            "streaming": True
        }
    }
    
    # Map latency requirement to model category
    latency_map = {
        "low": "low_latency",
        "standard": "standard",
        "high": "quality"
    }
    
    # Get the appropriate model category
    model_category = latency_map.get(latency_requirement.lower(), "standard")
    
    # Get the model configuration
    model_config = models[model_category]
    
    # Add query-specific adjustments if needed
    query_lower = query.lower()
    
    # For very short queries, we can reduce max_tokens
    if len(query.split()) < 5:
        model_config["max_tokens"] = max(200, model_config["max_tokens"] // 2)
    
    # For complex technical queries, adjust temperature for more precise answers
    if any(term in query_lower for term in ["how", "explain", "difference", "compare", "architecture"]):
        model_config["temperature"] = max(0.2, model_config["temperature"] - 0.2)
    
    return model_config

# Test the function
def test_model_selection():
    test_cases = [
        {"query": "What is S3?", "latency": "low"},
        {"query": "Explain the differences between EC2 and Lambda", "latency": "standard"},
        {"query": "Design a serverless architecture for a high-traffic e-commerce site", "latency": "high"}
    ]
    
    for case in test_cases:
        model = select_model_for_latency(case["query"], case["latency"])
        print(f"Query: {case['query']}")
        print(f"Latency requirement: {case['latency']}")
        print(f"Selected model: {model['model_id']}")
        print(f"Expected response time: ~{model['avg_response_time']} seconds")
        print(f"Parameters: max_tokens={model['max_tokens']}, temperature={model['temperature']}")
        print()

if __name__ == "__main__":
    test_model_selection()
```

### Step 4: Implement Parallel Requests for Complex Workflows

Let's create a function to handle parallel requests for complex workflows:

```python
import asyncio
import aiohttp
import time
from concurrent.futures import ThreadPoolExecutor

async def process_parallel_requests(workflow_steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process multiple model requests in parallel for complex workflows.
    
    Args:
        workflow_steps: List of workflow steps, each with a prompt and model configuration
        
    Returns:
        Dictionary with results from all steps
    """
    async def process_step(step):
        """Process a single workflow step"""
        start_time = time.time()
        bedrock_runtime = boto3.client('bedrock-runtime')
        
        try:
            model_id = step.get("model_id", "anthropic.claude-instant-v1")
            prompt = step.get("prompt", "")
            
            # Prepare the request based on model type
            if "anthropic" in model_id:
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": step.get("max_tokens", 1000),
                    "temperature": step.get("temperature", 0.7),
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                }
            else:
                # Default format for other models
                request_body = {
                    "prompt": prompt,
                    "max_tokens_to_sample": step.get("max_tokens", 1000),
                    "temperature": step.get("temperature", 0.7),
                    "top_p": step.get("top_p", 0.9)
                }
            
            # Execute in a thread to avoid blocking the event loop
            with ThreadPoolExecutor() as executor:
                response_future = executor.submit(
                    bedrock_runtime.invoke_model,
                    modelId=model_id,
                    body=json.dumps(request_body)
                )
                response = response_future.result()
            
            response_body = json.loads(response['body'].read())
            
            # Extract the response text based on model type
            if "anthropic" in model_id:
                response_text = response_body['content'][0]['text']
            else:
                response_text = response_body.get('completion', '')
            
            elapsed_time = time.time() - start_time
            
            return {
                "step_id": step.get("step_id"),
                "status": "success",
                "response": response_text,
                "elapsed_time": elapsed_time
            }
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            return {
                "step_id": step.get("step_id"),
                "status": "error",
                "error": str(e),
                "elapsed_time": elapsed_time
            }
    
    # Create tasks for all workflow steps
    tasks = [process_step(step) for step in workflow_steps]
    
    # Execute all tasks in parallel
    start_time = time.time()
    results = await asyncio.gather(*tasks)
    total_time = time.time() - start_time
    
    # Organize results by step_id
    organized_results = {
        result["step_id"]: result for result in results
    }
    
    # Calculate time saved compared to sequential execution
    sequential_time = sum(result["elapsed_time"] for result in results)
    time_saved = sequential_time - total_time
    
    return {
        "results": organized_results,
        "total_time": total_time,
        "sequential_time": sequential_time,
        "time_saved": time_saved,
        "time_saved_percentage": (time_saved / sequential_time) * 100 if sequential_time > 0 else 0
    }

# Example usage
async def test_parallel_workflow():
    # Define a complex workflow with multiple steps
    workflow = [
        {
            "step_id": "product_info",
            "model_id": "anthropic.claude-instant-v1",
            "prompt": "Provide a brief overview of AWS S3 service.",
            "max_tokens": 300,
            "temperature": 0.4
        },
        {
            "step_id": "pricing_info",
            "model_id": "anthropic.claude-instant-v1",
            "prompt": "Explain the pricing model for AWS S3.",
            "max_tokens": 300,
            "temperature": 0.4
        },
        {
            "step_id": "use_cases",
            "model_id": "anthropic.claude-instant-v1",
            "prompt": "List 3 common use cases for AWS S3.",
            "max_tokens": 300,
            "temperature": 0.4
        },
        {
            "step_id": "alternatives",
            "model_id": "anthropic.claude-instant-v1",
            "prompt": "What are alternatives to AWS S3?",
            "max_tokens": 300,
            "temperature": 0.4
        }
    ]
    
    print("Starting parallel workflow execution...")
    results = await process_parallel_requests(workflow)
    
    print(f"\nWorkflow completed in {results['total_time']:.2f} seconds")
    print(f"Sequential execution would take {results['sequential_time']:.2f} seconds")
    print(f"Time saved: {results['time_saved']:.2f} seconds ({results['time_saved_percentage']:.2f}%)")
    
    print("\nResults summary:")
    for step_id, result in results["results"].items():
        status = result["status"]
        time_taken = result["elapsed_time"]
        print(f"- {step_id}: {status} ({time_taken:.2f}s)")
        if status == "success":
            # Show first 50 chars of response
            print(f"  Response: {result['response'][:50]}...")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_parallel_workflow())
```

## Part 2: Retrieval performance optimization

### Step 1: Implement Query Preprocessing for Enhanced Retrieval

Let's create a function to preprocess queries for better retrieval:

```python
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# Download NLTK resources (only needed once)
try:
    nltk.data.find('corpora/stopwords')
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('stopwords')
    nltk.download('wordnet')
    nltk.download('punkt')

class QueryPreprocessor:
    """Class for preprocessing queries to improve retrieval performance"""
    
    def __init__(self):
        """Initialize the query preprocessor"""
        self.stop_words = set(stopwords.words('english'))
        self.lemmatizer = WordNetLemmatizer()
        
        # AWS-specific terms that should never be removed
        self.domain_terms = {
            'aws', 's3', 'ec2', 'lambda', 'dynamodb', 'rds', 'cloudfront',
            'vpc', 'iam', 'cloudwatch', 'sqs', 'sns', 'ebs', 'efs',
            'route53', 'cloudformation', 'fargate', 'eks', 'ecs'
        }
        
        # Common synonyms in AWS context
        self.synonyms = {
            'bucket': ['s3 bucket', 'storage bucket', 'object storage'],
            'instance': ['ec2 instance', 'virtual machine', 'vm', 'server'],
            'function': ['lambda function', 'serverless function'],
            'table': ['dynamodb table', 'database table'],
            'database': ['rds instance', 'database instance', 'db'],
            'user': ['iam user', 'account user'],
            'role': ['iam role', 'security role'],
            'policy': ['iam policy', 'security policy', 'permissions policy'],
            'cluster': ['eks cluster', 'kubernetes cluster', 'ecs cluster'],
            'container': ['docker container', 'ecs container']
        }
    
    def preprocess(self, query: str) -> Dict[str, Any]:
        """
        Preprocess a query to improve retrieval performance.
        
        Args:
            query: The original user query
            
        Returns:
            Dictionary with original and processed queries
        """
        original_query = query
        
        # Convert to lowercase
        query = query.lower()
        
        # Remove special characters but preserve AWS service names
        for term in self.domain_terms:
            # Temporarily replace domain terms with placeholders
            query = query.replace(term, f"___{term}___")
        
        # Remove special characters
        query = re.sub(r'[^\w\s]', ' ', query)
        
        # Restore domain terms
        for term in self.domain_terms:
            query = query.replace(f"___{term}___", term)
        
        # Tokenize
        tokens = nltk.word_tokenize(query)
        
        # Remove stop words but preserve domain terms
        filtered_tokens = [
            token for token in tokens 
            if token.lower() in self.domain_terms or token.lower() not in self.stop_words
        ]
        
        # Lemmatize
        lemmatized_tokens = [
            token if token.lower() in self.domain_terms 
            else self.lemmatizer.lemmatize(token) 
            for token in filtered_tokens
        ]
        
        # Reconstruct the processed query
        processed_query = ' '.join(lemmatized_tokens)
        
        # Generate expanded queries with synonyms
        expanded_queries = self.expand_with_synonyms(processed_query)
        
        return {
            "original_query": original_query,
            "processed_query": processed_query,
            "expanded_queries": expanded_queries
        }
    
    def expand_with_synonyms(self, query: str) -> List[str]:
        """
        Expand a query with relevant synonyms.
        
        Args:
            query: The processed query
            
        Returns:
            List of expanded queries with synonyms
        """
        expanded = [query]
        
        # Check for terms that have synonyms
        query_lower = query.lower()
        for term, synonyms in self.synonyms.items():
            if term in query_lower:
                # Create variations with synonyms
                for synonym in synonyms:
                    expanded_query = query_lower.replace(term, synonym)
                    if expanded_query not in expanded:
                        expanded.append(expanded_query)
        
        return expanded

# Test the query preprocessor
def test_query_preprocessor():
    preprocessor = QueryPreprocessor()
    
    test_queries = [
        "How do I create an S3 bucket?",
        "What are the differences between EC2 and Lambda functions?",
        "Can you explain IAM policies and roles?"
    ]
    
    for query in test_queries:
        result = preprocessor.preprocess(query)
        print(f"\nOriginal: {result['original_query']}")
        print(f"Processed: {result['processed_query']}")
        print(f"Expanded queries: {len(result['expanded_queries'])}")
        for i, exp_query in enumerate(result['expanded_queries'][:3], 1):
            print(f"  {i}. {exp_query}")

if __name__ == "__main__":
    test_query_preprocessor()
```