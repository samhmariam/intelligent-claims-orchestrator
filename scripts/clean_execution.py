import boto3
import argparse
import sys

def clean_execution(claim_id):
    client = boto3.client('stepfunctions')
    
    # 1. Find State Machine ARN (filtering by name prefix)
    state_machines = client.list_state_machines()['stateMachines']
    # Look for the V2 one preferably, or any match
    sm_arn = None
    for sm in state_machines:
        if 'OrchestrationStateMachine' in sm['name']:
            sm_arn = sm['stateMachineArn']
            print(f"Found State Machine: {sm['name']}")
            break # Take the first one (V2 should be it if deployed)
            
    if not sm_arn:
        print("Error: Could not find Orchestration State Machine.")
        return

    # 2. List Executions for this State Machine
    # We are looking for an execution named exactly {claim_id}
    print(f"Checking for execution named '{claim_id}' in {sm_arn}...")
    
    # Unfortunately list_executions doesn't filter by name directly in simplified API,
    # but we can construct the ARN if we know the Account/Region, or just list and filter.
    # Constructing ARN is safer: arn:aws:states:region:account:execution:SMName:ExecutionName
    # But finding the SM name part of ARN is easy.
    
    # Let's try list_executions
    paginator = client.get_paginator('list_executions')
    
    found = False
    for page in paginator.paginate(stateMachineArn=sm_arn):
        for exc in page['executions']:
            if exc['name'] == claim_id:
                found = True
                print(f"Found existing execution: {exc['executionArn']} (Status: {exc['status']})")
                
                if exc['status'] == 'RUNNING':
                    print("Stopping execution...")
                    client.stop_execution(executionArn=exc['executionArn'], cause="User requested cleanup")
                    print("Stopped.")
                else:
                    print("Execution is already finished. Cannot delete from history via API.")
                    print("NOTE: With Singleton Pattern, a finished execution prevents re-run.")
                    print("Ensure you are using a NEW State Machine (V2) or have deleted the old one.")
    
    if not found:
        print(f"No execution found with name '{claim_id}'. Clean slate.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--claim-id', default='CLM-000001')
    args = parser.parse_args()
    
    clean_execution(args.claim_id)
