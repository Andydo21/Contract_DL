"""The contract summary runs as a background job, as the risk analysis does."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from ai.ai_extract.services import bulk_service, extraction_service


class SummaryJobTests(SimpleTestCase):
    def setUp(self):
        self.user = SimpleNamespace(pk=7, is_superuser=False)
        self.contract = SimpleNamespace(pk=11)
        self.version = SimpleNamespace(pk=21)

    def test_summarize_queues_a_summary_job_for_the_chosen_version(self):
        with patch.object(extraction_service, 'select_version', return_value=(self.contract, self.version)), \
                patch.object(extraction_service.extraction_repository, 'clauses_for_version', return_value=['clause']), \
                patch.object(bulk_service, 'start', return_value=dict(id='a' * 32, status='waiting')) as start:
            result = extraction_service.summarize(self.user, 11, dict(version_id=21))
        start.assert_called_once_with(self.user, [11], 'summary', options={'version_id': 21})
        self.assertEqual(result, dict(success=True, contract_id=11, version_id=21, job_id='a' * 32, job_status='waiting'))

    def test_summarize_without_clauses_is_refused_before_queueing(self):
        with patch.object(extraction_service, 'select_version', return_value=(self.contract, self.version)), \
                patch.object(extraction_service.extraction_repository, 'clauses_for_version', return_value=[]), \
                patch.object(bulk_service, 'start') as start:
            with self.assertRaises(extraction_service.ExtractionError) as raised:
                extraction_service.summarize(self.user, 11, {})
        self.assertEqual(raised.exception.status, 409)
        start.assert_not_called()

    def test_summary_mode_is_open_to_users_who_may_read_the_contract(self):
        # Like a risk analysis, a summary only reads the document: no document-manager role is needed.
        contract = SimpleNamespace(pk=11, title='HĐ', latest_version=self.version)
        with patch('ai.legal_ai.services.case_rules.can_review', return_value=False), \
                patch('ai.ai_extract.repositories.layout_repository.contract_for', return_value=contract), \
                patch.object(bulk_service, 'write_job'), patch.object(bulk_service, 'active_job', return_value=None), \
                patch.object(bulk_service, 'read_job', side_effect=lambda job_id: dict(id=job_id, status='waiting')):
            job = bulk_service.start(self.user, [11], 'summary', options={'version_id': 21})
        self.assertEqual(job['status'], 'waiting')

    def test_the_background_job_summarizes_the_chosen_version(self):
        version = SimpleNamespace(pk=21)
        contract = SimpleNamespace(pk=11, latest_version=SimpleNamespace(pk=22))
        job = dict(id='b' * 32, mode='summary', user_id=7, status='queued', options={'version_id': 21},
                   items=[dict(contract_id=11, status='waiting', run_id=None, error=None)])
        with patch.object(bulk_service, 'read_job', return_value=job), patch.object(bulk_service, 'write_job'), \
                patch.object(bulk_service, 'active_job'), patch.object(bulk_service, '_cancelled', return_value=False), \
                patch.object(bulk_service, '_clean_deleted', return_value=False), \
                patch('ai.ai_extract.repositories.layout_repository.contracts_by_ids', return_value={11: contract}), \
                patch('ai.ai_extract.repositories.layout_repository.contract_exists', return_value=True), \
                patch('ai.ai_extract.repositories.layout_repository.latest_run', return_value=None), \
                patch('ai.ai_extract.repositories.layout_repository.user_by_id', return_value=self.user), \
                patch.object(extraction_service, 'select_version', return_value=(contract, version)) as select, \
                patch.object(extraction_service.SummarizeService, 'summarize_version') as summarize:
            result = bulk_service.run_job('b' * 32)
        select.assert_called_once_with(self.user, 11, 21)
        summarize.assert_called_once_with(version)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['items'][0]['status'], 'complete')
