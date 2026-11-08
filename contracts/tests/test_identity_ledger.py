"""The blockchain service as the ledger book: users get their certificate from it on registration, and every operation
Fabric confirmed is filed in it (retried by the ledger worker until it is)."""
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from contracts.models import Company, Role
from contracts.services import identity_service, ledger_book_service

BOOK = dict(BLOCKCHAIN_SERVICE_URL='http://blockchain-service:8000', LEDGER_BOOK_TOKEN='book-token')


def answer(code=200, **body):
    return Mock(status_code=code, json=lambda: body)


@override_settings(**BOOK)
class RegistrationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(company_name='Công ty TEST', tax_code='0107777777')
        self.role = Role.objects.create(role_name='MANAGER')

    def register(self):
        return identity_service.register_user(None, 'POST', dict(username='test_manager', email='m@test.vn', password='Pass-12345!',
                                                                 company_id=self.company.pk, role_id=self.role.pk), {})

    def test_a_registered_user_gets_a_certificate_from_the_blockchain_service(self):
        with patch.object(ledger_book_service.requests, 'post',
                          return_value=answer(status='success', serial_number='CG-1-AB', certificate_id=7)) as post:
            result = self.register()
        self.assertEqual(result.status, 200, result.payload)
        self.assertEqual(result.payload['certificate_serial'], 'CG-1-AB')
        url, headers = post.call_args.args[0], post.call_args.kwargs['headers']
        self.assertEqual((url, headers['X-Ledger-Book-Token']), ('http://blockchain-service:8000/book/users/', 'book-token'))

    def test_without_a_certificate_the_user_is_left_in_error_for_a_retry(self):
        with patch.object(ledger_book_service.requests, 'post', return_value=answer(401, error='Service authentication required')):
            result = self.register()
        self.assertEqual(result.status, 502)
        from contracts.models import User
        self.assertEqual(User.objects.get(username='test_manager').status, 'ERROR')


@override_settings(**BOOK)
class BookingTests(TestCase):
    def operation(self, booked=None):
        op = Mock(pk='op-1', kind='ANCHOR', version_id=5, company_id=1, actor_id=2, step_id=0, tx_id='a' * 64, block_number=9,
                  block_hash='b' * 64, signature_base64='', credential_id=None, booked_at=booked,
                  manifest='{"contract_id": 3, "document_hash": "' + 'c' * 64 + '"}')
        op.confirmed_at.isoformat.return_value = '2026-11-08T06:00:00+00:00'
        return op

    def test_confirmed_operations_are_filed_once_and_marked(self):
        op = self.operation()
        with patch.object(ledger_book_service.ledger_data_repository, 'unbooked_operations', return_value=[op]), \
             patch.object(ledger_book_service.ledger_data_repository, 'mark_booked') as mark, \
             patch.object(ledger_book_service.requests, 'post', return_value=answer(status='success', recorded=True)) as post:
            self.assertEqual(ledger_book_service.book_pending(), 1)
        body = __import__('json').loads(post.call_args.kwargs['data'])
        self.assertEqual((body['kind'], body['tx_id'], body['contract_id'], body['document_hash']), ('ANCHOR', 'a' * 64, 3, 'c' * 64))
        mark.assert_called_once()

    def test_an_unreachable_service_leaves_the_operation_for_the_next_round(self):
        import requests
        with patch.object(ledger_book_service.ledger_data_repository, 'unbooked_operations', return_value=[self.operation()]), \
             patch.object(ledger_book_service.ledger_data_repository, 'mark_booked') as mark, \
             patch.object(ledger_book_service.requests, 'post', side_effect=requests.ConnectionError('down')):
            self.assertEqual(ledger_book_service.book_pending(), 0)
        mark.assert_not_called()
