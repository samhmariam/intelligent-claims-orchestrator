# Task 3.1: Implement input and output safety controls

Build a secure generative AI assistant that:

- Filters harmful user inputs.
- Ensures safe outputs.
- Reduces hallucinations.
- Implements defense-in-depth safety.
- Detects and mitigates adversarial threats.

Bonus assignments are an open-ended way for you to assess your overall knowledge of this task. You can share your answers on social media and tag #awsexamprep for review.

## Best practices

- **Layered defense:** Implement multiple safety mechanisms at different stages of the processing pipeline.
- **Continuous evaluation:** Regularly test safety systems against new attack vectors.
- **Human oversight:** Maintain human review processes for edge cases and system improvements.
- **Transparency:** Document safety mechanisms and communicate them to users.
- **Proportional controls:** Balance safety requirements with usability and performance.

## Part 1: Project infrastructure

### Step 1: Set up project infrastructure

Create project structure and install dependencies:

```bash
# Create project directory
mkdir safe-genai-assistant
cd safe-genai-assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install boto3 aws-cdk-lib constructs aws-cdk.aws-lambda aws-cdk.aws-stepfunctions \
  aws-cdk.aws-apigateway aws-cdk.aws-iam aws-cdk.aws-comprehend
```

## Part 2: Implement input safety controls

### Step 1: Create a system to filter harmful user inputs using Amazon Bedrock guardrails

```python
# bedrock_guardrails.py
import boto3
import json

class InputSafetyFilter:
    def __init__(self, guardrail_id):
        self.bedrock = boto3.client("bedrock-runtime")
        self.guardrail_id = guardrail_id

    def filter_input(self, user_input):
        """
        Apply guardrails to filter harmful user inputs.
        """
        try:
            response = self.bedrock.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                contentType="text/plain",
                content=user_input,
                acceptType="application/json",
            )

            result = json.loads(response["output"])

            if result["blocked"]:
                return {
                    "is_safe": False,
                    "reason": result["blockReasons"],
                    "filtered_input": None,
                }

            return {
                "is_safe": True,
                "filtered_input": result["filteredContent"],
            }
        except Exception as e:
            print(f"Error applying guardrails: {str(e)}")
            return {
                "is_safe": False,
                "reason": ["Error processing input safety check"],
                "filtered_input": None,
            }
```

### Step 2: Create a Step Functions workflow for custom moderation

```python
# moderation_workflow.py
from aws_cdk import (
    Stack,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_lambda as lambda_,
    Duration,
)
from constructs import Construct

class ModerationWorkflowStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Lambda for initial content analysis
        content_analyzer = lambda_.Function(
            self,
            "ContentAnalyzer",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="content_analyzer.handler",
            code=lambda_.Code.from_asset("./lambda"),
            timeout=Duration.seconds(30),
        )

        # Lambda for detailed moderation
        detailed_moderator = lambda_.Function(
            self,
            "DetailedModerator",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="detailed_moderator.handler",
            code=lambda_.Code.from_asset("./lambda"),
            timeout=Duration.seconds(60),
        )

        analyze_content = tasks.LambdaInvoke(
            self,
            "AnalyzeContent",
            lambda_function=content_analyzer,
            output_path="$.Payload",
        )

        moderate_content = tasks.LambdaInvoke(
            self,
            "ModerateContent",
            lambda_function=detailed_moderator,
            output_path="$.Payload",
        )

        approve_content = sfn.Pass(
            self, "ApproveContent", result=sfn.Result.from_object({"status": "approved"})
        )

        reject_content = sfn.Pass(
            self, "RejectContent", result=sfn.Result.from_object({"status": "rejected"})
        )

        definition = analyze_content.next(
            sfn.Choice(self, "NeedsFurtherModeration")
            .when(
                sfn.Condition.string_equals("$.risk_level", "HIGH"),
                moderate_content.next(
                    sfn.Choice(self, "ModerationDecision")
                    .when(sfn.Condition.boolean_equals("$.is_approved", True), approve_content)
                    .otherwise(reject_content)
                ),
            )
            .when(
                sfn.Condition.string_equals("$.risk_level", "MEDIUM"),
                moderate_content.next(
                    sfn.Choice(self, "MediumRiskDecision")
                    .when(sfn.Condition.boolean_equals("$.is_approved", True), approve_content)
                    .otherwise(reject_content)
                ),
            )
            .otherwise(approve_content)
        )

        self.state_machine = sfn.StateMachine(
            self,
            "ModerationWorkflow",
            definition=definition,
            timeout=Duration.minutes(5),
        )
```

