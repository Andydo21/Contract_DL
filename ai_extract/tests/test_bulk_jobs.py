"""Bulk jobs of the A3 dashboard: documents go in order, each linking only to those already done."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from ai_extract.services import bulk_service


def contract(pk):
    return SimpleNamespace(pk=pk, title=f'Văn bản {pk}', latest_version=SimpleNamespace(pk=pk*10))


class BulkJobTests(SimpleTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        patcher = patch.object(bulk_service, 'job_dir', return_value=Path(self.folder.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.folder.cleanup)

    def job(self, ids, mode='rerun'):
        job = dict(id='a'*32, mode=mode, user_id=1, status='queued', done=0, error=None, pid=None,
                   items=[dict(contract_id=i, title=f'Văn bản {i}', status='waiting', run_id=None, error=None) for i in ids])
        bulk_service.write_job(job)
        return job

    def run_job(self, ids, failing=(), mode='rerun', completed=True):
        calls, relinked = [], []
        def enrich(run, deferred_contract_ids=()):
            if run.pk in failing:
                raise RuntimeError('Neo4j publication unavailable')
            calls.append((run.pk, set(deferred_contract_ids)))
        self.job(ids, mode)
        with patch('ai_extract.repositories.layout_repository.contracts_by_ids', return_value={i: contract(i) for i in ids}), \
                patch('ai_extract.repositories.layout_repository.latest_run',
                      side_effect=lambda version, completed=False: SimpleNamespace(pk=version.pk//10) if completed and completed_runs else None), \
                patch('ai_extract.repositories.layout_repository.run_with_contract', side_effect=lambda pk: SimpleNamespace(pk=pk)), \
                patch('ai_extract.services.layout_service.enrich_entity_graph', side_effect=enrich), \
                patch('ai_extract.services.layout_service.reindex_versions', return_value=[]), \
                patch('ai_extract.services.layout_service.link_other_documents', side_effect=lambda run, progress: relinked.append(run.pk)), \
                patch('ai_extract.services.inference_runtime_service.PipelineProgress'), \
                patch('ai_extract.services.layout_service.LayoutExtractionService') as service:
            completed_runs = completed
            service.return_value.extract_version.side_effect = lambda version: SimpleNamespace(pk=version.pk//10, status='COMPLETED')
            job = bulk_service.run_job('a'*32)
        return job, calls, relinked, service

    def test_each_document_defers_its_links_to_the_ones_after_it(self):
        job, calls, relinked, _ = self.run_job([1, 2, 3])
        self.assertEqual(calls, [(1, {2, 3}), (2, {3}), (3, set())])
        self.assertEqual((job['status'], job['done'], relinked), ('complete', 3, []))
        self.assertEqual([i['status'] for i in bulk_service.read_job('a'*32)['items']], ['complete']*3)

    def test_a_failed_document_is_linked_by_those_that_waited_for_it(self):
        job, calls, relinked, _ = self.run_job([1, 2, 3], failing={2})
        self.assertEqual(calls, [(1, {2, 3}), (3, set())])
        self.assertEqual(relinked, [1])
        self.assertEqual(job['status'], 'partial')
        self.assertIn('Neo4j', job['items'][1]['error'])

    def test_uploaded_documents_are_extracted_in_order(self):
        job, calls, _, service = self.run_job([4, 5], mode='extract', completed=False)
        self.assertEqual(calls, [])
        self.assertEqual([c.args[0].pk for c in service.return_value.extract_version.call_args_list], [40, 50])
        self.assertEqual([i['run_id'] for i in job['items']], [4, 5])

    def test_start_checks_its_input_and_runs_one_job_at_a_time(self):
        user = SimpleNamespace(pk=1, is_superuser=True, role=None)
        with self.assertRaises(ValueError):
            bulk_service.start(user, [], 'rerun')
        with self.assertRaises(ValueError):
            bulk_service.start(user, [1], 'delete')
        running = self.job([1])
        running.update(status='running', pid=None, created_at=1)
        bulk_service.write_job(running)
        found = SimpleNamespace(pk=2, title='Hợp đồng 2', latest_version=SimpleNamespace(pk=20))
        with patch('ai_extract.repositories.layout_repository.contract_for', return_value=found),                 patch.object(bulk_service, 'launch') as launch:
            queued = bulk_service.start(user, [2], 'extract')
        # A second job waits for the one running instead of starting beside it.
        self.assertEqual(queued['status'], 'waiting')
        launch.assert_not_called()
        self.assertTrue(bulk_service.waiting_contract(2))
        self.assertFalse(bulk_service.waiting_contract(3))
        # When the running job ends, the waiting one starts.
        running.update(status='complete')
        bulk_service.write_job(running)
        with patch.object(bulk_service, 'launch', side_effect=lambda job: job) as launch:
            bulk_service.active_job()
        self.assertEqual(launch.call_args.args[0]['id'], queued['id'])

    def test_job_ids_cannot_reach_other_files(self):
        with self.assertRaises(ValueError):
            bulk_service.job_path('../../settings')


class LegalDocumentAdminTests(SimpleTestCase):
    def test_the_admin_action_starts_a_rerun_of_the_selected_laws_in_order(self):
        from django.contrib import admin
        from ai_extract.admin import LegalDocumentAdmin
        from ai_extract.models import LegalDocument
        model_admin = LegalDocumentAdmin(LegalDocument, admin.site)
        queryset = SimpleNamespace(order_by=lambda *a: SimpleNamespace(values_list=lambda *a, **k: [7, 3]))
        messages = []
        with patch.object(bulk_service, 'start', return_value=dict(id='b'*32, items=[{}, {}])) as start, \
                patch.object(model_admin, 'message_user', side_effect=lambda request, text, level: messages.append(text)):
            model_admin.bulk_rerun(SimpleNamespace(user='admin'), queryset)
        start.assert_called_once_with('admin', [7, 3], 'rerun')
        self.assertIn('2 văn bản', messages[0])
