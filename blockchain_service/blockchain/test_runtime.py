from unittest.mock import Mock, patch
import requests
from django.test import TestCase
from .models import BlockchainTransaction
from .services import BlockchainAnchorService, EnterpriseRegistryService, ProofService, VerificationService


class FabricFailureTests(TestCase):
    def setUp(self):
        self.proof = ProofService.generate_proof(1, content='test contract')

    @patch('blockchain.services.requests.post', side_effect=requests.ConnectionError('offline'))
    def test_offline_anchor_never_records_confirmation(self, post):
        with self.assertRaises(RuntimeError):
            BlockchainAnchorService.anchor_proof(self.proof.pk)
        self.assertFalse(BlockchainTransaction.objects.exists())
        self.proof.refresh_from_db()
        self.assertFalse(self.proof.verified)

    @patch('blockchain.services.requests.post')
    def test_rejected_anchor_never_records_confirmation(self, post):
        post.return_value = Mock(status_code=503)
        post.return_value.json.return_value = {'error': 'chaincode unavailable'}
        with self.assertRaises(RuntimeError):
            BlockchainAnchorService.anchor_proof(self.proof.pk)
        self.assertFalse(BlockchainTransaction.objects.exists())

    @patch('blockchain.services.requests.post', side_effect=requests.ConnectionError('offline'))
    def test_offline_registration_never_records_confirmation(self, post):
        with self.assertRaises(RuntimeError):
            EnterpriseRegistryService.register_company(1, 'Demo', 'demo')
        with self.assertRaises(RuntimeError):
            EnterpriseRegistryService.register_user(1, 'demo', 1, 'USER')
        self.assertFalse(BlockchainTransaction.objects.exists())

    @patch('blockchain.services.requests.post')
    def test_only_real_gateway_metadata_is_saved(self, post):
        data = {'tx_hash': 'a' * 64, 'block_number': 3, 'block_hash': 'b' * 64}
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = data
        tx = BlockchainAnchorService.anchor_proof(self.proof.pk)
        self.assertEqual((tx.tx_hash, tx.block_number, tx.block_hash),
                         (data['tx_hash'], data['block_number'], data['block_hash']))

    @patch('blockchain.services.requests.post')
    def test_different_ledger_hash_is_not_verified_as_anchored(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {'verified': True, 'proof_hash': '0' * 64, 'anchors': [{'tx_hash': 'fake'}]}
        result = VerificationService.verify_proof(1, content='test contract')
        self.assertFalse(result['blockchain_anchored'])
        self.assertEqual(result['anchors'], [])

    @patch('blockchain.services.requests.post', side_effect=requests.ConnectionError('offline'))
    def test_local_confirmation_does_not_establish_live_verification(self, post):
        BlockchainTransaction.objects.create(proof=self.proof, tx_hash='legacy-simulation', status='CONFIRMED')
        result = VerificationService.verify_proof(1, content='test contract')
        self.assertFalse(result['blockchain_anchored'])
        self.assertEqual(result['anchors'], [])
