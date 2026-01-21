# Project Architecture Overview

## Phase 1: Set Up Foundation Model and Vector Database Infrastructure

### Objective

- Create the core infrastructure for a Retrieval-Augmented Generation (RAG) system using Amazon Bedrock and vector databases.

### Tasks

1. **Set up Amazon Bedrock Access**:
   - Enable Amazon Bedrock in your AWS account.
   - Request access to foundation models (Claude, Titan, etc.).
   - Create an IAM role with appropriate permissions.

2. **Create a Vector Database Using Amazon Bedrock Knowledge Bases**:
   - Set up a new Knowledge Base in Amazon Bedrock.
   - Configure storage options (e.g., S3 bucket for documents).
   - Select an appropriate embedding model.
   - Configure retrieval settings (e.g., number of results, similarity threshold).

3. **Set Up an Alternative Vector Store Using OpenSearch Service**:
   - Deploy an Amazon OpenSearch Service domain.
   - Enable the Neural Search plugin.
   - Configure instance types and storage.
   - Set up initial index settings and mappings for vector search.

4. **Create a Metadata Database Using DynamoDB**:
   - Design a schema for document metadata.
   - Create a DynamoDB table with appropriate partition and sort keys.
   - Configure capacity mode (on-demand or provisioned).

---

## Phase 2: Develop Document Processing and Embedding Pipeline

### Objective

- Build a robust pipeline to process documents, extract metadata, and generate vector embeddings.

### Tasks

1. **Create an S3 Bucket for Document Storage**:
   - Set up appropriate bucket policies and encryption.
   - Create folders for different document types (e.g., technical docs, research papers, policies).

2. **Implement Document Processing with AWS Lambda**:
   - Create a Lambda function triggered by S3 object creation.
   - Extract text content from various document formats (PDF, DOCX, HTML).
   - Implement chunking strategies (e.g., fixed size, semantic paragraphs, sliding window).
   - Extract and generate metadata from documents.

3. **Build an Embedding Generation Pipeline**:
   - Use Amazon Bedrock embedding models to generate vector embeddings.
   - Store embeddings in your vector database (Knowledge Base or OpenSearch).
   - Implement batch processing for efficient embedding generation.
   - Create a mechanism to track embedding status in DynamoDB.

4. **Develop a Metadata Enrichment Process**:
   - Extract document properties (e.g., creation date, author, title).
   - Generate additional metadata (e.g., document length, reading level, topic classification).
   - Store enriched metadata in DynamoDB.
   - Create relationships between chunks and parent documents.

---

## Implementation Details

### Amazon Bedrock Knowledge Base Setup

```python
import boto3
import json

# Initialize Bedrock client
bedrock = boto3.client('bedrock')

# Create a Knowledge Base
response = bedrock.create_knowledge_base(
    name="TechnicalDocumentationKB",
    description="Knowledge base for technical documentation",
    roleArn="arn:aws:iam::123456789012:role/BedrockKBRole",
    knowledgeBaseConfiguration={
        "type": "VECTOR",
        "vectorKnowledgeBaseConfiguration": {
            "embeddingModelArn": "arn:aws:bedrock:us-east-1::embeddings/amazon.titan-embed-text-v1"
        }
    }
)

# Extract Knowledge Base ID
knowledge_base_id = response['knowledgeBase']['knowledgeBaseId']
print(f"Created Knowledge Base with ID: {knowledge_base_id}")

# Create a Data Source for the Knowledge Base
response = bedrock.create_data_source(
    knowledgeBaseId=knowledge_base_id,
    name="TechnicalDocsSource",
    description="Technical documentation source",
    dataSourceConfiguration={
        "type": "S3",
        "s3Configuration": {
            "bucketArn": "arn:aws:s3:::technical-docs-bucket",
            "inclusionPrefixes": ["documentation/"]
        }
    },
    vectorIngestionConfiguration={
        "chunkingConfiguration": {
            "chunkingStrategy": "SEMANTIC_CHUNKING",
            "fixedSizeChunkingConfiguration": {
                "maxTokens": 300,
                "overlapPercentage": 10
            }
        }
    }
)

# Extract Data Source ID
data_source_id = response['dataSource']['dataSourceId']
print(f"Created Data Source with ID: {data_source_id}")
```

