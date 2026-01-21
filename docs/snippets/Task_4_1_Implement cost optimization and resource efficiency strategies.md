# Task 4.1: Implement cost optimization and resource efficiency strategies

## Prerequisites

- AWS account with appropriate permissions.
- Basic knowledge of Python programming.
- Familiarity with AWS services (Amazon Bedrock, Lambda, DynamoDB, etc.).
- Understanding of foundation models and generative AI concepts.

## Project architecture

```text
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  API Gateway        │────▶│  Lambda Router      │────▶│  Token Optimizer    │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                      │                           │
                                      ▼                           ▼
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Semantic Cache     │◀───▶│  Model Selector     │◀───▶│  CloudWatch         │
│  (DynamoDB)         │     │  (Lambda)           │     │  Metrics            │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                      │
                      ┌───────────────┼───────────────┐
                      ▼               ▼               ▼
         ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
         │ Small Model     │ │ Medium Model    │ │ Large Model     │
         │ (Claude Instant)│ │ (Claude 2)      │ │ (Claude 3)      │
         └─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Part 1: Token efficiency system

### Step 1: Create a Token Estimation Function

First, let's create a function to accurately estimate token counts for different models:

```python
import boto3
import json
import re
import time
import os
import uuid
from typing import Dict, List, Any, Tuple

# Function to estimate tokens for Claude models
def estimate_tokens(text: str, model_type: str = "claude") -> int:
    """
    Estimate token count for different model types.
    This is a simplified estimation - for production use, consider using model-specific tokenizers.
    
    Args:
        text: The text to estimate tokens for
        model_type: The type of model (claude, llama, etc.)
        
    Returns:
        Estimated token count
    """
    if model_type.lower() == "claude":
        # Claude models use ~4 characters per token on average (rough estimation)
        return len(text) // 4 + 1
    elif model_type.lower() == "llama":
        # Llama models use different tokenization
        # This is a simplified estimate
        return len(text.split()) * 1.3
    else:
        # Default estimation
        return len(text) // 4 + 1

# Test the function
test_text = "Hello, I'm having trouble with my EC2 instance. It's not connecting properly."
print(f"Estimated tokens: {estimate_tokens(test_text)}")
```

### Step 2: Implement Context Pruning

Now, let's create a function to prune context and reduce token usage:

```python
def prune_context(conversation_history: List[Dict[str, str]], 
                  max_tokens: int = 1000, 
                  preserve_last_n_turns: int = 2) -> List[Dict[str, str]]:
    """
    Prune conversation history to fit within token limits while preserving recent context.
    
    Args:
        conversation_history: List of conversation turns with 'role' and 'content'
        max_tokens: Maximum tokens to keep
        preserve_last_n_turns: Number of recent turns to always preserve
        
    Returns:
        Pruned conversation history
    """
    if not conversation_history:
        return []
    
    # Always preserve the most recent turns
    preserved_turns = conversation_history[-preserve_last_n_turns:] if len(conversation_history) >= preserve_last_n_turns else conversation_history
    
    # If only preserving the recent turns, return them if they fit
    preserved_tokens = sum(estimate_tokens(turn['content']) for turn in preserved_turns)
    if preserved_tokens <= max_tokens or len(conversation_history) <= preserve_last_n_turns:
        return preserved_turns
    
    # Start with system message if present, then add as many earlier turns as possible
    pruned_history = []
    
    # Add system message if present
    for turn in conversation_history:
        if turn.get('role') == 'system':
            pruned_history.append(turn)
            break
    
    # Calculate remaining tokens
    used_tokens = sum(estimate_tokens(turn['content']) for turn in pruned_history + preserved_turns)
    remaining_tokens = max_tokens - used_tokens
    
    # Add as many earlier non-preserved turns as possible, starting from the most recent
    for turn in reversed(conversation_history[:-preserve_last_n_turns]):
        if turn.get('role') == 'system':  # Skip system message as we've already added it
            continue
            
        turn_tokens = estimate_tokens(turn['content'])
        if turn_tokens <= remaining_tokens:
            pruned_history.append(turn)
            remaining_tokens -= turn_tokens
        else:
            # If we can't add the full turn, consider truncating it
            if remaining_tokens > 50:  # Only truncate if we can keep a meaningful portion
                truncated_content = turn['content'][:remaining_tokens*4]  # Rough char estimate
                pruned_history.append({
                    'role': turn['role'],
                    'content': truncated_content + "... [truncated for token efficiency]"
                })
            break
    
    # Combine system message (if any), earlier turns, and preserved recent turns
    pruned_history = sorted(pruned_history, key=lambda x: 0 if x.get('role') == 'system' else 1) + preserved_turns
    
    return pruned_history

