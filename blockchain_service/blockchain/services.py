import hashlib
import uuid
import random
import requests
from django.utils import timezone
from .models import (
    SignatureCertificate, HashProof, BlockchainNetwork, SmartContract,
    BlockchainTransaction, BlockchainAudit, DigitalSignature, VerificationHistory
)
from .repositories import (
    SignatureCertificateRepository, HashProofRepository
)

class CertificateService:
    @staticmethod
    def register_certificate(user_id, serial_number, issuer, valid_days=365, certificate_pem=None, public_key=None, signature_algorithm="SHA256withRSA"):
        cert = SignatureCertificateRepository.get_by_serial(serial_number)
        if not cert:
            now = timezone.now()
            cert = SignatureCertificate.objects.create(
                user_id=user_id,
                serial_number=serial_number,
                issuer=issuer,
                valid_from=now,
                valid_to=now + timezone.timedelta(days=valid_days),
                status="ACTIVE",
                certificate_pem=certificate_pem,
                public_key=public_key,
                signature_algorithm=signature_algorithm
            )
        return cert

class ProofService:
    @staticmethod
    def generate_proof(version_id, content=None, contract_code='CODE', version_number=1, change_summary='', previous_version_id=None):
        # Calculate SHA-256 hash
        if content:
            if isinstance(content, str):
                content_bytes = content.encode('utf-8')
            else:
                content_bytes = content
            doc_hash = hashlib.sha256(content_bytes).hexdigest()
            file_size = len(content_bytes)
        else:
            meta_str = f"{contract_code}-{version_number}-{change_summary}"
            doc_hash = hashlib.sha256(meta_str.encode('utf-8')).hexdigest()
            file_size = len(meta_str)

        # Get previous hash if previous version ID is provided
        previous_hash = None
        if previous_version_id:
            try:
                prev_proof = HashProof.objects.get(version_id=previous_version_id)
                previous_hash = prev_proof.document_hash
            except HashProof.DoesNotExist:
                pass

        # Merkle root calculation (simulated from current hash and previous hash)
        if previous_hash:
            merkle_root = hashlib.sha256((doc_hash + previous_hash).encode('utf-8')).hexdigest()
        else:
            merkle_root = hashlib.sha256(doc_hash.encode('utf-8')).hexdigest()

        proof, created = HashProof.objects.update_or_create(
            version_id=version_id,
            defaults={
                "hash_algorithm": "SHA-256",
                "document_hash": doc_hash,
                "file_size": file_size,
                "hash_version": 1,
                "previous_hash": previous_hash,
                "merkle_root": merkle_root,
                "verified": False
            }
        )

        return proof

class BlockchainAnchorService:
    @staticmethod
    def anchor_proof(proof_id, network_id=1, smart_contract_id=1, sender="System"):
        try:
            proof = HashProof.objects.get(id=proof_id)
        except HashProof.DoesNotExist:
            raise ValueError("Hash proof not found")

        # Get or create default network & smart contract to ensure no ForeignKey errors
        network, _ = BlockchainNetwork.objects.get_or_create(
            id=network_id,
            defaults={
                "network_name": "Hyperledger Fabric",
                "chain_type": "permissioned",
                "rpc_endpoint": "http://peer0.org1.example.com:7051"
            }
        )

        smart_contract = None
        if smart_contract_id:
            smart_contract, _ = SmartContract.objects.get_or_create(
                id=smart_contract_id,
                defaults={
                    "network": network,
                    "contract_address": "cc-contract-verify",
                    "contract_name": "ContractVerifyChaincode",
                    "version": "1.0",
                    "deployed_at": timezone.now()
                }
            )

        tx_hash = None
        block_number = None
        gas_fee = 0.0
        latency = 1.0

        # Try to anchor to the real Fabric network via the Node.js gateway
        try:
            resp = requests.post("http://fabric-gateway:5000/anchor", json={
                "proofId": str(proof.version_id),
                "documentHash": proof.document_hash,
                "merkleRoot": proof.merkle_root
            }, timeout=8)
            
            if resp.status_code != 200:
                error_msg = resp.json().get("error", "Unknown error from fabric-gateway")
                raise RuntimeError(f"Fabric Gateway returned error: {error_msg}")
                
            data = resp.json()
            tx_hash = data.get("tx_hash")
            block_number = data.get("block_number")
            block_hash = data.get("block_hash")
            latency = data.get("latency", 1.0)
            print(f"Successfully anchored to real Hyperledger Fabric. Tx Hash: {tx_hash} | Block Hash: {block_hash}")
        except requests.RequestException as e:
            raise RuntimeError(f"Fabric Gateway is offline or unreachable: {e}")

        tx = BlockchainTransaction.objects.create(
            proof=proof,
            network=network,
            smart_contract=smart_contract,
            tx_hash=tx_hash,
            block_hash=block_hash,
            block_number=block_number,
            gas_fee=gas_fee,
            status="CONFIRMED",
            tx_type="INVOKE",
            sender=sender,
            endorser="Peer0Org1MSP" if "Fabric" in network.network_name else None,
            channel_name="contracts-channel" if "Fabric" in network.network_name else "",
            chaincode_name=smart_contract.contract_name if smart_contract else "",
            fabric_tx_id=tx_hash,
            confirmation_time=latency,
            latency=latency,
            retry_count=0
        )

        # Create Blockchain Audit trail
        BlockchainAudit.objects.create(
            transaction=tx,
            action="Anchor Proof",
            resource=f"HashProof:{proof.id}",
            before_state="UNVERIFIED",
            after_state="VERIFIED",
            status="SUCCESS"
        )

        # Update proof status to verified
        proof.verified = True
        proof.verified_at = timezone.now()
        proof.save()

        return tx