### OpenSearch Service Setup

```yaml
# CloudFormation template excerpt for OpenSearch Service
Resources:
  OpenSearchServiceDomain:
    Type: AWS::OpenSearch::Domain
    Properties:
      DomainName: vector-search-domain
      EngineVersion: OpenSearch_2.11
      ClusterConfig:
        InstanceType: r6g.large.search
        InstanceCount: 3
        ZoneAwarenessEnabled: true
        ZoneAwarenessConfig:
          AvailabilityZoneCount: 3
      EBSOptions:
        EBSEnabled: true
        VolumeType: gp3
        VolumeSize: 100
      AdvancedOptions:
        "rest.action.multi.allow_explicit_index": "true"
        "plugins.ml_commons.only_run_on_ml_node": "false"
      AccessPolicies:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              AWS: !GetAtt LambdaExecutionRole.Arn
            Action: "es:*"
            Resource: !Sub "arn:aws:es:${AWS::Region}:${AWS::AccountId}:domain/vector-search-domain/*"
      AdvancedSecurityOptions:
        Enabled: true
        InternalUserDatabaseEnabled: true
        MasterUserOptions:
          MasterUserName: admin
          MasterUserPassword: !Ref MasterUserPassword
      NodeToNodeEncryptionOptions:
        Enabled: true
      EncryptionAtRestOptions:
        Enabled: true
      DomainEndpointOptions:
        EnforceHTTPS: true
      PluginOptions:
        - PluginName: "ml-commons"
          Enabled: true
        - PluginName: "neural-search"
          Enabled: true
```

### DynamoDB Metadata Table Setup

```python
import boto3

# Initialize DynamoDB client
dynamodb = boto3.client('dynamodb')

# Create table for document metadata
response = dynamodb.create_table(
    TableName='DocumentMetadata',
    KeySchema=[
        {
            'AttributeName': 'document_id',
            'KeyType': 'HASH'  # Partition key
        },
        {
            'AttributeName': 'chunk_id',
            'KeyType': 'RANGE'  # Sort key
        }
    ],
    AttributeDefinitions=[
        {
            'AttributeName': 'document_id',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'chunk_id',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'document_type',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'last_updated',
            'AttributeType': 'S'
        }
    ],
    GlobalSecondaryIndexes=[
        {
            'IndexName': 'DocumentTypeIndex',
            'KeySchema': [
                {
                    'AttributeName': 'document_type',
                    'KeyType': 'HASH'
                },
                {
                    'AttributeName': 'last_updated',
                    'KeyType': 'RANGE'
                }
            ],
            'Projection': {
                'ProjectionType': 'ALL'
            },
            'ProvisionedThroughput': {
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        }
    ],
    BillingMode='PAY_PER_REQUEST'
)

print(f"Created DynamoDB table: {response['TableDescription']['TableName']}")
```

### Lambda Function for Document Processing

