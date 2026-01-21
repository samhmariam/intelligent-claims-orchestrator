# Project Architecture and Components

## Part 1: Data Validation Workflow

### Overview

- **Goal**: Validate structured and unstructured customer feedback data.
- **Tools**: AWS Glue Data Quality, Lambda, CloudWatch.

### Step 1: Set Up AWS Glue Data Catalog and Data Quality

#### Create an S3 Bucket for Project Data

```bash
# Create a new S3 bucket for storing raw data
aws s3 mb s3://customer-feedback-analysis-<your-initials>
```

#### Upload Sample Data to S3

```bash
# Upload sample data files to the raw-data folder in the S3 bucket
aws s3 cp sample-data/ s3://customer-feedback-analysis-<your-initials>/raw-data/ --recursive
```

#### Create and Run an AWS Glue Crawler

```bash
# Create a Glue Crawler to catalog the raw data
aws glue create-crawler \
  --name customer-feedback-crawler \
  --role AWSGlueServiceRole-CustomerFeedback \
  --database-name customer_feedback_db \
  --targets '{"S3Targets": [{"Path": "s3://customer-feedback-analysis-<your-initials>/raw-data/"}]}'

# Start the Glue Crawler
aws glue start-crawler --name customer-feedback-crawler
```

#### Create a Glue Data Quality Ruleset

```python
import boto3
from awsglue.data_quality import DataQualityRule, DataQualityRulesetEvaluator

# Define rules for customer reviews
rules = [
    # Check for completeness of required fields
    DataQualityRule.is_complete("review_text"),
    DataQualityRule.is_complete("product_id"),
    DataQualityRule.is_complete("customer_id"),
    
    # Check for valid values
    DataQualityRule.column_values_match_pattern("review_text", ".{10,}"),  # At least 10 chars
    DataQualityRule.column_values_match_pattern("rating", "^[1-5]$"),  # Rating 1-5
    
    # Check for data consistency
    DataQualityRule.column_values_match_pattern("review_date", "\\d{4}-\\d{2}-\\d{2}"),  # YYYY-MM-DD
    
    # Check for statistical properties
    DataQualityRule.column_length_distribution_match("review_text", 
                                                    min_length=10, 
                                                    max_length=5000)
]

# Create ruleset
# Initialize Glue client
glue_client = boto3.client('glue')
response = glue_client.create_data_quality_ruleset(
    Name='customer_reviews_ruleset',
    Description='Data quality rules for customer reviews',
    Ruleset='\n'.join([str(rule) for rule in rules]),
    Tags={'Project': 'CustomerFeedbackAnalysis'}
)

print(f"Created ruleset: {response['Name']}")
```

### Step 2: Create Lambda Function for Custom Text Validation

```python
import json
import boto3
import re
from datetime import datetime

def lambda_handler(event, context):
    """
    Lambda function to validate text reviews uploaded to S3.
    """
    # Initialize S3 client
    s3_client = boto3.client('s3')
    
    # Extract bucket and object key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    # Only process text reviews
    if not key.endswith('.txt') and not key.endswith('.json'):
        return {
            'statusCode': 200,
            'body': json.dumps('Not a text review file')
        }
    
    try:
        # Retrieve the object content
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')
        
        # Parse the content (assuming JSON format)
        if key.endswith('.json'):
            review = json.loads(content)
            text = review.get('review_text', '')
        else:
            text = content
            
        # Perform validation checks
        validation_results = {
            'file_name': key,
            'timestamp': datetime.now().isoformat(),
            'checks': {
                'min_length': len(text) >= 10,
                'has_product_reference': bool(re.search(r'product|item|purchase', text, re.IGNORECASE)),
                'has_opinion': bool(re.search(r'like|love|hate|good|bad|great|terrible|excellent|poor|recommend', text, re.IGNORECASE)),
                'no_profanity': not bool(re.search(r'badword1|badword2', text, re.IGNORECASE)),  # Add actual profanity list
                'has_structure': text.count('.') >= 1  # At least one sentence
            }
        }
        
        # Calculate overall quality score
        passed_checks = sum(1 for check in validation_results['checks'].values() if check)
        total_checks = len(validation_results['checks'])
        validation_results['quality_score'] = passed_checks / total_checks
        
        # Send metrics to CloudWatch
        cloudwatch = boto3.client('cloudwatch')
        cloudwatch.put_metric_data(
            Namespace='CustomerFeedback/TextQuality',
            MetricData=[
                {
                    'MetricName': 'QualityScore',
                    'Value': validation_results['quality_score'],
                    'Unit': 'None',
                    'Dimensions': [
                        {
                            'Name': 'Source',
                            'Value': 'TextReviews'
                        }
                    ]
                }
            ]
        )
        
        # Save validation results to S3
        validation_key = key.replace('raw-data', 'validation-results').replace('.txt', '.json').replace('.json', '_validation.json')
        s3_client.put_object(
            Bucket=bucket,
            Key=validation_key,
            Body=json.dumps(validation_results),
            ContentType='application/json'
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps(validation_results)
        }
        
    except Exception as e:
        print(f"Error processing {key}: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error: {str(e)}")
        }
```

