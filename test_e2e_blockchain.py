import os
import django
import sys
import json
import uuid
from django.utils import timezone

# Setup Django environment
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.conf import settings
from contracts.models import Contract, ContractVersion, ContractFile
from contracts.crypto_utils import encrypt_pdf, decrypt_pdf

def test_crypto_utils():
    print("=== Testing Crypto Utilities ===")
    original_data = b"Hello, this is a highly confidential contract document. Keep it secret!"
    encrypted = encrypt_pdf(original_data)
    assert encrypted != original_data, "Encryption failed to alter data"
    decrypted = decrypt_pdf(encrypted)
    assert decrypted == original_data, "Decrypted data does not match original"
    print("Crypto utilities passed! AES-256-GCM works perfectly.\n")

def test_e2e_flow():
    print("=== Testing End-to-End Flow ===")
    client = Client()
    
    # 1. Create a contract and upload a file
    unique_code = f"TEST-{uuid.uuid4().hex[:6].upper()}"
    file_content = b"Contract Content: Party A agrees to pay Party B 100 USD."
    
    # Simulate file upload using SimpleUploadedFile
    from django.core.files.uploadedfile import SimpleUploadedFile
    uploaded_file = SimpleUploadedFile("contract_draft.txt", file_content, content_type="text/plain")
    
    # We will create the contract via the service to trigger encryption
    from contracts.services import ContractService
    service = ContractService()
    contract = service.create_and_analyze_contract(
        code=unique_code,
        title="E2E Test Contract",
        contract_type="Service",
        start_date=timezone.now().date(),
        end_date=timezone.now().date() + timezone.timedelta(days=30),
        contract_value=100.0,
        file_obj=uploaded_file
    )
    
    print(f"Contract created: {contract.contract_code}")
    
    # Verify the file is encrypted on disk
    version = contract.latest_version
    cf = version.files.first()
    assert cf is not None, "Contract file record was not created"
    
    # Read raw file from disk
    rel_path = cf.file_path.lstrip(settings.MEDIA_URL)
    physical_path = os.path.join(settings.MEDIA_ROOT, rel_path.replace('/', os.sep))
    with open(physical_path, 'rb') as f:
        disk_content = f.read()
        
    assert disk_content != file_content, "File on disk is not encrypted!"
    print("Verified: File on disk is encrypted.")
    
    # 2. Download the file via the download endpoint
    download_url = f"/api/contracts/files/{cf.id}/download/"
    resp = client.get(download_url)
    assert resp.status_code == 200, f"Download failed: {resp.status_code}"
    assert resp.content == file_content, "Downloaded content does not match original decrypted content!"
    print("Verified: Downloaded file is automatically decrypted correctly.")

    # 3. Generate Blockchain Proof (REST API proxy)
    proof_url = f"/api/contracts/{contract.id}/blockchain/proof/"
    resp = client.post(proof_url, content_type="application/json")
    assert resp.status_code == 200, f"Generate proof failed: {resp.content}"
    proof_data = resp.json()
    assert "document_hash" in proof_data, "document_hash missing from response"
    proof_id = proof_data["proof_id"]
    doc_hash = proof_data["document_hash"]
    print(f"Verified: Proof generated on blockchain-service. Hash: {doc_hash}")

    # 4. Verify Proof (Local integrity check before anchoring)
    verify_url = f"/api/contracts/{contract.id}/blockchain/verify/"
    resp = client.post(verify_url, content_type="application/json")
    assert resp.status_code == 200, f"Verify proof failed: {resp.content}"
    verify_data = resp.json()
    assert verify_data["verified"] is True, "Local verification failed"
    assert verify_data["blockchain_anchored"] is False, "Should not be anchored yet"
    print("Verified: Local integrity verified successfully, not yet anchored.")

    # 5. Anchor Proof to simulated Hyperledger/Ethereum
    anchor_url = f"/api/contracts/{contract.id}/blockchain/anchor/"
    resp = client.post(anchor_url, data=json.dumps({"proof_id": proof_id, "network_id": 1}), content_type="application/json")
    assert resp.status_code == 200, f"Anchor proof failed: {resp.content}"
    anchor_data = resp.json()
    assert anchor_data["status"] == "CONFIRMED", "Transaction status is not CONFIRMED"
    tx_hash = anchor_data["tx_hash"]
    print(f"Verified: Anchored to blockchain. Tx Hash: {tx_hash}")

    # 6. Verify Proof again (should be anchored now!)
    import time
    print("Waiting 2 seconds for block commitment...")
    time.sleep(2)
    resp = client.post(verify_url, content_type="application/json")
    assert resp.status_code == 200
    verify_data = resp.json()
    assert verify_data["verified"] is True
    assert verify_data["blockchain_anchored"] is True
    assert len(verify_data["anchors"]) > 0
    print("Verified: Verification now shows as anchored on blockchain.")

    # 7. Test Blockchain History Endpoint
    history_url = f"/api/blockchain/history/{version.id}/"
    resp = client.get(history_url)
    assert resp.status_code == 200
    history_data = resp.json()
    assert len(history_data["history"]) > 0
    print("Verified: History endpoint returned transaction and audit logs.")

    # 8. Test Blockchain Transaction Detail Endpoint
    tx_url = f"/api/blockchain/transaction/{tx_hash}/"
    resp = client.get(tx_url)
    assert resp.status_code == 200
    tx_detail = resp.json()
    assert tx_detail["tx_hash"] == tx_hash
    print("Verified: Transaction detail endpoint returned correct info.")

    # Clean up test contract
    contract.delete()
    print("\nE2E Flow passed successfully!\n")

if __name__ == "__main__":
    try:
        test_crypto_utils()
        test_e2e_flow()
        print("ALL TESTS PASSED SUCCESSFULLY!")
    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
