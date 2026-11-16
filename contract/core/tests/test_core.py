"""Shared helpers of contract.core: access policy/decorators, http_results, ServiceResult, encryption,
stored-file paths and the audit-log repository. No network is used."""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from contract.contracts.models import AuditLog, Company, Contract, Role, User
from contract.core.repositories.audit_log_repository import AuditLogRepository
from contract.core.services import access_service, document_encryption_service as enc, stored_file_service as files
from contract.core.services.results import ServiceResult
from contract.core.views import access
from contract.core.views.http_results import request_data, respond, service_errors


def anon():
    return SimpleNamespace(is_authenticated=False)


def ok_view(request, *args, **kwargs):
    return HttpResponse('ok')


class AccessServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(company_name='A', tax_code='111')
        self.other = Company.objects.create(company_name='B', tax_code='222')
        self.contract = Contract.objects.create(contract_code='C1', title='T', company=self.company)

    def user(self, name, role=None, company='own', **kw):
        role_obj = Role.objects.get_or_create(role_name=role)[0] if role else None
        return User.objects.create_user(name, password='x', role=role_obj,
                                        company=self.company if company == 'own' else company, **kw)

    def test_is_manager_true_for_manager_admin_and_case_insensitive(self):
        self.assertTrue(access_service.is_manager(self.user('m', 'MANAGER')))
        self.assertTrue(access_service.is_manager(self.user('a', 'ADMIN')))
        self.assertTrue(access_service.is_manager(self.user('l', 'manager')))

    def test_is_manager_false_for_staff_and_roleless(self):
        self.assertFalse(access_service.is_manager(self.user('s', 'STAFF')))
        self.assertFalse(access_service.is_manager(self.user('n')))

    def test_is_manager_true_for_superuser_without_role(self):
        root = User.objects.create_superuser('root', password='x')
        self.assertTrue(access_service.is_manager(root))

    def test_permission_same_company_only(self):
        self.assertTrue(access_service.check_contract_permission(self.user('u'), self.contract))
        outsider = self.user('o', company=self.other)
        self.assertFalse(access_service.check_contract_permission(outsider, self.contract))

    def test_permission_denied_for_anonymous_none_and_companyless(self):
        self.assertFalse(access_service.check_contract_permission(anon(), self.contract))
        self.assertFalse(access_service.check_contract_permission(None, self.contract))
        self.assertFalse(access_service.check_contract_permission(self.user('c', company=None), self.contract))

    def test_permission_granted_to_superuser_of_any_company(self):
        root = User.objects.create_superuser('root', password='x')
        self.assertTrue(access_service.check_contract_permission(root, self.contract))

    def test_contract_access_error_404_403_and_none(self):
        member = self.user('u')
        missing = access_service.contract_access_error(member, 987654)
        self.assertEqual((missing.status, missing.payload['error']), (404, 'Contract not found.'))
        denied = access_service.contract_access_error(self.user('o', company=self.other), self.contract.id)
        self.assertEqual(denied.status, 403)
        self.assertIsNone(access_service.contract_access_error(member, self.contract.id))


class ManagerDecoratorTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        company = Company.objects.create(company_name='A', tax_code='111')
        self.manager = User.objects.create_user('m', password='x', company=company,
                                                role=Role.objects.create(role_name='MANAGER'))
        self.staff = User.objects.create_user('s', password='x', company=company,
                                              role=Role.objects.create(role_name='STAFF'))

    def call(self, decorator, user):
        request = self.rf.get('/x')
        request.user = user
        return decorator(ok_view)(request)

    def test_manager_required_messages_and_codes(self):
        self.assertEqual(self.call(access.manager_required, anon()).status_code, 401)
        denied = self.call(access.manager_required, self.staff)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(json.loads(denied.content)['error'], 'Permission Denied: Manager role required.')
        self.assertEqual(self.call(access.manager_required, self.manager).content, b'ok')

    def test_api_manager_required_uses_api_messages(self):
        unauth = self.call(access.api_manager_required, anon())
        self.assertEqual(json.loads(unauth.content)['error'], 'Unauthorized. Please log in.')
        denied = self.call(access.api_manager_required, self.staff)
        self.assertEqual(json.loads(denied.content)['error'],
                         'Permission Denied: Only Managers can access this resource.')
        self.assertEqual(self.call(access.api_manager_required, self.manager).status_code, 200)

    def test_api_login_required_allows_any_authenticated_user(self):
        self.assertEqual(self.call(access.api_login_required, anon()).status_code, 401)
        self.assertEqual(self.call(access.api_login_required, self.staff).status_code, 200)

    def test_decorated_view_is_not_called_when_denied(self):
        calls = []

        def view(request):
            calls.append(1)
            return HttpResponse()
        request = self.rf.get('/x')
        request.user = self.staff
        access.manager_required(view)(request)
        self.assertEqual(calls, [])

    def test_get_headers_uses_user_identity_and_role(self):
        request = self.rf.get('/x')
        request.user = self.manager
        with patch('shared.jwt_middleware.get_auth_header', return_value={'Authorization': 'u'}) as auth, \
                patch('shared.jwt_middleware.get_system_auth_header', return_value={'Authorization': 's'}) as system:
            self.assertEqual(access._get_headers(request), {'Authorization': 'u'})
            auth.assert_called_once_with(self.manager.id, 'm', 'MANAGER')
            system.assert_not_called()

    def test_get_headers_falls_back_to_system_token_for_anonymous_or_missing_request(self):
        request = self.rf.get('/x')
        request.user = anon()
        with patch('shared.jwt_middleware.get_system_auth_header', return_value={'Authorization': 's'}):
            self.assertEqual(access._get_headers(request), {'Authorization': 's'})
            self.assertEqual(access._get_headers(), {'Authorization': 's'})


class HttpResultsTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_respond_rejects_non_service_result(self):
        with self.assertRaises(TypeError):
            respond(self.rf.get('/'), {'a': 1})

    def test_respond_json_dict_with_status_and_headers(self):
        result = ServiceResult({'a': 1}, status=201, headers={'X-Test': 'yes'})
        response = respond(self.rf.get('/'), result)
        self.assertEqual((response.status_code, response['X-Test']), (201, 'yes'))
        self.assertEqual(json.loads(response.content), {'a': 1})

    def test_respond_json_list_payload_is_allowed(self):
        response = respond(self.rf.get('/'), ServiceResult([1, 2]))
        self.assertEqual(json.loads(response.content), [1, 2])

    def test_respond_non_json_content_type_returns_raw_body(self):
        response = respond(self.rf.get('/'), ServiceResult('plain', content_type='text/plain', status=202))
        self.assertEqual((response.content, response['Content-Type'], response.status_code),
                         (b'plain', 'text/plain', 202))

    def test_respond_redirect_wins_over_payload(self):
        response = respond(self.rf.get('/'), ServiceResult({}, redirect_to='/somewhere/'))
        self.assertEqual((response.status_code, response['Location']), (302, '/somewhere/'))

    def test_respond_template_is_rendered_with_payload(self):
        with patch('contract.core.views.http_results.render', return_value=HttpResponse('page', status=200)) as render:
            response = respond(self.rf.get('/'), ServiceResult({'k': 1}, template='x.html', status=200))
        render.assert_called_once()
        self.assertEqual(render.call_args.args[1:], ('x.html', {'k': 1}))
        self.assertEqual(response.content, b'page')

    def test_service_result_item_assignment_sets_header(self):
        result = ServiceResult({})
        result['Content-Disposition'] = 'attachment'
        self.assertEqual(result.headers, {'Content-Disposition': 'attachment'})

    def test_service_result_headers_are_not_shared_between_instances(self):
        first, second = ServiceResult({}), ServiceResult({})
        first['A'] = '1'
        self.assertEqual(second.headers, {})

    def test_request_data_parses_json_body(self):
        request = self.rf.post('/', json.dumps({'a': 1}), content_type='application/json')
        self.assertEqual(request_data(request), {'a': 1})

    def test_request_data_empty_body_is_empty_dict(self):
        self.assertEqual(request_data(self.rf.post('/', '', content_type='application/json')), {})

    def test_request_data_reads_form_post(self):
        request = self.rf.post('/', {'a': 'x', 'b': 'y'})
        self.assertEqual(request_data(request), {'a': 'x', 'b': 'y'})

    def test_request_data_rejects_non_object_json(self):
        with self.assertRaises(ValueError):
            request_data(self.rf.post('/', '[1]', content_type='application/json'))

    def test_request_data_malformed_json_raises_value_error(self):
        with self.assertRaises(ValueError):
            request_data(self.rf.post('/', '{oops', content_type='application/json'))

    def test_service_errors_maps_exceptions_to_status_codes(self):
        cases = [(ObjectDoesNotExist(), 404, 'Resource not found.'), (ValueError('bad'), 400, 'bad'),
                 (TypeError('typ'), 400, 'typ'), (KeyError('k'), 400, "'k'")]
        for error, status, message in cases:
            @service_errors
            def view(request, error=error):
                raise error
            response = view(self.rf.get('/'))
            self.assertEqual(response.status_code, status)
            self.assertEqual(json.loads(response.content)['error'], message)

    def test_service_errors_passes_response_and_other_exceptions_through(self):
        @service_errors
        def fine(request):
            return HttpResponse('fine')

        @service_errors
        def boom(request):
            raise RuntimeError('x')
        self.assertEqual(fine(self.rf.get('/')).content, b'fine')
        with self.assertRaises(RuntimeError):
            boom(self.rf.get('/'))

    def test_service_errors_preserves_function_name(self):
        @service_errors
        def my_view(request):
            return HttpResponse()
        self.assertEqual(my_view.__name__, 'my_view')


