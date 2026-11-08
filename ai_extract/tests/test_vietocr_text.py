"""VietOCR replaces only body text reading; Surya keeps layout, tables and figures."""
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from PIL import Image

from ai_extract.services.surya_inference_service import SuryaStreamManager, surya_page
from ai_extract.services.vietocr_service import lines_in_blocks, read_blocks


class SuryaBlock:
    """Like Surya's result, bbox is computed from the polygon and cannot be assigned."""
    label, html, error, skipped, confidence, reading_order = 'Table', '<p>ô</p>', False, False, 1, 0

    @property
    def bbox(self):
        return [0, 40, 200, 80]


def box(label, position, bbox):
    a, b, c, d = bbox
    return NS(label=label, position=position, bbox=bbox, polygon=[[a, b], [c, b], [c, d], [a, d]])


class LineGroupingTests(SimpleTestCase):
    def test_lines_go_to_their_block_in_reading_order(self):
        lines = [[10, 60, 90, 80], [10, 10, 90, 30], [110, 10, 190, 30]]
        grouped = lines_in_blocks(lines, [[0, 0, 100, 100], [100, 0, 200, 100]], 1000)
        self.assertEqual(grouped, [[[10, 10, 90, 30], [10, 60, 90, 80]], [[110, 10, 190, 30]]])

    def test_block_without_detected_line_is_read_whole(self):
        self.assertEqual(lines_in_blocks([], [[1, 2, 30, 40]], 1000), [[[1, 2, 30, 40]]])

    def test_each_line_is_read_once(self):
        detector = Mock(return_value=[NS(bboxes=[NS(bbox=[10, 10, 90, 30]), NS(bbox=[10, 40, 90, 60])])])
        reader = NS(predict_batch=Mock(side_effect=lambda crops: ['Điều 1. Giá', 'Bên A trả'][:len(crops)]))
        text = read_blocks(Image.new('RGB', (200, 200)), [[0, 0, 100, 100]], (detector, reader))
        self.assertEqual(text, ['Điều 1. Giá\nBên A trả'])
        self.assertEqual(reader.predict_batch.call_count, 1)

    def test_a_page_of_lines_is_read_in_batches_and_returned_to_its_blocks(self):
        import ai_extract.services.vietocr_service as service
        boxes = [NS(bbox=[10, 10+20*i, 90, 25+20*i]) for i in range(5)]+[NS(bbox=[110, 10, 190, 25])]
        detector = Mock(return_value=[NS(bboxes=boxes)])
        seen = []

        def batch(crops):
            seen.append(len(crops))
            start = sum(seen[:-1])
            return [f'line {start+i}' for i in range(len(crops))]
        reader = NS(predict_batch=Mock(side_effect=batch))
        with patch.object(service, 'LINE_BATCH', 4):
            text = read_blocks(Image.new('RGB', (200, 200)), [[0, 0, 100, 120], [100, 0, 200, 40]], (detector, reader))
        self.assertEqual(seen, [4, 2])
        self.assertEqual(text, ['line 0\nline 1\nline 2\nline 3\nline 4', 'line 5'])


    def test_confidence_is_the_least_sure_line_of_each_block(self):
        detector = Mock(return_value=[NS(bboxes=[NS(bbox=[10, 10, 90, 30]), NS(bbox=[10, 40, 90, 60]), NS(bbox=[110, 10, 190, 30])])])
        reader = NS(predict_batch=Mock(return_value=(['Điều 1', 'E15(E4)', 'Bên A'], [.97, .61, .93])))
        read = read_blocks(Image.new('RGB', (200, 200)), [[0, 0, 100, 100], [100, 0, 200, 100]], (detector, reader), confidence=True)
        self.assertEqual(read, [('Điều 1\nE15(E4)', .61), ('Bên A', .93)])
        self.assertTrue(reader.predict_batch.call_args.kwargs['return_prob'])


