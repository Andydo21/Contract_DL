from .models import (
    SignatureCertificate, HashProof, BlockchainNetwork, SmartContract,
    BlockchainNode, BlockchainTransaction, BlockchainAudit, KeyManagement
)

class SignatureCertificateRepository:
    @staticmethod
    def get_by_serial(serial_number):
        return SignatureCertificate.objects.filter(serial_number=serial_number).first()

    @staticmethod
    def get_by_id(certificate_id):
        try:
            return SignatureCertificate.objects.get(id=certificate_id)
        except SignatureCertificate.DoesNotExist:
            return None

    @staticmethod
    def create_certificate(user_id, serial_number, issuer, valid_from, valid_to, status="ACTIVE"):
        return SignatureCertificate.objects.create(
            user_id=user_id,
            serial_number=serial_number,
            issuer=issuer,
            valid_from=valid_from,
            valid_to=valid_to,
            status=status
        )

class HashProofRepository:
    @staticmethod
    def get_by_version(version_id):
        return HashProof.objects.filter(version_id=version_id).first()

    @staticmethod
    def get_by_id(proof_id):
        try:
            return HashProof.objects.get(id=proof_id)
        except HashProof.DoesNotExist:
            return None

    @staticmethod
    def create_proof(version_id, hash_algorithm, document_hash):
        return HashProof.objects.create(
            version_id=version_id,
            hash_algorithm=hash_algorithm,
            document_hash=document_hash
        )

class BlockchainNetworkRepository:
    @staticmethod
    def get_by_id(network_id):
        try:
            return BlockchainNetwork.objects.get(id=network_id)
        except BlockchainNetwork.DoesNotExist:
            return None

class SmartContractRepository:
    @staticmethod
    def get_by_id(smart_contract_id):
        try:
            return SmartContract.objects.get(id=smart_contract_id)
        except SmartContract.DoesNotExist:
            return None

class BlockchainTransactionRepository:
    @staticmethod
    def get_confirmed_transactions_by_proof(proof):
        return BlockchainTransaction.objects.filter(proof=proof, status="CONFIRMED")

    @staticmethod
    def create_transaction(proof, network, smart_contract, tx_hash, block_hash, block_number, gas_fee, status="CONFIRMED"):
        return BlockchainTransaction.objects.create(
            proof=proof,
            network=network,
            smart_contract=smart_contract,
            tx_hash=tx_hash,
            block_hash=block_hash,
            block_number=block_number,
            gas_fee=gas_fee,
            status=status
        )

class BlockchainAuditRepository:
    @staticmethod
    def create_audit(transaction, event_type, event_data):
        return BlockchainAudit.objects.create(
            transaction=transaction,
            event_type=event_type,
            event_data=event_data
        )

class KeyManagementRepository:
    @staticmethod
    def get_by_id(key_id):
        try:
            return KeyManagement.objects.get(id=key_id)
        except KeyManagement.DoesNotExist:
            return None
