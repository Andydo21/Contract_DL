"""Summaries from the uploaded file (never extraction output), company scoping and pass-through to ai_summary."""
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from ai_extract.models import ContractSummary, LayoutExtractionBlock, LayoutExtractionPage, LayoutExtractionRun
from ai_extract.services import summary_service
from contracts.models import ContractContext, ContractFile
from contracts.services import ContractService
from contracts.services.document_encryption_service import encrypt_pdf
from contracts.tests import test_intelligence as intelligence_tests

SUMMARY = dict(summary='Giá trị hợp đồng: 100.000 đồng', structured={}, facts={}, unverified=[], checklist=None,
               model_id='test-model', cached=False, chunks=1, elapsed_ms=5,
               source=dict(kind='pdf', pages=1, ocr_pages=[], unreadable_pages=[], chars=20, warnings=[]))
PREPARE = dict(chars=10, facts={}, chunk_chars=18000, max_chunks=8, sections=[], chunks=[], cached=False)
READ = dict(source=SUMMARY['source'], text='Điều 1. Giá trị 100.000 đồng', prepare=PREPARE)
POST = 'ai_extract.services.summary_service.requests.post'
INFO = dict(llm_connected=True, analysis_version='v1|m')


def reply(data, status=200):
    response = Mock(ok=status < 400, status_code=status)
    response.json.return_value = data
    return response


