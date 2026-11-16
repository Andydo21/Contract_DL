import datetime
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jwt as pyjwt
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase

from shared import jwt_middleware
from shared.jwt_middleware import (
    ALGORITHM, SECRET_KEY, JWTMiddleware, JWTUserMiddleware, decode_token, extract_bearer,
    fastapi_jwt_required, generate_token, get_auth_header, get_system_auth_header, get_user_auth_header,
)


def make_token(secret=SECRET_KEY, minutes=5, **claims):
    now = datetime.datetime.utcnow()
    payload = {'user_id': 7, 'username': 'alice', 'role': 'MANAGER', 'iat': now,
               'exp': now + datetime.timedelta(minutes=minutes), **claims}
    return pyjwt.encode(payload, secret, algorithm=ALGORITHM)


class TokenHelperTests(SimpleTestCase):
    def test_extract_bearer_accepts_only_a_well_formed_header(self):
        self.assertEqual(extract_bearer('Bearer abc'), 'abc')
        self.assertEqual(extract_bearer('Bearer   abc  '), 'abc')
        for header in ('', None, 'abc', 'bearer abc', 'Basic abc', 'Token Bearer abc'):
            with self.subTest(header=header):
                self.assertIsNone(extract_bearer(header))

    def test_generated_token_round_trips_its_claims(self):
        payload = decode_token(generate_token(3, 'bob', 'STAFF'))
        self.assertEqual((payload['user_id'], payload['username'], payload['role']), (3, 'bob', 'STAFF'))
        self.assertGreater(payload['exp'], payload['iat'])

    def test_generated_token_honours_its_lifetime(self):
        payload = decode_token(generate_token(3, 'bob', 'STAFF', expires_in_hours=2))
        self.assertEqual(payload['exp'] - payload['iat'], 2 * 3600)

    def test_expired_token_is_refused(self):
        with self.assertRaises(pyjwt.ExpiredSignatureError):
            decode_token(make_token(minutes=-5))

    def test_token_signed_with_another_secret_is_refused(self):
        with self.assertRaises(pyjwt.InvalidTokenError):
            decode_token(make_token(secret='some-other-secret-key-of-enough-length'))

    def test_garbage_and_unsigned_tokens_are_refused(self):
        unsigned = pyjwt.encode({'user_id': 1}, None, algorithm='none')
        for token in ('garbage', '', 'a.b.c', unsigned):
            with self.subTest(token=token), self.assertRaises(pyjwt.InvalidTokenError):
                decode_token(token)

    def test_auth_header_carries_a_bearer_token(self):
        header = get_auth_header(1, 'u', 'ADMIN')
        self.assertTrue(header['Authorization'].startswith('Bearer '))
        self.assertEqual(decode_token(header['Authorization'][7:])['role'], 'ADMIN')

    def test_system_header_is_user_zero_admin(self):
        payload = decode_token(get_system_auth_header()['Authorization'][7:])
        self.assertEqual((payload['user_id'], payload['username'], payload['role']), (0, 'system', 'ADMIN'))

    def test_user_header_carries_identity_and_expires_within_minutes(self):
        user = SimpleNamespace(pk=9, username='carol', role=SimpleNamespace(role_name='MANAGER'), company_id=4,
                               is_superuser=True)
        payload = decode_token(get_user_auth_header(user)['Authorization'][7:])
        self.assertEqual((payload['user_id'], payload['company_id'], payload['is_superuser'], payload['role']),
                         (9, 4, True, 'MANAGER'))
        self.assertLessEqual(payload['exp'] - payload['iat'], 300)

    def test_user_header_without_role_defaults_to_user(self):
        user = SimpleNamespace(pk=9, username='carol', role=None, company_id=None, is_superuser=False)
        self.assertEqual(decode_token(get_user_auth_header(user)['Authorization'][7:])['role'], 'USER')


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


