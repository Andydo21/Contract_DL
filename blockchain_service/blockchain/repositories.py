from .models import (
    SignatureCertificate, HashProof, BlockchainNetwork, SmartContract,
    BlockchainTransaction, BlockchainAudit, BlockchainNode, DigitalSignature, VerificationHistory
)

class BookRepository:
    """Queries of the ledger book (book.py)."""

    @staticmethod
    def table_exists(name):
        from django.db import connection
        return name in connection.introspection.table_names()

    @staticmethod
    def network_by_name(name):
        return BlockchainNetwork.objects.filter(network_name=name).first()

    @staticmethod
    def create_network(**fields):
        return BlockchainNetwork.objects.create(**fields)

    @staticmethod
    def ensure_node(network, node_name, endpoint, organization):
        return BlockchainNode.objects.get_or_create(network=network, node_name=node_name,
                                                    defaults=dict(endpoint=endpoint, organization=organization))[0]

    @staticmethod
    def smart_contract(network, contract_name):
        return SmartContract.objects.filter(network=network, contract_name=contract_name).first()

    @staticmethod
    def create_smart_contract(**fields):
        return SmartContract.objects.create(**fields)

    @staticmethod
    def current_certificate(user_id, latest=True):
        qs = SignatureCertificate.objects.filter(user_id=user_id, revoked=False)
        return (qs.order_by('-valid_from') if latest else qs).first()

    @staticmethod
    def create_certificate(**fields):
        return SignatureCertificate.objects.create(**fields)

    @staticmethod
    def save(obj, update_fields=None):
        obj.save(update_fields=update_fields) if update_fields else obj.save()
        return obj

    @staticmethod
    def create_audit(**fields):
        return BlockchainAudit.objects.create(**fields)

    @staticmethod
    def transaction_by_hash(tx_hash):
        return BlockchainTransaction.objects.filter(tx_hash=tx_hash).first()

    @staticmethod
    def lock_proof(version_id):
        return HashProof.objects.select_for_update().filter(version_id=version_id).first()

    @staticmethod
    def create_proof(**fields):
        return HashProof.objects.create(**fields)

    @staticmethod
    def create_transaction(**fields):
        return BlockchainTransaction.objects.create(**fields)

    @staticmethod
    def create_signature(**fields):
        return DigitalSignature.objects.create(**fields)

    @staticmethod
    def create_verification(**fields):
        return VerificationHistory.objects.create(**fields)

    @staticmethod
    def latest_transaction_for_version(version_id):
        return BlockchainTransaction.objects.filter(proof__version_id=version_id).order_by('-block_number').first()

    @staticmethod
    def ping():
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
