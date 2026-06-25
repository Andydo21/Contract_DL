import os
import requests
import hashlib
from django.conf import settings
from .models import ContractVersion

class BlockchainService:
    def __init__(self):
        # Default to Docker service link, but allow override
        self.base_url = os.environ.get("BLOCKCHAIN_SERVICE_URL", "http://blockchain-service:8000")

    def _get_version_data(self, version_id):
        try:
            version = ContractVersion.objects.get(id=version_id)
        except ContractVersion.DoesNotExist:
            raise ValueError("ContractVersion not found.")

        # Try to read file content for hashing
        file_obj = version.files.first()
        content = None
        if file_obj and file_obj.file_path and os.path.exists(file_obj.file_path):
            try:
                with open(file_obj.file_path, "rb") as f:
                    content = f.read().decode('utf-8', errors='ignore')
            except Exception:
                pass

        return {
            "version_id": version.id,
            "content": content,
            "change_summary": version.change_summary or "",
            "contract_code": version.contract.contract_code,
            "version_number": version.version_number
        }

    def generate_hash_proof(self, version_id):
        data = self._get_version_data(version_id)
        response = requests.post(f"{self.base_url}/proofs/generate/", json=data)
        if response.status_code != 200:
            raise Exception(f"Blockchain microservice error: {response.text}")
        return response.json()

    def anchor_hash_proof(self, proof_id, network_id, smart_contract_id=None):
        payload = {
            "proof_id": proof_id,
            "network_id": network_id,
            "smart_contract_id": smart_contract_id
        }
        response = requests.post(f"{self.base_url}/proofs/anchor/", json=payload)
        if response.status_code != 200:
            raise Exception(f"Blockchain microservice error: {response.text}")
        return response.json()

    def verify_hash_proof(self, version_id):
        data = self._get_version_data(version_id)
        response = requests.post(f"{self.base_url}/proofs/verify/", json=data)
        if response.status_code != 200:
            raise Exception(f"Blockchain microservice error: {response.text}")
        return response.json()

