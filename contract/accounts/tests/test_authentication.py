import json
import unittest
from unittest.mock import patch

import jwt
from django.conf import settings
from django.test import TestCase, override_settings

from contract.contracts.models import Company, Role, User

LEDGER_REGISTER = 'blockchain.ledger.services.ledger_book_service.register_user'


@override_settings(DEMO_AUTO_LOGIN=False)
class TokenLoginTests(TestCase):
    def setUp(self):
        self.role = Role.objects.create(role_name='MANAGER')
        self.user = User.objects.create_user(username='alice', password='pw12345', email='a@x.com', role=self.role)

    def _post_json(self, payload):
        return self.client.post('/api/token/', json.dumps(payload), content_type='application/json')

    def test_token_login_success_returns_decodable_jwt(self):
        response = self._post_json({'username': 'alice', 'password': 'pw12345'})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        claims = jwt.decode(body['token'], settings.SECRET_KEY, algorithms=['HS256'])
        self.assertEqual(claims['user_id'], self.user.id)
        self.assertEqual(claims['role'], 'MANAGER')
        self.assertEqual(body['user']['username'], 'alice')

    def test_token_login_accepts_form_encoded_body(self):
        response = self.client.post('/api/token/', {'username': 'alice', 'password': 'pw12345'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.json())

    def test_token_login_user_without_role_gets_default_user_role(self):
        User.objects.create_user(username='norole', password='pw12345')
        response = self._post_json({'username': 'norole', 'password': 'pw12345'})
        self.assertEqual(response.json()['user']['role'], 'USER')

    def test_token_login_wrong_password_returns_401(self):
        response = self._post_json({'username': 'alice', 'password': 'bad'})
        self.assertEqual(response.status_code, 401)

    def test_token_login_unknown_user_returns_401(self):
        self.assertEqual(self._post_json({'username': 'ghost', 'password': 'x'}).status_code, 401)

    def test_token_login_missing_password_returns_400(self):
        self.assertEqual(self._post_json({'username': 'alice'}).status_code, 400)

    def test_token_login_get_method_returns_405(self):
        self.assertEqual(self.client.get('/api/token/').status_code, 405)

    def test_token_login_inactive_user_is_rejected(self):
        self.user.is_active = False
        self.user.save()
        response = self._post_json({'username': 'alice', 'password': 'pw12345'})
        self.assertIn(response.status_code, (400, 401))
        self.assertNotIn('token', response.json())

    @unittest.expectedFailure
    def test_token_login_error_status_user_should_be_rejected(self):
        # BUG: api_obtain_token only checks is_active, never User.status; a user whose
        # certificate failed (status 'ERROR') still receives a JWT.
        self.user.status = 'ERROR'
        self.user.save()
        response = self._post_json({'username': 'alice', 'password': 'pw12345'})
        self.assertNotEqual(response.status_code, 200)


@override_settings(DEMO_AUTO_LOGIN=False)
class WebLoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='bob', password='pw12345')

    def test_login_page_renders_for_anonymous(self):
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')

    def test_login_page_creates_manager_role(self):
        self.client.get('/login/')
        self.assertTrue(Role.objects.filter(role_name='MANAGER').exists())

    def test_login_post_valid_credentials_redirects_and_sets_session(self):
        response = self.client.post('/login/', {'username': 'bob', 'password': 'pw12345', 'next': '/identity/'})
        self.assertRedirects(response, '/identity/', fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.id)

    def test_login_post_defaults_to_root_without_next(self):
        response = self.client.post('/login/', {'username': 'bob', 'password': 'pw12345'})
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_login_post_wrong_password_shows_error_and_no_session(self):
        response = self.client.post('/login/', {'username': 'bob', 'password': 'nope'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['error'])
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_login_page_redirects_already_authenticated_user(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get('/login/'), '/', fetch_redirect_response=False)

    def test_logout_clears_session_and_redirects_to_login(self):
        self.client.force_login(self.user)
        response = self.client.get('/logout/')
        self.assertRedirects(response, '/login/', fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)


@override_settings(DEMO_AUTO_LOGIN=False)
class SignupTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(company_name='Acme', tax_code='111')
        self.role = Role.objects.create(role_name='STAFF')
        self.form = {'username': 'newbie', 'email': 'n@x.com', 'password': 'pw12345',
                     'company_id': self.company.id, 'role_id': self.role.id}

    def test_signup_page_renders_companies_and_roles(self):
        response = self.client.get('/signup/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.company, list(response.context['companies']))
        self.assertIn(self.role, list(response.context['roles']))

    @patch(LEDGER_REGISTER, return_value={'serial_number': 'S1'})
    def test_signup_valid_creates_active_user_and_logs_in(self, ledger):
        response = self.client.post('/signup/', self.form)
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        user = User.objects.get(username='newbie')
        self.assertEqual(user.status, 'ACTIVE')
        self.assertEqual(user.company, self.company)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.id)
        ledger.assert_called_once()

    def test_signup_ledger_failure_marks_user_error(self):
        from blockchain.ledger.services.ledger_book_service import LedgerBookError
        with patch(LEDGER_REGISTER, side_effect=LedgerBookError('down')):
            self.client.post('/signup/', self.form)
        self.assertEqual(User.objects.get(username='newbie').status, 'ERROR')

    @patch(LEDGER_REGISTER, return_value={})
    def test_signup_duplicate_username_is_rejected(self, ledger):
        User.objects.create_user(username='newbie', password='x', email='other@x.com')
        response = self.client.post('/signup/', self.form)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['error'])
        self.assertEqual(User.objects.filter(username='newbie').count(), 1)
        ledger.assert_not_called()

    @patch(LEDGER_REGISTER, return_value={})
    def test_signup_duplicate_email_is_rejected(self, ledger):
        User.objects.create_user(username='someone', password='x', email='n@x.com')
        response = self.client.post('/signup/', self.form)
        self.assertTrue(response.context['error'])
        self.assertFalse(User.objects.filter(username='newbie').exists())

    @patch(LEDGER_REGISTER, return_value={})
    def test_signup_missing_fields_is_rejected(self, ledger):
        del self.form['email']
        response = self.client.post('/signup/', self.form)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['error'])
        self.assertFalse(User.objects.filter(username='newbie').exists())

    @patch(LEDGER_REGISTER, return_value={})
    def test_signup_unknown_company_reports_error(self, ledger):
        self.form['company_id'] = 99999
        response = self.client.post('/signup/', self.form)
        self.assertTrue(response.context['error'])
        self.assertFalse(User.objects.filter(username='newbie').exists())
