"""A page scanned sideways or upside down is turned before it is stored and read."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import fitz
from django.test import SimpleTestCase, override_settings
from PIL import Image

from ai_extract.services import page_orientation_service as orientation


def found(angle, confidence=.99):
    return patch.object(orientation, 'detect', return_value=dict(angle=angle, confidence=confidence, model=orientation.MODEL_ID))


class OrientationTests(SimpleTestCase):
    def test_page_and_sharp_copy_turn_together(self):
        page, sharp = Image.new('RGB', (100, 200)), Image.new('RGB', (200, 400))
        with found(90):
            page, sharp, angle = orientation.upright(page, sharp)
        self.assertEqual((page.size, sharp.size, angle), ((200, 100), (400, 200), 90))

    def test_upright_or_unsure_pages_are_left_as_they_are(self):
        for angle, confidence in ((0, .99), (180, .5)):
            with self.subTest(angle=angle), found(angle, confidence):
                page = Image.new('RGB', (100, 200))
                self.assertEqual(orientation.upright(page), (page, 0))

    @override_settings(RAG_INFERENCE_URL='http://ocr.test')
    def test_runtime_answer_is_checked(self):
        for reply in (dict(angle=45, confidence=1., model=orientation.MODEL_ID), dict(angle=90, confidence=1., model='other')):
            with self.subTest(reply=reply), patch('requests.post', return_value=Mock(json=Mock(return_value=reply))):
                with self.assertRaisesRegex(ValueError, 'orientation'):
                    orientation.detect(Image.new('RGB', (2000, 3000)))

    @override_settings(RAG_INFERENCE_URL='http://ocr.test')
    def test_a_small_copy_is_sent(self):
        reply = dict(angle=180, confidence=.97, model=orientation.MODEL_ID)
        with patch('requests.post', return_value=Mock(json=Mock(return_value=reply))) as post:
            self.assertEqual(orientation.detect(Image.new('RGB', (2480, 3508)))['angle'], 180)
        import base64, io
        sent = Image.open(io.BytesIO(base64.b64decode(post.call_args.kwargs['json']['image_base64'])))
        self.assertLessEqual(max(sent.size), orientation.SEND_SIZE)

    def test_a_sideways_pdf_page_is_stored_and_read_upright(self):
        from ai_extract.services.layout_extractor import SuryaExtractor
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory, RAG_INFERENCE_URL='http://ocr.test'):
            path = Path(directory)/'sideways.pdf'
            document = fitz.open()
            document.new_page(width=842, height=595)
            document.save(path)
            seen = {}

            def read(extractor, **kwargs):
                seen.update(page=kwargs['page_img'].size, sharp=extractor._visual_ocr_image.size)
                return [dict(chunk_id=1, text='Điều 1', page_number=1)], 2
            extractor = SuryaExtractor(load_models=False)
            extractor.surya_layout_model = Mock()
            with found(270), patch.object(SuryaExtractor, '_extract_logged_page', autospec=True, side_effect=read):
                records = extractor._extract_pdf_pure_surya_vision(str(path), 1)
            stored = Image.open(Path(directory)/'extracted_images'/'pdf_page_1_p1.png')
            self.assertGreater(seen['page'][1], seen['page'][0])
            self.assertEqual(stored.size, seen['page'])
            # 300 and 150 dpi round their sizes apart by a pixel.
            for sharp, page in zip(seen['sharp'], seen['page']):
                self.assertLessEqual(abs(sharp-2*page), 2)
            self.assertEqual(records[0]['page_rotation'], 270)
