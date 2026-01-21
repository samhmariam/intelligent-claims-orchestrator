# Project Architecture Overview

## Document Processing and Segmentation

### Objective

- Implement and compare multiple chunking strategies.
- Create a hierarchical document representation.
- Evaluate retrieval performance across segmentation approaches.

### Tasks

1. **Setup**:
   - Create an S3 bucket to store AWS documentation PDFs and text files.
   - Set up an AWS Lambda function for document processing.

2. **Chunking Strategies**:

#### Strategy 1: Fixed-size Chunking with Overlap

```python
# Function to split text into fixed-size chunks with overlap
# This ensures that important context is not lost between chunks
def fixed_size_chunking(text, chunk_size=1000, overlap=100):
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Find a good breaking point (end of sentence)
        if end < len(text):
            # Look for period, question mark, or exclamation point followed by space
            for i in range(end-1, max(start+chunk_size//2, start), -1):
                if text[i] in ['.', '?', '!'] and i+1 < len(text) and text[i+1] == ' ':
                    end = i + 1
                    break
        chunks.append(text[start:end])
        start = end - overlap
    return chunks
```

#### Strategy 2: Hierarchical Chunking Based on Document Structure

```python
# Function to split text into hierarchical chunks based on sections and subsections
# This preserves the document's structure for better retrieval
import re

def hierarchical_chunking(text):
    # Split by sections, then subsections
    sections = re.split(r'\n## ', text)
    chunks = []
    
    for section in sections:
        if not section.strip():
            continue
            
        # Add section as a chunk with metadata
        section_title = section.split('\n')[0]
        chunks.append({
            'text': section,
            'metadata': {'level': 'section', 'title': section_title}
        })
        
        # Split into subsections
        subsections = re.split(r'\n### ', section)
        for i, subsection in enumerate(subsections):
            if i == 0 or not subsection.strip():  # Skip the first one (it's the section intro)
                continue
                
            subsection_title = subsection.split('\n')[0]
            chunks.append({
                'text': subsection,
                'metadata': {
                    'level': 'subsection', 
                    'title': subsection_title,
                    'parent_section': section_title
                }
            })
            
    return chunks
```

#### Strategy 3: Semantic Chunking Using Amazon Bedrock

```python
# Function to split text into semantic chunks using Amazon Bedrock
# This uses a foundation model to identify meaningful boundaries
import boto3
import json

def semantic_chunking(text, bedrock_client):
    # Use Amazon Bedrock to identify semantic boundaries
    response = bedrock_client.invoke_model(
        modelId="amazon.titan-text-express-v1",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": f"Split the following text into coherent chunks that preserve meaning:\n\n{text[:4000]}",
            "textGenerationConfig": {
                "maxTokenCount": 4096,
                "temperature": 0,
                "topP": 0.9
            }
        })
    )
    
    result = json.loads(response.get('body').read())
    # Process the response to extract chunks
    # Implementation depends on the exact response format
    
    return chunks
```

---

## Embedding Generation and Optimization

### Objective

- Compare embedding models for technical documentation.
- Implement batch processing for efficiency.
- Evaluate embedding performance metrics.

### Tasks

#### Compare Embedding Models

```python
import boto3
import json

# Initialize Bedrock runtime client
bedrock_runtime = boto3.client('bedrock-runtime')

# Function to generate embeddings using Amazon Titan
# This generates vector embeddings for text chunks
def generate_titan_embeddings(text_chunks):
    embeddings = []
    
    for chunk in text_chunks:
        response = bedrock_runtime.invoke_model(
            modelId='amazon.titan-embed-text-v1',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'inputText': chunk
            })
        )
        
        embedding = json.loads(response['body'].read())['embedding']
        embeddings.append(embedding)
        
    return embeddings

# Function to generate embeddings using Cohere
# This uses a different embedding model for comparison
def generate_cohere_embeddings(text_chunks):
    embeddings = []
    
    for chunk in text_chunks:
        response = bedrock_runtime.invoke_model(
            modelId='cohere.embed-english-v3',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'texts': [chunk],
                'input_type': 'search_document'
            })
        )
        
        embedding = json.loads(response['body'].read())['embeddings'][0]
        embeddings.append(embedding)
        
    return embeddings
```

#### Batch Processing for Efficiency

