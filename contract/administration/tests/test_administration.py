"""Administration endpoints: manager-only stats, user delete/retry and the OCR switch. No network is used."""
import json
import os
import unittest
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.urls import reverse

from contract.administration.services import administration_service as service
from contract.contracts.models import AuditLog, Company, Contract, Role, User


def fake_response(status=200):
    return MagicMock(status_code=status)


class AdminBase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(company_name='Cty A', tax_code='0100000001')
        self.other_company = Company.objects.create(company_name='Cty B', tax_code='0100000002')
        self.manager_role = Role.objects.create(role_name='MANAGER')
        self.admin_role = Role.objects.create(role_name='ADMIN')
        self.staff_role = Role.objects.create(role_name='STAFF')
        self.manager = User.objects.create_user('manager', password='x', company=self.company, role=self.manager_role)
        self.admin = User.objects.create_user('adminrole', password='x', company=self.company, role=self.admin_role)
        self.staff = User.objects.create_user('staff', password='x', company=self.company, role=self.staff_role)
        self.superuser = User.objects.create_superuser('root', password='x')
        self.target = User.objects.create_user('target', password='x', company=self.company, role=self.staff_role)
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)

    def delete_url(self, user_id):
        return reverse('api_admin_delete_user', args=[user_id])

    def retry_url(self, user_id):
        return reverse('api_admin_retry_user', args=[user_id])


class AccessControlTests(AdminBase):
    def test_anonymous_gets_401_on_every_admin_api(self):
        for url in (reverse('api_admin_stats'), reverse('api_admin_toggle_ocr')):
            self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.post(self.delete_url(self.target.id)).status_code, 401)
        self.assertEqual(self.client.post(self.retry_url(self.target.id)).status_code, 401)

    def test_staff_gets_403_on_every_admin_api(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('api_admin_stats')).status_code, 403)
        self.assertEqual(self.client.get(reverse('api_admin_toggle_ocr')).status_code, 403)
        self.assertEqual(self.client.post(self.delete_url(self.target.id)).status_code, 403)
        self.assertEqual(self.client.post(self.retry_url(self.target.id)).status_code, 403)
        self.assertTrue(User.objects.filter(id=self.target.id).exists())

    def test_non_admin_cannot_toggle_ocr(self):
        self.client.force_login(self.staff)
        before = os.environ.get('SKIP_OCR')
        response = self.client.post(reverse('api_admin_toggle_ocr'), json.dumps({'skip_ocr': True}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(os.environ.get('SKIP_OCR'), before)
        self.assertFalse(AuditLog.objects.exists())

    def test_user_without_role_is_not_manager(self):
        norole = User.objects.create_user('norole', password='x', company=self.company)
        self.client.force_login(norole)
        self.assertEqual(self.client.get(reverse('api_admin_stats')).status_code, 403)

    def test_dashboard_page_denied_for_anonymous_and_staff(self):
        url = reverse('admin_dashboard')
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_dashboard_page_renders_for_manager(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse('admin_dashboard')).status_code, 200)


@patch('contract.administration.services.administration_service._req')
class StatsTests(AdminBase):
    def test_stats_payload_shape_for_manager_role(self, req):
        req.get.return_value = fake_response(200)
        self.client.force_login(self.manager)
        response = self.client.get(reverse('api_admin_stats'))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {'stats', 'health', 'logs', 'logs_pagination', 'users', 'skip_ocr'})
        self.assertEqual(body['stats']['total_users'], User.objects.count())
        self.assertEqual(body['stats']['total_companies'], 2)
        self.assertEqual(body['stats']['total_contracts'], 0)

    def test_stats_allowed_for_admin_role_and_superuser(self, req):
        req.get.return_value = fake_response(200)
        for user in (self.admin, self.superuser):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('api_admin_stats')).status_code, 200)

    def test_health_online_when_service_answers_below_500(self, req):
        req.get.return_value = fake_response(404)
        self.client.force_login(self.manager)
        health = self.client.get(reverse('api_admin_stats')).json()['health']
        self.assertEqual(len(health), 4)
        self.assertTrue(all(h['status'] == 'ONLINE' for h in health.values()))
        self.assertIn('Fabric Gateway', health)

    def test_health_offline_on_500_and_on_exception(self, req):
        req.get.side_effect = [fake_response(503), ConnectionError('down'), fake_response(500), fake_response(200)]
        self.client.force_login(self.manager)
        health = list(self.client.get(reverse('api_admin_stats')).json()['health'].values())
        self.assertEqual([h['status'] for h in health], ['OFFLINE', 'OFFLINE', 'OFFLINE', 'ONLINE'])

    def test_health_checks_use_timeout_and_only_mocked_requests(self, req):
        req.get.return_value = fake_response(200)
        self.client.force_login(self.manager)
        self.client.get(reverse('api_admin_stats'))
        self.assertEqual(req.get.call_count, 4)
        for call in req.get.call_args_list:
            self.assertEqual(call.kwargs['timeout'], 2)

    def test_stats_lists_users_with_company_and_role(self, req):
        req.get.return_value = fake_response(200)
        loose = User.objects.create_user('loose', password='x')
        self.client.force_login(self.manager)
        users = {u['username']: u for u in self.client.get(reverse('api_admin_stats')).json()['users']}
        self.assertEqual(users['manager']['company_name'], 'Cty A')
        self.assertEqual(users['manager']['role_name'], 'MANAGER')
        self.assertEqual(users['loose']['company_name'], 'N/A')
        self.assertEqual(users['loose']['role_name'], 'Staff')
        self.assertEqual(loose.id, users['loose']['id'])

    def test_stats_logs_paginate_ten_per_page(self, req):
        req.get.return_value = fake_response(200)
        contract = Contract.objects.create(contract_code='HD-1', title='T', company=self.company)
        for i in range(12):
            AuditLog.objects.create(user=self.manager, contract=contract, action=f'A{i}', ip_address='1.2.3.4')
        self.client.force_login(self.manager)
        page1 = self.client.get(reverse('api_admin_stats')).json()
        page2 = self.client.get(reverse('api_admin_stats'), {'page': 2}).json()
        self.assertEqual(len(page1['logs']), 10)
        self.assertEqual(len(page2['logs']), 2)
        self.assertEqual(page1['logs_pagination'], {'page': 1, 'total_logs': 12, 'limit': 10, 'total_pages': 2})
        self.assertEqual(page1['logs'][0]['contract_code'], 'HD-1')
        self.assertEqual(page1['logs'][0]['user'], 'manager')

    def test_stats_invalid_page_falls_back_to_first(self, req):
        req.get.return_value = fake_response(200)
        self.client.force_login(self.manager)
        body = self.client.get(reverse('api_admin_stats'), {'page': 'abc'}).json()
        self.assertEqual(body['logs_pagination']['page'], 1)
        self.assertEqual(body['logs_pagination']['total_pages'], 1)

    def test_stats_log_without_user_is_reported_as_system(self, req):
        req.get.return_value = fake_response(200)
        AuditLog.objects.create(action='SYS')
        self.client.force_login(self.manager)
        log = self.client.get(reverse('api_admin_stats')).json()['logs'][0]
        self.assertEqual((log['user'], log['ip_address'], log['contract_code']), ('System', 'N/A', None))

    def test_stats_reports_skip_ocr_flag_from_environment(self, req):
        req.get.return_value = fake_response(200)
        self.client.force_login(self.manager)
        with patch.dict(os.environ, {'SKIP_OCR': 'yes'}):
            self.assertTrue(self.client.get(reverse('api_admin_stats')).json()['skip_ocr'])
        with patch.dict(os.environ, {'SKIP_OCR': 'False'}):
            self.assertFalse(self.client.get(reverse('api_admin_stats')).json()['skip_ocr'])