```python
import boto3
import json
import os
import uuid
import hashlib
from datetime import datetime
import PyPDF2
import docx
import io
import re

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime')

metadata_table = dynamodb.Table('DocumentMetadata')

def lambda_handler(event, context):
    # Get the S3 bucket and key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    # Generate a unique document ID
    document_id = str(uuid.uuid4())
    
    # Extract file metadata
    response = s3.head_object(Bucket=bucket, Key=key)
    content_type = response.get('ContentType', '')
    last_modified = response.get('LastModified').strftime('%Y-%m-%dT%H:%M:%S')
    
    # Download the document
    response = s3.get_object(Bucket=bucket, Key=key)
    document_content = response['Body'].read()
    
    # Extract text based on file type
    if key.lower().endswith('.pdf'):
        text = extract_text_from_pdf(document_content)
        document_type = 'pdf'
    elif key.lower().endswith('.docx'):
        text = extract_text_from_docx(document_content)
        document_type = 'docx'
    elif key.lower().endswith('.txt'):
        text = document_content.decode('utf-8')
        document_type = 'txt'
    else:
        raise ValueError(f"Unsupported file type: {key}")
    
    # Generate document checksum for change detection
    checksum = hashlib.md5(document_content).hexdigest()
    
    # Extract basic metadata
    title = os.path.basename(key)
    author = response.get('Metadata', {}).get('author', 'Unknown')
    
    # Create document chunks using semantic chunking
    chunks = create_semantic_chunks(text)
    
    # Store document metadata in DynamoDB
    base_metadata = {
        'document_id': document_id,
        'title': title,
        'author': author,
        'document_type': document_type,
        'source_bucket': bucket,
        'source_key': key,
        'content_type': content_type,
        'last_updated': last_modified,
        'checksum': checksum,
        'total_chunks': len(chunks)
    }
    
    # Process each chunk
    for i, chunk in enumerate(chunks):
        chunk_id = f"{document_id}-{i}"
        
        # Generate embedding for the chunk
        embedding = generate_embedding(chunk)
        
        # Store chunk metadata
        chunk_metadata = base_metadata.copy()
        chunk_metadata.update({
            'chunk_id': chunk_id,
            'chunk_index': i,
            'chunk_text': chunk,
            'chunk_length': len(chunk),
            'embedding_status': 'completed'
        })
        
        metadata_table.put_item(Item=chunk_metadata)
        
        # Store embedding in vector database (implementation depends on chosen vector store)
        store_embedding_in_vector_db(chunk_id, embedding, chunk, chunk_metadata)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'document_id': document_id,
            'chunks_processed': len(chunks)
        })
    }

def extract_text_from_pdf(pdf_content):
    pdf_file = io.BytesIO(pdf_content)
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page_num in range(len(pdf_reader.pages)):
        text += pdf_reader.pages[page_num].extract_text()
    return text

def extract_text_from_docx(docx_content):
    docx_file = io.BytesIO(docx_content)
    doc = docx.Document(docx_file)
    text = ""
    for para in doc.paragraphs:
        text += para.text + "\n"
    return text

def create_semantic_chunks(text, max_chunk_size=1000, overlap=100):
    # Simple implementation - in production, use more sophisticated semantic chunking
    chunks = []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            # Include overlap from the previous chunk
            overlap_text = " ".join(current_chunk.split()[-overlap:]) if overlap > 0 else ""
            current_chunk = overlap_text + " " + sentence + " "
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def generate_embedding(text):
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v1",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": text
        })
    )
    
    response_body = json.loads(response['body'].read())
    return response_body['embedding']

def store_embedding_in_vector_db(chunk_id, embedding, text, metadata):
    # Implementation depends on chosen vector database (OpenSearch or Bedrock KB)
    # This is a placeholder for the actual implementation
    pass
```

### OpenSearch Index Configuration for Hierarchical Documents

```python
import boto3
import requests
from requests_aws4auth import AWS4Auth
import json

# AWS region and service
region = 'us-east-1'
service = 'es'

# Get AWS credentials
credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, 
                   region, service, session_token=credentials.token)

# OpenSearch domain and index details
host = 'https://your-opensearch-domain.us-east-1.es.amazonaws.com'
index_name = 'technical_documentation'
url = host + '/' + index_name

# Define the index mapping with hierarchical structure
index_mapping = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 100
        }
    },
    "mappings": {
        "properties": {
            "document_id": {"type": "keyword"},
            "parent_id": {"type": "keyword"},
            "title": {"type": "text"},
            "content": {"type": "text"},
            "metadata": {
                "properties": {
                    "author": {"type": "keyword"},
                    "created_date": {"type": "date"},
                    "document_type": {"type": "keyword"},
                    "department": {"type": "keyword"},
                    "tags": {"type": "keyword"}
                }
            },
            "embedding": {
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
            },
            "hierarchy": {
                "type": "nested",
                "properties": {
                    "level": {"type": "keyword"},
                    "path": {"type": "keyword"},
                    "position": {"type": "integer"}
                }
            }
        }
    }
}

# Create the index
response = requests.put(url, auth=awsauth, json=index_mapping, headers={"Content-Type": "application/json"})
print(response.text)

# Function to search across multiple indices with metadata filtering
def search_documents(query_text, filters=None, indices=None):
    if indices is None:
        indices = ["technical_documentation", "research_papers", "company_policies"]
    
    # Generate embedding for the query
    bedrock = boto3.client('bedrock-runtime')
    embedding_response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v1",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": query_text})
    )
    
    embedding = json.loads(embedding_response['body'].read())['embedding']
    
    # Build the search query
    search_query = {
        "size": 10,
        "query": {
            "bool": {
                "must": [
                    {
                        "knn": {
                            "embedding": {
                                "vector": embedding,
                                "k": 10
                            }
                        }
                    }
                ]
            }
        }
    }
    
    # Add filters if provided
    if filters:
        filter_clauses = []
        for key, value in filters.items():
            if key.startswith("metadata."):
                filter_clauses.append({"term": {key: value}})
        
        if filter_clauses:
            search_query["query"]["bool"]["filter"] = filter_clauses
    
    # Execute search across multiple indices
    search_url = host + '/' + ','.join(indices) + '/_search'
    response = requests.post(search_url, auth=awsauth, json=search_query, headers={"Content-Type": "application/json"})
    
    return json.loads(response.text)
```

