import json
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings, Client
from ai.analysis.tests.test_intelligence import ContractIntelligenceTests
from contract.contracts.models import Contract, ContractVersion, KnowledgeSearchLog
from ai.ai_extract.models import Clause, LayoutExtractionRun, LayoutExtractionPage, LayoutExtractionBlock


class EnterpriseKnowledgeTests(TestCase):
    setUp = ContractIntelligenceTests.setUp
    search = ContractIntelligenceTests.search

    def discovery(self, **data):
        return self.client.post('/api/newidea/search/', json.dumps({'query': 'payment', **data}), content_type='application/json')

    def test_search_receipt_contains_answer_and_source_hash(self):
        body = self.search().json()
        log = KnowledgeSearchLog.objects.get(pk=body['search_id'])
        self.assertEqual(log.status, 'COMPLETED')
        self.assertEqual(log.version, self.new_version)
        self.assertEqual(log.result['answer'], body['answer'])
        self.assertEqual(len(log.result['sources'][0]['sha256']), 64)

    def test_quota_checked_before_model_or_retrieval(self):
        KnowledgeSearchLog.objects.bulk_create([KnowledgeSearchLog(user=self.user, query='test') for _ in range(30)])
        with patch('ai.legal_ai.services.contract_search_service.retrieve_hybrid') as retrieval:
            response = self.search()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '60')
        retrieval.assert_not_called()

    def test_searches_left_running_by_a_killed_process_stop_counting_after_30_minutes(self):
        from datetime import timedelta
        from django.utils import timezone
        from ai.legal_ai.services.search_job_service import reserve_search
        stale = KnowledgeSearchLog.objects.bulk_create([KnowledgeSearchLog(user=self.user, query='killed', generated=True, status='RUNNING')
                                                        for _ in range(3)])
        self.assertIsNone(reserve_search(self.user, 'question', generated=True, scope='knowledge'))
        KnowledgeSearchLog.objects.filter(pk__in=[s.pk for s in stale]).update(created_at=timezone.now()-timedelta(minutes=31))
        self.assertIsNotNone(reserve_search(self.user, 'question', generated=True, scope='knowledge'))

    def test_long_question_rejected_before_retrieval(self):
        with patch('ai.legal_ai.services.contract_search_service.retrieve_hybrid') as retrieval:
            self.assertEqual(self.search(query='x'*2001).status_code, 400)
        retrieval.assert_not_called()

    def test_company_discovery_finds_other_contract_and_only_latest_version(self):
        contract = Contract.objects.create(company=self.company, contract_code='SECOND', title='Another agreement')
        old = ContractVersion.objects.create(contract=contract, version_number=1)
        new = ContractVersion.objects.create(contract=contract, version_number=2)
        Clause.objects.create(version=old, clause_title='Payment', clause_content='Payment 123 days')
        Clause.objects.create(version=new, clause_title='Payment', clause_content='Payment 77 days')
        Clause.objects.create(version=self.foreign_version, clause_title='Payment', clause_content='Payment SECRET999')
        body = self.discovery().json()
        text = ' '.join(r['text'] for r in body['results'])
        self.assertIn('77 days', text)
        self.assertIn('60 days', text)
        self.assertNotIn('123 days', text)
        self.assertNotIn('30 days', text)
        self.assertNotIn('SECRET999', text)

    @override_settings(A3_HYBRID_ENABLED=True)
    def test_dense_discovery_ignores_forged_payloads_and_finds_synonym(self):
        run = LayoutExtractionRun.objects.create(version=self.new_version, status='COMPLETED', dense_index_status='COMPLETED', colpali_index_status='COMPLETED')
        page = LayoutExtractionPage.objects.create(run=run, page_number=1)
        block = LayoutExtractionBlock.objects.create(page=page, block_order=1, text='Article 1. Payment\nPay within 60 days.')
        payload = dict(source_app='contract_dl', company_id=self.company.pk, contract_id=self.contract.pk,
            version_id=self.new_version.pk, contract_dl_run_id=run.pk, chunk_id=block.pk, page_number=1)
        point = SimpleNamespace(payload=payload, score=.9)
        foreign = SimpleNamespace(payload=dict(payload, company_id=self.other.pk), score=1)
        with patch('ai.legal_ai.services.knowledge_search_service.SearchBackend.dense_knowledge', return_value=[foreign, point]) as dense, \
             patch('ai.legal_ai.services.knowledge_search_service.SearchBackend.dense', return_value=[point]), \
             patch('ai.legal_ai.services.knowledge_search_service.SearchBackend.colpali', return_value=[]), \
             patch('ai.legal_ai.services.knowledge_search_service.SearchBackend.rerank', side_effect=lambda q, c: c):
            body = self.discovery(query='settle invoices').json()
        self.assertEqual({v.pk for v in dense.call_args.args[1]}, {self.new_version.pk})
        self.assertEqual(dense.call_args.args[2], {self.new_version.pk: run.pk})
        self.assertTrue(body['results'])
        self.assertTrue(all(r['version_id'] == self.new_version.pk for r in body['results']))

    def test_global_search_requires_csrf_and_auth(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post('/api/newidea/search/', '{}', content_type='application/json').status_code, 403)
        self.client.logout()
        self.assertEqual(self.discovery().status_code, 401)

    def test_evidence_picker_is_scoped(self):
        self.assertEqual(self.client.get(f'/api/newidea/versions/{self.foreign_version.pk}/sources/').status_code, 404)
        body = self.client.get(f'/api/newidea/versions/{self.version.pk}/sources/').json()
        self.assertEqual(body['sources'][0]['chunk_id'], self.fields['source_reference'])

    def test_queued_search_runs_once_and_preserves_receipt(self):
        from ai.analysis.management.commands.knowledge_worker import process_one
        with patch('ai.ai_extract.services.contract_pipeline_service.request_qwen', side_effect=lambda task, payload:
                   {'supported': True, 'reason': 'Fixture evidence supports payment term'} if task == 'verify_answer'
                   else {'answer': 'Payment within 60 days [E1]'}) as model:
            response = self.client.post('/api/newidea/jobs/', json.dumps(dict(query='payment', version_id=self.new_version.pk)), content_type='application/json')
            self.assertEqual(response.status_code, 202)
            model.assert_not_called()
            pk = response.json()['search_id']
            self.assertEqual(KnowledgeSearchLog.objects.get(pk=pk).status, 'QUEUED')
            self.assertTrue(process_one())
            self.assertFalse(process_one())
        self.assertEqual(KnowledgeSearchLog.objects.count(), 1)
        body = self.client.get(f'/api/newidea/jobs/?id={pk}').json()
        self.assertEqual(body['status'], 'COMPLETED')
        self.assertEqual(body['result']['response']['generation_status'], 'generated')
        self.assertIn('sha256', body['result']['sources'][0])
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f'/api/newidea/jobs/?id={pk}').status_code, 404)

    def test_failed_worker_does_not_leave_running_job(self):
        from ai.analysis.management.commands.knowledge_worker import process_one
        response = self.client.post('/api/newidea/jobs/', json.dumps(dict(query='payment', version_id=self.new_version.pk)), content_type='application/json')
        with patch('ai.analysis.management.commands.knowledge_worker.search_contract', side_effect=RuntimeError('down')):
            self.assertTrue(process_one())
        log = KnowledgeSearchLog.objects.get(pk=response.json()['search_id'])
        self.assertEqual(log.status, 'FAILED')
        self.assertNotIn('down', log.result['error'])

    def test_worker_rechecks_access_after_company_changes(self):
        from ai.analysis.management.commands.knowledge_worker import process_one
        queued = self.client.post('/api/newidea/jobs/', json.dumps(dict(query='payment', version_id=self.new_version.pk)), content_type='application/json')
        self.user.company = self.other
        self.user.save(update_fields=['company'])
        with patch('ai.ai_extract.services.contract_pipeline_service.request_qwen') as model:
            self.assertTrue(process_one())
        model.assert_not_called()
        self.assertEqual(KnowledgeSearchLog.objects.get(pk=queued.json()['search_id']).status, 'FAILED')

    def test_pending_job_limit_prevents_unbounded_queue(self):
        for _ in range(3):
            response = self.client.post('/api/newidea/jobs/', json.dumps(dict(query='payment', version_id=self.new_version.pk)), content_type='application/json')
            self.assertEqual(response.status_code, 202)
        response = self.client.post('/api/newidea/jobs/', json.dumps(dict(query='payment', version_id=self.new_version.pk)), content_type='application/json')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(KnowledgeSearchLog.objects.filter(status='QUEUED').count(), 3)