### Step 3: Set Up S3 Trigger for Lambda Function

```bash
# Create an event source mapping to trigger the Lambda function on new S3 object creation
aws lambda create-event-source-mapping \
  --function-name TextValidationFunction \
  --batch-size 1 \
  --event-source-arn arn:aws:s3:::customer-feedback-analysis-<your-initials> \
  --events s3:ObjectCreated:*
```

### Step 4: Create CloudWatch Dashboard for Monitoring Data Quality

```python
import boto3

# Create CloudWatch dashboard
cloudwatch = boto3.client('cloudwatch')

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
                    ["CustomerFeedback/TextQuality", "QualityScore", "Source", "TextReviews"]
                ],
                "period": 86400,
                "stat": "Average",
                "region": "us-east-1",
                "title": "Text Review Quality Score"
            }
        },
        {
            "type": "metric",
            "x": 0,
            "y": 6,
            "width": 12,
            "height": 6,
            "properties": {
                "metrics": [
                    ["CustomerFeedback/DataQuality", "RulesetPassRate", "Ruleset", "customer_reviews_ruleset"]
                ],
                "period": 86400,
                "stat": "Average",
                "region": "us-east-1",
                "title": "Glue Data Quality Pass Rate"
            }
        }
    ]
}

response = cloudwatch.put_dashboard(
    DashboardName='CustomerFeedbackQuality',
    DashboardBody=json.dumps(dashboard_body)
)

print(f"Created dashboard: {response['DashboardArn']}")
```

### Step 5: Analyze Results and Create a Model Selection Strategy

```python
def create_model_selection_strategy(results_df):
    """Create a model selection strategy based on evaluation results."""
    # Calculate overall scores
    model_scores = results_df.groupby("model_id").agg({
        "latency": "mean",
        "similarity_score": "mean"
    }).reset_index()
    
    # Normalize scores (lower latency is better, higher similarity is better)
    max_latency = model_scores["latency"].max()
    model_scores["latency_score"] = 1 - (model_scores["latency"] / max_latency)
    
    # Calculate weighted score (adjust weights based on priorities)
    model_scores["overall_score"] = (
        0.7 * model_scores["similarity_score"] + 
        0.3 * model_scores["latency_score"]
    )
    
    # Sort by overall score
    model_scores = model_scores.sort_values("overall_score", ascending=False)
    
    # Create strategy
    strategy = {
        "primary_model": model_scores.iloc[0]["model_id"],
        "fallback_models": model_scores.iloc[1:]["model_id"].tolist(),
        "model_scores": model_scores.to_dict(orient="records")
    }
    
    return strategy

# Generate strategy
strategy = create_model_selection_strategy(results_df)
print(json.dumps(strategy, indent=2))

# Save strategy to file for AppConfig
with open("model_selection_strategy.json", "w") as f:
    json.dump(strategy, f, indent=2)
```

## Part 2: Multimodal Data Processing

### Step 1: Process Text Reviews with Amazon Comprehend

#### Create a Lambda Function to Process Text Reviews