```python
# Function to process text chunks in batches for embedding generation
# This improves efficiency by reducing API calls
def batch_generate_embeddings(chunks, model_id, batch_size=20):
    all_embeddings = []
    
    # Process in batches
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        
        if model_id == 'amazon.titan-embed-text-v1':
            # Titan processes one at a time
            batch_embeddings = []
            for text in batch:
                response = bedrock_runtime.invoke_model(
                    modelId=model_id,
                    contentType='application/json',
                    accept='application/json',
                    body=json.dumps({
                        'inputText': text
                    })
                )
                embedding = json.loads(response['body'].read())['embedding']
                batch_embeddings.append(embedding)
        
        elif model_id == 'cohere.embed-english-v3':
            # Cohere can process batches natively
            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    'texts': batch,
                    'input_type': 'search_document'
                })
            )
            batch_embeddings = json.loads(response['body'].read())['embeddings']
        
        all_embeddings.extend(batch_embeddings)
        
    return all_embeddings
```

#### Evaluate Embedding Performance

```python
# Create pairs of semantically similar and dissimilar chunks
# Calculate cosine similarity between pairs
# Measure embedding quality using:
# - Contrast: difference between similar and dissimilar pairs
# - Clustering quality: how well embeddings group related content
# - Query-document relevance: how well embeddings match queries to relevant chunks
```

---

## Vector Store Implementation

### Objective

- Deploy and configure multiple vector search solutions.
- Measure query latency and accuracy.

### Tasks

#### Deploy OpenSearch Service

```yaml
# CloudFormation snippet for OpenSearch with vector search
OpenSearchCluster:
  Type: AWS::OpenSearchService::Domain
  Properties:
    DomainName: technical-docs-search
    EngineVersion: OpenSearch_2.9
    ClusterConfig:
      InstanceType: r6g.large.search
      InstanceCount: 2
      DedicatedMasterEnabled: true
      DedicatedMasterType: r6g.large.search
      DedicatedMasterCount: 3
    EBSOptions:
      EBSEnabled: true
      VolumeType: gp3
      VolumeSize: 100
    AdvancedOptions:
      "rest.action.multi.allow_explicit_index": "true"
      "plugins.security.disabled": "true"
    AccessPolicies:
      Version: "2012-10-17"
      Statement:
        - Effect: Allow
          Principal:
            AWS: !GetAtt LambdaExecutionRole.Arn
          Action: "es:*"
          Resource: !Sub "arn:aws:es:${AWS::Region}:${AWS::AccountId}:domain/technical-docs-search/*"
```

#### Set Up Index Mappings for Vector Search

```python
# OpenSearch index creation with vector field
def create_opensearch_index(client):
    index_name = "technical-documentation"
    index_body = {
        "settings": {
            "index": {
                "number_of_shards": 4,
                "number_of_replicas": 1,
                "knn": True,
                "knn.algo_param.ef_search": 100
            }
        },
        "mappings": {
            "properties": {
                "text": {"type": "text"},
                "title": {"type": "text"},
                "document_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "metadata": {"type": "object"},
                "vector_embedding": {
                    "type": "knn_vector",
                    "dimension": 1536,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "nmslib",
                        "parameters": {
                            "ef_construction": 128,
                            "m": 16
                        }
                    }
                }
            }
        }
    }
    
    client.indices.create(index=index_name, body=index_body)
```

#### Configure Aurora with pgvector

```sql
-- SQL to set up pgvector in Aurora PostgreSQL
CREATE EXTENSION IF NOT EXISTS vector;

-- Create table for document chunks
CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    chunk_id VARCHAR(255) NOT NULL,
    text TEXT NOT NULL,
    title VARCHAR(255),
    metadata JSONB,
    embedding VECTOR(1536)
);

-- Create index for vector similarity search
CREATE INDEX embedding_idx ON document_chunks 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

#### Set Up Amazon Bedrock Knowledge Base

```python
# Python code to create a Bedrock Knowledge Base
import boto3

bedrock = boto3.client('bedrock')

# Create a knowledge base
response = bedrock.create_knowledge_base(
    name="TechnicalDocsKB",
    description="Knowledge base for AWS technical documentation",
    roleArn="arn:aws:iam::123456789012:role/BedrockKBServiceRole",
    knowledgeBaseConfiguration={
        "type": "VECTOR",
        "vectorKnowledgeBaseConfiguration": {
            "embeddingModelArn": "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1"
        }
    }
)

knowledge_base_id = response['knowledgeBase']['knowledgeBaseId']

