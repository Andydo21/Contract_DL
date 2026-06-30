import os
import django
import requests

# 1. Initialize Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from contracts.models import Contract, ContractVersion
from contracts.services import ContractService
from contracts.views import _bc_version_payload

BLOCKCHAIN_SERVICE_URL = os.environ.get("BLOCKCHAIN_SERVICE_URL", "http://blockchain-service:8000")

def anchor_existing_contracts():
    print("=== STARTING BLOCKCHAIN ANCHORING FOR EXISTING CONTRACTS ===")
    
    # We will pick a few specific contracts from the database
    target_ids = [11, 12, 13, 21, 22]
    contracts = Contract.objects.filter(id__in=target_ids)
    
    if not contracts.exists():
        print("No target contracts found. Picking the first 3 available contracts instead.")
        contracts = Contract.objects.all()[:3]
        
    if not contracts.exists():
        print("No contracts found in the database. Please create a contract first.")
        return

    service = ContractService()
    
    for contract in contracts:
        print(f"\nProcessing Contract: ID {contract.id} - '{contract.title}'")
        
        # 1. Create a new version
        change_summary = f"Blockchain anchoring validation version - Tx test"
        raw_content = f"This is an updated version of the contract '{contract.title}' (Code: {contract.contract_code}) generated for real-time Hyperledger Fabric blockchain anchoring validation."
        
        try:
            new_version = service.create_new_version(
                contract_id=contract.id,
                raw_content=raw_content,
                change_summary=change_summary
            )
            print(f"-> Created New Version: Number {new_version.version_number} (ID: {new_version.id})")
        except Exception as e:
            print(f"-> Failed to create new version: {e}")
            continue
            
        # 2. Generate Proof
        payload = _bc_version_payload(new_version)
        try:
            gen_resp = requests.post(f"{BLOCKCHAIN_SERVICE_URL}/proofs/generate/", json=payload, timeout=15)
            if not gen_resp.ok:
                print(f"-> Failed to generate proof: {gen_resp.text}")
                continue
            gen_data = gen_resp.json()
            proof_id = gen_data.get("proof_id")
            document_hash = gen_data.get("document_hash")
            print(f"-> Generated Proof ID: {proof_id} | Hash: {document_hash}")
        except Exception as e:
            print(f"-> Error calling proof generation: {e}")
            continue
            
        # 3. Anchor to Blockchain (Fabric)
        try:
            anchor_payload = {
                "proof_id": proof_id,
                "network_id": 1,
                "smart_contract_id": 1
            }
            anchor_resp = requests.post(f"{BLOCKCHAIN_SERVICE_URL}/proofs/anchor/", json=anchor_payload, timeout=15)
            if not anchor_resp.ok:
                print(f"-> Failed to anchor proof: {anchor_resp.text}")
                continue
            anchor_data = anchor_resp.json()
            tx_hash = anchor_data.get("tx_hash")
            block_number = anchor_data.get("block_number")
            print(f"-> SUCCESSFULLY ANCHORED to Fabric! Block: {block_number} | Tx Hash: {tx_hash}")
        except Exception as e:
            print(f"-> Error calling anchoring: {e}")
            continue

    print("\n=== ANCHORING COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    anchor_existing_contracts()
