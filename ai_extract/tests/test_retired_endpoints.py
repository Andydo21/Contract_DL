"""The retired standalone document API must stay gone from the main web app."""
from django.test import TestCase


class RetiredDocumentEndpointTests(TestCase):
    def test_retired_document_routes_are_not_served(self):
        for endpoint in ('/api/documents/', '/api/chat/', '/api/documents/1/extract/'):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.post(endpoint).status_code, 404)

    def test_anonymous_root_is_sent_to_login(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/login/'))