class DeleteUserTests(AdminBase):
    def test_manager_deletes_user_and_row_is_gone(self):
        self.client.force_login(self.manager)
        response = self.client.post(self.delete_url(self.target.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'deleted_id': self.target.id})
        self.assertFalse(User.objects.filter(id=self.target.id).exists())

    def test_cannot_delete_own_account(self):
        self.client.force_login(self.manager)
        response = self.client.post(self.delete_url(self.manager.id))
        self.assertEqual(response.status_code, 400)
        self.assertIn('own account', response.json()['error'])
        self.assertTrue(User.objects.filter(id=self.manager.id).exists())

    def test_delete_unknown_user_returns_404(self):
        self.client.force_login(self.manager)
        response = self.client.post(self.delete_url(999999))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error'], 'User not found')

    def test_delete_keeps_audit_log_with_null_author(self):
        AuditLog.objects.create(user=self.target, action='X')
        self.client.force_login(self.manager)
        self.client.post(self.delete_url(self.target.id))
        self.assertIsNone(AuditLog.objects.get(action='X').user)

    # REAL BUG (tenant isolation): a MANAGER of company A can delete a user of company B, because
    # administration_service.admin_delete_user never compares the target's company with the caller's.
    def test_company_manager_cannot_delete_user_of_another_company(self):
        foreign = User.objects.create_user('foreign', password='x', company=self.other_company, role=self.staff_role)
        self.client.force_login(self.manager)
        response = self.client.post(self.delete_url(foreign.id))
        self.assertIn(response.status_code, (403, 404))
        self.assertTrue(User.objects.filter(id=foreign.id).exists())