# Create a data source for the knowledge base
response = bedrock.create_data_source(
    knowledgeBaseId=knowledge_base_id,
    name="TechnicalDocsSource",
    description="AWS technical documentation source",
    dataSourceConfiguration={
        "type": "S3",
        "s3Configuration": {
            "bucketName": "technical-docs-bucket",
            "inclusionPrefixes": ["processed/"]
        }
    },
    vectorIngestionConfiguration={
        "chunkingConfiguration": {
            "chunkingStrategy": "HIERARCHICAL"
        }
    }
)
```

#### Performance Comparison

```python
# Implement benchmark queries across all vector stores
# Measure query latency, recall, and precision
# Document strengths and weaknesses of each approach
```

---

## Advanced Search Architecture

### Objective

- Implement hybrid search capabilities.
- Add reranking for improved relevance.
- Create evaluation metrics for search quality.

### Tasks

#### Implement Hybrid Search

```python
def hybrid_search(query_text, opensearch_client):
    # Generate embedding for the query
    query_embedding = generate_embedding(query_text)
    
    # Construct hybrid query with both keyword and vector components
    search_query = {
        "size": 20,
        "query": {
            "bool": {
                "should": [
                    # Vector similarity component (75% weight)
                    {
                        "knn": {
                            "vector_embedding": {
                                "vector": query_embedding,
                                "k": 20
                            }
                        }
                    },
                    # Keyword match component (25% weight)
                    {
                        "multi_match": {
                            "query": query_text,
                            "fields": ["text^3", "title^5"],
                            "fuzziness": "AUTO"
                        }
                    }
                ]
            }
        },
        "_source": ["text", "title", "document_id", "chunk_id", "metadata"]
    }
    
    response = opensearch_client.search(
        index="technical-documentation",
        body=search_query
    )
    
    return response['hits']['hits']
```

#### Implement Reranking with Bedrock

```python
def rerank_results(query, search_results, bedrock_client, top_k=5):
    # Extract texts from search results
    texts = [result["_source"]["text"] for result in search_results]
    
    # Call Bedrock reranker
    response = bedrock_client.invoke_model(
        modelId="amazon.titan-rerank-v1",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "query": query,
            "passages": texts
        })
    )
    
    reranked_results = json.loads(response['body'].read())
    
    # Sort original results based on reranking scores
    scored_results = []
    for i, score in enumerate(reranked_results["scores"]):
        scored_results.append({
            "score": score,
            "original_result": search_results[i]
        })
    
    # Sort by score descending and return top_k
    scored_results.sort(key=lambda x: x["score"], reverse=True)
    return scored_results[:top_k]