```python
import json
import boto3
import os

def lambda_handler(event, context):
    """
    Lambda function to process text reviews using Amazon Comprehend.
    """
    # Get the S3 object
    s3_client = boto3.client('s3')
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    # Only process validated text reviews
    if not key.endswith('_validation.json'):
        return {
            'statusCode': 200,
            'body': json.dumps('Not a validated review file')
        }
    
    try:
        # Get the validation results
        response = s3_client.get_object(Bucket=bucket, Key=key)
        validation_results = json.loads(response['Body'].read().decode('utf-8'))
        
        # Check if the quality score is sufficient
        if validation_results['quality_score'] < 0.7:  # Threshold for processing
            print(f"Quality score too low: {validation_results['quality_score']}")
            return {
                'statusCode': 200,
                'body': json.dumps('Quality score too low')
            }
        
        # Get the original review text
        original_key = key.replace('validation-results', 'raw-data').replace('_validation.json', '.json')
        response = s3_client.get_object(Bucket=bucket, Key=original_key)
        review = json.loads(response['Body'].read().decode('utf-8'))
        text = review.get('review_text', '')
        
        # Use Amazon Comprehend for entity extraction and sentiment analysis
        comprehend = boto3.client('comprehend')
        
        # Detect entities
        entity_response = comprehend.detect_entities(
            Text=text,
            LanguageCode='en'
        )
        
        # Detect sentiment
        sentiment_response = comprehend.detect_sentiment(
            Text=text,
            LanguageCode='en'
        )
        
        # Detect key phrases
        key_phrases_response = comprehend.detect_key_phrases(
            Text=text,
            LanguageCode='en'
        )
        
        # Combine the results
        processed_review = {
            'original_text': text,
            'entities': entity_response['Entities'],
            'sentiment': sentiment_response['Sentiment'],
            'sentiment_scores': sentiment_response['SentimentScore'],
            'key_phrases': key_phrases_response['KeyPhrases'],
            'metadata': {
                'product_id': review.get('product_id', ''),
                'customer_id': review.get('customer_id', ''),
                'review_date': review.get('review_date', '')
            }
        }
        
        # Save processed results
        processed_key = key.replace('validation-results', 'processed-data').replace('_validation.json', '_processed.json')
        s3_client.put_object(
            Bucket=bucket,
            Key=processed_key,
            Body=json.dumps(processed_review),
            ContentType='application/json'
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps('Successfully processed review')
        }
        
    except Exception as e:
        print(f"Error processing {key}: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error: {str(e)}")
        }
```

### Step 2: Process Product Images with Amazon Textract and Rekognition

#### Create a Lambda Function to Process Product Images

```python
import json
import boto3
import os

def lambda_handler(event, context):
    """
    Lambda function to process product images using Amazon Textract and Rekognition.
    """
    # Get the S3 object
    s3_client = boto3.client('s3')
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    # Only process image files
    if not key.lower().endswith(('.png', '.jpg', '.jpeg')):
        return {
            'statusCode': 200,
            'body': json.dumps('Not an image file')
        }
    
    try:
        # Extract text from the image using Amazon Textract
        textract = boto3.client('textract')
        response = textract.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': key
                }
            }
        )
        
        # Extract the text
        extracted_text = ""
        for item in response['Blocks']:
            if item['BlockType'] == 'LINE':
                extracted_text += item['Text'] + "\n"
        
        # Analyze the image using Amazon Rekognition
        rekognition = boto3.client('rekognition')
        
        # Detect labels
        label_response = rekognition.detect_labels(
            Image={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': key
                }
            },
            MaxLabels=10,
            MinConfidence=70
        )
        
        # Detect text (as a backup to Textract)
        text_response = rekognition.detect_text(
            Image={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': key
                }
            }
        )
        
        # Combine the results
        processed_image = {
            'image_key': key,
            'extracted_text': extracted_text,
            'labels': [label for label in label_response['Labels']],
            'detected_text': [text for text in text_response['TextDetections'] if text['Type'] == 'LINE'],
            'metadata': {
                'product_id': os.path.basename(key).split('_')[0] if '_' in os.path.basename(key) else ''
            }
        }
        
        # Save processed results
        processed_key = key.replace('raw-data', 'processed-data').replace(os.path.splitext(key)[1], '_processed.json')
        s3_client.put_object(
            Bucket=bucket,
            Key=processed_key,
            Body=json.dumps(processed_image),
            ContentType='application/json'
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps('Successfully processed image')
        }
        
    except Exception as e:
        print(f"Error processing {key}: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error: {str(e)}")
        }
```

### Step 3: Process Customer Service Calls with Amazon Transcribe

#### Create a Lambda Function to Process Audio Recordings