### Step 3: Implement the Lambda functions for content analysis

```python
# lambda/content_analyzer.py
import boto3

comprehend = boto3.client("comprehend")

def handler(event, context):
    """
    Analyze content for risk factors and determine if further moderation is needed.
    """
    user_input = event.get("input", "")

    sentiment_response = comprehend.detect_sentiment(Text=user_input, LanguageCode="en")
    pii_response = comprehend.detect_pii_entities(Text=user_input, LanguageCode="en")

    sentiment = sentiment_response["Sentiment"]
    sentiment_score = sentiment_response["SentimentScore"]

    pii_entities = pii_response["Entities"]
    has_pii = len(pii_entities) > 0

    risk_level = "LOW"
    if sentiment == "NEGATIVE" and sentiment_score["Negative"] > 0.7:
        risk_level = "HIGH"
    elif has_pii or (sentiment == "NEGATIVE" and sentiment_score["Negative"] > 0.4):
        risk_level = "MEDIUM"

    return {
        "input": user_input,
        "risk_level": risk_level,
        "has_pii": has_pii,
        "sentiment": sentiment,
    }
```

```python
# lambda/detailed_moderator.py
import boto3
import json

bedrock = boto3.client("bedrock-runtime")

def handler(event, context):
    """
    Perform detailed moderation on potentially harmful content.
    """
    user_input = event.get("input", "")
    risk_level = event.get("risk_level", "LOW")

    prompt = f"""
    Please analyze the following text for harmful content, including but not limited to:
    - Hate speech
    - Violence
    - Sexual content
    - Personal attacks
    - Illegal activities

    Text to analyze: "{user_input}"

    Respond with a JSON object with the following structure:
    {{
        "is_harmful": true/false,
        "categories": ["category1", "category2"],
        "explanation": "brief explanation"
    }}
    """

    response = bedrock.invoke_model(
        modelId="anthropic.claude-v2",
        contentType="application/json",
        accept="application/json",
        body=json.dumps(
            {
                "prompt": prompt,
                "max_tokens_to_sample": 500,
                "temperature": 0,
                "top_p": 0.9,
            }
        ),
    )

    response_body = json.loads(response.get("body").read())
    model_output = response_body.get("completion", "")

    try:
        start_idx = model_output.find("{")
        end_idx = model_output.rfind("}") + 1
        json_str = model_output[start_idx:end_idx]
        analysis = json.loads(json_str)

        is_approved = not analysis.get("is_harmful", False)
        if risk_level == "HIGH" and len(analysis.get("categories", [])) > 0:
            is_approved = False

        return {
            "is_approved": is_approved,
            "analysis": analysis,
            "risk_level": risk_level,
        }
    except Exception as e:
        return {
            "is_approved": False,
            "error": str(e),
            "risk_level": risk_level,
        }
```

## Part 3: Implement output safety controls

### Step 1: Create a system to ensure model outputs are safe