class RunAtOnce:
    """threading.Thread stand-in: the automatic summary runs inside the test."""

    def __init__(self, target, args=(), **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@override_settings(ROOT_URLCONF='contracts.tests.integration_urls', AI_SUMMARY_URL='http://summary.test',
                   MEDIA_URL='media/', AI_SUMMARY_AUTO=False)
class SummaryLabTests(TestCase):
    def setUp(self):
        intelligence_tests.ContractIntelligenceTests.setUp(self)
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.media = Path(media.name)
        override = override_settings(MEDIA_ROOT=str(self.media))
        override.enable()
        self.addCleanup(override.disable)

    def add_file(self, version, name, content):
        """Stored the way uploads are: encrypted under MEDIA_ROOT, referenced by its media URL."""
        (self.media / 'contracts').mkdir(exist_ok=True)
        (self.media / 'contracts' / name).write_bytes(encrypt_pdf(content))
        return ContractFile.objects.create(version=version, file_name=name, file_path=f'/media/contracts/{name}')

    def sent_file(self, post, field='file'):
        name, data = post.call_args.kwargs['files'][field]
        return name, data

    @patch(POST)
    def test_contract_view_reads_the_decrypted_upload_not_ocr_output(self, post):
        post.return_value = reply(READ)
        run = LayoutExtractionRun.objects.create(version=self.new_version, status='COMPLETED')
        page = LayoutExtractionPage.objects.create(run=run, page_number=1)
        LayoutExtractionBlock.objects.create(page=page, block_order=0, text='OCR text that must not be used')
        self.add_file(self.new_version, 'hop-dong.pdf', b'%PDF-1.7 original bytes')
        data = self.client.get(f'/api/ai/summary-lab/contracts/{self.contract.pk}/').json()
        self.assertTrue(post.call_args.args[0].endswith('/api/v1/read'))
        self.assertEqual(self.sent_file(post), ('hop-dong.pdf', b'%PDF-1.7 original bytes'))
        self.assertEqual(data['source']['kind'], 'pdf')
        self.assertEqual(data['file']['name'], 'hop-dong.pdf')

    @patch(POST)
    def test_version_without_file_reports_it_without_calling_service(self, post):
        data = self.client.get(f'/api/ai/summary-lab/contracts/{self.contract.pk}/').json()
        self.assertIsNone(data['source'])
        self.assertIn('chưa có text hay file', data['read_error'])
        post.assert_not_called()

    def test_file_outside_media_root_is_refused(self):
        ContractFile.objects.create(version=self.new_version, file_name='x', file_path='/media/../../etc/passwd')
        data = self.client.get(f'/api/ai/summary-lab/contracts/{self.contract.pk}/').json()
        self.assertIn('ngoài kho', data['read_error'])

    def test_other_company_contract_is_not_visible(self):
        self.assertEqual(self.client.get(f'/api/ai/summary-lab/contracts/{self.foreign.pk}/').status_code, 404)

    @patch(POST)
    def test_summarize_sends_file_with_options_and_persists_result(self, post):
        post.return_value = reply(SUMMARY)
        self.add_file(self.new_version, 'hd.docx', b'PK docx bytes')
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/',
                                    json.dumps({'force': True}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(post.call_args.args[0].endswith('/api/v1/summarize-file'))
        self.assertEqual(self.sent_file(post), ('hd.docx', b'PK docx bytes'))
        form = post.call_args.kwargs['data']
        self.assertEqual((form['force'], form['perspective'], form['explain_terms']), ('true', 'general', 'false'))
        self.assertEqual(json.loads(form['contract_metadata'])['contract_code'], 'HD-001')
        saved = ContractSummary.objects.get(version=self.new_version)
        self.assertEqual((saved.summary, saved.model_id), (SUMMARY['summary'], 'test-model'))

    @patch(POST)
    def test_unreadable_file_is_a_client_error_not_a_gateway_error(self, post):
        post.return_value = reply({'detail': 'PDF có mật khẩu; hãy gỡ mật khẩu rồi tải lên lại.'}, status=422)
        self.add_file(self.new_version, 'locked.pdf', b'%PDF')
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 422)
        self.assertIn('mật khẩu', response.json()['error'])

    @patch(POST)
    def test_upload_starts_summary_without_extraction(self, post):
        post.return_value = reply(SUMMARY)
        from contracts.services import ContractService
        upload = SimpleUploadedFile('phu-luc.txt', 'Điều 1. Giá trị 100.000 đồng'.encode())
        with override_settings(AI_SUMMARY_AUTO=True), patch.object(summary_service.threading, 'Thread', RunAtOnce), \
                self.captureOnCommitCallbacks(execute=True):
            version = ContractService().create_new_version(self.contract.pk, file_obj=upload)
        self.assertEqual(self.sent_file(post), ('phu-luc.txt', 'Điều 1. Giá trị 100.000 đồng'.encode()))
        self.assertEqual(ContractSummary.objects.get(version=version).summary, SUMMARY['summary'])
        self.assertEqual(summary_service.get_status(version.pk)['state'], 'done')
        self.assertFalse(LayoutExtractionRun.objects.filter(version=version).exists())

    @patch(POST)
    def test_uploader_can_opt_out_of_the_immediate_summary(self, post):
        upload = SimpleUploadedFile('hd.txt', b'Dieu 1')
        with override_settings(AI_SUMMARY_AUTO=True), patch.object(summary_service.threading, 'Thread', RunAtOnce), \
                self.captureOnCommitCallbacks(execute=True):
            self.client.force_login(self.manager)
            response = self.client.post(f'/api/contracts/{self.contract.pk}/versions/',
                                        {'file': upload, 'change_summary': 'v3', 'summarize': 'false'})
        self.assertEqual(response.status_code, 200)
        post.assert_not_called()
        self.assertIsNone(summary_service.get_status(response.json()['version_id']))

    @patch(POST)
    def test_second_run_for_a_version_in_progress_is_refused_without_calling_the_model(self, post):
        self.add_file(self.new_version, 'hd.txt', b'Dieu 1')
        summary_service.set_status(self.new_version.pk, 'running')
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 409)
        post.assert_not_called()

    @patch(POST)
    def test_viewing_another_perspective_does_not_touch_the_run_status(self, post):
        post.return_value = reply({'detail': 'summary model request failed'}, status=502)
        self.add_file(self.new_version, 'hd.txt', b'Dieu 1')
        ContractSummary.objects.create(version=self.new_version, summary='Stored')
        summary_service.set_status(self.new_version.pk, 'done')
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/',
                                    json.dumps({'perspective': 'hr'}), content_type='application/json')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(summary_service.get_status(self.new_version.pk)['state'], 'done')

    @patch(POST)
    def test_run_left_behind_by_a_dead_process_is_reported_and_can_be_retried(self, post):
        post.return_value = reply(SUMMARY)
        self.add_file(self.new_version, 'hd.txt', b'Dieu 1')
        summary_service.set_status(self.new_version.pk, 'running')
        ContractSummary.objects.filter(version=self.new_version).update(run_status_at=timezone.now() - timedelta(days=1))
        self.assertEqual(summary_service.get_status(self.new_version.pk)['state'], 'failed')
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(summary_service.get_status(self.new_version.pk)['state'], 'done')

    def test_row_holding_only_a_run_state_is_not_presented_as_a_summary(self):
        summary_service.set_status(self.new_version.pk, 'queued')
        self.assertIsNone(self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/').json()['summary'])
        details = ContractService().get_contract_details(self.contract.pk, version_id=self.new_version.pk)
        self.assertIsNone(details['ai_summary'])

    def test_status_change_does_not_move_the_generation_time(self):
        stored = ContractSummary.objects.create(version=self.new_version, summary='Bản chung')
        summary_service.set_status(self.new_version.pk, 'failed', 'x')
        self.assertEqual(ContractSummary.objects.get(pk=stored.pk).updated_at, stored.updated_at)

    @patch(POST)
    def test_structured_result_is_stored_and_returned(self, post):
        post.return_value = reply(dict(SUMMARY, checklist={'items': []}, key_dates=[{'kind': 'end', 'date': '2026-02-28'}]))
        self.add_file(self.new_version, 'hd.txt', b'Dieu 1')
        self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', '{}', content_type='application/json')
        data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/').json()
        self.assertEqual(data['result']['key_dates'][0]['date'], '2026-02-28')
        self.assertEqual(data['result']['source']['kind'], 'pdf')
        self.assertNotIn('summary', data['result'])

    @patch(POST)
    def test_model_outage_keeps_a_preliminary_summary_and_the_worker_finishes_it(self, post):
        def down(url, **kwargs):
            if url.endswith('/api/v1/read'):
                return reply(dict(READ, preliminary='Số tiền: 100.000 đồng', suggest={}))
            return reply({'detail': 'summary model request failed'}, status=502)
        post.side_effect = down
        self.add_file(self.new_version, 'hd.txt', b'Dieu 1')
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', '{}', content_type='application/json')
        self.assertEqual(response.status_code, 502)
        data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/').json()
        self.assertEqual((data['summary'], data['preliminary'], data['status']['state']), (None, 'Số tiền: 100.000 đồng', 'failed'))

        with patch('ai_extract.services.summary_service.model_info', return_value=None):
            self.assertEqual(summary_service.retry_failed_runs(), 0)
        post.side_effect = None
        post.return_value = reply(SUMMARY)
        with patch('ai_extract.services.summary_service.model_info', return_value=INFO):
            self.assertEqual(summary_service.retry_failed_runs(), 1)
            self.assertEqual(summary_service.retry_failed_runs(), 0)
        data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/').json()
        self.assertEqual((data['summary'], data['preliminary']), (SUMMARY['summary'], ''))

    @patch(POST)
    def test_unreadable_file_is_not_retried_by_the_worker(self, post):
        post.return_value = reply({'detail': 'PDF có mật khẩu'}, status=422)
        self.add_file(self.new_version, 'locked.pdf', b'%PDF')
        self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', '{}', content_type='application/json')
        with patch('ai_extract.services.summary_service.model_info', return_value=INFO):
            self.assertEqual(summary_service.retry_failed_runs(), 0)

    @patch(POST)
    def test_changes_compare_with_the_previous_version(self, post):
        post.return_value = reply(dict(changes=[{'field': 'salary'}], summary='• Lương: tăng'))
        self.add_file(self.version, 'v1.txt', b'one')
        self.add_file(self.new_version, 'v2.txt', b'two')
        data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/changes/').json()
        self.assertEqual((data['previous_number'], data['summary']), (1, '• Lương: tăng'))
        self.assertEqual((self.sent_file(post, 'old_file')[1], self.sent_file(post, 'new_file')[1]), (b'one', b'two'))
        first = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/changes/?version_id={self.version.pk}').json()
        self.assertIsNone(first['previous_number'])

    @patch(POST)
    def test_citation_sections_come_from_the_file(self, post):
        post.return_value = reply({'sections': {'Điều 1': 'Giá trị'}})
        self.add_file(self.new_version, 'hd.txt', b'Dieu 1')
        data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/sections/').json()
        self.assertEqual(data['sections']['Điều 1'], 'Giá trị')
        self.assertEqual(self.client.get(f'/api/ai/contracts/{self.foreign.pk}/summary/sections/').status_code, 404)

    def test_export_returns_word_and_respects_scope(self):
        import io
        import docx
        ContractSummary.objects.create(version=self.new_version, summary='Lương: 15.000.000\nNghĩa vụ:\n  • Báo trước 30 ngày')
        response = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/export/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        paragraphs = [p.text for p in docx.Document(io.BytesIO(response.content)).paragraphs]
        self.assertIn('Báo trước 30 ngày', paragraphs)
        self.assertEqual(self.client.get(f'/api/ai/contracts/{self.foreign.pk}/summary/export/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/export/?version_id={self.version.pk}').status_code, 404)

    @patch(POST)
    def test_upload_prefill_returns_suggestions_without_saving(self, post):
        post.return_value = reply(dict(READ, preliminary='', suggest={'title': 'HỢP ĐỒNG'}))
        response = self.client.post('/api/ai/summary-lab/read/', {'file': SimpleUploadedFile('a.pdf', b'%PDF')})
        self.assertEqual(response.json()['suggest']['title'], 'HỢP ĐỒNG')
        self.assertFalse(ContractSummary.objects.exists())

    def add_text(self, version, *pages):
        for number, content in enumerate(pages, start=1):
            ContractContext.objects.create(version=version, context_type='raw_text', source=f'plan-a:page:{number}', content=content)

    @patch(POST)
    def test_text_in_the_database_is_the_source_even_when_a_file_exists(self, post):
        post.return_value = reply(SUMMARY)
        self.add_file(self.new_version, 'hd.pdf', b'%PDF-1.7 file bytes')
        ContractContext.objects.create(version=self.new_version, context_type='advice', source='AI', content='Không phải hợp đồng')
        self.add_text(self.new_version, 'Trang 1', '  ', 'Trang 2')
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', '{}', content_type='application/json')
        self.assertEqual(response.json()['origin'], 'database')
        self.assertEqual(self.sent_file(post)[1], 'Trang 1\n\nTrang 2'.encode())
        data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/').json()
        self.assertTrue(data['has_text'])
        self.assertEqual(data['result']['origin'], 'database')

    @patch(POST)
    def test_file_is_only_the_fallback_when_no_text_is_stored(self, post):
        post.return_value = reply(SUMMARY)
        self.add_file(self.new_version, 'hd.pdf', b'%PDF-1.7 file bytes')
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', '{}', content_type='application/json')
        self.assertEqual(response.json()['origin'], 'file')
        self.assertEqual(self.sent_file(post)[1], b'%PDF-1.7 file bytes')

    @patch(POST)
    def test_worker_summarizes_text_that_reached_the_database(self, post):
        post.return_value = reply(SUMMARY)
        self.add_text(self.new_version, 'Trang 1', '   ', '', 'Trang 2')
        self.add_text(self.version, '')
        with override_settings(AI_SUMMARY_AUTO=True), patch('ai_extract.services.summary_service.model_info', return_value=INFO):
            self.assertEqual(summary_service.retry_failed_runs(), 1)
            self.assertEqual(summary_service.retry_failed_runs(), 0)
        self.assertEqual(ContractSummary.objects.get(version=self.new_version).summary, SUMMARY['summary'])
        self.assertFalse(ContractSummary.objects.filter(version=self.version).exists())

    @patch(POST)
    def test_worker_leaves_text_alone_when_automatic_summaries_are_off_or_refused(self, post):
        self.add_text(self.new_version, 'Trang 1')
        with override_settings(AI_SUMMARY_AUTO=False), patch('ai_extract.services.summary_service.model_info', return_value=INFO):
            self.assertEqual(summary_service.retry_failed_runs(), 0)
        summary_service.set_status(self.new_version.pk, 'failed', 'file problem')
        with override_settings(AI_SUMMARY_AUTO=True), patch('ai_extract.services.summary_service.model_info', return_value=INFO):
            self.assertEqual(summary_service.retry_failed_runs(), 0)
        post.assert_not_called()

    @patch(POST)
    def test_worker_redoes_a_summary_when_its_text_changes_and_panel_sees_it_as_stale(self, post):
        post.return_value = reply(SUMMARY)
        self.add_text(self.new_version, 'Lương 15.000.000')
        with override_settings(AI_SUMMARY_AUTO=True), patch('ai_extract.services.summary_service.model_info', return_value=INFO):
            self.assertEqual(summary_service.retry_failed_runs(), 1)
            self.assertEqual(summary_service.retry_failed_runs(), 0)
            ContractContext.objects.filter(version=self.new_version).update(content='Lương 18.000.000')  # same length
            data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/').json()
            self.assertTrue(data['stale'])
            post.return_value = reply(dict(SUMMARY, summary='Bản mới'))
            self.assertEqual(summary_service.retry_failed_runs(), 1)
        data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/').json()
        self.assertEqual((data['summary'], data['stale']), ('Bản mới', False))
        self.assertEqual(self.sent_file(post)[1], 'Lương 18.000.000'.encode())

    @patch(POST)
    def test_changing_the_model_or_prompt_redoes_stored_summaries(self, post):
        post.return_value = reply(dict(SUMMARY, analysis_version='v1|m'))
        self.add_text(self.new_version, 'Trang 1')
        with override_settings(AI_SUMMARY_AUTO=True):
            with patch('ai_extract.services.summary_service.model_info', return_value=INFO):
                self.assertEqual(summary_service.retry_failed_runs(), 1)
                self.assertEqual(summary_service.retry_failed_runs(), 0)
            with patch('ai_extract.services.summary_service.model_info', return_value=dict(INFO, analysis_version='v2|m')):
                self.assertEqual(summary_service.retry_failed_runs(), 1)

    @patch(POST)
    def test_text_refused_once_is_tried_again_only_after_it_changes(self, post):
        post.return_value = reply({'detail': 'Không đọc được'}, status=422)
        self.add_text(self.new_version, 'Trang 1')
        with override_settings(AI_SUMMARY_AUTO=True), patch('ai_extract.services.summary_service.model_info', return_value=INFO):
            self.assertEqual(summary_service.retry_failed_runs(), 0)
            calls = post.call_count
            self.assertEqual(summary_service.retry_failed_runs(), 0)
            self.assertEqual(post.call_count, calls)
            ContractContext.objects.filter(version=self.new_version).update(content='Trang 1 đã sửa')
            post.return_value = reply(SUMMARY)
            self.assertEqual(summary_service.retry_failed_runs(), 1)

    @patch(POST)
    def test_failed_rerun_keeps_the_details_of_the_summary_on_screen(self, post):
        post.return_value = reply(dict(SUMMARY, key_dates=[{'kind': 'end', 'date': '2026-02-28'}]))
        self.add_text(self.new_version, 'Trang 1')
        self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', '{}', content_type='application/json')
        post.side_effect = lambda url, **kw: reply(dict(READ, preliminary='p', suggest={})) if url.endswith('/read') else reply({'detail': 'down'}, status=502)
        self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/', '{"force": true}', content_type='application/json')
        data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/').json()
        self.assertEqual(data['result']['key_dates'][0]['date'], '2026-02-28')
        self.assertEqual(data['status']['state'], 'failed')

    def test_text_waits_until_it_stops_changing(self):
        now = [0]
        settle = summary_service.SettleTracker(60, clock=lambda: now[0])
        self.assertEqual(settle.ready({1: 'a', 2: 'x'}), [])
        now[0] = 40
        self.assertEqual(settle.ready({1: 'ab', 2: 'x'}), [])  # page 2 of version 1 arrived
        now[0] = 70
        self.assertEqual(settle.ready({1: 'ab', 2: 'x'}), [2])
        now[0] = 100
        self.assertEqual(sorted(settle.ready({1: 'ab', 2: 'x'})), [1, 2])

    @patch(POST)
    def test_worker_order_is_newest_first(self, post):
        post.return_value = reply(SUMMARY)
        self.add_text(self.version, 'Một')
        self.add_text(self.new_version, 'Hai')
        with override_settings(AI_SUMMARY_AUTO=True), patch('ai_extract.services.summary_service.model_info', return_value=INFO):
            self.assertEqual(summary_service.retry_failed_runs(), 2)
        self.assertEqual([c.kwargs['files']['file'][1] for c in post.call_args_list], ['Hai'.encode(), 'Một'.encode()])

    def test_overview_reports_states_gaps_and_what_expires_scoped_to_company(self):
        soon = (timezone.localdate() + timedelta(days=10)).isoformat()
        ContractSummary.objects.create(version=self.new_version, summary='Có', source_fingerprint='x', run_status='done', result=dict(
            key_dates=[dict(kind='end', date=soon)], checklist=dict(items=[dict(status='found'), dict(status='missing'), dict(status='partial')])))
        ContractSummary.objects.create(version=self.foreign_version, summary='Khác', result=dict(key_dates=[dict(kind='end', date=soon)]))
        data = self.client.get('/api/ai/summaries/overview/').json()
        item = data['contracts'][str(self.contract.pk)]
        self.assertEqual((item['state'], item['gaps'], item['days_left'], item['has_summary']), ('done', 2, 10, True))
        self.assertEqual([e['code'] for e in data['expiring']], ['HD-001'])
        self.assertNotIn(str(self.foreign.pk), data['contracts'])
        self.add_text(self.new_version, 'Text đổi')
        self.assertEqual(self.client.get('/api/ai/summaries/overview/').json()['contracts'][str(self.contract.pk)]['state'], 'stale')

    @patch(POST)
    def test_changes_can_compare_any_two_versions_oldest_first(self, post):
        post.return_value = reply(dict(changes=[], summary='x'))
        self.add_file(self.version, 'v1.txt', b'one')
        self.add_file(self.new_version, 'v2.txt', b'two')
        url = f'/api/ai/contracts/{self.contract.pk}/summary/changes/?version_id={self.version.pk}&against={self.new_version.pk}'
        self.assertEqual(self.client.get(url).json()['previous_number'], 2)
        self.assertEqual(self.sent_file(post, 'old_file')[1], b'one')

    def test_vietnamese_file_name_is_shown_decoded(self):
        ContractFile.objects.create(version=self.version, file_name='h%E1%BB%A3p%20%C4%91%E1%BB%93ng.pdf', file_path='/media/contracts/x.pdf')
        data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/?version_id={self.version.pk}').json()
        self.assertEqual(data['file_name'], 'hợp đồng.pdf')

    def test_duplicate_contract_code_gets_a_readable_message(self):
        self.client.force_login(self.manager)
        response = self.client.post('/api/contracts/', {'contract_code': 'HD-001', 'title': 'Trùng', 'raw_content': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('đã tồn tại', response.json()['error'])

    @patch(POST)
    def test_only_the_default_rendering_is_stored(self, post):
        post.return_value = reply(dict(SUMMARY, summary='Góc nhìn người lao động'))
        self.add_file(self.new_version, 'hd.txt', b'Dieu 1')
        ContractSummary.objects.create(version=self.new_version, summary='Bản chung')
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/',
                                    json.dumps({'perspective': 'employee'}), content_type='application/json')
        self.assertFalse(response.json()['saved'])
        self.assertEqual(ContractSummary.objects.get(version=self.new_version).summary, 'Bản chung')

    @patch(POST)
    def test_forced_rerun_in_another_view_also_refreshes_the_stored_default(self, post):
        post.side_effect = lambda url, files, data, **kw: reply(dict(SUMMARY, summary=f"view {data['perspective']}"))
        self.add_file(self.new_version, 'hd.txt', b'Dieu 1')
        response = self.client.post(f'/api/ai/contracts/{self.contract.pk}/summarize/',
                                    json.dumps({'perspective': 'hr', 'force': True}), content_type='application/json')
        self.assertEqual(response.json()['summary'], 'view hr')
        self.assertEqual(ContractSummary.objects.get(version=self.new_version).summary, 'view general')
        self.assertEqual([c.kwargs['data']['force'] for c in post.call_args_list], ['true', 'false'])

    def test_summary_endpoint_reports_state_when_nothing_is_stored_yet(self):
        self.add_file(self.version, 'v1.pdf', b'%PDF')
        summary_service.set_status(self.version.pk, 'running')
        data = self.client.get(f'/api/ai/contracts/{self.contract.pk}/summary/?version_id={self.version.pk}').json()
        self.assertEqual((data['summary'], data['status']['state'], data['file_name'], data['version_number']),
                         (None, 'running', 'v1.pdf', 1))

    @patch(POST, side_effect=__import__('requests').ConnectionError('down'))
    def test_failed_automatic_summary_never_breaks_the_upload(self, post):
        from contracts.services import ContractService
        upload = SimpleUploadedFile('hd.txt', b'Dieu 1')
        with override_settings(AI_SUMMARY_AUTO=True), patch.object(summary_service.threading, 'Thread', RunAtOnce), \
                self.captureOnCommitCallbacks(execute=True):
            version = ContractService().create_new_version(self.contract.pk, file_obj=upload)
        self.assertTrue(version.files.exists())
        status = summary_service.get_status(version.pk)
        self.assertEqual(status['state'], 'failed')
        self.assertIn('không phản hồi', status['error'])

    @patch(POST)
    def test_lab_file_upload_is_summarized_without_persisting(self, post):
        post.return_value = reply(SUMMARY)
        upload = SimpleUploadedFile('thu.pdf', b'%PDF-1.7 lab')
        response = self.client.post('/api/ai/summary-lab/file/', {'file': upload, 'length': 'short', 'force': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sent_file(post), ('thu.pdf', b'%PDF-1.7 lab'))
        self.assertEqual((post.call_args.kwargs['data']['length'], post.call_args.kwargs['data']['force']), ('short', 'true'))
        self.assertFalse(ContractSummary.objects.exists())

    @patch(POST)
    def test_pasted_text_is_summarized_without_persisting(self, post):
        post.return_value = reply(SUMMARY)
        response = self.client.post('/api/ai/summary-lab/text/', json.dumps({'text': 'Điều 1. Giá trị'}),
                                    content_type='application/json')
        self.assertEqual(response.json()['summary'], SUMMARY['summary'])
        self.assertFalse(ContractSummary.objects.exists())

    @patch(POST)
    def test_service_error_detail_is_returned(self, post):
        post.return_value = reply({'detail': 'summary model request failed'}, status=502)
        response = self.client.post('/api/ai/summary-lab/text/', json.dumps({'text': 'x'}), content_type='application/json')
        self.assertEqual(response.status_code, 502)
        self.assertIn('summary model request failed', response.json()['error'])

    @patch(POST)
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

    @patch(POST)
    def test_compare_sends_both_versions_files(self, post):
        post.return_value = reply(dict(changes=[], summary='Không phát hiện thay đổi nội dung chính.'))
        self.add_file(self.version, 'v1.txt', 'Lương 10.000.000 đồng'.encode())
        self.add_file(self.new_version, 'v2.txt', 'Lương 12.000.000 đồng'.encode())
        response = self.client.post('/api/ai/summary-lab/compare/', json.dumps(dict(
            contract_id=self.contract.pk, old_version_id=self.version.pk, new_version_id=self.new_version.pk)),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(post.call_args.args[0].endswith('/api/v1/compare-files'))
        self.assertEqual(self.sent_file(post, 'old_file')[1], 'Lương 10.000.000 đồng'.encode())
        self.assertEqual(self.sent_file(post, 'new_file')[1], 'Lương 12.000.000 đồng'.encode())

    @patch(POST)
    def test_compare_rejects_other_company_versions(self, post):
        response = self.client.post('/api/ai/summary-lab/compare/', json.dumps(dict(
            contract_id=self.foreign.pk, old_version_id=self.foreign_version.pk, new_version_id=self.foreign_version.pk)),
            content_type='application/json')
        self.assertEqual(response.status_code, 404)
        post.assert_not_called()

    @patch('ai_extract.services.summary_service.requests.get', side_effect=__import__('requests').ConnectionError('down'))
    def test_health_reports_unreachable_service(self, get):
        data = self.client.get('/api/ai/summary-lab/health/').json()
        self.assertEqual(data['status'], 'unreachable')
        self.assertFalse(data['llm_connected'])

    def test_page_lists_only_visible_contracts(self):
        page = self.client.get('/ai-extract/summary-lab/')
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'HD-001')
        self.assertNotContains(page, 'HD-002')
