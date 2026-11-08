"""The ledger book files what the contract web confirmed on Fabric, once per transaction."""
import json
import os
from unittest.mock import patch

from django.test import Client, TestCase

from . import book
from .models import (BlockchainAudit, BlockchainNode, BlockchainTransaction, DigitalSignature, HashProof, SignatureCertificate,
                     SmartContract, VerificationHistory)

KEY = '-----BEGIN PUBLIC KEY-----\nMIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEA\n-----END PUBLIC KEY-----\n'


def operation(**changes):
    return dict(dict(operation_id='0e5c1d6e-1111-4222-8333-944445555666', kind='ANCHOR', version_id=10, contract_id=3, company_id=1,
                     actor_id=7, step_id=0, document_hash='a' * 64, tx_id='b' * 64, block_number=9, block_hash='c' * 64,
                     confirmed_at='2026-11-08T06:00:00+00:00', signature='', public_key_pem='', credential_fingerprint=''), **changes)


class LedgerBookTests(TestCase):
    def test_an_anchor_files_proof_transaction_and_audit_once(self):
        self.assertTrue(book.record_operation(operation())['recorded'])
        self.assertFalse(book.record_operation(operation())['recorded'])
        tx = BlockchainTransaction.objects.get()
        self.assertEqual((tx.tx_type, tx.block_number, tx.status, tx.proof.document_hash), ('ANCHOR', 9, 'CONFIRMED', 'a' * 64))
        self.assertEqual((tx.network.chain_type, tx.smart_contract.contract_name), ('Hyperledger Fabric 2.5', 'contract_verify'))
        self.assertEqual(BlockchainAudit.objects.get().action, 'LEDGER_ANCHOR')
        self.assertEqual(SmartContract.objects.count(), 1)

    def test_the_network_lists_its_orderer_peer_and_gateway_once(self):
        book.network(); book.network()
        self.assertEqual(sorted(BlockchainNode.objects.values_list('node_name', flat=True)),
                         ['fabric-gateway', 'orderer.example.com', 'peer0.org1.example.com'])

    def test_a_registration_is_audited_without_a_transaction(self):
        book.register_user(dict(user_id=11, username='u', company_id=1, role='FINANCE'))
        entry = BlockchainAudit.objects.get(action='USER_REGISTERED')
        self.assertEqual((entry.transaction_id, entry.user_id), (None, 11))

    def test_a_new_file_of_the_same_version_keeps_the_previous_hash(self):
        book.record_operation(operation())
        book.record_operation(operation(tx_id='d' * 64, document_hash='e' * 64, block_number=10))
        proof = HashProof.objects.get(version_id=10)
        self.assertEqual((proof.document_hash, proof.previous_hash, proof.hash_version), ('e' * 64, 'a' * 64, 2))

    def test_a_signature_binds_the_key_to_the_signers_certificate(self):
        registered = book.register_user(dict(user_id=7, username='signer', company_id=1, role='LEGAL'))
        self.assertEqual(registered['certificate_status'], 'PENDING_KEY')
        book.record_operation(operation(kind='SIGN', signature='c2ln', public_key_pem=KEY, credential_fingerprint='f' * 64, step_id=9))
        certificate = SignatureCertificate.objects.get(user_id=7)
        self.assertEqual((certificate.status, certificate.public_key, certificate.serial_number), ('ACTIVE', KEY, registered['serial_number']))
        signature = DigitalSignature.objects.get()
        self.assertEqual((signature.certificate_id, signature.tx_hash, signature.verified), (certificate.pk, 'b' * 64, True))

    def test_a_revoked_key_revokes_the_certificate(self):
        book.register_user(dict(user_id=8, username='u', company_id=1, role='LEGAL'))
        book.record_credential(dict(user_id=8, status='REVOKED', public_key_pem=KEY))
        self.assertTrue(SignatureCertificate.objects.get(user_id=8).revoked)

    def test_a_verification_is_kept_with_its_result(self):
        book.record_operation(operation())
        book.record_verification(dict(version_id=10, user_id=7, company_id=1, result=False, reason='upload mismatch'))
        self.assertEqual(VerificationHistory.objects.get().verify_result, False)
        self.assertEqual(BlockchainAudit.objects.filter(action='LEDGER_VERIFIED').get().status, 'MISMATCH')


class BookEndpointTests(TestCase):
    @patch.dict(os.environ, {'LEDGER_BOOK_TOKEN': 'book-token'})
    def test_registration_answers_with_the_certificate(self):
        response = Client().post('/book/users/', json.dumps(dict(user_id=9, username='u', company_id=1, role='LEGAL')),
                                 content_type='application/json', HTTP_X_LEDGER_BOOK_TOKEN='book-token')
        self.assertEqual((response.status_code, response.json()['status'], response.json()['certificate_status']), (200, 'success', 'PENDING_KEY'))

    @patch.dict(os.environ, {'LEDGER_BOOK_TOKEN': 'book-token'})
    def test_the_book_takes_only_the_service_token(self):
        client = Client()
        body = json.dumps(operation())
        self.assertEqual(client.post('/book/operations/', body, content_type='application/json').status_code, 401)
        response = client.post('/book/operations/', body, content_type='application/json', HTTP_X_LEDGER_BOOK_TOKEN='book-token')
        self.assertEqual((response.status_code, response.json()['recorded']), (200, True))