```

#### Create Evaluation Metrics

```python
# Implement Mean Reciprocal Rank (MRR) calculation
# Measure Normalized Discounted Cumulative Gain (NDCG)
# Compare performance between vector-only, keyword-only, hybrid, and reranked approaches
```

---

## Query Processing System

### Objective

- Build query expansion capabilities.
- Implement query decomposition for complex questions.
- Create a workflow for handling multi-part queries.

### Tasks

#### Implement Query Expansion

```python
def expand_query(query_text, bedrock_client):
    # Use Bedrock to expand the query with relevant terms
    response = bedrock_client.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": f"""Given this technical query about AWS services: 
                    "{query_text}"
                    
                    Generate 3-5 alternative ways to phrase this query that would help in a search system.
                    Include relevant AWS terminology, service names, and technical concepts.
                    Format your response as a JSON array of strings with no additional text."""
                }
            ]
        })
    )
    
    result = json.loads(response['body'].read())
    expanded_queries = json.loads(result['content'][0]['text'])
    
    # Add the original query to the expanded queries
    expanded_queries.insert(0, query_text)
    
    return expanded_queries
```

#### Implement Query Decomposition

```python
def decompose_complex_query(query_text, bedrock_client):
    # Use Bedrock to break down complex queries
    response = bedrock_client.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": f"""Break down this complex technical query into simpler sub-queries that can be answered independently:
                    "{query_text}"
                    
                    Format your response as a JSON object with:
                    1. "sub_queries": an array of simpler questions
                    2. "reasoning": explanation of how these sub-queries relate to the original question
                    
                    Return only the JSON with no additional text."""
                }
            ]
        })
    )
    
    result = json.loads(response['body'].read())
    decomposition = json.loads(result['content'][0]['text'])
    
    return decomposition
```

#### Create Step Functions Workflow

```json
{
  "Comment": "Query Processing Workflow",
  "StartAt": "AnalyzeQueryComplexity",
  "States": {
    "AnalyzeQueryComplexity": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:AnalyzeQueryComplexity",
        "Payload": {
          "query": "$.query"
        }
      },
      "ResultPath": "$.complexity",
      "Next": "ComplexityChoice"
    },
    "ComplexityChoice": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.complexity.isComplex",
          "BooleanEquals": true,
          "Next": "DecomposeQuery"
        }
      ],
      "Default": "ExpandQuery"
    },
    "DecomposeQuery": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:DecomposeQuery",
        "Payload": {
          "query": "$.query"
        }
      },
      "ResultPath": "$.subQueries",
      "Next": "ProcessSubQueries"
    },
    "ProcessSubQueries": {
      "Type": "Map",
      "ItemsPath": "$.subQueries.sub_queries",
      "Parameters": {
        "subQuery.$": "$$.Map.Item.Value"
      },
      "Iterator": {
        "StartAt": "ExpandSubQuery",
        "States": {
          "ExpandSubQuery": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:ExpandQuery",
              "Payload": {
                "query": "$.subQuery"
              }
            },
            "ResultPath": "$.expandedQueries",
            "Next": "SearchWithSubQuery"
          },
          "SearchWithSubQuery": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:SearchDocuments",
              "Payload": {
                "queries": "$.expandedQueries"
              }
            },
            "End": true
          }
        }
      },
      "ResultPath": "$.subQueryResults",
      "Next": "AggregateResults"
    },
    "ExpandQuery": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:ExpandQuery",
        "Payload": {
          "query": "$.query"
        }
      },
      "ResultPath": "$.expandedQueries",
      "Next": "SearchDocuments"
    },
    "SearchDocuments": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:SearchDocuments",
        "Payload": {
          "queries": "$.expandedQueries"
        }
      },
      "ResultPath": "$.searchResults",
      "Next": "RerankResults"
    },
    "RerankResults": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:RerankResults",
        "Payload": {
          "query": "$.query",
          "results": "$.searchResults"
        }
      },
      "ResultPath": "$.rankedResults",
      "End": true
    },
    "AggregateResults": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "arn:aws:lambda:us-east-1:123456789012:function:AggregateResults",
        "Payload": {
          "originalQuery": "$.query",
          "subQueryResults": "$.subQueryResults",
          "decomposition": "$.subQueries"
        }
      },
      "ResultPath": "$.aggregatedResults",
      "Next": "RerankResults"
    }
  }
}
```

---

## Integration Layer

### Objective

- Create standardized access patterns.
- Implement function calling interfaces.
- Build a consistent API layer for foundation model integration.

### Tasks

#### Create Standardized API for Vector Search

```python
# Lambda function for API Gateway integration
def lambda_handler(event, context):
    try:
        # Extract parameters from the request
        body = json.loads(event['body'])
        query = body.get('query')
        search_type = body.get('search_type', 'hybrid')  # Default to hybrid search
        top_k = body.get('top_k', 5)
        rerank = body.get('rerank', True)
        
        # Validate input
        if not query:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Query parameter is required'})
            }
        
        # Initialize clients
        bedrock_client = boto3.client('bedrock-runtime')
        opensearch_client = get_opensearch_client()
        
        # Process query based on search type
        if search_type == 'vector':
            # Vector search only
            results = vector_search(query, opensearch_client, top_k)
        elif search_type == 'keyword':
            # Keyword search only
            results = keyword_search(query, opensearch_client, top_k)
        elif search_type == 'hybrid':
            # Hybrid search
            results = hybrid_search(query, opensearch_client, top_k)
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Invalid search_type: {search_type}'})
            }
        
        # Apply reranking if requested
        if rerank and results:
            results = rerank_results(query, results, bedrock_client, top_k)
        
        # Format and return results
        formatted_results = format_search_results(results)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'query': query,
                'search_type': search_type,
                'results': formatted_results
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

#### Implement Function Calling Interface

```python
def create_function_schema():
    # Define the function schema for search capabilities
    search_function = {
        "name": "search_documentation",
        "description": "Search technical documentation for relevant information",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query or question"
                },
                "search_type": {
                    "type": "string",
                    "enum": ["vector", "keyword", "hybrid"],
                    "description": "Type of search to perform"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return"
                },
                "rerank": {
                    "type": "boolean",
                    "description": "Whether to apply reranking to results"
                }
            },
            "required": ["query"]
        }
    }
    
    return [search_function]

def invoke_fm_with_function_calling(user