```python
# output_safety.py
import boto3
import json

class OutputSafetyFilter:
    def __init__(self, guardrail_id):
        self.bedrock = boto3.client("bedrock-runtime")
        self.guardrail_id = guardrail_id

    def filter_output(self, model_output):
        """
        Apply guardrails to filter potentially harmful model outputs.
        """
        try:
            response = self.bedrock.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                contentType="text/plain",
                content=model_output,
                acceptType="application/json",
            )

            result = json.loads(response["output"])

            if result["blocked"]:
                return {
                    "is_safe": False,
                    "reason": result["blockReasons"],
                    "filtered_output": "I'm sorry, I can't provide that information.",
                }

            return {
                "is_safe": True,
                "filtered_output": result["filteredContent"],
            }
        except Exception as e:
            print(f"Error applying output guardrails: {str(e)}")
            return {
                "is_safe": False,
                "reason": ["Error processing output safety check"],
                "filtered_output": "I'm sorry, I can't provide a response at this time.",
            }

    def evaluate_toxicity(self, content):
        """
        Use a specialized FM to evaluate content for toxicity.
        """
        prompt = f"""
        Analyze the following text for toxicity, bias, or harmful content.
        Respond with a JSON object containing:
        1. A toxicity score from 0 to 1
        2. Categories of potential issues detected
        3. A brief explanation

        Text to analyze: "{content}"
        """

        try:
            response = self.bedrock.invoke_model(
                modelId="anthropic.claude-v2",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(
                    {
                        "prompt": prompt,
                        "max_tokens_to_sample": 500,
                        "temperature": 0,
                        "top_p": 0.9,
                    }
                ),
            )

            response_body = json.loads(response.get("body").read())
            model_output = response_body.get("completion", "")

            start_idx = model_output.find("{")
            end_idx = model_output.rfind("}") + 1
            json_str = model_output[start_idx:end_idx]
            analysis = json.loads(json_str)

            return analysis
        except Exception as e:
            print(f"Error evaluating toxicity: {str(e)}")
            return {
                "toxicity_score": 1.0,
                "categories": ["error"],
                "explanation": "Error evaluating content",
            }
```

### Step 2: Add structured output validation using JSON Schema

```python
# structured_output.py
import json
import jsonschema

class StructuredOutputValidator:
    def __init__(self, schema):
        self.schema = schema

    def validate_and_fix(self, output):
        """
        Validate output against JSON schema and attempt to fix if invalid.
        """
        try:
            if isinstance(output, str):
                try:
                    parsed_output = json.loads(output)
                except json.JSONDecodeError:
                    import re

                    json_match = re.search(r"(\{.*\})", output, re.DOTALL)
                    if json_match:
                        try:
                            parsed_output = json.loads(json_match.group(1))
                        except Exception:
                            return {
                                "is_valid": False,
                                "error": "Could not parse JSON from output",
                                "fixed_output": None,
                            }
                    else:
                        return {
                            "is_valid": False,
                            "error": "Output is not valid JSON",
                            "fixed_output": None,
                        }
            else:
                parsed_output = output

            jsonschema.validate(instance=parsed_output, schema=self.schema)

            return {
                "is_valid": True,
                "validated_output": parsed_output,
            }
        except jsonschema.exceptions.ValidationError as e:
            return {
                "is_valid": False,
                "error": str(e),
                "fixed_output": None,
            }
```

## Part 4: Implement hallucination reduction

### Step 1: Create a system to reduce hallucinations using Amazon Bedrock Knowledge Base