# Test the function
test_conversation = [
    {"role": "system", "content": "You are a helpful customer support agent for AWS services."},
    {"role": "user", "content": "I'm having trouble with my EC2 instance."},
    {"role": "assistant", "content": "I'm sorry to hear that. What specific issue are you experiencing with your EC2 instance?"},
    {"role": "user", "content": "It won't start up. I get a status check failure."},
    {"role": "assistant", "content": "That could be due to several reasons. Let's troubleshoot step by step."}
]

pruned = prune_context(test_conversation, max_tokens=50)
print("Pruned conversation:")
for turn in pruned:
    print(f"{turn['role']}: {turn['content']}")
```

### Step 3: Implement Prompt Compression

Let's create a function to compress prompts while maintaining their effectiveness:

```python
def compress_prompt(prompt: str, target_reduction: float = 0.3) -> str:
    """
    Compress a prompt to reduce token usage while preserving meaning.
    
    Args:
        prompt: The original prompt
        target_reduction: Target percentage reduction in length
        
    Returns:
        Compressed prompt
    """
    # Strategy 1: Remove unnecessary phrases
    filler_phrases = [
        "I was wondering if", "I would like to know", "Can you tell me",
        "I'm curious about", "Please provide information on", "I need to understand",
        "Could you explain", "I want to learn about", "Please help me understand",
        "I would appreciate it if you could", "It would be great if you could",
        "I'm interested in learning"
    ]
    
    compressed = prompt
    for phrase in filler_phrases:
        compressed = compressed.replace(phrase, "")
    
    # Strategy 2: Replace verbose constructions with concise ones
    replacements = {
        "in order to": "to",
        "due to the fact that": "because",
        "at this point in time": "now",
        "a large number of": "many",
        "a majority of": "most",
        "a sufficient amount of": "enough",
        "in the event that": "if",
        "in the near future": "soon",
        "in spite of the fact that": "although",
        "with regard to": "about",
        "with the exception of": "except",
    }
    
    for verbose, concise in replacements.items():
        compressed = compressed.replace(verbose, concise)
    
    # Strategy 3: Remove redundant adjectives and adverbs
    redundant_words = [
        "very", "really", "quite", "basically", "actually", "definitely",
        "certainly", "probably", "essentially", "fundamentally", "particularly"
    ]
    
    for word in redundant_words:
        compressed = re.sub(r'\b' + word + r'\b', '', compressed)
    
    # Clean up extra spaces
    compressed = re.sub(r'\s+', ' ', compressed).strip()
    
    # If we haven't achieved target reduction, truncate less important parts
    original_tokens = estimate_tokens(prompt)
    compressed_tokens = estimate_tokens(compressed)
    
    if compressed_tokens > original_tokens * (1 - target_reduction):
        # Look for sections to truncate, like examples or context
        # This is a simplified approach - in production you'd want more sophisticated truncation
        sections = compressed.split(". ")
        if len(sections) > 3:
            # Keep first and last sections, reduce middle sections
            compressed = sections[0] + ". " + sections[-1]
    
    return compressed

# Test the function
test_prompt = """
I would like to know more about how to optimize my AWS Lambda functions. 
I'm particularly interested in understanding how to reduce cold start times and 
improve the overall performance. Could you explain the best practices for Lambda optimization? 
I would appreciate it if you could provide some concrete examples and step-by-step guidance.
"""