class VietOCRPageTests(SimpleTestCase):
    def page(self, texts=('Điều 1 <b>', 'Bên A')):
        manager = SuryaStreamManager.__new__(SuryaStreamManager)
        manager.calls = []
        layout = NS(error=False, image_bbox=[0, 0, 100, 100], bboxes=[
            box('SectionHeader', 0, [0, 0, 100, 10]), box('Table', 1, [0, 20, 100, 40]), box('Text', 2, [0, 50, 100, 60])])
        predictor = Mock(return_value=[NS(blocks=[SuryaBlock()])], manager=manager)
        patches = [patch.object(SuryaStreamManager, 'begin_page'),
                   patch.dict('sys.modules', {'surya.layout': NS(LayoutPredictor=Mock(return_value=Mock(return_value=[layout])))}),
                   patch('ai_extract.services.vietocr_service.read_blocks', return_value=list(texts))]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return surya_page(Image.new('RGB', (100, 100)), predictor, high_resolution_image=Image.new('RGB', (200, 200)),
                          text_engine='vietocr'), predictor

    def test_only_body_text_goes_to_vietocr_and_order_is_surya_layout(self):
        from ai_extract.services import vietocr_service
        page, predictor = self.page()
        self.assertEqual([r['label'] for r in page['layout']], ['SectionHeader', 'Table', 'Text'])
        self.assertEqual([r['reading_order'] for r in page['layout']], [0, 1, 2])
        self.assertEqual([line['text'] for line in page['ocr_lines']], ['Điều 1 <b>', 'ô', 'Bên A'])
        self.assertEqual(page['metrics']['text_engine'], 'vietocr')
        # VietOCR reads the page image in layout coordinates; the sharp copy made it invent words.
        self.assertEqual(vietocr_service.read_blocks.call_args.args[0].size, (100, 100))
        self.assertEqual(vietocr_service.read_blocks.call_args.args[1], [[0, 0, 100, 10], [0, 50, 100, 60]])
        self.assertEqual([b.label for b in predictor.call_args.kwargs['layout_results'][0].bboxes], ['Table'])
        self.assertEqual(page['layout'][1]['bbox'], [0.0, 20.0, 100.0, 40.0])

    def test_unreadable_text_block_is_a_failed_region_and_not_cached(self):
        page, _ = self.page(('', 'Bên A'))
        self.assertEqual(page['metrics']['failed_regions'], 1)
        self.assertFalse(page['cacheable'])

    LANGUAGES = {'Điều khoản': 'vi', 'Điều 1': 'vi', 'Bên A': 'vi', 'Article 1. Scope': 'en', '第一条 合同标的': 'zh',
                 'Статья 1': 'ru', '제1조': 'ko', 'E15(E4)': 'nl', 'Bên B trả tiền': 'vi', 'ĐĂNG KÝ HỘ TỊCH': 'vi', 'ĐĂNG KY HỘ TICH': 'vi'}

    def auto_page(self, sampled_html, read=('Điều 1', 'Bên A'), html_by_top=None):
        """html_by_top gives Surya's reading of the block at that top edge; others read as sampled_html."""
        html_by_top = html_by_top or {}
        block = lambda source: NS(label=source.label, html=html_by_top.get(source.bbox[1], sampled_html), error=False, skipped=False, confidence=1)
        manager = SuryaStreamManager.__new__(SuryaStreamManager)
        manager.calls = []
        layout = NS(error=False, image_bbox=[0, 0, 100, 100], bboxes=[
            box('Text', 0, [0, 0, 100, 10]), box('Table', 1, [0, 20, 100, 40]), box('Text', 2, [0, 50, 100, 90])])
        predictor = Mock(side_effect=lambda images, layout_results, full_page: [NS(blocks=[block(source) for source in layout_results[0].bboxes])], manager=manager)
        rows = [r if isinstance(r, tuple) else (r, .95) for r in read]
        reader = patch('ai_extract.services.vietocr_service.read_blocks', side_effect=lambda image, boxes, confidence=False:
                       [r if confidence else r[0] for r in rows[:len(boxes)]])
        language = patch('ai_extract.services.language_service.language', side_effect=lambda text: next((code for phrase, code in self.LANGUAGES.items() if phrase in text), None))
        for item in (patch.object(SuryaStreamManager, 'begin_page'), reader, language,
                     patch.dict('sys.modules', {'surya.layout': NS(LayoutPredictor=Mock(return_value=Mock(return_value=[layout])))})):
            mocked = item.start()
            self.addCleanup(item.stop)
            if item is reader:
                self.read_blocks = mocked
        return surya_page(Image.new('RGB', (100, 100)), predictor, text_engine='auto'), predictor

    def test_auto_gives_a_vietnamese_page_to_vietocr(self):
        page, _ = self.auto_page('<p>Điều khoản</p>')
        self.assertEqual(page['metrics']['text_engine'], 'vietocr')
        self.assertEqual(self.read_blocks.call_count, 1)
        self.assertEqual([r['label'] for r in page['layout']], ['Text', 'Table', 'Text'])

    def test_auto_lets_surya_read_other_languages_once_per_block(self):
        for html in ('<p>Article 1. Scope</p>', '<p>第一条 合同标的</p>', '<p>Статья 1</p>', '<p>제1조</p>'):
            with self.subTest(html=html):
                page, predictor = self.auto_page(html)
                self.assertEqual(page['metrics']['text_engine'], 'surya')
                self.read_blocks.assert_not_called()
                read = sum(len(call.kwargs['layout_results'][0].bboxes) for call in predictor.call_args_list)
                self.assertEqual(read, 3)
                self.assertEqual([r['reading_order'] for r in page['layout']], [0, 1, 2])

    def test_foreign_passage_on_a_vietnamese_page_is_read_again_by_surya(self):
        """VietOCR turns a Japanese line into Latin noise; only that block goes back to Surya."""
        page, predictor = self.auto_page('<p>Điều khoản</p>', read=('Điều 1', 'E15(E4)'), html_by_top={50: '<p>第一条 合同标的</p>'})
        self.assertEqual(page['metrics']['text_engine'], 'vietocr+surya')
        self.assertEqual([line['text'] for line in page['ocr_lines']], ['Điều 1', 'Điều khoản', '第一条 合同标的'])
        last = predictor.call_args.kwargs['layout_results'][0].bboxes
        self.assertEqual([b.bbox for b in last], [[0, 50, 100, 90]])

    def test_digits_vietocr_doubts_are_replaced_only_by_a_foreign_reading(self):
        """'038150012428' has no letters; VietOCR's low probability sends it to Surya, whose Chinese stands."""
        page, _ = self.auto_page('<p>Điều khoản</p>', read=('Điều 1', ('038150012428', .62)), html_by_top={50: '<p>第一条 合同标的</p>'})
        self.assertEqual(page['metrics']['text_engine'], 'vietocr+surya')
        self.assertIn('第一条 合同标的', [line['text'] for line in page['ocr_lines']])

    def test_doubtful_vietnamese_line_keeps_vietocr_when_surya_also_reads_vietnamese(self):
        page, predictor = self.auto_page('<p>Điều khoản</p>', read=('Điều 1', ('ĐĂNG KÝ HỘ TỊCH', .65)), html_by_top={50: '<p>ĐĂNG KY HỘ TICH</p>'})
        self.assertEqual(page['metrics']['text_engine'], 'vietocr')
        self.assertIn('ĐĂNG KÝ HỘ TỊCH', [line['text'] for line in page['ocr_lines']])
        self.assertEqual([b.bbox for b in predictor.call_args.kwargs['layout_results'][0].bboxes], [[0, 50, 100, 90]])

    def test_vietnamese_passage_on_a_foreign_page_goes_to_vietocr(self):
        self.LANGUAGES['Bên B tra tien'] = 'vi'
        self.addCleanup(self.LANGUAGES.pop, 'Bên B tra tien')
        page, _ = self.auto_page('<p>Article 1. Scope</p>', read=('Bên B trả tiền',), html_by_top={50: '<p>Bên B tra tien</p>'})
        self.assertEqual(page['metrics']['text_engine'], 'surya+vietocr')
        self.assertEqual(self.read_blocks.call_args.args[1], [[0, 50, 100, 90]])
        self.assertIn('Bên B trả tiền', [line['text'] for line in page['ocr_lines']])
        self.assertNotIn('Bên B tra tien', [line['text'] for line in page['ocr_lines']])

    def test_unknown_engine_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'text_engine'):
            surya_page(Image.new('RGB', (10, 10)), Mock(), text_engine='other')