```python
# hallucination_reduction.py
import boto3
import json

class HallucinationReducer:
    def __init__(self, knowledge_base_id, model_id):
        self.bedrock = boto3.client("bedrock-runtime")
        self.knowledge_base_id = knowledge_base_id
        self.model_id = model_id

    def ground_response(self, query):
        """
        Generate a response grounded in a knowledge base to reduce hallucinations.
        """
        try:
            kb_response = self.bedrock.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={"text": query},
                numberOfResults=3,
            )

            retrieved_docs = kb_response["retrievalResults"]
            context = "\n\n".join([doc["content"] for doc in retrieved_docs])

            prompt = f"""
            You are an AI assistant that only provides factual information based on the provided context.
            If the context doesn't contain the information needed to answer the question, say
            "I don't have enough information to answer that question."

            Context:
            {context}

            Question: {query}

            Answer:
            """

            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(
                    {
                        "prompt": prompt,
                        "max_tokens_to_sample": 500,
                        "temperature": 0,
                        "top_p": 0.9,
                    }
                ),
            )

            response_body = json.loads(response.get("body").read())
            answer = response_body.get("completion", "")

            sources = [
                {
                    "source_id": doc["retrievalId"],
                    "source_name": doc.get("location", {})
                    .get("s3Location", {})
                    .get("uri", "Unknown"),
                    "relevance_score": doc.get("score", 0),
                }
                for doc in retrieved_docs
            ]

            return {
                "answer": answer,
                "sources": sources,
                "is_grounded": True,
            }
        except Exception as e:
            print(f"Error grounding response: {str(e)}")
            return {
                "answer": "I'm unable to provide a response at this time.",
                "sources": [],
                "is_grounded": False,
                "error": str(e),
            }

    def verify_with_semantic_search(self, claim, corpus):
        """
        Verify a claim against a corpus using semantic similarity.
        """
        try:
            claim_embedding_response = self.bedrock.invoke_model(
                modelId="amazon.titan-embed-text-v1",
                contentType="application/json",
                accept="application/json",
                body=json.dumps({"inputText": claim}),
            )

            claim_embedding = json.loads(
                claim_embedding_response.get("body").read()
            ).get("embedding")

            highest_similarity = 0
            most_similar_passage = ""

            for passage in corpus:
                passage_embedding_response = self.bedrock.invoke_model(
                    modelId="amazon.titan-embed-text-v1",
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps({"inputText": passage}),
                )

                passage_embedding = json.loads(
                    passage_embedding_response.get("body").read()
                ).get("embedding")

                similarity = self._cosine_similarity(claim_embedding, passage_embedding)

                if similarity > highest_similarity:
                    highest_similarity = similarity
                    most_similar_passage = passage

            return {
                "verified": highest_similarity > 0.8,
                "confidence": highest_similarity,
                "supporting_evidence": (
                    most_similar_passage if highest_similarity > 0.8 else None
                ),
            }
        except Exception as e:
            print(f"Error in semantic verification: {str(e)}")
            return {
                "verified": False,
                "confidence": 0,
                "error": str(e),
            }

    def _cosine_similarity(self, vec1, vec2):
        """Calculate cosine similarity between two vectors."""
        import numpy as np

        dot_product = np.dot(vec1, vec2)
        norm_a = np.linalg.norm(vec1)
        norm_b = np.linalg.norm(vec2)
        return dot_product / (norm_a * norm_b)
```

## Part 5: Implement defense-in-depth safety system

### Step 1: Integrate all components into a defense-in-depth safety system

