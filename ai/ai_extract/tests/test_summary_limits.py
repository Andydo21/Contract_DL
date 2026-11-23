"""Limits around the summary endpoints (size, force, per-minute budget), the export that never re-runs, the summary
worker hand-off and the cached fingerprints of the contract list."""
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from ai.ai_extract.models import ContractSummary
from ai.ai_extract.repositories import ContractSummaryRepository
from ai.ai_extract.services import summary_service
from ai.ai_extract.tests import test_summary_lab as lab
from ai.ai_extract.tests.test_summary_lab import POST, SUMMARY, reply
from contract.contracts.models import ContractContext


@override_settings(ROOT_URLCONF='contract.contracts.tests.integration_urls', MEDIA_URL='media/', AI_SUMMARY_AUTO=False,
                   AI_SUMMARY_WORKER=False, AI_SUMMARY_RATE_PER_MINUTE=0)
class SummaryLimitTests(TestCase):
    add_file = lab.SummaryLabTests.add_file  # the same fixtures, without running SummaryLabTests' own tests again

    def setUp(self):
        lab.SummaryLabTests.setUp(self)
        cache.clear()
        self.addCleanup(cache.clear)

    def summarize(self, **body):
        return self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', json.dumps(body), content_type='application/json')

    @patch(POST)
    def test_only_a_manager_may_force_a_rerun(self, post):
        post.return_value = reply(SUMMARY)
        self.add_file(self.new_version, 'hd.pdf', b'%PDF-1.7 x')
        self.user.role = None
        self.user.save(update_fields=['role'])
        response = self.summarize(force=True)
        self.assertEqual(response.status_code, 403)
        post.assert_not_called()
        self.assertEqual(self.summarize().status_code, 200, 'a first summary without force is open to every reader')

    @patch(POST)
    def test_one_account_has_a_per_minute_budget_of_model_calls(self, post):
        post.return_value = reply(SUMMARY)
        self.add_file(self.new_version, 'hd.pdf', b'%PDF-1.7 x')
        with override_settings(AI_SUMMARY_RATE_PER_MINUTE=2):
            self.assertEqual(self.summarize(force=True).status_code, 200)
            self.assertEqual(self.summarize(force=True).status_code, 200)
            refused = self.summarize(force=True)
            self.assertEqual(refused.status_code, 429)
            self.assertIn('quá nhiều yêu cầu', refused.json()['error'])
            calls = post.call_count
            self.client.force_login(self.manager)  # the budget is per account
            self.assertEqual(self.summarize(force=True).status_code, 200)
        self.assertGreater(post.call_count, calls)

    def test_oversized_input_is_refused_before_any_work(self):
        with override_settings(AI_SUMMARY_MAX_TEXT_CHARS=10, ROOT_URLCONF='config.urls'):
            response = self.client.post('/api/ai/summary/summarize/', json.dumps({'text': 'x' * 11}), content_type='application/json')
            self.assertEqual(response.status_code, 413)
            lab = self.client.post('/api/ai/summary-lab/text/', json.dumps({'text': 'x' * 11}), content_type='application/json')
            self.assertEqual(lab.status_code, 413)

    def test_the_health_check_shows_the_model_address_to_administrators_only(self):
        self.client.logout()
        with override_settings(ROOT_URLCONF='config.urls'), patch('ai.ai_summary.services.llm_service.is_connected', return_value=True):
            self.assertNotIn('llm_url', self.client.get('/api/ai/summary/health/').json())

    @patch(POST)
    def test_exporting_another_view_of_an_outdated_summary_does_not_run_the_model(self, post):
        ContractContext.objects.create(version=self.new_version, context_type='raw_text', content='Điều 1. Văn bản mới')
        ContractSummary.objects.create(version=self.new_version, summary='Bản cũ', source_fingerprint='older text')
        response = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/export/?perspective=employee')
        self.assertEqual(response.status_code, 409)
        post.assert_not_called()
        self.assertEqual(self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/export/').status_code, 200,
                         'the stored default view is still exported as it is')

    def test_with_a_summary_worker_the_web_process_only_queues_the_run(self):
        with override_settings(AI_SUMMARY_WORKER=True), patch.object(summary_service.threading, 'Thread') as thread, \
                self.captureOnCommitCallbacks(execute=True):
            summary_service.schedule_auto_summary(self.new_version, True)
        thread.assert_not_called()
        self.assertEqual(summary_service.get_status(self.new_version.pk)['state'], 'queued')
        from django.utils import timezone
        self.assertIn(self.new_version.pk, ContractSummaryRepository.retryable_version_ids(timezone.now()),
                      'the worker picks up a fresh queued run, not only lost ones')

    def test_the_contract_list_fingerprints_are_cached_until_the_text_changes(self):
        ContractContext.objects.create(version=self.new_version, context_type='raw_text', content='Trang 1')
        with patch.object(ContractSummaryRepository, 'text_fingerprints', wraps=ContractSummaryRepository.text_fingerprints) as hashed:
            first = ContractSummaryRepository.cached_text_fingerprints([self.new_version.pk])
            self.assertEqual(ContractSummaryRepository.cached_text_fingerprints([self.new_version.pk]), first)
            self.assertEqual(hashed.call_count, 1)
            ContractContext.objects.create(version=self.new_version, context_type='raw_text', content='Trang 2')
            self.assertNotEqual(ContractSummaryRepository.cached_text_fingerprints([self.new_version.pk]), first)
            self.assertEqual(hashed.call_count, 2)