```python
import json
import boto3
import os
import uuid
import time

def lambda_handler(event, context):
    """
    Lambda function to process customer service audio recordings using Amazon Transcribe.
    """
    # Get the S3 object
    s3_client = boto3.client('s3')
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    # Only process audio files
    if not key.lower().endswith(('.mp3', '.wav', '.flac')):
        return {
            'statusCode': 200,
            'body': json.dumps('Not an audio file')
        }
    
    try:
        # Start a transcription job
        transcribe = boto3.client('transcribe')
        job_name = f"transcribe-{uuid.uuid4()}"
        output_key = key.replace('raw-data', 'transcriptions').replace(os.path.splitext(key)[1], '.json')
        output_uri = f"s3://{bucket}/{output_key}"
        
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={
                'MediaFileUri': f"s3://{bucket}/{key}"
            },
            MediaFormat=os.path.splitext(key)[1][1:],  # Remove the dot
            LanguageCode='en-US',
            OutputBucketName=bucket,
            OutputKey=output_key,
            Settings={
                'ShowSpeakerLabels': True,
                'MaxSpeakerLabels': 2  # Assuming customer and agent
            }
        )
        
        # Wait for the transcription job to complete (in production, use Step Functions or EventBridge)
        while True:
            status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            if status['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
                break
            time.sleep(5)
        
        if status['TranscriptionJob']['TranscriptionJobStatus'] == 'COMPLETED':
            # Process the transcription with Comprehend
            # First, get the transcription file
            response = s3_client.get_object(Bucket=bucket, Key=output_key)
            transcription = json.loads(response['Body'].read().decode('utf-8'))
            
            # Extract the transcript text
            transcript = transcription['results']['transcripts'][0]['transcript']
            
            # Use Amazon Comprehend for sentiment analysis
            comprehend = boto3.client('comprehend')
            sentiment_response = comprehend.detect_sentiment(
                Text=transcript,
                LanguageCode='en'
            )
            
            # Detect key phrases
            key_phrases_response = comprehend.detect_key_phrases(
                Text=transcript,
                LanguageCode='en'
            )
            
            # Combine the results
            processed_call = {
                'audio_key': key,
                'transcript': transcript,
                'speakers': transcription['results'].get('speaker_labels', {}).get('segments', []),
                'sentiment': sentiment_response['Sentiment'],
                'sentiment_scores': sentiment_response['SentimentScore'],
                'key_phrases': key_phrases_response['KeyPhrases'],
                'metadata': {
                    'call_id': os.path.basename(key).split('.')[0],
                    'duration': status['TranscriptionJob']['MediaFormat']
                }
            }
            
            # Save processed results
            processed_key = key.replace('raw-data', 'processed-data').replace(os.path.splitext(key)[1], '_processed.json')
            s3_client.put_object(
                Bucket=bucket,
                Key=processed_key,
                Body=json.dumps(processed_call),
                ContentType='application/json'
            )
            
            return {
                'statusCode': 200,
                'body': json.dumps('Successfully processed audio')
            }
        else:
            return {
                'statusCode': 500,
                'body': json.dumps(f"Transcription failed: {status['TranscriptionJob']['FailureReason']}")
            }
        
    except Exception as e:
        print(f"Error processing {key}: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error: {str(e)}")
        }
```

### Step 4: Process Survey Data with SageMaker Processing

#### Create a SageMaker Processing Script for Survey Data

```python
import pandas as pd
import numpy as np
import argparse
import os
import json

def process_survey_data(input_path, output_path):
    """
    Process survey data to generate summaries and statistics.
    """
    # Read the survey data
    df = pd.read_csv(f"{input_path}/surveys.csv")
    
    # Basic data cleaning
    df = df.dropna(subset=['customer_id', 'survey_date'])  # Drop rows with missing key fields
    
    # Convert categorical ratings to numerical
    rating_map = {'Very Dissatisfied': 1, 'Dissatisfied': 2, 'Neutral': 3, 'Satisfied': 4, 'Very Satisfied': 5}
    for col in df.columns:
        if 'rating' in col.lower() or 'satisfaction' in col.lower():
            df[col] = df[col].map(rating_map).fillna(df[col])
    
    # Calculate summary statistics
    summary_stats = {
        'total_surveys': len(df),
        'avg_satisfaction': df['overall_satisfaction'].mean(),
        'sentiment_distribution': df['overall_satisfaction'].value_counts().to_dict(),
        'top_issues': df['improvement_area'].value_counts().head(3).to_dict()
    }
    
    # Generate natural language summaries for each survey
    summaries = []
    for _, row in df.iterrows():
        summary = {
            'customer_id': row['customer_id'],
            'survey_date': row['survey_date'],
            'summary_text': generate_summary(row),
            'ratings': {col: row[col] for col in df.columns if 'rating' in col.lower() or 'satisfaction' in col.lower()},
            'comments': row.get('comments', '')
        }
        summaries.append(summary)
    
    # Save the processed data
    with open(f"{output_path}/survey_summaries.json", 'w') as f:
        json.dump(summaries, f)
    
    with open(f"{output_path}/survey_statistics.json", 'w') as f:
        json.dump(summary_stats, f)

def generate_summary(row):
    """Generate a natural language summary of a survey response"""
    satisfaction_level = "satisfied" if row['overall_satisfaction'] >= 4 else \
                        "neutral" if row['overall_satisfaction'] == 3 else "dissatisfied"
    
    summary = f"Customer {row['customer_id']} was {satisfaction_level} overall with their experience. "
    
    # Add details about specific ratings
    if 'product_rating' in row:
        summary += f"They rated the product {row['product_rating']}/5. "
    
    if 'service_rating' in row:
        summary += f"They rated the customer service {row['service_rating']}/5. "
    
    # Add improvement area if available
    if 'improvement_area' in row and pd.notna(row['improvement_area']):
        summary += f"They suggested improvements in the area of {row['improvement_area']}. "
    
    # Add comments if available
    if 'comments' in row and pd.notna(row['comments']) and len(str(row['comments'])) > 0:
        summary += f"Their comments: '{row['comments']}'"
    
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-path", type=str, default="/opt/ml/processing/input")
    parser.add_argument("--output-path", type=str, default="/opt/ml/processing/output")
    args = parser.parse_args()
    
    process_survey_data(args.input_path, args.output_path)
```

