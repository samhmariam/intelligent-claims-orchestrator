# Task 5.2: Troubleshoot GenAI Applications

## Prerequisites

You'll need:

- AWS account with appropriate permissions
- Basic knowledge of Python programming
- Familiarity with AWS services (Amazon Bedrock, Lambda, CloudWatch, etc.)
- Understanding of foundation models and generative AI concepts

## Project architecture

```text
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Customer Support   │────▶│  Troubleshooting    │────▶│  Amazon Bedrock     │
│  Chatbot            │     │  Toolkit            │     │  Foundation Models  │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
         │                           │                           │
         │                           │                           │
         ▼                           ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Comprehensive Troubleshooting System                    │
├─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│ Content         │ API             │ Prompt          │ Retrieval       │
│ Handling        │ Integration     │ Engineering     │ System          │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
         │                 │                 │                 │
         └─────────────────┼─────────────────┼─────────────────┘
                           │                 │
                           ▼                 ▼
                  ┌─────────────────┐ ┌─────────────────┐
                  │ CloudWatch      │ │ Diagnostic      │
                  │ Logs & Metrics  │ │ Dashboard       │
                  └─────────────────┘ └─────────────────┘
```

## Module 1: Content handling diagnostics

### Step 1: Create a Context Window Overflow Diagnostic Tool

First, let's build a tool to diagnose context window overflow issues:

