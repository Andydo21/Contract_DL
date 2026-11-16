import json
import unittest
from unittest.mock import patch

from django.test import TestCase, override_settings

from contract.contracts.models import Company, Role, User

LEDGER_REGISTER = 'blockchain.ledger.services.ledger_book_service.register_user'


@override_settings(DEMO_AUTO_LOGIN=False)
class IdentityBase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(company_name='Acme', tax_code='111')
        self.other = Company.objects.create(company_name='Beta', tax_code='222')
        self.role = Role.objects.create(role_name='STAFF')
        self.admin = User.objects.create_superuser(username='root', password='pw12345', email='r@x.com')
        self.member = User.objects.create_user(username='member', password='pw12345', email='m@x.com',
                                               company=self.company, role=self.role)

    def post_json(self, url, payload):
        return self.client.post(url, json.dumps(payload), content_type='application/json')


class RegisterCompanyTests(IdentityBase):
    URL = '/api/identity/companies/register/'

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_register_company_success(self):
        response = self.post_json(self.URL, {'company_name': 'Gamma', 'tax_code': '333'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(Company.objects.get(tax_code='333').status, 'ACTIVE')

    def test_register_company_accepts_form_encoded(self):
        response = self.client.post(self.URL, {'company_name': 'Gamma', 'tax_code': '333'})
        self.assertEqual(response.status_code, 200)

    def test_register_company_duplicate_tax_code_rejected(self):
        response = self.post_json(self.URL, {'company_name': 'New name', 'tax_code': '111'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Company.objects.count(), 2)

    def test_register_company_duplicate_name_rejected(self):
        response = self.post_json(self.URL, {'company_name': 'Acme', 'tax_code': '999'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Company.objects.count(), 2)

    def test_register_company_missing_fields_rejected(self):
        self.assertEqual(self.post_json(self.URL, {'company_name': 'Gamma'}).status_code, 400)
        self.assertEqual(self.post_json(self.URL, {'tax_code': '333'}).status_code, 400)

    def test_register_company_get_returns_405(self):
        self.assertEqual(self.client.get(self.URL).status_code, 405)

    def test_register_company_malformed_json_returns_400(self):
        response = self.client.post(self.URL, '{bad', content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_register_company_anonymous_should_be_rejected(self):
        self.client.logout()
        response = self.post_json(self.URL, {'company_name': 'Gamma', 'tax_code': '333'})
        self.assertIn(response.status_code, (401, 403))


class RegisterUserTests(IdentityBase):
    URL = '/api/identity/users/register/'

    def payload(self, **over):
        data = {'username': 'carol', 'email': 'c@x.com', 'password': 'pw12345',
                'company_id': self.company.id, 'role_id': self.role.id}
        data.update(over)
        return data

    @patch(LEDGER_REGISTER, return_value={'serial_number': 'SN1', 'certificate_status': 'ISSUED'})
    def test_register_user_success_issues_certificate(self, ledger):
        self.client.force_login(self.admin)
        response = self.post_json(self.URL, self.payload())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['certificate_serial'], 'SN1')
        self.assertEqual(body['company_name'], 'Acme')
        user = User.objects.get(username='carol')
        self.assertEqual(user.status, 'ACTIVE')
        self.assertTrue(user.check_password('pw12345'))
        ledger.assert_called_once()

    @patch(LEDGER_REGISTER, return_value={})
    def test_register_user_get_returns_405(self, ledger):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.URL).status_code, 405)

    @patch(LEDGER_REGISTER, return_value={})
    def test_register_user_missing_fields_returns_400(self, ledger):
        self.client.force_login(self.admin)
        response = self.post_json(self.URL, self.payload(password=''))
        self.assertEqual(response.status_code, 400)
        ledger.assert_not_called()

    @patch(LEDGER_REGISTER, return_value={})
    def test_register_user_unknown_role_returns_404(self, ledger):
        self.client.force_login(self.admin)
        response = self.post_json(self.URL, self.payload(role_id=99999))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(User.objects.filter(username='carol').exists())

    @patch(LEDGER_REGISTER, return_value={})
    def test_register_user_unknown_company_returns_404(self, ledger):
        self.client.force_login(self.admin)
        response = self.post_json(self.URL, self.payload(company_id=99999))
        self.assertEqual(response.status_code, 404)

    @patch(LEDGER_REGISTER, return_value={})
    def test_register_user_already_anchored_username_rejected(self, ledger):
        self.member.block_number = 5
        self.member.save()
        self.client.force_login(self.admin)
        response = self.post_json(self.URL, self.payload(username='member'))
        self.assertEqual(response.status_code, 400)
        ledger.assert_not_called()

    @patch(LEDGER_REGISTER, return_value={'serial_number': 'SN2'})
    def test_register_user_existing_unanchored_username_is_updated(self, ledger):
        self.client.force_login(self.admin)
        response = self.post_json(self.URL, self.payload(username='member', company_id=self.other.id))
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.company, self.other)
        self.assertEqual(User.objects.filter(username='member').count(), 1)

    def test_register_user_ledger_failure_returns_502_and_marks_error(self):
        from blockchain.ledger.services.ledger_book_service import LedgerBookError
        self.client.force_login(self.admin)
        with patch(LEDGER_REGISTER, side_effect=LedgerBookError('down')):
            response = self.post_json(self.URL, self.payload())
        self.assertEqual(response.status_code, 502)
        self.assertEqual(User.objects.get(username='carol').status, 'ERROR')

    @patch(LEDGER_REGISTER, return_value={'serial_number': 'SN3'})
    def test_register_user_non_admin_cannot_create_user_for_other_company(self, ledger):
        self.client.force_login(self.member)
        response = self.post_json(self.URL, self.payload(company_id=self.other.id))
        self.assertIn(response.status_code, (401, 403))


class IdentityListTests(IdentityBase):
    def test_companies_list_deduplicates_by_tax_code(self):
        Company.objects.create(company_name='Acme Dup', tax_code='111')
        self.client.force_login(self.admin)
        names = [c['company_name'] for c in self.client.get('/api/identity/companies/').json()]
        self.assertEqual(len(names), 2)
        self.assertIn('Beta', names)

    def test_companies_list_is_sorted_by_name(self):
        self.client.force_login(self.admin)
        names = [c['company_name'] for c in self.client.get('/api/identity/companies/').json()]
        self.assertEqual(names, sorted(names))

    def test_users_list_returns_all_users_with_company_and_role(self):
        self.client.force_login(self.admin)
        rows = {u['username']: u for u in self.client.get('/api/identity/users/').json()}
        self.assertEqual(set(rows), {'root', 'member'})
        self.assertEqual(rows['member']['company_name'], 'Acme')
        self.assertEqual(rows['member']['role_name'], 'STAFF')
        self.assertEqual(rows['root']['company_name'], 'N/A')

    def test_users_list_is_tenant_scoped_for_regular_user(self):
        # A non-superuser sees only the users of their own company.
        User.objects.create_user(username='outsider', password='x', company=self.other)
        self.client.force_login(self.member)
        names = [u['username'] for u in self.client.get('/api/identity/users/').json()]
        self.assertNotIn('outsider', names)
        self.assertIn('member', names)

    def test_roles_list_includes_default_manager_role(self):
        self.client.force_login(self.admin)
        names = [r['role_name'] for r in self.client.get('/api/identity/roles/').json()]
        self.assertIn('MANAGER', names)
        self.assertIn('STAFF', names)

    def test_users_list_anonymous_should_be_rejected(self):
        self.assertIn(self.client.get('/api/identity/users/').status_code, (401, 403))


class IdentityPageTests(IdentityBase):
    def test_identity_page_redirects_anonymous_to_login(self):
        response = self.client.get('/identity/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/login/'))

    def test_identity_page_renders_for_logged_in_user(self):
        self.client.force_login(self.member)
        response = self.client.get('/identity/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/identity_registry.html')
