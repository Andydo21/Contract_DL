"""Run from ai_summary/: python -m unittest test_reader"""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import docx
import pymupdf
from docx.oxml import parse_xml

import reader
import services

CONTRACT = ['CONTRACT FOR THE SALE OF GOODS', 'Article 1. Goods', 'Party B delivers 500 office chairs.',
            'Article 2. Price', 'Total value 85,000,000 VND, paid within 30 days.']


def pdf(lines_per_page, scanned=False):
    """A text-layer PDF, or with scanned=True the same pages flattened into images (no text layer)."""
    document = pymupdf.open()
    for lines in lines_per_page:
        page = document.new_page()
        for index, line in enumerate(lines):
            page.insert_text((72, 100 + 30 * index), line, fontsize=16)
    if scanned:
        images = pymupdf.open()
        for page in document:
            pixmap = page.get_pixmap(dpi=200)
            images.new_page(width=page.rect.width, height=page.rect.height).insert_image(page.rect, pixmap=pixmap)
        document = images
    return document.tobytes()


class ReaderTests(unittest.TestCase):
    def test_docx_keeps_paragraphs_and_tables_in_document_order(self):
        document = docx.Document()
        document.add_paragraph('HỢP ĐỒNG LAO ĐỘNG')
        document.add_paragraph('Điều 3. Tiền lương')
        table = document.add_table(rows=2, cols=2)
        table.cell(0, 0).text, table.cell(0, 1).text = 'Lương cơ bản', '15.000.000 đồng/tháng'
        merged = table.cell(1, 0).merge(table.cell(1, 1))
        merged.text = 'Phụ cấp ăn trưa 730.000 đồng'
        document.add_paragraph('Điều 4. Bảo hiểm')
        buffer = io.BytesIO()
        document.save(buffer)
        result = reader.read(buffer.getvalue(), 'hop-dong.docx')
        self.assertEqual(result['kind'], 'docx')
        self.assertEqual(result['text'].splitlines(), [
            'HỢP ĐỒNG LAO ĐỘNG', 'Điều 3. Tiền lương', 'Lương cơ bản | 15.000.000 đồng/tháng',
            'Phụ cấp ăn trưa 730.000 đồng', 'Điều 4. Bảo hiểm'])

    def test_pdf_text_layer_is_read_page_by_page(self):
        result = reader.read(pdf([CONTRACT[:3], CONTRACT[3:]]), 'contract.pdf')
        self.assertEqual((result['kind'], result['pages'], result['ocr_pages']), ('pdf', 2, []))
        self.assertIn('Party B delivers 500 office chairs.\n\nArticle 2. Price', result['text'])

    def test_content_decides_the_format_not_the_name(self):
        self.assertEqual(reader.read(pdf([CONTRACT]), 'contract_LAB.txt')['kind'], 'pdf')
        self.assertEqual(reader.read('Điều 1. Giá trị'.encode(), 'upload.bin')['text'], 'Điều 1. Giá trị')

    @unittest.skipIf(reader.ocr_available(), 'Tesseract installed: covered by the OCR test')
    def test_scanned_pdf_without_ocr_is_reported_not_silently_empty(self):
        with self.assertRaisesRegex(reader.ReadError, 'ảnh scan'):
            reader.read(pdf([CONTRACT], scanned=True), 'scan.pdf')
        mixed = pymupdf.open(stream=pdf([CONTRACT]))
        mixed.insert_pdf(pymupdf.open(stream=pdf([CONTRACT], scanned=True)))
        result = reader.read(mixed.tobytes(), 'mixed.pdf')
        self.assertEqual(result['unreadable_pages'], [2])
        self.assertIn('Tesseract', result['warnings'][0])

    @unittest.skipUnless(reader.ocr_available(), 'needs Tesseract (present in the Docker image)')
    def test_scanned_pages_are_ocred(self):
        result = reader.read(pdf([CONTRACT], scanned=True), 'scan.pdf')
        self.assertEqual(result['ocr_pages'], [1])
        self.assertIn('500 office chairs', result['text'])

    def test_legacy_doc_and_bad_files_give_actionable_errors(self):
        with self.assertRaisesRegex(reader.ReadError, '.docx'):
            reader.read(b'\xd0\xcf\x11\xe0' + b'\x00' * 100, 'old.doc')
        with self.assertRaisesRegex(reader.ReadError, 'rỗng'):
            reader.read(b'', 'empty.pdf')
        with self.assertRaisesRegex(reader.ReadError, 'PDF'):
            reader.read(b'%PDF-1.7 broken', 'broken.pdf')

    def test_docx_keeps_tracked_insertions_content_controls_and_text_boxes(self):
        ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
             'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
        document = docx.Document()
        body = document.element.body
        for xml in (
                f'<w:p {ns}><w:r><w:t>Lương </w:t></w:r><w:ins><w:r><w:t>18.000.000</w:t></w:r></w:ins>'
                f'<w:del><w:r><w:delText>15.000.000</w:delText></w:r></w:del></w:p>',
                f'<w:sdt {ns}><w:sdtContent><w:p><w:r><w:t>Trong content control</w:t></w:r></w:p></w:sdtContent></w:sdt>',
                f'<w:p {ns}><w:r><mc:AlternateContent><mc:Choice><w:txbxContent><w:p><w:r><w:t>Trong text box</w:t></w:r></w:p>'
                f'</w:txbxContent></mc:Choice><mc:Fallback><w:t>Bản lặp</w:t></mc:Fallback></mc:AlternateContent></w:r></w:p>'):
            body.insert(0, parse_xml(xml))
        buffer = io.BytesIO()
        document.save(buffer)
        text = reader.read(buffer.getvalue(), 'hd.docx')['text']
        self.assertIn('Lương 18.000.000', text)
        self.assertNotIn('15.000.000', text)
        self.assertIn('Trong content control', text)
        self.assertEqual(text.count('Trong text box'), 1)
        self.assertNotIn('Bản lặp', text)

    def test_legacy_encoded_text_is_recognised(self):
        self.assertTrue(reader.looks_garbled('Hîp ®ång lao ®éng ¸p dông ®èi víi ng­êi lao ®éng t¹i c«ng ty'))
        self.assertTrue(reader.looks_garbled('Hôïp ñoàng lao ñoäng ñöôïc kyù keát giöõa hai beân'))
        self.assertFalse(reader.looks_garbled('Hợp đồng lao động được ký kết giữa hai bên, lương 15.000.000 đồng/tháng'))
        self.assertFalse(reader.looks_garbled('This contract is signed by both parties for 36,000 USD per year.'))

    def test_garbled_text_layer_goes_to_ocr_and_blank_page_does_not(self):
        garbled = pdf([['Hip ong lao ong ap dung oi voi nguoi lao ong tai cong ty'], []])
        calls = []
        with patch.object(reader, 'ocr_available', return_value=True), \
                patch.object(reader, 'looks_garbled', side_effect=lambda text: 'Hip ong' in text), \
                patch.object(reader, '_ocr_page', side_effect=lambda page: calls.append(page.number) or 'Hợp đồng lao động'):
            result = reader.read(garbled, 'cu.pdf')
        self.assertEqual(calls, [0])
        self.assertEqual(result['ocr_pages'], [1])
        self.assertEqual(result['text'], 'Hợp đồng lao động')

    def test_failed_ocr_is_reported_not_silently_dropped(self):
        mixed = pymupdf.open(stream=pdf([CONTRACT]))
        mixed.insert_pdf(pymupdf.open(stream=pdf([CONTRACT], scanned=True)))
        with patch.object(reader, 'ocr_available', return_value=True), patch.object(reader, '_ocr_page', return_value=''):
            result = reader.read(mixed.tobytes(), 'mixed.pdf')
        self.assertEqual(result['unreadable_pages'], [2])
        self.assertIn('không OCR được', result['warnings'][0])

    def test_reading_is_cached_by_content_so_views_do_not_ocr_again(self):
        data = pdf([CONTRACT])
        with tempfile.TemporaryDirectory() as folder, patch.object(services, 'CACHE_DIR', Path(folder)), \
                patch.object(services.reader, 'read', wraps=reader.read) as read:
            services._memory.clear()
            first, second = services.read_document(data, 'a.pdf'), services.read_document(data, 'a.pdf')
        self.assertEqual(read.call_count, 1)
        self.assertEqual(first['text'], second['text'])

    def test_page_ranges_are_compact(self):
        self.assertEqual(reader._ranges([1, 2, 3, 7, 9, 10]), '1-3, 7, 9-10')


if __name__ == '__main__':
    unittest.main()