```python
import boto3
import json
import time
import os
from typing import Dict, List, Any
import tiktoken  # For token counting

class ContextWindowDiagnostic:
    """Class for diagnosing context window overflow issues"""
    
    def __init__(self):
        """Initialize the context window diagnostic tool"""
        # Define model context window limits
        self.model_limits = {
            "anthropic.claude-instant-v1": 100000,
            "anthropic.claude-v2": 100000,
            "anthropic.claude-3-sonnet-20240229-v1:0": 200000,
            "amazon.titan-text-express-v1": 8000
        }
        
        # Initialize tokenizers
        self.tokenizers = {
            "anthropic": tiktoken.get_encoding("cl100k_base"),  # Claude uses cl100k_base
            "amazon": tiktoken.get_encoding("p50k_base")  # Approximate for Titan
        }
    
    def analyze_context_window(self, 
                              model_id: str, 
                              prompt: str, 
                              expected_completion_tokens: int = 1000) -> Dict[str, Any]:
        """
        Analyze potential context window overflow issues.
        
        Args:
            model_id: The model ID
            prompt: The prompt text
            expected_completion_tokens: Expected number of tokens in the completion
            
        Returns:
            Dictionary with analysis results
        """
        try:
            # Get model family for tokenizer selection
            model_family = "anthropic" if "anthropic" in model_id else "amazon"
            
            # Count tokens in the prompt
            tokenizer = self.tokenizers.get(model_family, self.tokenizers["anthropic"])
            prompt_tokens = len(tokenizer.encode(prompt))
            
            # Get model context window limit
            context_window_limit = self.model_limits.get(model_id, 8000)  # Default to 8K if unknown
            
            # Calculate total expected tokens
            total_expected_tokens = prompt_tokens + expected_completion_tokens
            
            # Check for overflow
            is_overflow = total_expected_tokens > context_window_limit
            overflow_amount = max(0, total_expected_tokens - context_window_limit)
            
            # Calculate utilization percentage
            utilization_percentage = (total_expected_tokens / context_window_limit) * 100
            
            # Determine risk level
            if is_overflow:
                risk_level = "High - Overflow detected"
            elif utilization_percentage > 90:
                risk_level = "Medium - Near context window limit"
            elif utilization_percentage > 75:
                risk_level = "Low - Approaching context window limit"
            else:
                risk_level = "Safe - Well within context window limit"
            
            # Generate recommendations
            recommendations = []
            if is_overflow:
                recommendations.append("Reduce prompt size by removing non-essential information")
                recommendations.append("Use a model with a larger context window")
                recommendations.append("Implement a chunking strategy to process content in smaller pieces")
                recommendations.append("Use summarization to condense context while preserving key information")
            elif utilization_percentage > 90:
                recommendations.append("Monitor closely for potential overflow")
                recommendations.append("Consider optimizing prompt for token efficiency")
                recommendations.append("Prepare fallback strategy for handling overflow cases")
            
            return {
                "model_id": model_id,
                "context_window_limit": context_window_limit,
                "prompt_tokens": prompt_tokens,
                "expected_completion_tokens": expected_completion_tokens,
                "total_expected_tokens": total_expected_tokens,
                "is_overflow": is_overflow,
                "overflow_amount": overflow_amount,
                "utilization_percentage": utilization_percentage,
                "risk_level": risk_level,
                "recommendations": recommendations
            }
        except Exception as e:
            print(f"Error analyzing context window: {e}")
            return {
                "error": str(e),
                "model_id": model_id
            }
    
    def suggest_chunking_strategy(self, 
                                 document_text: str, 
                                 model_id: str) -> Dict[str, Any]:
        """
        Suggest an appropriate chunking strategy for a document.
        
        Args:
            document_text: The document text
            model_id: The model ID
            
        Returns:
            Dictionary with chunking strategy suggestions
        """
        try:
            # Get model family for tokenizer selection
            model_family = "anthropic" if "anthropic" in model_id else "amazon"
            
            # Count tokens in the document
            tokenizer = self.tokenizers.get(model_family, self.tokenizers["anthropic"])
            document_tokens = len(tokenizer.encode(document_text))
            
            # Get model context window limit
            context_window_limit = self.model_limits.get(model_id, 8000)  # Default to 8K if unknown
            
            # Calculate number of chunks needed with different strategies
            # Allow 20% of context window for prompt and response
            effective_chunk_size = int(context_window_limit * 0.8)
            
            # Simple fixed-size chunking
            fixed_chunks_needed = (document_tokens / effective_chunk_size) + (1 if document_tokens % effective_chunk_size > 0 else 0)
            
            # Analyze document structure
            paragraphs = document_text.split('\n\n')
            avg_paragraph_tokens = document_tokens / len(paragraphs) if paragraphs else 0
            
            # Determine if document has natural breakpoints
            has_sections = any(line.strip().startswith('#') for line in document_text.split('\n'))
            has_clear_paragraphs = len(paragraphs) > 5 and avg_paragraph_tokens < 200
            
            # Suggest chunking strategies
            strategies = []
            
            if document_tokens <= effective_chunk_size:
                strategies.append({
                    "name": "No chunking needed",
                    "description": "Document fits within context window",
                    "implementation": "Process the entire document at once"
                })
            else:
                # Fixed-size chunking
                strategies.append({
                    "name": "Fixed-size chunking",
                    "description": f"Split into {int(fixed_chunks_needed)} chunks of {effective_chunk_size} tokens each",
                    "implementation": "Use a sliding window with fixed token count and 10% overlap between chunks"
                })
                
                # Semantic chunking if document has structure
                if has_sections or has_clear_paragraphs:
                    strategies.append({
                        "name": "Semantic chunking",
                        "description": "Split based on document structure (sections/paragraphs)",
                        "implementation": "Use section headers or paragraph breaks as chunk boundaries"
                    })
                
                # Recursive chunking for very large documents
                if document_tokens > context_window_limit * 5:
                    strategies.append({
                        "name": "Recursive chunking with summarization",
                        "description": "Process document in layers, summarizing each chunk",
                        "implementation": "First chunk and summarize sections, then combine summaries for full context"
                    })
            
            return {
                "document_tokens": document_tokens,
                "context_window_limit": context_window_limit,
                "effective_chunk_size": effective_chunk_size,
                "document_structure": {
                    "paragraphs": len(paragraphs),
                    "avg_paragraph_tokens": avg_paragraph_tokens,
                    "has_sections": has_sections,
                    "has_clear_paragraphs": has_clear_paragraphs
                },
                "recommended_strategies": strategies
            }
        except Exception as e:
            print(f"Error suggesting chunking strategy: {e}")
            return {
                "error": str(e),
                "model_id": model_id
            }
    
    def implement_dynamic_chunking(self, 
                                  document_text: str, 
                                  model_id: str,
                                  strategy: str = "semantic",
                                  max_tokens_per_chunk: int = None) -> Dict[str, Any]:
        """
        Implement dynamic chunking for a document.
        
        Args:
            document_text: The document text
            model_id: The model ID
            strategy: Chunking strategy (fixed, semantic, recursive)
            max_tokens_per_chunk: Maximum tokens per chunk (defaults to 80% of context window)
            
        Returns:
            Dictionary with chunked document
        """
        try:
            # Get model family for tokenizer selection
            model_family = "anthropic" if "anthropic" in model_id else "amazon"
            
            # Get tokenizer
            tokenizer = self.tokenizers.get(model_family, self.tokenizers["anthropic"])
            
            # Get model context window limit
            context_window_limit = self.model_limits.get(model_id, 8000)  # Default to 8K if unknown
            
            # Set default max tokens per chunk if not provided
            if not max_tokens_per_chunk:
                max_tokens_per_chunk = int(context_window_limit * 0.8)
            
            chunks = []
            
            if strategy == "fixed":
                # Fixed-size chunking with overlap
                overlap_tokens = int(max_tokens_per_chunk * 0.1)  # 10% overlap
                document_tokens = tokenizer.encode(document_text)
                
                for i in range(0, len(document_tokens), max_tokens_per_chunk - overlap_tokens):
                    chunk_tokens = document_tokens[i:i + max_tokens_per_chunk]
                    chunk_text = tokenizer.decode(chunk_tokens)
                    chunks.append({
                        "chunk_id": len(chunks),
                        "text": chunk_text,
                        "tokens": len(chunk_tokens),
                        "start_position": i,
                        "end_position": i + len(chunk_tokens)
                    })
            
            elif strategy == "semantic":
                # Semantic chunking based on document structure
                current_chunk = ""
                current_tokens = 0
                
                # Try to split by sections first
                sections = self._split_by_sections(document_text)
                
                if len(sections) > 1:
                    # Document has clear sections
                    for section in sections:
                        section_tokens = len(tokenizer.encode(section))
                        
                        if section_tokens > max_tokens_per_chunk:
                            # Section is too large, split into paragraphs
                            section_chunks = self._chunk_by_paragraphs(section, tokenizer, max_tokens_per_chunk)
                            chunks.extend(section_chunks)
                        else:
                            # Check if adding this section would exceed the limit
                            if current_tokens + section_tokens > max_tokens_per_chunk and current_tokens > 0:
                                # Save current chunk and start a new one
                                chunks.append({
                                    "chunk_id": len(chunks),
                                    "text": current_chunk,
                                    "tokens": current_tokens
                                })
                                current_chunk = section
                                current_tokens = section_tokens
                            else:
                                # Add section to current chunk
                                if current_chunk:
                                    current_chunk += "\n\n"
                                current_chunk += section
                                current_tokens += section_tokens
                else:
                    # No clear sections, split by paragraphs
                    chunks = self._chunk_by_paragraphs(document_text, tokenizer, max_tokens_per_chunk)
                
                # Add the last chunk if there's anything left
                if current_chunk:
                    chunks.append({
                        "chunk_id": len(chunks),
                        "text": current_chunk,
                        "tokens": current_tokens
                    })
            
            elif strategy == "recursive":
                # Recursive chunking with summarization
                # This is a simplified implementation - in a real system, you would
                # recursively summarize chunks and then combine summaries
                
                # First, split into major sections
                sections = self._split_by_sections(document_text)
                
                if len(sections) <= 1:
                    # No clear sections, split by paragraphs
                    sections = document_text.split('\n\n')
                
                # Process each section
                for section_idx, section in enumerate(sections):
                    section_tokens = len(tokenizer.encode(section))
                    
                    if section_tokens <= max_tokens_per_chunk:
                        # Section fits in a chunk
                        chunks.append({
                            "chunk_id": len(chunks),
                            "text": section,
                            "tokens": section_tokens,
                            "section_id": section_idx
                        })
                    else:
                        # Section needs to be split
                        paragraphs = section.split('\n\n')
                        current_chunk = ""
                        current_tokens = 0
                        
                        for para in paragraphs:
                            para_tokens = len(tokenizer.encode(para))
                            
                            if current_tokens + para_tokens > max_tokens_per_chunk:
                                # Save current chunk and start a new one
                                if current_chunk:
                                    chunks.append({
                                        "chunk_id": len(chunks),
                                        "text": current_chunk,
                                        "tokens": current_tokens,
                                        "section_id": section_idx
                                    })
                                
                                # If paragraph is too large, split it further
                                if para_tokens > max_tokens_per_chunk:
                                    # Split paragraph into sentences
                                    sentences = self._split_into_sentences(para)
                                    sentence_chunks = self._chunk_by_sentences(sentences, tokenizer, max_tokens_per_chunk)
                                    
                                    for sc in sentence_chunks:
                                        sc["section_id"] = section_idx
                                        sc["chunk_id"] = len(chunks)
                                        chunks.append(sc)
                                    
                                    current_chunk = ""
                                    current_tokens = 0
                                else:
                                    current_chunk = para
                                    current_tokens = para_tokens
                            else:
                                # Add paragraph to current chunk
                                if current_chunk:
                                    current_chunk += "\n\n"
                                current_chunk += para
                                current_tokens += para_tokens
                        
                        # Add the last chunk if there's anything left
                        if current_chunk:
                            chunks.append({
                                "chunk_id": len(chunks),
                                "text": current_chunk,
                                "tokens": current_tokens,
                                "section_id": section_idx
                            })
            
            return {
                "original_document_tokens": len(tokenizer.encode(document_text)),
                "chunking_strategy": strategy,
                "max_tokens_per_chunk": max_tokens_per_chunk,
                "number_of_chunks": len(chunks),
                "chunks": chunks
            }
        except Exception as e:
            print(f"Error implementing dynamic chunking: {e}")
            return {
                "error": str(e),
                "model_id": model_id
            }
    
    def _split_by_sections(self, text: str) -> List[str]:
        """Split text by section headers"""
        import re
        
        # Look for Markdown-style headers or numbered sections
        section_pattern = re.compile(r'^(#+\s+.*|[0-9]+\.\s+.*)', re.MULTILINE)
        
        # Find all section headers
        matches = list(section_pattern.finditer(text))
        
        if not matches:
            return [text]
        
        sections = []
        for i in range(len(matches)):
            start = matches[i].start()
            end = matches[i+1].start() if i < len(matches) - 1 else len(text)
            sections.append(text[start:end].strip())
        
        return sections
    
    def _chunk_by_paragraphs(self, text: str, tokenizer, max_tokens: int) -> List[Dict[str, Any]]:
        """Chunk text by paragraphs"""
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""
        current_tokens = 0
        
        for para in paragraphs:
            para_tokens = len(tokenizer.encode(para))
            
            if current_tokens + para_tokens > max_tokens and current_tokens > 0:
                # Save current chunk and start a new one
                chunks.append({
                    "chunk_id": len(chunks),
                    "text": current_chunk,
                    "tokens": current_tokens
                })
                current_chunk = para
                current_tokens = para_tokens
            else:
                # Add paragraph to current chunk
                if current_chunk:
                    current_chunk += "\n\n"
                current_chunk += para
                current_tokens += para_tokens
        
        # Add the last chunk if there's anything left
        if current_chunk:
            chunks.append({
                "chunk_id": len(chunks),
                "text": current_chunk,
                "tokens": current_tokens
            })
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        import re
        sentence_pattern = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s')
        sentences = sentence_pattern.split(text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _chunk_by_sentences(self, sentences: List[str], tokenizer, max_tokens: int) -> List[Dict[str, Any]]:
        """Chunk text by sentences"""
        chunks = []
        current_chunk = ""
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = len(tokenizer.encode(sentence))
            
            if current_tokens + sentence_tokens > max_tokens and current_tokens > 0:
                # Save current chunk and start a new one
                chunks.append({
                    "chunk_id": len(chunks),
                    "text": current_chunk,
                    "tokens": current_tokens
                })
                current_chunk = sentence
                current_tokens = sentence_tokens
            else:
                # Add sentence to current chunk
                if current_chunk:
                    current_chunk += " "
                current_chunk += sentence
                current_tokens += sentence_tokens
        
        # Add the last chunk if there's anything left
        if current_chunk:
            chunks.append({
                "chunk_id": len(chunks),
                "text": current_chunk,
                "tokens": current_tokens
            })
        
        return chunks

# Test the context window diagnostic tool
def test_context_window_diagnostic():
    diagnostic = ContextWindowDiagnostic()
    
    # Test prompt for context window analysis
    test_prompt = """
    You are a customer support agent for AWS. Please help the customer with their question.
    
    Customer: I'm having trouble understanding the difference between Amazon S3 storage classes. 
    Can you explain the key differences between S3 Standard, S3 Intelligent-Tiering, S3 Standard-IA, 
    S3 One Zone-IA, S3 Glacier, and S3 Glacier Deep Archive? I'm particularly interested in 
    durability, availability, retrieval times, and cost considerations for each storage class.
    
    Previous conversation:
    Customer: Hello, I'm new to AWS and trying to understand storage options.
    Agent: Welcome to AWS! I'd be happy to help you understand our storage options. 
    AWS offers several storage services, with Amazon S3 being the most commonly used object storage service. 
    What specific aspects of AWS storage would you like to learn about?
    Customer: I'm specifically interested in S3 storage classes.
    """
    
    # Analyze context window
    analysis = diagnostic.analyze_context_window(
        model_id="anthropic.claude-instant-v1",
        prompt=test_prompt,
        expected_completion_tokens=1000
    )
    
    print("Context Window Analysis:")
    print(json.dumps(analysis, indent=2))
    
    # Test document for chunking strategy suggestion
    test_document = """# Amazon S3 Storage Classes

## S3 Standard
Amazon S3 Standard is designed for frequently accessed data, with high durability (99.999999999%, 11 9's) and high availability (99.99%). It has low latency and high throughput performance. This storage class is ideal for a wide range of use cases including cloud applications, dynamic websites, content distribution, mobile and gaming applications, and big data analytics.

Key features:
- Durability: 99.999999999% (11 9's)
- Availability: 99.99%
- Low latency and high throughput
- Designed for frequent access
- No minimum object size
- No retrieval fees

## S3 Intelligent-Tiering
S3 Intelligent-Tiering is designed to optimize costs by automatically moving data to the most cost-effective access tier, without performance impact or operational overhead. It works by monitoring access patterns and moving objects that haven't been accessed for 30 consecutive days to the infrequent access tier.

Key features:
- Durability: 99.999999999% (11 9's)
- Availability: 99.9%
- Automatic cost savings for changing access patterns
- No retrieval fees
- Small monthly monitoring and automation fee per object
- Ideal for data with unknown or changing access patterns

## S3 Standard-IA (Infrequent Access)
S3 Standard-IA is designed for data that is accessed less frequently, but requires rapid access when needed. It offers the high durability, high throughput, and low latency of S3 Standard, with a lower per GB storage price and a per GB retrieval fee.

Key features:
- Durability: 99.999999999% (11 9's)
- Availability: 99.9%
- Lower storage cost compared to S3 Standard
- Retrieval fee applies
- Minimum billable object size: 128KB
- Ideal for long-term storage, backups, and disaster recovery files

## S3 One Zone-IA
S3 One Zone-IA is designed for data that is accessed less frequently, but requires rapid access when needed. Unlike other S3 Storage Classes which store data in a minimum of three Availability Zones, S3 One Zone-IA stores data in a single AZ and costs 20% less than S3 Standard-IA.

Key features:
- Durability: 99.999999999% (11 9's) within a single AZ
- Availability: 99.5%
- Lower storage cost compared to S3 Standard-IA
- Retrieval fee applies
- Minimum billable object size: 128KB
- Ideal for secondary backup copies or easily recreatable data

## S3 Glacier Instant Retrieval
S3 Glacier Instant Retrieval is an archive storage class that delivers the lowest-cost storage for long-lived data that is rarely accessed and requires retrieval in milliseconds.

Key features:
- Durability: 99.999999999% (11 9's)
- Availability: 99.9%
- Milliseconds retrieval time
- Minimum storage duration: 90 days
- Retrieval fee applies
- Minimum billable object size: 128KB
- Ideal for archive data that needs immediate access

## S3 Glacier Flexible Retrieval (formerly S3 Glacier)
S3 Glacier Flexible Retrieval is a secure, durable, and low-cost storage class for data archiving. It provides three retrieval options that range from minutes to hours.

Key features:
- Durability: 99.999999999% (11 9's)
- Retrieval options: Expedited (1-5 minutes), Standard (3-5 hours), Bulk (5-12 hours)
- Minimum storage duration: 90 days
- Retrieval fee applies
- Minimum billable object size: 40KB
- Ideal for archive data that occasionally needs to be retrieved

## S3 Glacier Deep Archive
S3 Glacier Deep Archive is Amazon S3's lowest-cost storage class and supports long-term retention and digital preservation for data that may be accessed once or twice in a year.

Key features:
- Durability: 99.999999999% (11 9's)
- Retrieval time: Standard (12 hours), Bulk (48 hours)
- Minimum storage duration: 180 days
- Retrieval fee applies
- Minimum billable object size: 40KB
- Ideal for long-term data archiving and preservation

## Comparison Table

| Storage Class | Durability | Availability | Retrieval Time | Min Storage Duration | Min Billable Size |
|---------------|------------|--------------|----------------|----------------------|-------------------|
| S3 Standard | 99.999999999% | 99.99% | Milliseconds | None | None |
| S3 Intelligent-Tiering | 99.999999999% | 99.9% | Milliseconds | None | None |
| S3 Standard-IA | 99.999999999% | 99.9% | Milliseconds | 30 days | 128KB |
| S3 One Zone-IA | 99.999999999% (single AZ) | 99.5% | Milliseconds | 30 days | 128KB |
| S3 Glacier Instant Retrieval | 99.999999999% | 99.9% | Milliseconds | 90 days | 128KB |
| S3 Glacier Flexible Retrieval | 99.999999999% | N/A | Minutes to hours | 90 days | 40KB |
| S3 Glacier Deep Archive | 99.999999999% | N/A | Hours | 180 days | 40KB |

## Module 2: API integration troubleshooting

### Step 1: Create an API Error Logging and Analysis System

Let's build a system to diagnose API integration issues:

```python
import boto3
import json
import time
import uuid
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any

