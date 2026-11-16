"""Operations Fabric can never take are rejected at once instead of being retried, and a revoked key is revoked on
the ledger too (written by the ledger worker until Fabric has it)."""
from unittest.mock import Mock, patch

import requests

from blockchain.ledger.services import ledger_service as ledger
from blockchain.ledger.tests.test_ledger import LedgerTests
from contract.contracts.models import ContractLedgerOperation, ContractSigningCredential

GATEWAY = 'blockchain.ledger.services.ledger_service.gateway'


def http_error(status, error=''):
    response = Mock(status_code=status)
    response.json.return_value = {'error': error}
    return requests.HTTPError(response=response)


class LedgerRejectionTests(LedgerTests):
    def submit(self, *answers):
        op = self.accepted()
        with patch(GATEWAY, side_effect=[http_error(404), *answers]) as gateway:
            ledger.process(ledger.claim())
        op.refresh_from_db()
        return op, gateway

    def test_chaincode_refusal_is_rejected_and_not_retried(self):
        op, _ = self.submit(http_error(422, 'invalid signature for this company and version'))
        self.assertEqual(op.state, 'REJECTED')
        self.assertIn('invalid signature', op.last_error)
        self.assertIsNone(op.tx_id)
        ContractLedgerOperation.objects.filter(pk=op.pk).update(next_attempt_at=op.created_at)
        self.assertIsNone(ledger.claim())

    def test_network_failure_is_still_retried(self):
        op, _ = self.submit(http_error(503, 'peer unavailable'))
        self.assertEqual(op.state, 'FAILED')
        ContractLedgerOperation.objects.filter(pk=op.pk).update(next_attempt_at=op.created_at)
        self.assertIsNotNone(ledger.claim())

    def test_key_revoked_after_signing_is_rejected_without_reaching_fabric(self):
        op = self.accepted()
        ContractSigningCredential.objects.filter(pk=self.key.pk).update(status='REVOKED')
        with patch(GATEWAY, side_effect=[http_error(404)]) as gateway:
            ledger.process(ledger.claim())
        op.refresh_from_db()
        self.assertEqual(op.state, 'REJECTED')
        self.assertEqual(gateway.call_count, 1)  # the lookup only; nothing was committed

    def test_rejected_operation_can_be_retried_by_its_owner(self):
        op, _ = self.submit(http_error(422, 'refused'))
        response = self.post(f'/api/ledger/operations/{op.pk}/', {'action': 'retry'})
        self.assertEqual(response.status_code, 200)
        op.refresh_from_db()
        self.assertEqual((op.state, op.attempts), ('PENDING', 0))

    def test_revocation_is_written_to_the_ledger_once(self):
        self.client.force_login(self.reviewer)
        with patch('blockchain.ledger.services.ledger_book_service.post'):
            self.assertEqual(self.post(f'/api/ledger/credentials/{self.key.pk}/', {'action': 'revoke'}).status_code, 200)
        self.key.refresh_from_db()
        self.assertEqual((self.key.status, self.key.revocation_tx_id), ('REVOKED', ''))
        with patch(GATEWAY, side_effect=requests.ConnectionError('offline')):
            self.assertEqual(ledger.revoke_pending(), 0)  # Fabric down: stays pending
        answer = {'fingerprint': self.key.fingerprint, 'revoked': True, 'tx_id': 'c' * 64}
        with patch(GATEWAY, return_value=answer) as gateway:
            self.assertEqual(ledger.revoke_pending(), 1)
            self.assertEqual(ledger.revoke_pending(), 0)
        gateway.assert_called_once_with('/enterprise/credentials/revoke', {'fingerprint': self.key.fingerprint})
        self.key.refresh_from_db()
        self.assertEqual(self.key.revocation_tx_id, 'c' * 64)

    def test_answer_for_another_key_does_not_mark_the_revocation(self):
        ContractSigningCredential.objects.filter(pk=self.key.pk).update(status='REVOKED')
        with patch(GATEWAY, return_value={'fingerprint': 'f' * 64, 'tx_id': 'c' * 64}):
            self.assertEqual(ledger.revoke_pending(), 0)
        self.key.refresh_from_db()
        self.assertEqual(self.key.revocation_tx_id, '')
