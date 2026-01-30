import boto3
import sys
from boto3.dynamodb.conditions import Key

def check_status(external_id):
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('ICPA_Claims')
    
    print(f"Querying for External ID: {external_id}")
    
    response = table.query(
        IndexName='ExternalIdIndex',
        KeyConditionExpression=Key('external_id').eq(external_id)
    )
    
    items = response.get('Items', [])
    if not items:
        print("No items found.")
        return

    print(f"Found {len(items)} items.")
    for item in items:
        print(f"PK: {item.get('PK')}")
        print(f"Status: {item.get('status')}")
        print(f"Decision Reason: {item.get('decision_reason', 'N/A')}")
        print(f"Last Updated: {item.get('updated_at', 'N/A')}")
        print("-" * 20)


def check_sf_executions():
    sf = boto3.client('stepfunctions', region_name='us-east-1')
    arn = "arn:aws:states:us-east-1:120106008631:stateMachine:OrchestrationStateMachineFE6E059A-WVpJU4U9FW9b"
    
    print(f"\nChecking Executions for {arn}...")
    resp = sf.list_executions(stateMachineArn=arn, maxResults=5)
    
    for ex in resp.get('executions', []):
        print(f"ExecutionArn: {ex['executionArn']}")
        print(f"Status: {ex['status']}")
        
        # Get Output
        if ex['status'] == 'SUCCEEDED':
            desc = sf.describe_execution(executionArn=ex['executionArn'])
            print(f"Output: {desc.get('output')}")
            
        if ex['status'] == 'FAILED':
            # Get History
            hist = sf.get_execution_history(executionArn=ex['executionArn'], maxResults=5, reverseOrder=True)
            for event in hist['events']:
                 if 'executionFailedEventDetails' in event:
                     print(f"FAILURE CAUSE: {event['executionFailedEventDetails']}")
                     break
        print("-" * 20)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        check_status(sys.argv[1])
    else:
        check_status("CLM-000001")
    check_sf_executions()