### Integration Component for Wiki Systems

```python
import boto3
import requests
import json
import os
import base64
from datetime import datetime

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime')

# Configuration
WIKI_API_URL = "https://your-wiki-api.com"
WIKI_USERNAME = "your_username"
WIKI_PASSWORD = "your_password"
S3_BUCKET_NAME = "your-s3-bucket-name"

def lambda_handler(event, context):
    # Step 1: Fetch documents from the wiki system
    documents = fetch_wiki_documents()
    
    # Step 2: Process and store each document
    for document in documents:
        process_and_store_document(document)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Document processing complete')
    }

def fetch_wiki_documents():
    # Example function to fetch documents from a wiki API
    response = requests.get(
        f"{WIKI_API_URL}/api/v1/documents",
        auth=(WIKI_USERNAME, WIKI_PASSWORD)
    )
    
    if response.status_code != 200:
        raise Exception(f"Failed to fetch documents: {response.text}")
    
    return response.json()

def process_and_store_document(document):
    # Extract document details
    document_id = document['id']
    title = document['title']
    content = document['content']
    author = document.get('author', 'Unknown')
    created_date = document.get('created_date', datetime.utcnow().isoformat())
    
    # Convert document content to bytes
    content_bytes = bytes(content, encoding='utf-8')
    
    # Upload document to S3
    s3_key = f"wiki_documents/{document_id}.txt"
    s3.upload_fileobj(io.BytesIO(content_bytes), S3_BUCKET_NAME, s3_key)
    
    # Store metadata in DynamoDB
    metadata = {
        'document_id': document_id,
        'title': title,
        'author': author,
        'created_date': created_date,
        'source': 'wiki'
    }
    
    dynamodb.Table('DocumentMetadata').put_item(Item=metadata)
    
    # Generate embedding and store in vector database
    embedding = generate_embedding(content)
    store_embedding_in_vector_db(document_id, embedding, content, metadata)
```

### API Integration for Internal Systems

```python
import boto3
import requests
import json
import os
import base64
from datetime import datetime

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime')

# Configuration
API_BASE_URL = "https://internal-api.yourcompany.com"
API_KEY = "your_api_key"
S3_BUCKET_NAME = "your-s3-bucket-name"

def lambda_handler(event, context):
    # Step 1: Fetch documents from the internal API
    documents = fetch_api_documents()
    
    # Step 2: Process and store each document
    for document in documents:
        process_and_store_document(document)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Document processing complete')
    }

def fetch_api_documents():
    # Example function to fetch documents from an internal API
    response = requests.get(
        f"{API_BASE_URL}/documents",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    
    if response.status_code != 200:
        raise Exception(f"Failed to fetch documents: {response.text}")
    
    return response.json()

def process_and_store_document(document):
    # Extract document details
    document_id = document['id']
    title = document['title']
    content = document['content']
    author = document.get('author', 'Unknown')
    created_date = document.get('created_date', datetime.utcnow().isoformat())
    
    # Convert document content to bytes
    content_bytes = bytes(content, encoding='utf-8')
    
    # Upload document to S3
    s3_key = f"api_documents/{document_id}.txt"
    s3.upload_fileobj(io.BytesIO(content_bytes), S3_BUCKET_NAME, s3_key)
    
    # Store metadata in DynamoDB
    metadata = {
        'document_id': document_id,
        'title': title,
        'author': author,
        'created_date': created_date,
        'source': 'api'
    }
    
    dynamodb.Table('DocumentMetadata').put_item(Item=metadata)
    
    # Generate embedding and store in vector database
    embedding = generate_embedding(content)
    store_embedding_in_vector_db(document_id, embedding, content, metadata)
```