class FastApiDependencyTests(SimpleTestCase):
    """fastapi is not installed in the web project, so a stand-in module supplies HTTPException."""

    def setUp(self):
        patcher = patch.dict(sys.modules, {'fastapi': SimpleNamespace(HTTPException=FakeHTTPException)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def status_of(self, header):
        with self.assertRaises(FakeHTTPException) as caught:
            fastapi_jwt_required(header)
        return caught.exception.status_code, caught.exception.detail

    def test_valid_bearer_returns_the_payload(self):
        self.assertEqual(fastapi_jwt_required(f'Bearer {make_token()}')['username'], 'alice')

    def test_missing_or_malformed_header_is_401(self):
        for header in (None, '', 'Token abc'):
            with self.subTest(header=header):
                self.assertEqual(self.status_of(header)[0], 401)

    def test_expired_token_is_401_with_clear_message(self):
        self.assertEqual(self.status_of(f'Bearer {make_token(minutes=-1)}'), (401, 'Token has expired.'))

    def test_invalid_token_is_401(self):
        status, detail = self.status_of('Bearer nonsense')
        self.assertEqual(status, 401)
        self.assertTrue(detail.startswith('Invalid token'))


class MiddlewareTests(SimpleTestCase):
    """The stateless-service path: contract.contracts is reported as not installed."""

    def run_middleware(self, **request_kwargs):
        cookies = request_kwargs.pop('cookies', {})
        request = RequestFactory().get('/', **request_kwargs)
        request.COOKIES.update(cookies)
        seen = {}

        def view(req):
            seen['request'] = req
            return HttpResponse('ok')
        with patch('django.apps.apps.is_installed', return_value=False):
            response = JWTMiddleware(view)(request)
        self.assertEqual(response.status_code, 200)
        return seen['request']

    def test_valid_bearer_token_attaches_identity(self):
        request = self.run_middleware(HTTP_AUTHORIZATION=f'Bearer {make_token(company_id=3, is_superuser=True)}')
        self.assertEqual((request.jwt_user_id, request.jwt_username, request.jwt_role), (7, 'alice', 'MANAGER'))
        self.assertEqual((request.jwt_company_id, request.jwt_is_superuser), (3, True))
        self.assertTrue(request.user.is_authenticated)
        self.assertEqual((request.user.company_id, request.user.role.role_name), (3, 'MANAGER'))

    def test_bearer_header_skips_csrf_but_cookie_token_does_not(self):
        bearer = self.run_middleware(HTTP_AUTHORIZATION=f'Bearer {make_token()}')
        cookie = self.run_middleware(cookies={'jwt_token': make_token()})
        self.assertTrue(bearer._dont_enforce_csrf_checks)
        self.assertFalse(cookie._dont_enforce_csrf_checks)

    def test_token_may_arrive_in_either_cookie(self):
        for name in ('jwt_token', 'access_token'):
            with self.subTest(cookie=name):
                self.assertEqual(self.run_middleware(cookies={name: make_token()}).jwt_user_id, 7)

    def test_header_wins_over_cookie(self):
        request = self.run_middleware(HTTP_AUTHORIZATION=f'Bearer {make_token(user_id=1)}',
                                      cookies={'jwt_token': make_token(user_id=2)})
        self.assertEqual(request.jwt_user_id, 1)

    def test_missing_token_leaves_the_request_anonymous(self):
        request = self.run_middleware()
        self.assertFalse(hasattr(request, 'jwt_user_id'))
        self.assertFalse(hasattr(request, 'user'))

    def test_expired_invalid_and_forged_tokens_do_not_authenticate(self):
        tokens = {'expired': make_token(minutes=-5), 'garbage': 'garbage',
                  'forged': make_token(secret='attacker-controlled-secret-key-123')}
        for label, token in tokens.items():
            with self.subTest(token=label):
                request = self.run_middleware(HTTP_AUTHORIZATION=f'Bearer {token}')
                self.assertFalse(hasattr(request, 'jwt_user_id'))
                self.assertFalse(hasattr(request, 'user'))

    def test_a_bad_bearer_header_does_not_fall_back_to_a_good_cookie_silently(self):
        request = self.run_middleware(HTTP_AUTHORIZATION='Bearer garbage', cookies={'jwt_token': make_token()})
        self.assertFalse(hasattr(request, 'jwt_user_id'))

    def test_system_identity_keeps_user_id_zero(self):
        request = self.run_middleware(HTTP_AUTHORIZATION=get_system_auth_header()['Authorization'])
        self.assertEqual(request.jwt_user_id, 0)

    def test_legacy_id_claim_and_defaults(self):
        token = pyjwt.encode({'id': 11, 'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=1)},
                             SECRET_KEY, algorithm=ALGORITHM)
        request = self.run_middleware(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual((request.jwt_user_id, request.jwt_role, request.jwt_username), (11, 'USER', ''))
        self.assertFalse(request.jwt_is_superuser)

    def test_session_cookie_fallback_builds_a_lightweight_user(self):
        request = RequestFactory().get('/')
        request.COOKIES['sessionid'] = 'abc'
        with patch('django.apps.apps.is_installed', return_value=False), \
                patch('shared.session_repository.session_data', return_value='raw'), \
                patch('django.contrib.sessions.backends.db.SessionStore.decode', return_value={'_auth_user_id': '5'}), \
                patch('shared.session_repository.session_user', return_value=(5, 'dave', 'STAFF', 2, False)):
            JWTMiddleware(lambda req: HttpResponse())(request)
        self.assertEqual((request.jwt_user_id, request.jwt_username, request.jwt_company_id), (5, 'dave', 2))
        self.assertEqual(request.user.role.role_name, 'STAFF')

    def test_session_fallback_errors_leave_the_request_anonymous(self):
        request = RequestFactory().get('/')
        request.COOKIES['sessionid'] = 'abc'
        with patch('django.apps.apps.is_installed', return_value=False), \
                patch('shared.session_repository.session_data', side_effect=RuntimeError('db down')):
            JWTMiddleware(lambda req: HttpResponse())(request)
        self.assertFalse(hasattr(request, 'user'))

    def test_jwt_user_middleware_restores_the_jwt_user(self):
        request = RequestFactory().get('/')
        request._jwt_user = 'jwt-user'
        request.user = 'session-user'
        JWTUserMiddleware(lambda req: HttpResponse())(request)
        self.assertEqual(request.user, 'jwt-user')

    def test_jwt_user_middleware_keeps_user_without_jwt(self):
        request = RequestFactory().get('/')
        request.user = 'session-user'
        JWTUserMiddleware(lambda req: HttpResponse())(request)
        self.assertEqual(request.user, 'session-user')


class MainWebMiddlewareTests(TestCase):
    """With the contracts app installed, the user is the real database user."""

    def test_token_of_a_real_user_attaches_that_user(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username='erin')
        request = RequestFactory().get('/', HTTP_AUTHORIZATION=f'Bearer {make_token(user_id=user.pk)}')
        JWTMiddleware(lambda req: HttpResponse())(request)
        self.assertEqual(request.user, user)
        self.assertEqual(request._jwt_user, user)

    def test_token_of_a_deleted_user_attaches_no_user_but_keeps_identity(self):
        request = RequestFactory().get('/', HTTP_AUTHORIZATION=f'Bearer {make_token(user_id=424242)}')
        JWTMiddleware(lambda req: HttpResponse())(request)
        self.assertFalse(hasattr(request, '_jwt_user'))
        self.assertEqual(request.jwt_user_id, 424242)


class PrivateConfigTests(SimpleTestCase):
    def test_algorithm_is_hmac_sha256(self):
        self.assertEqual(jwt_middleware.ALGORITHM, 'HS256')
