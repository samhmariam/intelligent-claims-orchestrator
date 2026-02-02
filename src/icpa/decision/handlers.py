import os
import json
import boto3
from typing import Dict, Any, List

from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from .agents import FraudAgent, AdjudicationAgent

# Initialize Powertools
logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="ICPA/Production")

s3 = boto3.client('s3')
dynamodb = boto3.client('dynamodb') # For direct updates if needed, though Step Function handles status updates normally. 
# Actually, SF handles DB updates, but we need to return 'reason' and 'metadata'.
# We verify in phase 3 passing 'decision_reason' back to SF.

@tracer.capture_method
def smart_truncate(docs: List[Dict[str, str]], limit: int = 150000) -> str:
    """
    Prioritizes text from FNOL, INVOICE, POLICE_REPORT.
    docs: [{'key': '...', 'text': '...'}]
    """
    priority_order = ["FNOL", "INVOICE", "POLICE_REPORT", "ADJUSTER"]
    
    sorted_docs = sorted(docs, key=lambda d: next((i for i, k in enumerate(priority_order) if k in d['key'].upper()), 999))
    
    final_text = ""
    for d in sorted_docs:
        chunk = f"\n--- Document: {d['key']} ---\n{d['text']}\n"
        if len(final_text) + len(chunk) < limit:
            final_text += chunk
        else:
            remaining = limit - len(final_text)
            if remaining > 100:
                final_text += chunk[:remaining] + "...[TRUNCATED]"
            break
            
    return final_text

@logger.inject_lambda_context(log_event=True)
@metrics.log_metrics(capture_cold_start_metric=True)
@tracer.capture_lambda_handler
def decision_handler(event, context):
    """
    Decision Engine (Agentic Phase 3b).
    Orchestrates FraudAgent and AdjudicationAgent.
    """
    claim_id = event.get('claim_uuid') or event.get('claim_id')
    if not claim_id:
        raise ValueError("Missing required input: claim_uuid")
        
    tracer.put_annotation(key="claim_id", value=claim_id)
    logger.info(f"Starting Agentic Eval for {claim_id}")
    
    # 1. Fetch Context (Phase 4: Consumption)
    bucket = os.environ.get('CLEAN_BUCKET_NAME', 'icpa-clean-data')
    # The assembler saves to: <claim_id>/context/context_bundle_optimized.json
    key = f"{claim_id}/context/context_bundle_optimized.json"
    
    try:
        logger.info(f"Fetching context bundle from {key}")
        resp = s3.get_object(Bucket=bucket, Key=key)
        bundle = json.loads(resp['Body'].read().decode('utf-8'))
        
        # Flatten documents for Agents
        # Bundle docs have {doc_id, text, metadata}
        docs_data = [{'key': d['doc_id'], 'text': d['text']} for d in bundle.get('documents', [])]
        aggregated_metadata = bundle.get('metadata', {})
        
        # Verify Context Status
        if bundle.get('status') == 'PARTIAL_CONTEXT':
             logger.warning("Operating on PARTIAL_CONTEXT")
             
    except Exception as e:
        logger.exception("Failed to fetch context bundle")
        return {"status": "error", "reason": f"Context Fetch Failed: {str(e)}"}

    # Ensure external_id is available for downstream consumers
    ext_id = aggregated_metadata.get('external_id') or event.get('external_id') or "UNKNOWN"

    # 2. Prepare Context
    context_text = smart_truncate(docs_data)
    context_data = {
        "claim_documents": context_text,
        "claim_metadata": json.dumps(aggregated_metadata) 
    }
    
    # 3. Summarization Agent (Context Assembly)
    logger.info("Invoking SummarizationAgent...")
    from .agents import SummarizationAgent
    summary_agent = SummarizationAgent()
    summary_result = summary_agent.invoke(context_data)
    
    logger.info(f"Summarization Result: {summary_result}")
    
    # Enrich context with summary for downstream agents
    # We pass 'claim_summary' as string to match prompt placeholders
    # If summary_result has 'summary' key, use it. Else use json dump.
    summary_text = summary_result.get('summary', json.dumps(summary_result))
    
    context_data['claim_summary'] = summary_text
    
    # 4. Fraud Agent
    logger.info("Invoking FraudAgent...")
    fraud_agent = FraudAgent()
    fraud_result = fraud_agent.invoke(context_data)
    
    logger.info(f"Fraud Result: {fraud_result}")
    
    # Audit Logic (Fail Fast)
    if fraud_result.get('decision') == 'DENY' or fraud_result.get('recommendation') == 'DENY' or fraud_result.get('recommendation') == 'REVIEW':
         # Adjust logic: Fraud usually returns 'PASS' or 'REVIEW'.
         # Our prompt says: "recommendation": "PASS" or "REVIEW".
         # Existing code checks 'decision'. Let's support both.
         rec = fraud_result.get('recommendation', fraud_result.get('decision'))
         
         if rec in ['DENY', 'REVIEW'] or fraud_result.get('fraud_score', 0) > 0.7:
             return {
                "status": "success",
                "claim_uuid": claim_id,
                "recommendation": rec if rec else "REVIEW",
                "decision": rec if rec else "REVIEW",
                "reason": f"Fraud Check: {fraud_result.get('reason', 'High Risk Detected')}",
                "decision_reason": fraud_result.get('_rationale', "Fraud Logic"),
                "fraud_score": fraud_result.get('assessment', {}).get('confidence_score', 0.0),
                "payout_gbp": 0.0,
                "external_id": ext_id,
                "metadata": aggregated_metadata
             }
    
    # 5. Adjudication Agent (If Fraud Passed)
    logger.info("Invoking AdjudicationAgent...")
    adj_agent = AdjudicationAgent()
    adj_result = adj_agent.invoke(context_data)
    
    logger.info(f"Adjudication Result: {adj_result}")
    
    # 6. Final Decision & Payout Logic
    # If Adjudication is APPROVE, we pay the total amount from extracted facts.
    payout_gbp = 0.0
    context_s3_key = key
    
    if adj_result.get('decision') == 'APPROVE':
        extracted_facts = summary_result.get('extracted_facts', {})
        # Try to find total amount
        # Facts might be in summary_result or we parse from text?
        # SummarizationAgent prompt asks for 'extracted_facts': {'invoice_total': ...}
        
        amount = extracted_facts.get('total_amount') or extracted_facts.get('invoice_total') or 0.0
        try:
            # Simple cleanup
            payout_gbp = float(str(amount).replace('£', '').replace('$', '').replace(',', ''))
        except (ValueError, TypeError):
            logger.warning(f"Could not parse payout amount from {amount}")
            payout_gbp = 0.0

    return {
        "status": "success",
        "claim_uuid": claim_id,
        "recommendation": adj_result.get('decision', 'REVIEW'),
        "decision": adj_result.get('decision', 'REVIEW'), # Explicit for SF choice
        "reason": adj_result.get('reason', 'Analysis completed'),
        "decision_reason": adj_result.get('_rationale', "No rationale provided"),
        "fraud_score": fraud_result.get('assessment', {}).get('confidence_score', 0.0),
        "payout_gbp": payout_gbp,
        "context_s3_key": context_s3_key,
        "external_id": ext_id,
        "metadata": aggregated_metadata
    }
