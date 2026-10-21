"""Verify page concurrency and failure isolation without calling real models."""
from contextlib import nullcontext
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from ai_extract.services.contract_pipeline_service import IndexResult
from ai_extract.services.layout_service import PageExtractionSession


@override_settings(MEDIA_ROOT=Path('/test-media'))
class PagePipelineTests(SimpleTestCase):
    def setUp(self):
        index = patch('NewIdea.repositories.contract_repository.refresh_snapshot')
        index.start()
        self.addCleanup(index.stop)


    def run_object(self):
        return SimpleNamespace(pk=7, id=7, version_id=3, version=SimpleNamespace(contract=SimpleNamespace(title='Source', id=2, company_id=1, contract_code='C')),
                               structure={}, total_pages=0, total_blocks=0)

    def test_structure_retains_previous_pages_without_rereading_old_blocks(self):
        observed = []
        def structure(records, title):
            observed.append([dict(record) for record in records])
            return dict(leaves=[], structure_status='native_structure')
        with patch('ai_extract.services.layout_service.transaction.atomic', side_effect=nullcontext), \
             patch('ai_extract.repositories.layout_repository.persist_pages',
                   side_effect=[([dict(chunk_id='block:1', text='Heading', page_number=1)], 1),
                                ([dict(chunk_id='block:2', text='Continued content', page_number=2)], 1)]) as persist, \
             patch('ai_extract.repositories.layout_repository.save_run'), \
             patch('ai_extract.services.document_structure_service.analyze_document_structure', side_effect=structure), \
             patch('ai_extract.services.document_graph_service.infer_relations', return_value={'status': 'disabled'}), \
             patch('ai_extract.services.document_graph_service.sync_graph', return_value={'status': 'ready'}):
            with PageExtractionSession(self.run_object()) as session:
                session._index_visual = lambda number: IndexResult('SKIPPED')
                for number in (1, 2):
                    session.process_page(SimpleNamespace(page_number=number, blocks=[object()]))
        self.assertEqual([[r['chunk_id'] for r in rows] for rows in observed],
                         [['block:1'], ['block:1', 'block:2']])
        self.assertTrue(all(call.kwargs == dict(incremental=True, cumulative=False)
                            for call in persist.call_args_list))

    def test_colpali_overlaps_page_structure_but_dense_waits_for_complete_document(self):
        started, structure_done = Event(), Event()
        def visual(page_number):
            started.set()
            if not structure_done.wait(3):
                raise AssertionError('Structure branch did not overlap ColPali')
            return IndexResult('COMPLETED', 1)
        def structure(*args):
            self.assertTrue(started.wait(3))
            structure_done.set()
            return dict(leaves=[], structure_status='native_structure')
        indexer = Mock()
        indexer.index_dense.return_value = IndexResult('COMPLETED', 4)
        with patch('ai_extract.services.layout_service.transaction.atomic', side_effect=nullcontext), \
             patch('ai_extract.repositories.layout_repository.persist_rendered_page'), \
             patch('ai_extract.repositories.layout_repository.persist_pages', return_value=([], 0)), \
             patch('ai_extract.repositories.layout_repository.save_run'), \
             patch('ai_extract.services.document_structure_service.analyze_document_structure', side_effect=structure), \
             patch('ai_extract.services.document_graph_service.infer_relations', return_value={'status': 'disabled'}), \
             patch('ai_extract.services.document_graph_service.sync_graph', return_value={'status': 'ready'}), \
             patch('ai_extract.services.contract_pipeline_service.PlanACollectionIndexer', return_value=indexer):
            run = self.run_object()
            with PageExtractionSession(run) as session:
                session._index_visual = visual
                for number in (1, 2):
                    started.clear()
                    structure_done.clear()
                    session.start_page_image(number, Path('/test-media') / f'{number}.png', 100, 200)
                    self.assertFalse(started.is_set(), 'ColPali must wait for confirmed Surya figures')
                    with self.assertRaisesRegex(RuntimeError, 'previous page'):
                        session.start_page_image(number + 1, Path('/test-media/other.png'), 100, 200)
                    session.process_page(SimpleNamespace(page_number=number, blocks=[]))
                    self.assertFalse(session.visual_tasks)
                    self.assertEqual(session.page_states[-1]['dense'], 'DEFERRED')
                    self.assertEqual(session.page_states[-1]['colpali'], 'COMPLETED')
                    indexer.index_dense.assert_not_called()
                session.finish()
        indexer.index_dense.assert_called_once_with(run, replace_existing=False)
        self.assertEqual(run.total_pages, 2)
        self.assertEqual((run.dense_points_count, run.colpali_points_count), (4, 2))

    def test_failure_in_one_index_does_not_erase_the_other(self):
        indexer = Mock()
        indexer.index_dense.return_value = IndexResult('FAILED', error='embedding unavailable')
        with patch('ai_extract.services.layout_service.transaction.atomic', side_effect=nullcontext), \
             patch('ai_extract.repositories.layout_repository.persist_pages', return_value=([], 0)), \
             patch('ai_extract.repositories.layout_repository.save_run'), \
             patch('ai_extract.services.document_structure_service.analyze_document_structure',
                   return_value=dict(leaves=[], structure_status='native_structure')), \
             patch('ai_extract.services.document_graph_service.infer_relations', return_value={'status': 'disabled'}), \
             patch('ai_extract.services.document_graph_service.sync_graph', return_value={'status': 'ready'}), \
             patch('ai_extract.services.contract_pipeline_service.PlanACollectionIndexer', return_value=indexer):
            run = self.run_object()
            with PageExtractionSession(run) as session:
                session._index_visual = lambda number: IndexResult('COMPLETED', 1)
                session.process_page(SimpleNamespace(page_number=1, blocks=[]))
                session.finish()
        self.assertEqual(run.dense_index_status, 'FAILED')
        self.assertEqual(run.colpali_index_status, 'COMPLETED')
        self.assertEqual(run.colpali_points_count, 1)

    def test_visual_failure_continues_to_next_page_and_retries_only_at_finish(self):
        calls = []
        def visual(number):
            calls.append(number)
            if calls == [1]:
                return IndexResult('FAILED', error='temporary connection failure')
            return IndexResult('COMPLETED', 1, point_ids=(f'p{number}',))
        indexer = Mock()
        def dense(*args, **kwargs):
            self.assertEqual(calls, [1, 2], 'Text indexing must not wait for the final visual retry')
            return IndexResult('COMPLETED', 4)
        indexer.index_dense.side_effect = dense
        with patch('ai_extract.services.layout_service.transaction.atomic', side_effect=nullcontext), \
             patch('ai_extract.repositories.layout_repository.persist_pages', return_value=([], 0)) as persist, \
             patch('ai_extract.repositories.layout_repository.save_run'), \
             patch('ai_extract.services.document_structure_service.analyze_document_structure',
                   return_value=dict(leaves=[], structure_status='native_structure')) as structure, \
             patch('ai_extract.services.document_graph_service.infer_relations', return_value={'status': 'empty'}), \
             patch('ai_extract.services.document_graph_service.sync_graph', return_value={'status': 'ready'}), \
             patch('ai_extract.services.contract_pipeline_service.PlanACollectionIndexer', return_value=indexer):
            run = self.run_object()
            with PageExtractionSession(run) as session:
                session._index_visual = visual
                session.process_page(SimpleNamespace(page_number=1, blocks=[]))
                self.assertEqual(run.colpali_index_status, 'FAILED')
                session.process_page(SimpleNamespace(page_number=2, blocks=[]))
                self.assertEqual(calls, [1, 2])
                session.finish()
                self.assertEqual(session.page_states[0]['colpali_attempts'], 2)
                self.assertEqual(session.page_states[1]['colpali_attempts'], 1)
                self.assertEqual(session.page_states[0]['colpali_error'], '')
        self.assertEqual(calls, [1, 2, 1])
        self.assertEqual(persist.call_count, 2)
        self.assertEqual(structure.call_count, 2)
        indexer.index_dense.assert_called_once_with(run, replace_existing=False)
        self.assertEqual(run.colpali_index_status, 'COMPLETED')
        self.assertEqual(run.colpali_points_count, 2)
        self.assertEqual(run.colpali_index_error, '')
        self.assertEqual(run.structure['processing']['colpali_missing_pages'], [])

    def test_partial_retry_keeps_old_vectors_without_double_counting_or_looping(self):
        run = self.run_object()
        indexer = Mock()
        indexer.index_dense.return_value = IndexResult('COMPLETED', 2)
        with patch('ai_extract.repositories.layout_repository.save_run'), \
             patch('ai_extract.services.document_graph_service.sync_graph', return_value={'status': 'ready'}), \
             patch('ai_extract.services.contract_pipeline_service.PlanACollectionIndexer', return_value=indexer):
            with PageExtractionSession(run) as session:
                session.records = [dict(page_number=1, text='source')]
                run.structure = dict(leaves=session.records)
                session.page_states = [dict(page_number=1, colpali_attempts=1),
                                       dict(page_number=2, colpali_attempts=1),
                                       dict(page_number=3, colpali_attempts=1)]
                session.colpali_results = {1: IndexResult('COMPLETED', 1, point_ids=('good',)),
                    2: IndexResult('PARTIAL', 2, 'first error', ('a', 'b')),
                    3: IndexResult('SKIPPED')}
                retry = Mock(return_value=IndexResult('PARTIAL', 2, 'still unavailable', ('b', 'c')))
                session._index_visual = retry
                session.finish()
        retry.assert_called_once_with(2)
        self.assertEqual(run.colpali_points_count, 4)  # good + a, b, c
        self.assertEqual(run.colpali_index_status, 'PARTIAL')
        self.assertEqual(run.colpali_index_error, 'still unavailable')
        self.assertEqual(run.structure['processing']['colpali_missing_pages'], [2])
        self.assertEqual(session.page_states[1]['colpali_attempts'], 2)

    def test_all_failed_ocr_still_retries_visuals_without_claiming_ocr_success(self):
        run = self.run_object()
        with patch('ai_extract.repositories.layout_repository.save_run'), \
             patch('ai_extract.services.contract_pipeline_service.PlanACollectionIndexer') as indexer:
            with PageExtractionSession(run) as session:
                session.failed_pages = [dict(page_number=1, stage='surya', error_type='RuntimeError')]
                session.page_states = [dict(page_number=1, structure='FAILED', colpali_attempts=1)]
                session.colpali_results = {1: IndexResult('FAILED', error='temporary network failure')}
                retry = Mock(return_value=IndexResult('COMPLETED', 1, point_ids=('p1',)))
                session._index_visual = retry
                session.finish()
        retry.assert_called_once_with(1)
        indexer.assert_not_called()
        self.assertEqual(run.status, 'FAILED')
        self.assertEqual(run.colpali_index_status, 'COMPLETED')
        self.assertEqual(session.page_states[0]['structure'], 'FAILED')

    def test_health_does_not_wait_for_ocr_lock(self):
        from concurrent.futures import ThreadPoolExecutor
        from PIL import Image
        import base64, io
        from ai_extract.views.inference_views import register_contract_rag
        routes = {}
        app = SimpleNamespace(get=lambda path: lambda fn: routes.setdefault(path, fn),
                              post=lambda path: lambda fn: routes.setdefault(path, fn))
        entered, release = Event(), Event()
        def ocr(*args):
            entered.set()
            if not release.wait(3):
                raise AssertionError('Health blocked behind OCR')
            return {'layout': []}
        buffer = io.BytesIO()
        Image.new('RGB', (2, 2)).save(buffer, 'PNG')
        with patch('ai_extract.services.surya_inference_service.create_surya_predictor', return_value=object()), \
             patch('ai_extract.services.surya_inference_service.surya_page', side_effect=ocr), \
             patch.dict('sys.modules', fastapi=SimpleNamespace(HTTPException=RuntimeError)):
            register_contract_rag(app)
            with ThreadPoolExecutor(max_workers=2) as pool:
                task = pool.submit(routes['/rag/extract_page'],
                    {'image_base64': base64.b64encode(buffer.getvalue()).decode()})
                try:
                    self.assertTrue(entered.wait(2))
                    health = pool.submit(routes['/rag/health']).result(timeout=1)
                    self.assertEqual(health['model_family'], 'contract-a3')
                finally:
                    release.set()
                task.result(timeout=2)

    def test_failed_ocr_is_recorded_and_all_failed_document_is_not_completed(self):
        from concurrent.futures import Future
        run = self.run_object()
        result = Future()
        result.set_result(IndexResult('COMPLETED', 1))
        with patch('ai_extract.repositories.layout_repository.save_run'), \
             patch('ai_extract.services.contract_pipeline_service.PlanACollectionIndexer') as indexer:
            with PageExtractionSession(run) as session:
                session.expected_pages = 1
                session.page_states = [dict(page_number=1)]
                session.visual_tasks[1] = result
                session.fail_page(1, RuntimeError())
                self.assertFalse(session.visual_tasks)
                self.assertEqual(session.page_states[0]['structure'], 'FAILED')
                self.assertEqual(run.colpali_points_count, 1)
                session.finish()
        self.assertEqual(run.status, 'FAILED')
        self.assertEqual(run.structure['processing']['failed_pages'][0]['page_number'], 1)
        indexer.assert_not_called()

    def test_prepared_pdf_visual_branch_does_not_reopen_neon(self):
        run = self.run_object()
        page = SimpleNamespace(id=24, page_number=14, image_path='p14.png')
        visuals = [SimpleNamespace(page=page, block=None, image_path='p14.png')]
        indexer = Mock()
        indexer.index_colpali.return_value = IndexResult('COMPLETED', 1)
        with PageExtractionSession(run) as session, \
             patch('ai_extract.repositories.layout_repository.indexed_run') as read, \
             patch('ai_extract.services.layout_extractor.visual_sources') as sources, \
             patch('ai_extract.services.contract_pipeline_service.PlanACollectionIndexer', return_value=indexer):
            session.visual_inputs[14] = (run, visuals)
            result = session._index_visual(14)
        self.assertEqual(result.status, 'COMPLETED')
        read.assert_not_called()
        sources.assert_not_called()
        indexer.index_colpali.assert_called_once_with(run, page_number=14, visuals=visuals)

    def test_partial_document_indexes_successful_pages_without_claiming_completion(self):
        indexer = Mock()
        indexer.index_dense.return_value = IndexResult('COMPLETED', 2)
        with patch('ai_extract.repositories.layout_repository.save_run'), \
             patch('ai_extract.services.document_graph_service.sync_graph', return_value={'status': 'ready'}), \
             patch('ai_extract.services.contract_pipeline_service.PlanACollectionIndexer', return_value=indexer):
            run = self.run_object()
            with PageExtractionSession(run) as session:
                session.records = [dict(page_number=1, text='good source'), dict(page_number=3, text='other source')]
                session.failed_pages = [dict(page_number=2, stage='surya', error_type='RuntimeError')]
                session.page_knowledge = [{'status': 'empty'}]
                session.colpali_results = {1: IndexResult('COMPLETED', 3)}
                run.structure = dict(leaves=session.records)
                run.total_pages = 2
                session.finish()
        self.assertEqual(run.status, 'FAILED')
        self.assertEqual(run.total_pages, 2)
        self.assertEqual(run.dense_points_count, 2)
        self.assertEqual(run.colpali_points_count, 3)
        self.assertIn('pages: 2.', run.error_message)
        self.assertEqual(run.structure['processing']['failed_pages'][0]['page_number'], 2)