compressed_prompt = compress_prompt(test_prompt)
print(f"Original tokens: {estimate_tokens(test_prompt)}")
print(f"Compressed tokens: {estimate_tokens(compressed_prompt)}")
print(f"Original: {test_prompt}")
print(f"Compressed: {compressed_prompt}")
```

### Step 4: Implement Response Size Controls

Create a function to control response size based on query complexity:

```python
def calculate_response_limits(query: str, user_tier: str = "standard") -> Dict[str, int]:
    """
    Calculate appropriate response size limits based on query complexity and user tier.
    
    Args:
        query: The user query
        user_tier: User subscription tier (standard, premium, etc.)
        
    Returns:
        Dictionary with max_tokens and other response parameters
    """
    # Estimate query complexity
    complexity_factors = {
        "simple": ["how", "what is", "define", "list", "show me"],
        "complex": ["explain", "compare", "analyze", "troubleshoot", "optimize", "architecture"],
        "very_complex": ["design a system", "create a solution", "develop a strategy", "implement"]
    }
    
    query_lower = query.lower()
    
    # Determine complexity level
    complexity = "simple"
    for level, factors in complexity_factors.items():
        if any(factor in query_lower for factor in factors):
            complexity = level
            break
    
    # Base token limits by complexity
    base_limits = {
        "simple": 150,
        "complex": 300,
        "very_complex": 500
    }
    
    # Adjust based on user tier
    tier_multipliers = {
        "basic": 0.8,
        "standard": 1.0,
        "premium": 1.5,
        "enterprise": 2.0
    }
    
    multiplier = tier_multipliers.get(user_tier.lower(), 1.0)
    max_tokens = int(base_limits[complexity] * multiplier)
    
    # Additional parameters for response control
    return {
        "max_tokens": max_tokens,
        "temperature": 0.7 if complexity == "simple" else 0.4,
        "top_p": 0.9,
        "stop_sequences": ["\n\n\n"]
    }

# Test the function
test_queries = [
    "What is Amazon S3?",
    "Explain the differences between EC2 and Lambda",
    "Design a serverless architecture for a high-traffic e-commerce site"
]

for query in test_queries:
    limits = calculate_response_limits(query)
    print(f"Query: {query}")
    print(f"Response limits: {limits}")
    print()