class VerificationService:
    @staticmethod
    def verify_proof(version_id, content=None, contract_code='CODE', version_number=1, change_summary='', previous_version_id=None, user_id=None):
        proof = HashProof.objects.filter(version_id=version_id).first()
        if not proof:
            res = {
                "verified": False,
                "message": "No hash proof generated for this version.",
                "proof_hash": None,
                "current_hash": None
            }
            VerificationHistory.objects.create(
                version_id=version_id,
                verify_result=False,
                reason=res["message"],
                user_id=user_id
            )
            return res

        if content:
            if isinstance(content, str):
                content_bytes = content.encode('utf-8')
            else:
                content_bytes = content
            current_hash = hashlib.sha256(content_bytes).hexdigest()
        else:
            meta_str = f"{contract_code}-{version_number}-{change_summary}"
            current_hash = hashlib.sha256(meta_str.encode('utf-8')).hexdigest()

        # 1. Integrity Check (Current vs Proof Hash)
        if current_hash != proof.document_hash:
            res = {
                "verified": False,
                "message": "Integrity check failed: document hash mismatch.",
                "proof_hash": proof.document_hash,
                "current_hash": current_hash
            }
            VerificationHistory.objects.create(
                version_id=version_id,
                verify_result=False,
                reason=res["message"],
                user_id=user_id
            )
            return res

        # 2. Version Chain Check (Previous Hash validation)
        if previous_version_id:
            try:
                prev_proof = HashProof.objects.get(version_id=previous_version_id)
                if proof.previous_hash != prev_proof.document_hash:
                    res = {
                        "verified": False,
                        "message": "Version chain integrity check failed: previous hash mismatch.",
                        "proof_hash": proof.document_hash,
                        "current_hash": current_hash
                    }
                    VerificationHistory.objects.create(
                        version_id=version_id,
                        verify_result=False,
                        reason=res["message"],
                        user_id=user_id
                    )
                    return res
            except HashProof.DoesNotExist:
                pass

        # Try to verify on the real Fabric network via the Node.js gateway
        real_anchors = []
        blockchain_anchored = False
        try:
            resp = requests.post("http://fabric-gateway:5000/verify", json={
                "version_id": str(version_id)
            }, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("verified"):
                    blockchain_anchored = True
                    real_anchors = data.get("anchors", [])
                    print(f"Successfully verified against real Hyperledger Fabric.")
            else:
                error_msg = resp.json().get("error", "Unknown error")
                raise RuntimeError(f"Fabric Gateway verification failed: {error_msg}")
        except requests.RequestException as e:
            raise RuntimeError(f"Fabric Gateway connection failed: {e}")

        res = {
            "verified": True,
            "message": "Integrity successfully verified with blockchain anchors." if blockchain_anchored else "Integrity verified locally, but not anchored to the blockchain.",
            "proof_hash": proof.document_hash,
            "current_hash": current_hash,
            "blockchain_anchored": blockchain_anchored,
            "anchors": real_anchors
        }
        
        VerificationHistory.objects.create(
            version_id=version_id,
            verify_result=True,
            reason=res["message"],
            user_id=user_id
        )
        return res

class SignatureService:
    @staticmethod
    def verify_and_sign(step_id, user_id, certificate_id, signature_hash):
        cert = SignatureCertificate.objects.filter(id=certificate_id).first()
        if not cert:
            raise ValueError("Signature certificate not found")
        if cert.user_id != user_id:
            raise ValueError("Certificate does not belong to the user")
        if cert.status != "ACTIVE" or cert.revoked:
            raise ValueError("Certificate is not active or has been revoked")
        if cert.valid_to < timezone.now():
            raise ValueError("Certificate is expired")

        # Find the latest hashproof generated
        proof = HashProof.objects.order_by('-generated_at').first()
        if not proof:
            raise ValueError("No HashProof found to sign")

        sig = DigitalSignature.objects.create(
            certificate=cert,
            hashproof=proof,
            signature=signature_hash,
            algorithm=cert.signature_algorithm,
            verified=True,
            verified_at=timezone.now()
        )

        return {
            "status": "success",
            "message": "Signature verified and created successfully",
            "signature_id": sig.id,
            "step_id": step_id,
            "user_id": user_id,
            "signature_hash": signature_hash,
            "certificate_serial": cert.serial_number
        }

class EnterpriseRegistryService:
    @staticmethod
    def register_company(company_id, company_name, tax_code, status="ACTIVE", network_id=1, smart_contract_id=1, sender="System"):
        network, _ = BlockchainNetwork.objects.get_or_create(
            id=network_id,
            defaults={
                "network_name": "Hyperledger Fabric",
                "chain_type": "permissioned",
                "rpc_endpoint": "http://peer0.org1.example.com:7051"
            }
        )

        smart_contract, _ = SmartContract.objects.get_or_create(
            id=smart_contract_id,
            defaults={
                "contract_name": "ContractVerifyChaincode",
                "version": "1.0",
                "address": "ContractVerifyChaincode"
            }
        )

        try:
            resp = requests.post("http://fabric-gateway:5000/company/store", json={
                "companyId": str(company_id),
                "companyName": company_name,
                "taxCode": tax_code,
                "status": status
            }, timeout=15)
            
            if resp.status_code != 200:
                error_msg = resp.json().get("error", "Unknown error from fabric-gateway")
                raise RuntimeError(f"Fabric Gateway returned error: {error_msg}")
                
            data = resp.json()
            tx_hash = data.get("tx_hash")
            block_number = data.get("block_number")
            block_hash = data.get("block_hash")
            latency = data.get("latency", 1.0)
            print(f"Successfully registered Company {company_name} on Fabric. Tx Hash: {tx_hash} | Block Hash: {block_hash}")
        except requests.RequestException as e:
            raise RuntimeError(f"Fabric Gateway is offline or unreachable: {e}")

        tx = BlockchainTransaction.objects.create(
            proof=None,
            network=network,
            smart_contract=smart_contract,
            tx_hash=tx_hash,
            block_hash=block_hash,
            block_number=block_number,
            gas_fee=0.0,
            status="CONFIRMED",
            tx_type="INVOKE",
            sender=sender,
            endorser="Peer0Org1MSP",
            channel_name="contracts-channel",
            chaincode_name=smart_contract.contract_name,
            fabric_tx_id=tx_hash,
            confirmation_time=latency,
            latency=latency,
            retry_count=0
        )

        BlockchainAudit.objects.create(
            transaction=tx,
            action="Register Company",
            resource=f"Company:{company_id}",
            before_state="UNREGISTERED",
            after_state="REGISTERED",
            status="SUCCESS"
        )

        return tx

    @staticmethod
    def register_user(user_id, username, company_id, role, status="ACTIVE", network_id=1, smart_contract_id=1, sender="System"):
        network, _ = BlockchainNetwork.objects.get_or_create(
            id=network_id,
            defaults={
                "network_name": "Hyperledger Fabric",
                "chain_type": "permissioned",
                "rpc_endpoint": "http://peer0.org1.example.com:7051"
            }
        )

        smart_contract, _ = SmartContract.objects.get_or_create(
            id=smart_contract_id,
            defaults={
                "contract_name": "ContractVerifyChaincode",
                "version": "1.0",
                "address": "ContractVerifyChaincode"
            }
        )

        try:
            resp = requests.post("http://fabric-gateway:5000/user/store", json={
                "userId": str(user_id),
                "username": username,
                "companyId": str(company_id),
                "role": role,
                "status": status
            }, timeout=15)
            
            if resp.status_code != 200:
                error_msg = resp.json().get("error", "Unknown error from fabric-gateway")
                raise RuntimeError(f"Fabric Gateway returned error: {error_msg}")
                
            data = resp.json()
            tx_hash = data.get("tx_hash")
            block_number = data.get("block_number")
            block_hash = data.get("block_hash")
            latency = data.get("latency", 1.0)
            print(f"Successfully registered User {username} on Fabric. Tx Hash: {tx_hash} | Block Hash: {block_hash}")
        except requests.RequestException as e:
            raise RuntimeError(f"Fabric Gateway is offline or unreachable: {e}")

        tx = BlockchainTransaction.objects.create(
            proof=None,
            network=network,
            smart_contract=smart_contract,
            tx_hash=tx_hash,
            block_hash=block_hash,
            block_number=block_number,
            gas_fee=0.0,
            status="CONFIRMED",
            tx_type="INVOKE",
            sender=sender,
            endorser="Peer0Org1MSP",
            channel_name="contracts-channel",
            chaincode_name=smart_contract.contract_name,
            fabric_tx_id=tx_hash,
            confirmation_time=latency,
            latency=latency,
            retry_count=0
        )

        BlockchainAudit.objects.create(
            transaction=tx,
            action="Register User",
            resource=f"User:{user_id}",
            before_state="UNREGISTERED",
            after_state="REGISTERED",
            status="SUCCESS"
        )

        return tx