class EncryptionTests(SimpleTestCase):
    def test_round_trip(self):
        data = b'%PDF-1.4 secret \x00\xff'
        self.assertEqual(enc.decrypt_pdf(enc.encrypt_pdf(data)), data)

    def test_ciphertext_is_not_plaintext_and_uses_random_nonce(self):
        first, second = enc.encrypt_pdf(b'same'), enc.encrypt_pdf(b'same')
        self.assertNotIn(b'same', first)
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 12 + len(b'same') + 16)

    def test_tampered_ciphertext_is_rejected(self):
        blob = bytearray(enc.encrypt_pdf(b'hello world'))
        blob[-1] ^= 1
        with self.assertRaises(Exception):
            enc.decrypt_pdf(bytes(blob))

    def test_too_short_input_raises_value_error(self):
        with self.assertRaises(ValueError):
            enc.decrypt_pdf(b'short')

    def test_wrong_key_cannot_decrypt(self):
        with override_settings(ENCRYPTION_KEY='key-one'):
            blob = enc.encrypt_pdf(b'data')
        with override_settings(ENCRYPTION_KEY='key-two'):
            with self.assertRaises(Exception):
                enc.decrypt_pdf(blob)

    def test_key_is_32_bytes_and_prefers_encryption_key_over_secret_key(self):
        with override_settings(ENCRYPTION_KEY='abc', SECRET_KEY='other'):
            key = enc._get_encryption_key()
        with override_settings(ENCRYPTION_KEY=None, SECRET_KEY='other'):
            fallback = enc._get_encryption_key()
        self.assertEqual(len(key), 32)
        self.assertNotEqual(key, fallback)


MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA, MEDIA_URL='/media/')
class StoredFileTests(SimpleTestCase):
    def store(self, name, data):
        path = Path(MEDIA) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_physical_path_strips_media_url_and_unquotes_name(self):
        result = files.physical_path('/media/contracts/H%E1%BB%A3p_%C4%91%E1%BB%93ng.pdf')
        self.assertEqual(result, (Path(MEDIA) / 'contracts' / 'Hợp_đồng.pdf').resolve())

    def test_physical_path_accepts_storage_relative_name(self):
        self.assertEqual(files.physical_path('contracts/a.pdf'), (Path(MEDIA) / 'contracts' / 'a.pdf').resolve())

    def test_physical_path_blocks_traversal_outside_media_root(self):
        self.assertIsNone(files.physical_path('/media/../secret.txt'))
        self.assertIsNone(files.physical_path('..%2F..%2Fetc%2Fpasswd'))

    def test_physical_path_handles_empty_value(self):
        self.assertEqual(files.physical_path(None), Path(MEDIA).resolve())

    def test_file_name_of_decodes_percent_encoding(self):
        self.assertEqual(files.file_name_of('/media/contracts/H%E1%BB%A3p_%C4%91%E1%BB%93ng.pdf'), 'Hợp_đồng.pdf')
        self.assertEqual(files.file_name_of(None), '')

    def test_read_decrypted_returns_plain_bytes(self):
        self.store('c/ok.bin', enc.encrypt_pdf(b'payload'))
        self.assertEqual(files.read_decrypted('/media/c/ok.bin'), b'payload')

    def test_read_decrypted_none_for_missing_corrupt_or_escaping_file(self):
        self.store('c/bad.bin', b'not encrypted at all, just junk bytes')
        self.assertIsNone(files.read_decrypted('/media/c/missing.bin'))
        self.assertIsNone(files.read_decrypted('/media/c/bad.bin'))
        self.assertIsNone(files.read_decrypted('/media/../outside'))

    def test_document_text_decodes_txt_and_ignores_other_extensions(self):
        self.store('c/note.txt', enc.encrypt_pdf('Điều khoản'.encode()))
        self.store('c/data.bin', enc.encrypt_pdf(b'abc'))
        txt = SimpleNamespace(file_path='/media/c/note.txt', file_name='note.txt')
        other = SimpleNamespace(file_path='/media/c/data.bin', file_name='data.bin')
        self.assertEqual(files.document_text(txt), 'Điều khoản')
        self.assertEqual(files.document_text(other), '')

    def test_document_text_empty_for_missing_inputs(self):
        self.assertEqual(files.document_text(None), '')
        self.assertEqual(files.document_text(SimpleNamespace(file_path='', file_name='')), '')
        self.assertEqual(files.document_text(SimpleNamespace(file_path='/media/none.txt', file_name='none.txt')), '')

    def test_document_text_extracts_pdf_text_layer(self):
        import fitz
        pdf = fitz.open()
        pdf.new_page().insert_text((72, 72), 'Hello contract')
        raw = pdf.tobytes()
        pdf.close()
        self.store('c/doc.pdf', enc.encrypt_pdf(raw))
        text = files.document_text(SimpleNamespace(file_path='/media/c/doc.pdf', file_name='doc.pdf'))
        self.assertIn('Hello contract', text)

    def test_document_text_empty_for_broken_pdf(self):
        self.store('c/broken.pdf', enc.encrypt_pdf(b'%PDF-garbage'))
        self.assertEqual(files.document_text(SimpleNamespace(file_path='/media/c/broken.pdf', file_name='broken.pdf')), '')


class AuditLogRepositoryTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(company_name='A', tax_code='111')
        self.user = User.objects.create_user('u', password='x', company=self.company)
        self.contract = Contract.objects.create(contract_code='C1', title='T', company=self.company)

    def test_log_action_links_contract_target(self):
        log = AuditLogRepository.log_action(self.user, 'VIEW', 'Contract', self.contract.id)
        self.assertEqual((log.user, log.contract, log.action), (self.user, self.contract, 'VIEW'))

    def test_log_action_unknown_contract_still_writes_log_without_contract(self):
        log = AuditLogRepository.log_action(self.user, 'VIEW', 'Contract', 99999)
        self.assertIsNone(log.contract)
        self.assertEqual(AuditLog.objects.count(), 1)

    def test_log_action_unknown_review_or_model_writes_log_without_contract(self):
        self.assertIsNone(AuditLogRepository.log_action(self.user, 'A', 'Review', 99999).contract)
        self.assertIsNone(AuditLogRepository.log_action(self.user, 'B', 'Other', 1).contract)

    def test_record_request_and_contract_by_id(self):
        log = AuditLogRepository.record_request(user=self.user, action='REQ', ip_address='1.1.1.1')
        self.assertEqual(AuditLog.objects.get(pk=log.pk).ip_address, '1.1.1.1')
        self.assertEqual(AuditLogRepository.contract_by_id(self.contract.id), self.contract)
        with self.assertRaises(Contract.DoesNotExist):
            AuditLogRepository.contract_by_id(99999)
