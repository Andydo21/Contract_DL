"""Pushing a contract version into workflow-service, reading its status, and the proxy's forwarding details."""
import json
from contextlib import contextmanager
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from contract.approvals.services.workflow_service import WorkflowService
from contract.contracts.models import (
    Company, Contract, ContractContext, ContractVersion, Role,
)



@contextmanager
def SERVICE():
    """The service module imports requests inside its methods, so patch the library's own functions."""
    with patch('requests.post') as post, patch('requests.get') as get:
        yield Mock(post=post, get=get)

PROXY = 'contract.approvals.views.workflow_proxy.requests.request'


def reply(status=200, body=None):
    response = Mock(status_code=status)
    response.json.return_value = body if body is not None else {}
    response.raise_for_status.side_effect = (
        requests.HTTPError(f'{status} error') if status >= 400 else None)
    return response


@override_settings(WORKFLOW_SERVICE_URL='http://wf:8000', WORKFLOW_SERVICE_TOKEN='tok')
class PushAndStatusTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(company_name='Mine')
        self.other_company = Company.objects.create(company_name='Other')
        manager = Role.objects.create(role_name='MANAGER')
        staff = Role.objects.create(role_name='STAFF')
        User = get_user_model()
        self.manager = User.objects.create_user(username='mgr', company=self.company, role=manager)
        self.staff = User.objects.create_user(username='stf', company=self.company, role=staff)
        self.outsider = User.objects.create_user(username='out', company=self.other_company, role=manager)
        self.contract = Contract.objects.create(contract_code='C1', title='Sale', company=self.company,
                                                contract_type='SALE')
        self.version = ContractVersion.objects.create(contract=self.contract, version_number=1)
        ContractContext.objects.create(version=self.version, context_type='raw_text', source='s', content='Body text')
        self.push_url = f'/api/contracts/{self.contract.id}/workflow/'
        self.status_url = f'/api/contracts/{self.contract.id}/workflow/status/'

    def created(self):
        return reply(201, {'success': True, 'workflow': {'workflow_id': 7, 'workflow_name': 'WF',
                                                         'status': 'PENDING', 'steps': [{'step_order': 1}]}})

    def test_push_creates_workflow_and_returns_its_summary(self):
        self.client.force_login(self.manager)
        with SERVICE() as http:
            http.post.return_value = self.created()
            http.RequestException = requests.RequestException
            response = self.client.post(self.push_url, data='{}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual((body['workflow_id'], body['status']), (7, 'PENDING'))
        sent = http.post.call_args
        self.assertEqual(sent.args[0], 'http://wf:8000/workflows/')
        self.assertEqual(sent.kwargs['json']['version_id'], self.version.id)
        self.assertEqual(sent.kwargs['json']['contract_text'], 'Body text')
        self.assertEqual(sent.kwargs['json']['contract_type'], 'SALE')
        self.assertEqual(sent.kwargs['headers']['X-Workflow-Service-Token'], 'tok')

    def test_push_accepts_version_id_from_json_body(self):
        second = ContractVersion.objects.create(contract=self.contract, version_number=2)
        self.client.force_login(self.manager)
        with SERVICE() as http:
            http.post.return_value = self.created()
            http.RequestException = requests.RequestException
            self.client.post(self.push_url, data=json.dumps({'version_id': self.version.id}),
                             content_type='application/json')
        self.assertEqual(http.post.call_args.kwargs['json']['version_id'], self.version.id)
        self.assertNotEqual(self.version.id, second.id)

    def test_push_conflict_falls_back_to_existing_workflow(self):
        self.client.force_login(self.manager)
        existing = reply(200, {'workflow_id': 3, 'workflow_name': 'Old', 'status': 'IN_PROGRESS', 'steps': []})
        with SERVICE() as http:
            http.post.return_value = reply(409)
            http.get.return_value = existing
            http.RequestException = requests.RequestException
            response = self.client.post(self.push_url, data='{}', content_type='application/json')
        self.assertEqual(response.json()['workflow_id'], 3)
        self.assertEqual(http.get.call_args.args[0], f'http://wf:8000/workflows/{self.version.id}/')

    def test_push_version_of_another_contract_is_rejected(self):
        foreign = ContractVersion.objects.create(
            contract=Contract.objects.create(contract_code='C2', title='Other', company=self.company),
            version_number=1)
        self.client.force_login(self.manager)
        with SERVICE() as http:
            response = self.client.post(f'{self.push_url}?version_id={foreign.id}')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Version not found', response.json()['error'])
        http.post.assert_not_called()

    def test_push_contract_without_version_is_rejected(self):
        empty = Contract.objects.create(contract_code='C3', title='Empty', company=self.company)
        self.client.force_login(self.manager)
        with SERVICE() as http:
            response = self.client.post(f'/api/contracts/{empty.id}/workflow/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('no version', response.json()['error'])
        http.post.assert_not_called()

    def test_push_other_companys_contract_is_forbidden(self):
        self.client.force_login(self.outsider)
        with SERVICE() as http:
            response = self.client.post(self.push_url)
        self.assertEqual(response.status_code, 403)
        http.post.assert_not_called()

    def test_push_unknown_contract_is_not_found(self):
        self.client.force_login(self.manager)
        response = self.client.post('/api/contracts/99999/workflow/')
        self.assertEqual(response.status_code, 404)

    def test_push_requires_manager_role_and_login(self):
        anonymous = self.client.post(self.push_url)
        self.client.force_login(self.staff)
        with SERVICE() as http:
            staff = self.client.post(self.push_url)
        self.assertEqual((anonymous.status_code, staff.status_code), (401, 403))
        http.post.assert_not_called()

    def test_push_rejects_other_methods(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(self.push_url).status_code, 405)

    def test_push_reports_error_when_workflow_service_is_down(self):
        self.client.force_login(self.manager)
        with SERVICE() as http:
            http.RequestException = requests.RequestException
            http.post.side_effect = requests.ConnectionError('refused')
            response = self.client.post(self.push_url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Workflow service error', response.json()['error'])

    def test_push_reports_error_when_workflow_service_returns_500(self):
        self.client.force_login(self.manager)
        with SERVICE() as http:
            http.RequestException = requests.RequestException
            http.post.return_value = reply(500)
            response = self.client.post(self.push_url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Workflow service error', response.json()['error'])

    def test_push_records_audit_log_only_on_success(self):
        from contract.contracts.models import AuditLog
        self.manager.is_superuser = True
        self.manager.save()
        self.client.force_login(self.manager)
        with SERVICE() as http:
            http.RequestException = requests.RequestException
            http.post.side_effect = requests.ConnectionError('x')
            self.client.post(self.push_url)
        self.assertEqual(AuditLog.objects.filter(action='PUSHED_TO_WORKFLOW').count(), 0)
        with SERVICE() as http:
            http.RequestException = requests.RequestException
            http.post.return_value = self.created()
            self.client.post(self.push_url)
        self.assertEqual(AuditLog.objects.filter(action='PUSHED_TO_WORKFLOW').count(), 1)

    def test_status_returns_workflow_of_latest_version(self):
        self.client.force_login(self.staff)
        with SERVICE() as http:
            http.RequestException = requests.RequestException
            http.get.return_value = reply(200, {'workflow_id': 5, 'status': 'APPROVED'})
            response = self.client.get(self.status_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'workflow': {'workflow_id': 5, 'status': 'APPROVED'}})
        self.assertEqual(http.get.call_args.args[0], f'http://wf:8000/workflows/{self.version.id}/')

    def test_status_is_null_when_service_has_no_workflow(self):
        self.client.force_login(self.staff)
        with SERVICE() as http:
            http.RequestException = requests.RequestException
            http.get.return_value = reply(404)
            response = self.client.get(self.status_url)
        self.assertEqual(response.json(), {'workflow': None})

    def test_status_is_null_when_contract_has_no_version(self):
        empty = Contract.objects.create(contract_code='C4', title='Empty', company=self.company)
        self.client.force_login(self.staff)
        with SERVICE() as http:
            response = self.client.get(f'/api/contracts/{empty.id}/workflow/status/')
        self.assertEqual(response.json(), {'workflow': None})
        http.get.assert_not_called()

    def test_status_unknown_version_is_error(self):
        self.client.force_login(self.staff)
        response = self.client.get(f'{self.status_url}?version_id=99999')
        self.assertEqual(response.status_code, 400)

    def test_status_service_down_is_error(self):
        self.client.force_login(self.staff)
        with SERVICE() as http:
            http.RequestException = requests.RequestException
            http.get.side_effect = requests.Timeout('slow')
            response = self.client.get(self.status_url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Workflow service error', response.json()['error'])

    def test_status_access_rules(self):
        anonymous = self.client.get(self.status_url)
        self.client.force_login(self.outsider)
        outsider = self.client.get(self.status_url)
        missing = self.client.get('/api/contracts/99999/workflow/status/')
        self.assertEqual((anonymous.status_code, outsider.status_code, missing.status_code), (401, 403, 404))

    def test_status_rejects_post(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(self.status_url).status_code, 405)

    def test_delete_workflows_counts_removed_and_wraps_failures(self):
        with SERVICE() as http:
            http.RequestException = requests.RequestException
            http.post.return_value = reply(200, {'deleted': 2})
            self.assertEqual(WorkflowService().delete_workflows([1, 2]), 4)
            http.post.side_effect = requests.ConnectionError('x')
            with self.assertRaises(RuntimeError):
                WorkflowService().delete_workflows([1])


@override_settings(WORKFLOW_SERVICE_URL='http://wf:8000/')
class ProxyForwardingTests(TestCase):
    def setUp(self):
        company = Company.objects.create(company_name='T')
        role = Role.objects.create(role_name='STAFF')
        self.user = get_user_model().objects.create_user(username='u', company=company, role=role)
        self.client.force_login(self.user)

    def forward(self, status=200, body=b'{}', headers=None):
        return patch(PROXY, return_value=Mock(content=body, status_code=status,
                                              headers={'Content-Type': 'application/json'} if headers is None else headers))

    def test_method_body_and_query_string_are_forwarded(self):
        with self.forward() as call:
            self.client.post('/workflows/steps/4/reject/?x=1', data='{"a": 1}', content_type='application/json')
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs['method'], 'POST')
        self.assertEqual(kwargs['url'], 'http://wf:8000/workflows/steps/4/reject/?x=1')
        self.assertEqual(kwargs['data'], b'{"a": 1}')
        self.assertFalse(kwargs['allow_redirects'])

    def test_routes_map_to_the_matching_service_paths(self):
        cases = {'/board/a/b': 'board/a/b', '/workflows/detail/3/': 'workflows/detail/3/',
                 '/workflows/steps/2/approve/': 'workflows/steps/2/approve/',
                 '/workflows/9/steps/': 'workflows/9/steps/', '/dependencies/5/delete/': 'dependencies/5/delete/',
                 '/api/admin/keys/': 'keys/', '/api/admin/keys/3/rotate/': 'keys/3/rotate/',
                 '/api/admin/keys/3/revoke/': 'keys/3/revoke/'}
        for path, expected in cases.items():
            with self.subTest(path=path), self.forward() as call:
                self.client.get(path, HTTP_ACCEPT='application/json')
                self.assertEqual(call.call_args.kwargs['url'], f'http://wf:8000/{expected}')

    def test_cookie_and_host_headers_are_dropped_but_custom_headers_kept(self):
        self.client.cookies['sessionid_extra'] = 'secret'
        with self.forward() as call:
            self.client.get('/board/', HTTP_X_CUSTOM='yes')
        headers = call.call_args.kwargs['headers']
        self.assertEqual(headers['X-Custom'], 'yes')
        self.assertNotIn('Cookie', headers)
        self.assertTrue(headers['Authorization'].startswith('Bearer '))

    def test_error_status_and_body_pass_through(self):
        with self.forward(status=409, body=b'{"error": "dup"}'):
            response = self.client.get('/workflows/detail/1/')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.content, b'{"error": "dup"}')
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_content_type_defaults_to_html(self):
        with self.forward(headers={}):
            response = self.client.get('/board/')
        self.assertTrue(response['Content-Type'].startswith('text/html'))

    def test_redirect_location_is_made_relative_to_the_web_domain(self):
        with self.forward(status=302, headers={'Location': 'http://wf:8000/board/x/'}):
            response = self.client.get('/board/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/board/x/')

    def test_timeout_is_reported_as_bad_gateway(self):
        with patch(PROXY, side_effect=requests.Timeout('slow')):
            response = self.client.get('/board/')
        self.assertEqual(response.status_code, 502)

    def test_workflow_board_page_redirects_to_public_url(self):
        with override_settings(WORKFLOW_SERVICE_PUBLIC_URL='http://public:8003/'):
            response = self.client.get('/workflows/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'http://public:8003/board/')