class RenderedPagePersistenceTests(TestCase):
    def test_ocr_fills_rendered_page_without_duplicate_or_changing_old_run(self):
        from contracts.models import Company, Contract, ContractVersion
        from ai_extract.models import LayoutExtractionRun, LayoutExtractionPage, LayoutExtractionBlock
        from ai_extract.repositories.layout_repository import persist_rendered_page, persist_pages
        company = Company.objects.create(company_name='Test', tax_code='PAGE')
        contract = Contract.objects.create(company=company, contract_code='PAGE', title='Test')
        version = ContractVersion.objects.create(contract=contract)
        old_run = LayoutExtractionRun.objects.create(version=version)
        old_page = LayoutExtractionPage.objects.create(run=old_run, page_number=1, extracted_text='Old source')
        run = LayoutExtractionRun.objects.create(version=version)
        rendered = persist_rendered_page(run, 1, 'page.png', 100, 200)
        block = SimpleNamespace(order=1, text='OCR source', layout_type='paragraph', bbox=[0,0,100,100], confidence=1)
        page = SimpleNamespace(page_number=1, width=100, height=200, image_path='page.png', text='OCR source', blocks=[block])
        records, count = persist_pages(run, SimpleNamespace(pages=[page]), incremental=True)
        rendered.refresh_from_db()
        old_page.refresh_from_db()
        self.assertEqual(run.pages.count(), 1)
        self.assertEqual(rendered.extracted_text, 'OCR source')
        self.assertEqual(count, 1)
        self.assertEqual(records[0]['text'], 'OCR source')
        self.assertEqual(old_page.extracted_text, 'Old source')

        # Returning only the new page must not SELECT any existing block rows.
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        second = SimpleNamespace(page_number=2, width=100, height=200, image_path='two.png',
                                 text='Second page', blocks=[block])
        with CaptureQueriesContext(connection) as queries:
            current, count = persist_pages(run, SimpleNamespace(pages=[second]), incremental=True, cumulative=False)
        self.assertEqual(count, 1)
        self.assertEqual([r['page_number'] for r in current], [2])
        self.assertNotEqual(current[0]['chunk_id'], records[0]['chunk_id'])
        self.assertFalse(any('SELECT' in q['sql'].upper() and LayoutExtractionBlock._meta.db_table in q['sql']
                             for q in queries))


