from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings


class DemoAutoLoginTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_superuser(username='admin', password='unused-password')

    @override_settings(DEMO_AUTO_LOGIN=False)
    def test_anonymous_visitor_is_rejected_by_default(self):
        self.assertEqual(Client().get('/api/ledger/operations/').status_code, 401)

    @override_settings(DEMO_AUTO_LOGIN=True)
    def test_anonymous_visitor_becomes_demo_user_only_when_enabled(self):
        self.assertEqual(Client().get('/api/ledger/operations/').status_code, 200)