```

## Part 2: Cost-Effective Model Selection Framework

### Step 1: Create a Model Selection Function

Let's create a function to select the most cost-effective model based on query complexity:

```python
def select_model(query: str, user_context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Select the most appropriate model based on query complexity and user context.
    
    Args:
        query: The user query
        user_context: Additional context about the user and their usage
        
    Returns:
        Dictionary with selected model and parameters
    """
    if user_context is None:
        user_context = {}
    
    # Define available models with their capabilities and costs
    models = {
        "anthropic.claude-instant-v1": {
            "capability": "basic",
            "cost_per_1k_input_tokens": 0.00080,
            "cost_per_1k_output_tokens": 0.00240,
            "max_tokens": 100000,
            "strengths": ["fast responses", "basic Q&A", "simple instructions"],
            "weaknesses": ["complex reasoning", "nuanced understanding"]
        },
        "anthropic.claude-v2": {
            "capability": "advanced",
            "cost_per_1k_input_tokens": 0.00800,
            "cost_per_1k_output_tokens": 0.02400,
            "max_tokens": 100000,
            "strengths": ["reasoning", "nuanced instructions", "detailed explanations"],
            "weaknesses": ["highest cost", "overkill for simple queries"]
        },
        "anthropic.claude-3-sonnet-20240229-v1:0": {
            "capability": "premium",
            "cost_per_1k_input_tokens": 0.01500,
            "cost_per_1k_output_tokens": 0.06000,
            "max_tokens": 200000,
            "strengths": ["advanced reasoning", "complex instructions", "creative content"],
            "weaknesses": ["highest cost", "overkill for most queries"]
        }
    }
    
    # Analyze query complexity
    query_complexity = analyze_query_complexity(query)
    
    # Consider user's historical usage patterns
    user_tier = user_context.get("tier", "standard")
    is_premium_user = user_tier in ["premium", "enterprise"]
    
    # Consider time sensitivity
    is_time_sensitive = user_context.get("is_time_sensitive", False)
    
    # Select model based on complexity and context
    selected_model = None
    
    if query_complexity == "simple":
        selected_model = "anthropic.claude-instant-v1"
    elif query_complexity == "medium":
        # For medium complexity, consider user tier
        if is_premium_user:
            selected_model = "anthropic.claude-v2"
        else:
            selected_model = "anthropic.claude-instant-v1"
    else:  # complex
        if is_premium_user or is_time_sensitive:
            selected_model = "anthropic.claude-3-sonnet-20240229-v1:0"
        else:
            selected_model = "anthropic.claude-v2"
    
    # Calculate estimated cost
    estimated_input_tokens = estimate_tokens(query)
    estimated_output_tokens = models[selected_model]["max_tokens"]
    
    estimated_cost = (
        (estimated_input_tokens / 1000) * models[selected_model]["cost_per_1k_input_tokens"] +
        (estimated_output_tokens / 1000) * models[selected_model]["cost_per_1k_output_tokens"]
    )
    
    return {
        "model_id": selected_model,
        "estimated_cost": estimated_cost,
        "query_complexity": query_complexity,
        "model_capabilities": models[selected_model]["capability"],
        "max_tokens": calculate_response_limits(query, user_tier)["max_tokens"],
        "temperature": 0.7 if query_complexity == "simple" else 0.4
    }

def analyze_query_complexity(query: str) -> str:
    """
    Analyze the complexity of a query.
    
    Args:
        query: The user query
        
    Returns:
        Complexity level: "simple", "medium", or "complex"
    """
    query_lower = query.lower()
    
    # Check for complex patterns
    complex_patterns = [
        "architecture", "design", "optimize", "compare", "analyze", 
        "troubleshoot", "debug", "implement", "develop a", "create a system",
        "best practices", "trade-offs", "performance tuning"
    ]
    
    # Check for medium complexity patterns
    medium_patterns = [
        "explain", "how to", "difference between", "advantages", 
        "disadvantages", "benefits", "limitations", "use cases"
    ]
    
    # Check for simple patterns
    simple_patterns = [
        "what is", "define", "who is", "when", "where", "list", "show"
    ]
    
    # Determine complexity based on patterns
    if any(pattern in query_lower for pattern in complex_patterns):
        return "complex"
    elif any(pattern in query_lower for pattern in medium_patterns):
        return "medium"
    else:
        return "simple"

# Test the function
test_queries = [
    "What is Amazon S3?",
    "Explain the differences between EC2 and Lambda",
    "Design a serverless architecture for a high-traffic e-commerce site"
]

for query in test_queries:
    model_selection = select_model(query)
    print(f"Query: {query}")
    print(f"Selected model: {model_selection['model_id']}")
    print(f"Estimated cost: ${model_selection['estimated_cost']:.6f}")
    print(f"Complexity: {model_selection['query_complexity']}")
    print()
```

### Step 2: Implement Cost-Capability Tradeoff Analysis

Create a function to analyze cost-capability tradeoffs:

```python
def analyze_cost_capability_tradeoff(query_history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze cost-capability tradeoffs based on historical query data.
    
    Args:
        query_history: List of previous queries with models used and outcomes
        
    Returns:
        Analysis of cost-effectiveness and recommendations
    """
    if not query_history:
        return {
            "error": "No query history provided for analysis"
        }
    
    # Group by model
    model_stats = {}
    for entry in query_history:
        model_id = entry.get("model_id")
        if not model_id:
            continue
            
        if model_id not in model_stats:
            model_stats[model_id] = {
                "total_cost": 0,
                "total_queries": 0,
                "successful_queries": 0,
                "query_types": {
                    "simple": 0,
                    "medium": 0,
                    "complex": 0
                }
            }
        
        model_stats[model_id]["total_cost"] += entry.get("cost", 0)
        model_stats[model_id]["total_queries"] += 1
        
        # Count successful queries (those that didn't need follow-up clarification)
        if entry.get("needed_clarification") != True:
            model_stats[model_id]["successful_queries"] += 1
        
        # Track query complexity
        complexity = entry.get("query_complexity", "simple")
        model_stats[model_id]["query_types"][complexity] += 1
    
    # Calculate cost-effectiveness metrics
    for model_id, stats in model_stats.items():
        if stats["total_queries"] > 0:
            stats["avg_cost_per_query"] = stats["total_cost"] / stats["total_queries"]
            stats["success_rate"] = stats["successful_queries"] / stats["total_queries"]
            stats["cost_per_successful_query"] = (
                stats["total_cost"] / stats["successful_queries"] 
                if stats["successful_queries"] > 0 else float('inf')
            )
    
    # Analyze optimal model for each complexity level
    optimal_models = {}
    for complexity in ["simple", "medium", "complex"]:
        best_model = None
        best_cost_effectiveness = float('inf')
        
        for model_id, stats in model_stats.items():
            if stats["query_types"][complexity] > 0:
                # Calculate cost-effectiveness for this complexity level
                # Lower is better
                cost_effectiveness = (
                    stats["total_cost"] / stats["query_types"][complexity]
                ) / stats["success_rate"]
                
                if cost_effectiveness < best_cost_effectiveness:
                    best_cost_effectiveness = cost_effectiveness
                    best_model = model_id
        
        optimal_models[complexity] = best_model
    
    # Generate recommendations
    recommendations = []
    
    # Check if cheaper models are being underutilized for simple queries
    if optimal_models.get("simple") != "anthropic.claude-instant-v1":
        recommendations.append(
            "Consider using Claude Instant more frequently for simple queries to reduce costs"
        )
    
    # Check if expensive models are being overused
    claude_3_usage = sum(
        1 for entry in query_history 
        if entry.get("model_id") == "anthropic.claude-3-sonnet-20240229-v1:0" and entry.get("query_complexity") != "complex"
    )
    
    if claude_3_usage > 0:
        recommendations.append(
            f"Found {claude_3_usage} non-complex queries using Claude 3. Consider downgrading these to Claude 2 or Claude Instant"
        )
    
    return {
        "model_stats": model_stats,
        "optimal_models": optimal_models,
        "recommendations": recommendations
    }

# Test the function
test_history = [
    {
        "query": "What is Amazon S3?",
        "query_complexity": "simple",
        "model_id": "anthropic.claude-instant-v1",
        "cost": 0.0005,
        "needed_clarification": False
    },
    {
        "query": "What is Amazon EC2?",
        "query_complexity": "simple",
        "model_id": "anthropic.claude-v2",
        "cost": 0.005,
        "needed_clarification": False
    },
    {
        "query": "Explain the differences between EC2 and Lambda",
        "query_complexity": "medium",
        "model_id": "anthropic.claude-v2",
        "cost": 0.008,
        "needed_clarification": False
    },
    {
        "query": "Design a serverless architecture for a high-traffic e-commerce site",
        "query_complexity": "complex",
        "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
        "cost": 0.02,
        "needed_clarification": False
    },
    {
        "query": "How do I optimize Lambda cold starts?",
        "query_complexity": "medium",
        "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
        "cost": 0.015,
        "needed_clarification": False
    }
]

analysis = analyze_cost_capability_tradeoff(test_history)
print("Cost-Capability Tradeoff Analysis:")
print(f"Optimal models by complexity: {analysis['optimal_models']}")
print("Recommendations:")
for rec in analysis['recommendations']:
    print(f"- {rec}")
```