### Data Maintenance and Synchronization

```python
import boto3
import json
import hashlib
from datetime import datetime, timedelta

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime')

metadata_table = dynamodb.Table('DocumentMetadata')

def lambda_handler(event, context):
    # Step 1: Detect changes in documents
    changed_documents = detect_document_changes()
    
    # Step 2: Process updates for changed documents
    for document in changed_documents:
        process_document_update(document)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Data maintenance complete')
    }

def detect_document_changes():
    # Example function to detect changes in documents
    # In production, implement logic to detect changes (e.g., using checksums, versioning)
    response = metadata_table.scan()
    current_time = datetime.utcnow()
    threshold_time = current_time - timedelta(days=1)
    
    changed_documents = []
    for item in response['Items']:
        last_updated = item.get('last_updated')
        if last_updated and last_updated > threshold_time.isoformat():
            changed_documents.append(item)
    
    return changed_documents

def process_document_update(document):
    # Extract document details
    document_id = document['document_id']
    title = document['title']
    content = document['content']
    author = document.get('author', 'Unknown')
    last_updated = document.get('last_updated', datetime.utcnow().isoformat())
    
    # Download the document from S3
    s3_key = f"documents/{document_id}.txt"
    response = s3.get_object(Bucket='your-s3-bucket-name', Key=s3_key)
    document_content = response['Body'].read()
    
    # Generate checksum for the document
    checksum = hashlib.md5(document_content).hexdigest()
    
    # Update metadata in DynamoDB
    metadata_table.update_item(
        Key={
            'document_id': document_id,
            'chunk_id': document_id  # Assuming chunk_id is same as document_id for single-chunk documents
        },
        UpdateExpression="SET last_updated = :last_updated, checksum = :checksum",
        ExpressionAttributeValues={
            ':last_updated': last_updated,
            ':checksum': checksum
        }
    )
    
    # Generate embedding and update in vector database
    embedding = generate_embedding(document_content)
    store_embedding_in_vector_db(document_id, embedding, document_content, document)
```

### RAG Application Implementation

```python
import boto3
import json

# Initialize AWS clients
bedrock = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    # Extract query from the event
    query = event.get('query')
    
    if not query:
        return {
            'statusCode': 400,
            'body': json.dumps('Query parameter is required')
        }
    
    # Step 1: Retrieve relevant documents using vector search
    retrieved_docs = retrieve_relevant_documents(query)
    
    # Step 2: Generate response using foundation model
    response = generate_response(query, retrieved_docs)
    
    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }

def retrieve_relevant_documents(query):
    # Generate embedding for the query
    embedding = generate_embedding(query)
    
    # Perform vector search in the vector database
    # Implementation depends on chosen vector database (OpenSearch or Bedrock KB)
    search_results = search_documents_in_vector_db(embedding)
    
    # Extract document IDs from search results
    document_ids = [result['document_id'] for result in search_results]
    
    # Retrieve full document details from DynamoDB
    documents = []
    for doc_id in document_ids:
        response = dynamodb.Table('DocumentMetadata').get_item(Key={'document_id': doc_id})
        if 'Item' in response:
            documents.append(response['Item'])
    
    return documents

def generate_response(query, documents):
    # Implement response generation logic using foundation model (e.g., Amazon Bedrock)
    response = bedrock.invoke_model(
        modelId="amazon.titan",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "inputText": query,
            "contextDocuments": documents
        })
    )
    
    response_body = json.loads(response['body'].read())
    return response_body['generatedText']
```
