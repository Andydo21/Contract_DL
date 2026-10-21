"""Compatibility checks for the retained standalone document database."""
from django.apps import apps
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase
from .models import DocumentFile


class HistoricalSchemaTests(TestCase):
    def test_original_app_label_table_and_records_remain_readable(self):
        self.assertEqual(apps.get_app_config('documents').name, 'ai_extract.legacy_schema')
        self.assertEqual(DocumentFile._meta.db_table, 'documents_file')
        record = DocumentFile.objects.create(original_name='Historical contract.txt', extension='.txt', file_size=10, file='uploaded_documents/example.txt')
        self.assertEqual(DocumentFile.objects.get(pk=record.pk).original_name, record.original_name)

    def test_original_migration_graph_is_preserved(self):
        loader = MigrationLoader(connection)
        self.assertEqual(loader.graph.leaf_nodes('documents'), [('documents', '0003_documentfile_content_hash_and_more')])


class RetiredDocumentEndpointTests(SimpleTestCase):
    def test_only_main_web_handles_document_processing(self):
        self.assertRedirects(self.client.get('/'), 'http://localhost:8000/ai-extract/', fetch_redirect_response=False)
        for endpoint in ('/api/documents/', '/api/chat/', '/api/documents/1/extract/'):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.post(endpoint).status_code, 404)