class RetryUserTests(AdminBase):
    LEDGER = 'blockchain.ledger.services.ledger_book_service.register_user'

    def setUp(self):
        super().setUp()
        self.target.status = 'ERROR'
        self.target.save()
        self.client.force_login(self.manager)

    def retry(self, body='{}'):
        return self.client.post(self.retry_url(self.target.id), body, content_type='application/json')

    def test_retry_issues_certificate_and_activates_user(self):
        with patch(self.LEDGER, return_value={'serial_number': 'SN-1'}) as issue:
            response = self.retry()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success', 'user_id': self.target.id, 'certificate_serial': 'SN-1'})
        issue.assert_called_once()
        self.target.refresh_from_db()
        self.assertEqual(self.target.status, 'ACTIVE')

    def test_retry_user_without_company_returns_400_and_skips_blockchain(self):
        self.target.company = None
        self.target.save()
        self.client.force_login(self.superuser)  # a company manager would get 404: the user is outside their company
        with patch(self.LEDGER) as issue:
            response = self.retry()
        self.assertEqual(response.status_code, 400)
        issue.assert_not_called()

    def test_retry_user_without_role_returns_400(self):
        self.target.role = None
        self.target.save()
        with patch(self.LEDGER):
            response = self.retry()
        self.assertEqual(response.status_code, 400)
        self.assertIn('missing company or role', response.json()['error'])

    def test_retry_blockchain_failure_returns_502_and_keeps_status(self):
        from blockchain.ledger.services.ledger_book_service import LedgerBookError
        with patch(self.LEDGER, side_effect=LedgerBookError('boom')):
            response = self.retry()
        self.assertEqual(response.status_code, 502)
        self.assertIn('Blockchain service', response.json()['error'])
        self.target.refresh_from_db()
        self.assertEqual(self.target.status, 'ERROR')

    def test_retry_unknown_user_returns_404(self):
        response = self.client.post(self.retry_url(424242), '{}', content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_retry_with_malformed_json_returns_400(self):
        self.assertEqual(self.retry('{bad').status_code, 400)


class ToggleOcrTests(AdminBase):
    def setUp(self):
        super().setUp()
        self.url = reverse('api_admin_toggle_ocr')
        self.client.force_login(self.manager)

    def post(self, body, **extra):
        return self.client.post(self.url, json.dumps(body), content_type='application/json', **extra)

    def test_get_reports_current_flag(self):
        with patch.dict(os.environ, {'SKIP_OCR': 'true'}):
            self.assertEqual(self.client.get(self.url).json(), {'skip_ocr': True})
        with patch.dict(os.environ, {'SKIP_OCR': '0'}):
            self.assertEqual(self.client.get(self.url).json(), {'skip_ocr': False})

    def test_post_true_sets_env_and_writes_audit_log(self):
        response = self.post({'skip_ocr': True}, REMOTE_ADDR='9.9.9.9')
        self.assertEqual(response.json(), {'status': 'success', 'skip_ocr': True})
        self.assertEqual(os.environ['SKIP_OCR'], 'True')
        log = AuditLog.objects.get(action__startswith='Changed system OCR')
        self.assertEqual(log.user, self.manager)
        self.assertEqual(log.ip_address, '9.9.9.9')
        self.assertIn('SKIP_OCR=True', log.action)

    def test_post_false_turns_flag_off(self):
        self.post({'skip_ocr': False})
        self.assertEqual(os.environ['SKIP_OCR'], 'False')
        self.assertTrue(AuditLog.objects.filter(action__contains='SKIP_OCR=False').exists())

    def test_post_without_value_defaults_to_skipping_ocr(self):
        self.assertTrue(self.post({}).json()['skip_ocr'])

    def test_unsupported_method_returns_405(self):
        self.assertEqual(service.admin_toggle_ocr(self.manager, 'PUT', {}, {}).status, 405)

    # REAL BUG: the string "false" is truthy, so posting {"skip_ocr": "false"} sets SKIP_OCR=True.
    # admin_toggle_ocr does not coerce string booleans.
    def test_string_false_does_not_enable_skip_ocr(self):
        self.post({'skip_ocr': 'false'})
        self.assertEqual(os.environ['SKIP_OCR'], 'False')

    def test_non_object_json_returns_400_and_changes_nothing(self):
        response = self.client.post(self.url, '[1,2]', content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AuditLog.objects.exists())