class EngineRequestTests(SimpleTestCase):
    def extract(self):
        from ai_extract.services.contract_pipeline_service import remote_page
        response = Mock(status_code=200)
        response.json.return_value = dict(model='surya-ocr-v2', ocr_lines=[], layout=[], metrics={})
        with patch('ai_extract.services.contract_pipeline_service.requests.post', return_value=response) as post:
            remote_page(NS(), Image.new('RGB', (10, 10)))
        return post.call_args.kwargs['json']

    @override_settings(RAG_INFERENCE_URL='http://inference')
    def test_surya_default_keeps_the_request_unchanged(self):
        with override_settings(OCR_TEXT_ENGINE='surya'):
            body = self.extract()
        self.assertNotIn('text_engine', body)
        with override_settings(OCR_TEXT_ENGINE='vietocr'):
            other = self.extract()
        self.assertEqual(other['text_engine'], 'vietocr')


class CellEdgeSplitTests(SimpleTestCase):
    # Page 15 header: four cells over two rows, "Hao phí" across the last two columns.
    CELLS = [[142, 280, 250, 349], [250, 280, 364, 349], [364, 280, 637, 349], [637, 280, 709, 349],
             [709, 280, 912, 298], [709, 298, 807, 349], [807, 298, 912, 349]]

    def test_line_running_over_two_header_cells_is_cut_at_their_edge(self):
        from ai_extract.services.vietocr_service import split_at_cell_edges
        self.assertEqual(split_at_cell_edges([[150, 305, 350, 325]], self.CELLS),
                         [[150, 305, 250, 325], [250, 305, 350, 325]])

    def test_line_inside_a_spanning_cell_stays_whole(self):
        from ai_extract.services.vietocr_service import split_at_cell_edges
        self.assertEqual(split_at_cell_edges([[760, 283, 860, 295]], self.CELLS), [[760, 283, 860, 295]])

    def test_split_pieces_go_to_their_own_cells(self):
        detector = Mock(return_value=[NS(bboxes=[NS(bbox=[150, 305, 350, 325])])])
        reader = Mock()
        reader.predict_batch.side_effect = lambda crops, return_prob=False: (
            (['Mã dịch vụ', 'Tên dịch vụ'][:len(crops)], [.99]*len(crops)) if return_prob else ['Mã dịch vụ', 'Tên dịch vụ'][:len(crops)])
        image = Image.new('RGB', (1000, 400), 'white')
        texts = read_blocks(image, self.CELLS[:2], models=(detector, reader), confidence=True, split_lines=True)
        self.assertEqual([text for text, _ in texts], ['Mã dịch vụ', 'Tên dịch vụ'])
