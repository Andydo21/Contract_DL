"""Summary Lab: OCR source selection, company scoping and pass-through to ai_summary."""
import json
from unittest.mock import Mock, patch
from django.test import TestCase, override_settings
from ai_extract.models import ContractSummary, LayoutExtractionBlock, LayoutExtractionPage, LayoutExtractionRun
from contracts.tests import test_intelligence as intelligence_tests

SUMMARY = dict(summary='Giá trị hợp đồng: 100.000 đồng', structured={}, facts={}, unverified=[],
               model_id='test-model', cached=False, chunks=1, elapsed_ms=5)
PREPARE = dict(chars=10, facts={}, chunk_chars=18000, max_chunks=8, sections=[], chunks=[], cached=False)


def reply(data, status=200):
    response = Mock(ok=status < 400, status_code=status)
    response.json.return_value = data
    return response


@override_settings(ROOT_URLCONF='contracts.tests.integration_urls', AI_SUMMARY_URL='http://summary.test')
class SummaryLabTests(TestCase):
    setUp = intelligence_tests.ContractIntelligenceTests.setUp

    def add_ocr(self, version, pages):
        run = LayoutExtractionRun.objects.create(version=version, status='COMPLETED')
        for number, blocks in pages.items():
            page = LayoutExtractionPage.objects.create(run=run, page_number=number)
            for order, text in enumerate(blocks):
                LayoutExtractionBlock.objects.create(page=page, block_order=order, text=text)
        return run

    @patch('ai_extract.services.extraction_service.requests.post')
    def test_contract_view_uses_ocr_blocks_in_page_order(self, post):
        post.return_value = reply(PREPARE)
        run = self.add_ocr(self.new_version, {2: ['Điều 2. Thanh toán'], 1: ['HỢP ĐỒNG', 'Điều 1. Đối tượng']})
        data = self.client.get(f'/api/ai/summary-lab/contracts/{self.contract.pk}/').json()
        self.assertEqual(data['source']['origin'], 'ocr_blocks')
        self.assertEqual(data['run']['id'], run.pk)
        sent = post.call_args.kwargs['json']['text']
        self.assertEqual(sent, 'HỢP ĐỒNG\n\nĐiều 1. Đối tượng\n\nĐiều 2. Thanh toán')
        self.assertTrue(post.call_args.args[0].endswith('/api/v1/prepare'))

    @patch('ai_extract.services.extraction_service.requests.post')
    def test_contract_without_text_reports_none_without_calling_service(self, post):
        data = self.client.get(f'/api/ai/summary-lab/contracts/{self.contract.pk}/').json()
        self.assertEqual(data['source']['origin'], 'none')
        self.assertIsNone(data['prepare'])
        post.assert_not_called()

    def test_other_company_contract_is_not_visible(self):
        self.assertEqual(self.client.get(f'/api/ai/summary-lab/contracts/{self.foreign.pk}/').status_code, 404)

    @patch('ai_extract.services.extraction_service.requests.post')
    def test_summarize_persists_service_result(self, post):
        post.return_value = reply(SUMMARY)
        self.add_ocr(self.new_version, {1: ['Giá trị 100.000 đồng']})
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', json.dumps({'force': True}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(post.call_args.kwargs['json']['force'])
        saved = ContractSummary.objects.get(version=self.new_version)
        self.assertEqual((saved.summary, saved.model_id), (SUMMARY['summary'], 'test-model'))

    @patch('ai_extract.services.extraction_service.requests.post')
    def test_pasted_text_is_summarized_without_persisting(self, post):
        post.return_value = reply(SUMMARY)
        response = self.client.post('/api/ai/summary-lab/text/', json.dumps({'text': 'Điều 1. Giá trị'}),
                                    content_type='application/json')
        self.assertEqual(response.json()['summary'], SUMMARY['summary'])
        self.assertFalse(ContractSummary.objects.exists())

    @patch('ai_extract.services.extraction_service.requests.post')
    def test_service_error_detail_is_returned(self, post):
        post.return_value = reply({'detail': 'summary model request failed'}, status=502)
        response = self.client.post('/api/ai/summary-lab/text/', json.dumps({'text': 'x'}), content_type='application/json')
        self.assertEqual(response.status_code, 502)
        self.assertIn('summary model request failed', response.json()['error'])

    @patch('ai_extract.services.extraction_service.requests.post')
    def test_display_options_are_forwarded_and_unknown_values_fall_back(self, post):
        post.return_value = reply(SUMMARY)
        self.client.post('/api/ai/summary-lab/text/', json.dumps({'text': 'x', 'perspective': 'employee', 'length': 'short',
                                                                   'explain_terms': True}), content_type='application/json')
        sent = post.call_args.kwargs['json']
        self.assertEqual((sent['perspective'], sent['length'], sent['explain_terms']), ('employee', 'short', True))
        self.client.post('/api/ai/summary-lab/text/', json.dumps({'text': 'x', 'perspective': 'boss', 'length': 'novel'}),
                         content_type='application/json')
        sent = post.call_args.kwargs['json']
        self.assertEqual((sent['perspective'], sent['length'], sent['explain_terms']), ('general', 'detailed', False))

    @patch('ai_extract.services.extraction_service.requests.post')
    def test_compare_sends_both_versions_text(self, post):
        post.return_value = reply(dict(changes=[], summary='Không phát hiện thay đổi nội dung chính.'))
        self.add_ocr(self.version, {1: ['Lương 10.000.000 đồng']})
        self.add_ocr(self.new_version, {1: ['Lương 12.000.000 đồng']})
        response = self.client.post('/api/ai/summary-lab/compare/', json.dumps(dict(
            contract_id=self.contract.pk, old_version_id=self.version.pk, new_version_id=self.new_version.pk)),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(post.call_args.args[0].endswith('/api/v1/compare'))
        sent = post.call_args.kwargs['json']
        self.assertEqual((sent['old_text'], sent['new_text']), ('Lương 10.000.000 đồng', 'Lương 12.000.000 đồng'))

    @patch('ai_extract.services.extraction_service.requests.post')
    def test_compare_rejects_other_company_versions(self, post):
        response = self.client.post('/api/ai/summary-lab/compare/', json.dumps(dict(
            contract_id=self.foreign.pk, old_version_id=self.foreign_version.pk, new_version_id=self.foreign_version.pk)),
            content_type='application/json')
        self.assertEqual(response.status_code, 404)
        post.assert_not_called()

    @patch('ai_extract.services.extraction_service.requests.get', side_effect=__import__('requests').ConnectionError('down'))
    def test_health_reports_unreachable_service(self, get):
        data = self.client.get('/api/ai/summary-lab/health/').json()
        self.assertEqual(data['status'], 'unreachable')
        self.assertFalse(data['llm_connected'])

    def test_page_lists_only_visible_contracts(self):
        page = self.client.get('/ai-extract/summary-lab/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'HD-001')
        self.assertNotContains(page, 'HD-002')