```python
# defense_in_depth.py
import boto3
import json
from input_safety import InputSafetyFilter
from output_safety import OutputSafetyFilter
from hallucination_reduction import HallucinationReducer
from structured_output import StructuredOutputValidator

class DefenseInDepthSystem:
    def __init__(self, config):
        self.bedrock = boto3.client("bedrock-runtime")
        self.comprehend = boto3.client("comprehend")

        self.input_filter = InputSafetyFilter(config["input_guardrail_id"])
        self.output_filter = OutputSafetyFilter(config["output_guardrail_id"])
        self.hallucination_reducer = HallucinationReducer(
            config["knowledge_base_id"],
            config["model_id"],
        )

        self.schema_validator = None
        if "output_schema" in config:
            self.schema_validator = StructuredOutputValidator(config["output_schema"])

        self.model_id = config["model_id"]

    def process_request(self, user_input, require_grounding=True):
        """
        Process user request with multiple layers of safety controls.
        """
        pii_response = self.comprehend.detect_pii_entities(Text=user_input, LanguageCode="en")

        if pii_response["Entities"]:
            user_input = self._redact_pii(user_input, pii_response["Entities"])

        input_safety_result = self.input_filter.filter_input(user_input)
        if not input_safety_result["is_safe"]:
            return {
                "status": "rejected",
                "reason": input_safety_result["reason"],
                "response": "I'm sorry, but I cannot process that request.",
            }

        filtered_input = input_safety_result["filtered_input"]

        if require_grounding:
            grounded_response = self.hallucination_reducer.ground_response(filtered_input)
            model_output = grounded_response["answer"]
            is_grounded = grounded_response["is_grounded"]
            sources = grounded_response["sources"]
        else:
            try:
                response = self.bedrock.invoke_model(
                    modelId=self.model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(
                        {
                            "prompt": filtered_input,
                            "max_tokens_to_sample": 500,
                            "temperature": 0.7,
                            "top_p": 0.9,
                        }
                    ),
                )

                response_body = json.loads(response.get("body").read())
                model_output = response_body.get("completion", "")
                is_grounded = False
                sources = []
            except Exception as e:
                return {
                    "status": "error",
                    "reason": f"Model invocation failed: {str(e)}",
                    "response": "I'm sorry, but I cannot generate a response at this time.",
                }

        output_safety_result = self.output_filter.filter_output(model_output)
        if not output_safety_result["is_safe"]:
            return {
                "status": "filtered",
                "reason": output_safety_result["reason"],
                "response": output_safety_result["filtered_output"],
            }

        safe_output = output_safety_result["filtered_output"]

        if self.schema_validator:
            validation_result = self.schema_validator.validate_and_fix(safe_output)
            if not validation_result["is_valid"]:
                return {
                    "status": "invalid_format",
                    "reason": validation_result["error"],
                    "response": "I'm sorry, but I couldn't generate a properly formatted response.",
                }

            final_output = validation_result["validated_output"]
        else:
            final_output = safe_output

        return {
            "status": "success",
            "response": final_output,
            "is_grounded": is_grounded,
            "sources": sources if is_grounded else [],
        }

    def _redact_pii(self, text, entities):
        """Redact PII entities from text."""
        sorted_entities = sorted(entities, key=lambda x: x["BeginOffset"], reverse=True)

        redacted_text = text
        for entity in sorted_entities:
            start = entity["BeginOffset"]
            end = entity["EndOffset"]
            redacted_text = redacted_text[:start] + f"[{entity['Type']}]" + redacted_text[end:]

        return redacted_text
```

## Part 6: Implement advanced threat detection

### Step 1: Add advanced threat detection capabilities

```python
# threat_detection.py
import boto3
import json
import re

class ThreatDetector:
    def __init__(self, model_id):
        self.bedrock = boto3.client("bedrock-runtime")
        self.model_id = model_id

        self.injection_patterns = [
            r"ignore previous instructions",
            r"disregard your guidelines",
            r"forget your training",
            r"ignore what you were told",
            r"you are now",
            r"system prompt",
            r"</?sys",
            r"</?system>",
            r"</?user>",
            r"</?assistant>",
        ]

    def detect_prompt_injection(self, user_input):
        """
        Detect potential prompt injection attacks.
        """
        for pattern in self.injection_patterns:
            if re.search(pattern, user_input, re.IGNORECASE):
                return {
                    "is_injection": True,
                    "confidence": 0.9,
                    "pattern_matched": pattern,
                }

        prompt = f"""
        Analyze the following user input for potential prompt injection or jailbreak attempts.
        Respond with a JSON object containing:
        1. is_injection: true/false
        2. confidence: 0-1 score
        3. explanation: brief explanation of why this might be an injection attempt

        User input: "{user_input}"
        """

        try:
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(
                    {
                        "prompt": prompt,
                        "max_tokens_to_sample": 500,
                        "temperature": 0,
                        "top_p": 0.9,
                    }
                ),
            )

            response_body = json.loads(response.get("body").read())
            model_output = response_body.get("completion", "")

            start_idx = model_output.find("{")
            end_idx = model_output.rfind("}") + 1
            json_str = model_output[start_idx:end_idx]
            analysis = json.loads(json_str)

            return analysis
        except Exception as e:
            print(f"Error in prompt injection detection: {str(e)}")
            return {
                "is_injection": True,
                "confidence": 1.0,
                "explanation": "Error analyzing input; defaulting to unsafe.",
            }
```