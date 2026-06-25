import json
import uuid
import random
import hashlib
import datetime
from django.utils import timezone
from .repositories import (
    SignatureCertificateRepository, HashProofRepository, BlockchainNetworkRepository,
    SmartContractRepository, BlockchainTransactionRepository, BlockchainAuditRepository
)

class CertificateService:
    @staticmethod
    def register_certificate(user_id, serial_number, issuer, valid_days=365):
        cert = SignatureCertificateRepository.get_by_serial(serial_number)
        if not cert:
            now = timezone.now()
            cert = SignatureCertificateRepository.create_certificate(
                user_id=user_id,
                serial_number=serial_number,
                issuer=issuer,
                valid_from=now,
                valid_to=now + datetime.timedelta(days=valid_days),
                status="ACTIVE"
            )
        return cert

class ProofService:
    @staticmethod
    def generate_proof(version_id, content=None, contract_code='CODE', version_number=1, change_summary=''):
        if content:
            doc_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        else:
            meta_str = f"{contract_code}-{version_number}-{change_summary}"
            doc_hash = hashlib.sha256(meta_str.encode('utf-8')).hexdigest()
            
        proof = HashProofRepository.get_by_version(version_id)
        if proof:
            proof.document_hash = doc_hash
            proof.save()
        else:
            proof = HashProofRepository.create_proof(
                version_id=version_id,
                hash_algorithm="SHA-256",
                document_hash=doc_hash
            )
        return proof

class BlockchainAnchorService:
    @staticmethod
    def anchor_proof(proof_id, network_id, smart_contract_id=None):
        proof = HashProofRepository.get_by_id(proof_id)
        if not proof:
            raise ValueError("Hash proof not found")
            
        network = BlockchainNetworkRepository.get_by_id(network_id)
        if not network:
            raise ValueError("Blockchain network not found")
            
        smart_contract = None
        if smart_contract_id:
            smart_contract = SmartContractRepository.get_by_id(smart_contract_id)
            if not smart_contract:
                raise ValueError("Smart contract not found")
                
        # Generate mock transaction details
        tx_hash = "0x" + uuid.uuid4().hex + uuid.uuid4().hex
        block_hash = "0x" + uuid.uuid4().hex
        block_number = random.randint(15000000, 20000000)
        gas_fee = random.uniform(0.001, 0.05)
        
        tx = BlockchainTransactionRepository.create_transaction(
            proof=proof,
            network=network,
            smart_contract=smart_contract,
            tx_hash=tx_hash,
            block_hash=block_hash,
            block_number=block_number,
            gas_fee=gas_fee,
            status="CONFIRMED"
        )
        
        event_data = {
            "tx_hash": tx_hash,
            "document_hash": proof.document_hash,
            "block_number": block_number,
            "gas_fee": f"{gas_fee:.6f}",
            "anchored_by": "Blockchain Django Microservice"
        }
        
        BlockchainAuditRepository.create_audit(
            transaction=tx,
            event_type="ANCHOR_PROOF",
            event_data=json.dumps(event_data)
        )
        
        return tx

class VerificationService:
    @staticmethod
    def verify_proof(version_id, content=None, contract_code='CODE', version_number=1, change_summary=''):
        proof = HashProofRepository.get_by_version(version_id)
        if not proof:
            return {
                "verified": False,
                "message": "No hash proof generated for this version.",
                "proof_hash": None,
                "current_hash": None
            }
            
        if content:
            current_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        else:
            meta_str = f"{contract_code}-{version_number}-{change_summary}"
            current_hash = hashlib.sha256(meta_str.encode('utf-8')).hexdigest()
            
        if current_hash != proof.document_hash:
            return {
                "verified": False,
                "message": "Integrity check failed: document hash mismatch.",
                "proof_hash": proof.document_hash,
                "current_hash": current_hash
            }
            
        txs = BlockchainTransactionRepository.get_confirmed_transactions_by_proof(proof)
        if not txs.exists():
            return {
                "verified": True,
                "message": "Integrity verified locally, but not anchored to any blockchain.",
                "proof_hash": proof.document_hash,
                "current_hash": current_hash,
                "blockchain_anchored": False,
                "anchors": []
            }
            
        anchors = []
        for tx in txs:
            anchors.append({
                "network": tx.network.network_name,
                "tx_hash": tx.tx_hash,
                "block_number": tx.block_number,
                "gas_fee": float(tx.gas_fee) if tx.gas_fee else None,
                "created_at": tx.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        return {
            "verified": True,
            "message": "Integrity successfully verified with blockchain anchors.",
            "proof_hash": proof.document_hash,
            "current_hash": current_hash,
            "blockchain_anchored": True,
            "anchors": anchors
        }

class SignatureService:
    @staticmethod
    def verify_and_sign(step_id, user_id, certificate_id, signature_hash):
        from .repositories import SignatureCertificateRepository
        cert = SignatureCertificateRepository.get_by_id(certificate_id)
        if not cert:
            raise ValueError("Signature certificate not found")
            
        if cert.user_id != user_id:
            raise ValueError("Certificate does not belong to the user")
            
        if cert.status != "ACTIVE":
            raise ValueError("Certificate is not active")
            
        if cert.valid_to < timezone.now():
            raise ValueError("Certificate is expired")
            
        return {
            "status": "success",
            "message": "Signature verified and created successfully",
            "step_id": step_id,
            "user_id": user_id,
            "signature_hash": signature_hash,
            "certificate_serial": cert.serial_number
        }