class ProgressLogTests(SimpleTestCase):
    def test_slow_step_emits_heartbeat_and_stops_it_when_step_completes(self):
        from ai_extract.services.inference_runtime_service import PipelineProgress
        waiting = Event()
        records = []
        progress = PipelineProgress('contract_run_7')
        def emit(stage, event, **fields):
            records.append((stage, event, fields))
            if event == 'waiting':
                waiting.set()
        with patch.object(progress, 'emit', side_effect=emit):
            with progress.stage('surya', heartbeat_seconds=.01, page=2, total_pages=14):
                self.assertTrue(waiting.wait(1))
        self.assertEqual(records[0][1], 'started')
        self.assertEqual(records[-1][1], 'completed')
        self.assertEqual(records[-1][2]['page'], 2)
        self.assertGreaterEqual(records[-1][2]['elapsed_s'], .01)

    def test_failed_step_logs_error_type_and_does_not_swallow_exception(self):
        import json
        from ai_extract.services.inference_runtime_service import PipelineProgress
        with self.assertLogs('ai_extract.pipeline', level='INFO') as logs:
            with self.assertRaises(RuntimeError):
                with PipelineProgress(7).stage('colpali', page=2):
                    raise RuntimeError('Sensitive source content must not enter logs')
        record = json.loads(logs.records[-1].getMessage().removeprefix('A3 '))
        self.assertEqual(record['run'], 7)
        self.assertEqual(record['event'], 'failed')
        self.assertEqual(record['error_type'], 'RuntimeError')
        self.assertNotIn('Sensitive source', str(logs.output))
