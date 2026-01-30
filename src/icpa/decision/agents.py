import boto3
import json
import re
from typing import Dict, Any, List
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit

logger = Logger(child=True)
tracer = Tracer()
metrics = Metrics(namespace="ICPA/Production")

bedrock = boto3.client('bedrock-runtime')
ssm = boto3.client('ssm')

class BedrockAgent:
    def __init__(self, agent_name: str, model_id: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"):
        self.agent_name = agent_name
        self.model_id = model_id
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """Loads prompt from SSM."""
        try:
            param_name = f"/icpa/prompts/{self.agent_name}/latest"
            resp = ssm.get_parameter(Name=param_name)
            return resp['Parameter']['Value']
        except Exception as e:
            logger.error(f"Failed to load prompt for {self.agent_name}: {e}")
            raise e

    def _parse_response(self, response_body: str) -> Dict[str, Any]:
        """
        Parses Claude's XML-wrapped response.
        Expected format:
        <thinking>...</thinking>
        <json>{...}</json>
        """
        try:
            # 1. Extract Thinking (Optional but good for audit)
            thinking_match = re.search(r"<thinking>(.*?)</thinking>", response_body, re.DOTALL)
            thinking = thinking_match.group(1).strip() if thinking_match else "No thinking block found."

            # 2. Extract JSON
            json_match = re.search(r"<json>(.*?)</json>", response_body, re.DOTALL)
            if not json_match:
                 # Fallback: Try to find raw JSON if tags missing
                 json_match = re.search(r"(\{.*\})", response_body, re.DOTALL)
            
            if not json_match:
                raise ValueError("No JSON block found in LLM response.")

            json_str = json_match.group(1).strip()
            data = json.loads(json_str)
            
            # Inject thinking into result for audit
            data['_rationale'] = thinking
            return data

        except Exception as e:
            logger.error(f"LLM Parse Error: {e}. Raw Body: {response_body}")
            # Return Fail-Safe Decision
            return {
                "decision": "REVIEW",
                "reason": f"LLM_PARSE_FAILURE: {str(e)}",
                "_rationale": "Parsing failed."
            }

    @tracer.capture_method
    def invoke(self, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invokes Bedrock Model.
        context_data: {'claim_documents': '...', 'claim_metadata': '...'}
        """
        # Format Prompt
        # We assume system prompt has placeholders like {claim_documents}
        # But AWS Bedrock System Prompts are static. We usually pass context in User Message.
        # Let's assume the SSM prompt is the SYSTEM PROMPT template.
        
        # Wait, System Prompts in Claude 3.5 are passed in 'system' field.
        # Placeholders should be in the USER message or we format the system prompt?
        # Best practice: System Prompt = Behavior/Persona. User Message = Context/Data.
        # But our Seed script put placeholders in the prompt text.
        # Let's treat the fetched prompt as a Template for the USER message or System?
        # The prompt in seed_prompts.py has {claim_documents}. This implies it's a template.
        
        # Strategy: 
        # 1. Split SSM content? No.
        # 2. Just use the SSM string as the Template, format it, and send as User Message.
        # System Message can be simple identity.
        
        # Custom format to avoid KeyError when prompt contains JSON examples with braces
        formatted_prompt = self.system_prompt
        for k, v in context_data.items():
            formatted_prompt = formatted_prompt.replace(f"{{{k}}}", str(v))
        
        # Payload Factory
        if "amazon.nova" in self.model_id:
            # Nova (Converse API style)
            body = json.dumps({
                "inferenceConfig": {
                    "max_new_tokens": 4096,
                    "temperature": 0.0
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": formatted_prompt}]
                    }
                ],
                 # Nova System Prompt is strictly top-level list of dicts or string?
                 # Amazon Nova Pro via Bedrock InvokeModel uses specific schema.
                 # "system": [{"text": "..."}]
                "system": [{"text": "You are a specialized Insurance Claim AI Agent. Output valid JSON."}]
            })
        else:
            # Claude (Messages API)
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": "You are a specialized Insurance Claim AI Agent. Output valid JSON wrapped in <json> tags.",
                "messages": [
                    {
                        "role": "user",
                        "content": formatted_prompt
                    }
                ],
                "temperature": 0.0
            })

        try:
            response = bedrock.invoke_model(
                modelId=self.model_id,
                body=body
            )
            
            # Metrics
            headers = response.get('ResponseMetadata', {}).get('HTTPHeaders', {})
            
            resp_body = json.loads(response['body'].read())
            
            # Token Usage & Content Extraction
            if "amazon.nova" in self.model_id:
                # Nova Response
                # {"output": {"message": {"content": [{"text": "..."}]}}, "usage": {...}}
                usage = resp_body.get('usage', {})
                content = resp_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text', '')
                
                # Nova Pricing ($0.80 / $3.20)
                input_price = 0.80
                output_price = 3.20
            else:
                # Claude Response
                usage = resp_body.get('usage', {})
                content = resp_body['content'][0]['text']
                
                # Claude 3.5 Sonnet Pricing ($3.00 / $15.00)
                input_price = 3.00
                output_price = 15.00

            input_tokens = usage.get('input_tokens', 0)
            output_tokens = usage.get('output_tokens', 0)
            
            metrics.add_metric(name="InputTokenCount", unit=MetricUnit.Count, value=input_tokens)
            metrics.add_metric(name="OutputTokenCount", unit=MetricUnit.Count, value=output_tokens)
            
            cost = (input_tokens / 1_000_000 * input_price) + (output_tokens / 1_000_000 * output_price)
            metrics.add_metric(name="EstimatedCost", unit=MetricUnit.Count, value=cost)

            return self._parse_response(content)

        except Exception as e:
            logger.exception("Bedrock Invocation Failed")
            return {
                "decision": "REVIEW", 
                "reason": f"BEDROCK_ERROR: {str(e)}",
                "_rationale": "System Error"
            }

class FraudAgent(BedrockAgent):
    def __init__(self):
        super().__init__(agent_name="fraud_agent", model_id="amazon.nova-pro-v1:0")

class AdjudicationAgent(BedrockAgent):
    def __init__(self):
        super().__init__(agent_name="adjudication_agent", model_id="amazon.nova-pro-v1:0")

class SummarizationAgent(BedrockAgent):
    def __init__(self):
        super().__init__(agent_name="summarization_agent")