class APIIntegrationDiagnostic:
    """Class for diagnosing API integration issues with Amazon Bedrock"""
    
    def __init__(self, log_group_name="/aws/bedrock/api-diagnostics"):
        """Initialize the API integration diagnostic tool"""
        self.bedrock_runtime = boto3.client('bedrock-runtime')
        self.cloudwatch = boto3.client('cloudwatch')
        self.logs = boto3.client('logs')
        self.log_group_name = log_group_name
        self.log_stream_name = f"api-diagnostics-{datetime.utcnow().strftime('%Y-%m-%d')}"
        
        # Ensure log group exists
        self._ensure_log_group_exists()
        
        # Define common error patterns and solutions
        self.error_patterns = {
            "AccessDeniedException": {
                "description": "The request was denied due to insufficient permissions",
                "possible_causes": [
                    "IAM policy does not grant access to Bedrock API",
                    "Resource-based policy restricts access",
                    "Service control policies (SCPs) are restricting access"
                ],
                "solutions": [
                    "Check IAM permissions for the calling identity",
                    "Ensure the IAM role/user has bedrock:InvokeModel permission",
                    "Verify no SCPs are blocking Bedrock access"
                ]
            },
            "ValidationException": {
                "description": "The request parameters are invalid",
                "possible_causes": [
                    "Invalid model ID",
                    "Malformed request body",
                    "Missing required parameters",
                    "Parameter values outside allowed range"
                ],
                "solutions": [
                    "Verify the model ID is correct and available in your region",
                    "Check request body structure against API documentation",
                    "Ensure all required parameters are provided",
                    "Validate parameter values are within allowed ranges"
                ]
            },
            "ThrottlingException": {
                "description": "The request was denied due to request throttling",
                "possible_causes": [
                    "Exceeded API rate limits",
                    "Exceeded concurrent request limits",
                    "Burst of requests exceeding quota"
                ],
                "solutions": [
                    "Implement exponential backoff and retry strategy",
                    "Request quota increase if consistently hitting limits",
                    "Implement request batching or queuing",
                    "Consider using provisioned throughput"
                ]
            },
            "ServiceQuotaExceededException": {
                "description": "The request was denied because a service quota was exceeded",
                "possible_causes": [
                    "Exceeded token quota",
                    "Exceeded model invocation quota",
                    "Exceeded concurrent request quota"
                ],
                "solutions": [
                    "Request quota increase through AWS Support",
                    "Implement request throttling in your application",
                    "Optimize token usage to stay within limits"
                ]
            },
            "ModelStreamErrorException": {
                "description": "Error occurred during streaming response",
                "possible_causes": [
                    "Network interruption during streaming",
                    "Client disconnection",
                    "Server-side streaming error"
                ],
                "solutions": [
                    "Implement robust error handling for streaming responses",
                    "Add retry logic for streaming failures",
                    "Consider non-streaming API for critical operations"
                ]
            },
            "ModelTimeoutException": {
                "description": "The model request timed out",
                "possible_causes": [
                    "Complex prompt requiring excessive processing time",
                    "Model overloaded",
                    "Request too large"
                ],
                "solutions": [
                    "Simplify or shorten prompts",
                    "Break complex requests into smaller chunks",
                    "Implement client-side timeout handling"
                ]
            },
            "InternalServerException": {
                "description": "An internal server error occurred",
                "possible_causes": [
                    "Temporary service issue",
                    "Backend processing error"
                ],
                "solutions": [
                    "Implement retry logic with exponential backoff",
                    "Check AWS Health Dashboard for service issues",
                    "Contact AWS Support if persistent"
                ]
            }
        }
    
    def _ensure_log_group_exists(self):
        """Ensure the CloudWatch Logs group exists"""
        try:
            self.logs.create_log_group(logGroupName=self.log_group_name)
        except self.logs.exceptions.ResourceAlreadyExistsException:
            pass  # Log group already exists
        
        try:
            self.logs.create_log_stream(
                logGroupName=self.log_group_name,
                logStreamName=self.log_stream_name
            )
        except self.logs.exceptions.ResourceAlreadyExistsException:
            pass  # Log stream already exists
    
    def log_api_request(self, 
                       request_id: str,
                       model_id: str,
                       request_data: Dict[str, Any],
                       response_data: Dict[str, Any] = None,
                       error: Exception = None,
                       latency_ms: float = None) -> Dict[str, Any]:
        """
        Log an API request to CloudWatch Logs.
        
        Args:
            request_id: Unique identifier for the request
            model_id: The model ID
            request_data: Request data (excluding sensitive content)
            response_data: Response data (if successful)
            error: Exception object (if failed)
            latency_ms: Request latency in milliseconds
            
        Returns:
            Dictionary with logging results
        """
        try:
            # Prepare log entry
            timestamp = int(datetime.utcnow().timestamp() * 1000)
            
            # Create sanitized request data (remove sensitive content)
            sanitized_request = self._sanitize_request_data(request_data)
            
            # Create sanitized response data (if available)
            sanitized_response = None
            if response_data:
                sanitized_response = self._sanitize_response_data(response_data)
            
            # Create error data (if available)
            error_data = None
            if error:
                error_data = {
                    "type": error.__class__.__name__,
                    "message": str(error),
                    "analysis": self._analyze_error(error)
                }
            
            # Create log entry
            log_entry = {
                "request_id": request_id,
                "timestamp": timestamp,
                "model_id": model_id,
                "request": sanitized_request,
                "response": sanitized_response,
                "error": error_data,
                "latency_ms": latency_ms,
                "success": error is None
            }
            
            # Log to CloudWatch Logs
            self.logs.put_log_events(
                logGroupName=self.log_group_name,
                logStreamName=self.log_stream_name,
                logEvents=[
                    {
                        'timestamp': timestamp,
                        'message': json.dumps(log_entry)
                    }
                ]
            )
            
            # Publish metrics to CloudWatch
            self._publish_metrics(model_id, error, latency_ms)
            
            return {
                "logged": True,
                "request_id": request_id,
                "log_group": self.log_group_name,
                "log_stream": self.log_stream_name
            }
        except Exception as e:
            print(f"Error logging API request: {e}")
            return {
                "logged": False,
                "error": str(e),
                "request_id": request_id
            }
    
    def _sanitize_request_data(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize request data to remove sensitive content"""
        if not request_data:
            return {}
        
        sanitized = {}
        
        # Copy request data
        for key, value in request_data.items():
            if key in ["prompt", "inputText", "messages"]:
                # For prompts and messages, include only length or count
                if isinstance(value, str):
                    sanitized[key] = f"[Text length: {len(value)} chars]"
                elif isinstance(value, list):
                    sanitized[key] = f"[{len(value)} messages]"
                else:
                    sanitized[key] = "[Content redacted]"
            else:
                # Include other parameters as-is
                sanitized[key] = value
        
        return sanitized
    
    def _sanitize_response_data(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize response data to remove sensitive content"""
        if not response_data:
            return {}
        
        sanitized = {}
        
        # Copy response data
        for key, value in response_data.items():
            if key in ["completion", "outputText", "content", "results"]:
                # For response content, include only length
                if isinstance(value, str):
                    sanitized[key] = f"[Text length: {len(value)} chars]"
                elif isinstance(value, list):
                    sanitized[key] = f"[{len(value)} items]"
                else:
                    sanitized[key] = "[Content redacted]"
            else:
                # Include other parameters as-is
                sanitized[key] = value
        
        return sanitized
    
    def _analyze_error(self, error: Exception) -> Dict[str, Any]:
        """Analyze an error and provide diagnostic information"""
        error_type = error.__class__.__name__
        error_message = str(error)
        
        # Check for known error patterns
        for pattern, info in self.error_patterns.items():
            if pattern in error_type or pattern in error_message:
                return {
                    "error_type": pattern,
                    "description": info["description"],
                    "possible_causes": info["possible_causes"],
                    "solutions": info["solutions"]
                }
        
        # If no pattern matches, return generic error analysis
        return {
            "error_type": error_type,
            "description": "An unexpected error occurred",
            "possible_causes": [error_message],
            "solutions": [
                "Review the error message for specific details",
                "Check AWS service status",
                "Verify your request parameters",
                "Consult AWS documentation for the specific service"
            ]
        }

### Step 2: Test the API integration diagnostic tool

```python
def test_api_diagnostics():
    diagnostic = APIIntegrationDiagnostic()
    
    # Test with a valid model
    print("Testing API integration...")
    
    result = diagnostic.diagnose_api_call(
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        request_body={
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": "What is Amazon Bedrock?"
                }
            ]
        }
    )
    
    print("\nDiagnostic Results:")
    print(json.dumps(result, indent=2))
    
    # Test with an invalid model (should generate an error)
    print("\n\nTesting with invalid model...")
    
    result = diagnostic.diagnose_api_call(
        model_id="invalid-model-id",
        request_body={
            "prompt": "Test",
            "max_tokens": 100
        }
    )
    
    print("\nDiagnostic Results:")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_api_diagnostics()
```

The document formatting is now complete with proper headers, code blocks, and structure.