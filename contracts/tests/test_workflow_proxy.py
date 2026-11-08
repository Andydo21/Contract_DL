"""The workflow proxy requires login and forwards only the signed-in user's own identity."""
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from contracts.models import Company, Role
from shared.jwt_middleware import decode_token


@override_settings(WORKFLOW_SERVICE_URL='http://workflow-service:8000')
class WorkflowProxyTests(TestCase):
    def setUp(self):
        company = Company.objects.create(company_name='Tenant')
        self.role = Role.objects.create(role_name='STAFF')
        self.user = get_user_model().objects.create_user(username='staff', company=company, role=self.role)

    def forward(self):
        reply = Mock(content=b'{}', status_code=200, headers={'Content-Type': 'application/json'})
        return patch('contracts.views.workflow_proxy.requests.request', return_value=reply)

    def test_anonymous_page_goes_to_login_without_reaching_the_service(self):
        with self.forward() as call:
            response = self.client.get('/board/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])
        call.assert_not_called()

    def test_anonymous_api_and_post_are_refused_without_reaching_the_service(self):
        with self.forward() as call:
            posted = self.client.post('/workflows/steps/1/approve/', data='{}', content_type='application/json')
            fetched = self.client.get('/workflows/detail/1/', HTTP_ACCEPT='application/json')
        self.assertEqual((posted.status_code, fetched.status_code), (401, 401))
        call.assert_not_called()

    def test_forged_identity_headers_do_not_reach_the_service(self):
        self.client.force_login(self.user)
        self.client.cookies['jwt_token'] = 'forged'
        with self.forward() as call:
            self.client.get('/board/', HTTP_AUTHORIZATION='Bearer forged')
        options = call.call_args.kwargs
        self.assertNotIn('cookies', options)
        self.assertNotIn('Cookie', options['headers'])
        self.assertNotIn('forged', options['headers']['Authorization'])
        self.assertEqual(options['url'], 'http://workflow-service:8000/board/')

    def test_token_carries_the_real_user_and_expires(self):
        self.client.force_login(self.user)
        with self.forward() as call:
            self.client.get('/board/')
        token = decode_token(call.call_args.kwargs['headers']['Authorization'][7:])
        self.assertEqual((token['user_id'], token['username'], token['role'], token['is_superuser']),
                         (self.user.pk, 'staff', 'STAFF', False))
        self.assertIn('exp', token)

    def test_csrf_stays_enforced_for_every_proxy_route(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.user)
        with self.forward() as call:
            statuses = [client.post(path, data='{}', content_type='application/json').status_code
                        for path in ('/board/', '/workflows/steps/1/approve/')]
        self.assertEqual(statuses, [403, 403])
        call.assert_not_called()

    def test_system_identity_keeps_user_zero(self):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from shared.jwt_middleware import JWTMiddleware, get_system_auth_header
        request = RequestFactory().get('/', HTTP_AUTHORIZATION=get_system_auth_header()['Authorization'])
        JWTMiddleware(lambda _: HttpResponse())(request)
        self.assertEqual(request.jwt_user_id, 0)

    def test_web_sends_the_workflow_service_token_with_the_system_identity(self):
        from contracts.services.workflow_service import _service_headers
        with override_settings(WORKFLOW_SERVICE_TOKEN='shared-token'):
            headers = _service_headers()
        self.assertEqual(headers['X-Workflow-Service-Token'], 'shared-token')
        self.assertEqual(decode_token(headers['Authorization'][7:])['user_id'], 0)

    def test_service_down_reports_without_leaking_details(self):
        self.client.force_login(self.user)
        with patch('contracts.views.workflow_proxy.requests.request', side_effect=requests.ConnectionError('http://secret-host')):
            response = self.client.get('/board/')
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(b'secret-host', response.content)
