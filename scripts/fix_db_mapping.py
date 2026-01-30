import boto3
import json

# Config
CLAIMS_TABLE = "ICPA_Claims"
ID_TO_FIX = "CLM-000001"

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(CLAIMS_TABLE)

def inspect_and_fix():
    print(f"Inspecting mappings for {ID_TO_FIX}...")
    
    # 1. Check Mapping
    try:
        resp = table.get_item(Key={'PK': f"MAPPING#{ID_TO_FIX}", 'SK': 'META'})
        item = resp.get('Item')
        
        if item:
            print(f"Found existing mapping: {item}")
            current_claim_id = item.get('claim_id')
            
            if current_claim_id != ID_TO_FIX:
                print(f"MISMATCH! Mapping points to {current_claim_id} instead of {ID_TO_FIX}")
                print("Deleting corrupt mapping...")
                table.delete_item(Key={'PK': f"MAPPING#{ID_TO_FIX}", 'SK': 'META'})
                print("Deleted.")
            else:
                print("Mapping is correct (Self-referential).")
        else:
            print("No mapping found (Clean slate).")
            
    except Exception as e:
        print(f"Error checking mapping: {e}")

    # 2. Check Claim Record
    try:
        resp = table.get_item(Key={'PK': f"CLAIM#{ID_TO_FIX}", 'SK': 'META'})
        item = resp.get('Item')
        if item:
            print(f"Found existing CLAIM record: {item.get('PK')} Status: {item.get('status')}")
        else:
             print("No CLAIM record found.")
             
    except Exception as e:
        print(f"Error checking claim: {e}")

    # 3. Check for Orphaned UUID Claims logic?
    # Not strictly necessary if we fix the mapping.

if __name__ == "__main__":
    inspect_and_fix()