#### Create a Python Script to Run the SageMaker Processing Job

```python
import boto3
import sagemaker
from sagemaker.processing import ScriptProcessor, ProcessingInput, ProcessingOutput

def run_survey_processing_job():
    """
    Run a SageMaker Processing job to process survey data.
    """
    # Initialize SageMaker session
    sagemaker_session = sagemaker.Session()
    role = sagemaker.get_execution_role()
    
    # Define the processing job
    script_processor = ScriptProcessor(
        command=['python3'],
        image_uri='737474898029.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:0.23-1-cpu-py3',
        role=role,
        instance_count=1,
        instance_type='ml.m5.xlarge',
        sagemaker_session=sagemaker_session
    )
    
    # Run the processing job
    script_processor.run(
        code='survey_processing.py',
        inputs=[
            ProcessingInput(
                source='s3://customer-feedback-analysis-<your-initials>/raw-data/surveys.csv',
                destination='/opt/ml/processing/input'
            )
        ],
        outputs=[
            ProcessingOutput(
                output_name='survey_output',
                source='/opt/ml/processing/output',
                destination='s3://customer-feedback-analysis-<your-initials>/processed-data/surveys/'
            )
        ]
    )
    
    print("Survey processing job started")

if __name__ == "__main__":
    run_survey_processing_job()
```

## Part 3: Data Formatting for FMs

### Step 1: Create a Lambda Function for Formatting Data for Claude

```python
import json
import boto3
import base64
import os

def lambda_handler(event, context):
    """
    Lambda function to format processed data for Claude in Amazon Bedrock.
    """
    # Get the S3 object
    s3_client = boto3.client('s3')
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    
    # Only process processed data files
    if not key.endswith('_processed.json'):
        return {
            'statusCode': 200,
            'body': json.dumps('Not a processed data file')
        }
    
    try:
        # Get the processed data
        response = s3_client.get_object(Bucket=bucket, Key=key)
        processed_data = json.loads(response['Body'].read().decode('utf-8'))
        
        # Determine the data type and format accordingly
        if 'transcript' in processed_data:
            # Audio data
            formatted_data = format_audio_data(processed_data)
        elif 'extracted_text' in processed_data:
            # Image data
            formatted_data = format_image_data(processed_data, bucket, key)
        elif 'entities' in processed_data:
            # Text review data
            formatted_data = format_text_data(processed_data)
        elif 'summary_text' in processed_data:
            # Survey data
            formatted_data = format_survey_data(processed_data)
        else:
            return {
                'statusCode': 400,
                'body': json.dumps('Unsupported data format')
            }
        
        # Save the formatted data to a new S3 location
        formatted_key = key.replace('_processed.json', '_formatted.json')
        s3_client.put_object(
            Bucket=bucket,
            Key=formatted_key,
            Body=json.dumps(formatted_data),
            ContentType='application/json'
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps('Successfully formatted data')
        }
        
    except Exception as e:
        print(f"Error processing {key}: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error: {str(e)}")
        }
```