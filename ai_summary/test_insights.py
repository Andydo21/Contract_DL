"""Run from ai_summary/: python -m unittest test_insights"""
import unittest

import insights
import legal

LABOR = """HỢP ĐỒNG LAO ĐỘNG
Số: 15/2025/HĐLĐ
NGƯỜI SỬ DỤNG LAO ĐỘNG: Công ty TNHH Phần mềm Bình Minh
NGƯỜI LAO ĐỘNG: Ông Nguyễn Văn Nam
Điều 1. Thời hạn
Hợp đồng có thời hạn 12 tháng, từ ngày 01/03/2025 đến ngày 28/02/2026.
Điều 2. Tiền lương
Mức lương: 15.000.000 đồng/tháng.
Điều 3. Chấm dứt
Người lao động phải báo trước 30 ngày."""


# What Tesseract really produced from a scan of the same contract.
OCR = """HỢP ĐÔNG LAO ĐỘNG
Số: 15/2025/HĐLĐ
NGƯỜI SỬDỤNG LAO DONG: Công ty TNHH Phần mềm Bình Minh
NGƯỜI LAO ĐỌNG: Ông Nguyễn Văn Nam
Điều 2. Thời hạn hợp đồng 12 tháng, từngày 01/03/2025 đến ngày 28/02/2026.
Điều 4. Người sửdụng lao động đóng bảo hiem xã hội theo quy định."""


class KeyDateTests(unittest.TestCase):
    def test_stated_period_and_notice(self):
        items = insights.key_dates(dict(term='12 tháng, từ ngày 01/03/2025 đến ngày 28/02/2026',
                                        termination=[dict(text='Phải báo trước 30 ngày')]), LABOR)
        self.assertEqual([(i['kind'], i['date'], i['computed']) for i in items],
                         [('start', '2025-03-01', False), ('end', '2026-02-28', False), ('notice', None, False)])
        self.assertIn('30 ngày', items[2]['label'])

    def test_end_date_is_computed_from_a_duration_and_marked(self):
        items = insights.key_dates(dict(term='12 tháng', effective_date='01/03/2025'), '')
        self.assertEqual((items[1]['date'], items[1]['computed']), ('2026-02-28', True))
        items = insights.key_dates(dict(term='1 tháng', effective_date='31/01/2024'), '')
        self.assertEqual(items[1]['date'], '2024-02-28')

    def test_term_without_a_start_date_gives_no_invented_dates(self):
        self.assertEqual(insights.key_dates(dict(term='180 ngày kể từ ngày bàn giao'), ''), [])
        self.assertEqual(insights.key_dates(dict(term='31/02/2025'), ''), [])


class PreliminaryTests(unittest.TestCase):
    def test_copies_values_and_labour_gaps_without_the_model(self):
        text = insights.preliminary(LABOR)
        self.assertIn('15/2025/HĐLĐ', text)
        self.assertIn('15.000.000', text)
        self.assertIn('Ông Nguyễn Văn Nam', text)
        self.assertIn('Không thấy nội dung về bảo hiểm xã hội', text)

    def test_suggests_upload_fields(self):
        values = insights.suggest(LABOR)
        self.assertEqual(values['contract_code'], '15/2025/HĐLĐ')
        self.assertEqual(values['title'], 'HỢP ĐỒNG LAO ĐỘNG')
        self.assertEqual(values['contract_type'], 'Lao động')
        self.assertEqual(values['contract_value'], 15_000_000)
        self.assertEqual((values['start_date'], values['end_date']), ('2025-03-01', '2026-02-28'))

    def test_ocr_damaged_scan_is_still_understood(self):
        values = insights.suggest(OCR)
        self.assertEqual((values['title'], values['contract_type']), ('HỢP ĐÔNG LAO ĐỘNG', 'Lao động'))
        text = insights.preliminary(OCR)
        self.assertIn('Người lao động: Ông Nguyễn Văn Nam', text)
        self.assertIn('Người sử dụng lao động: Công ty TNHH Phần mềm Bình Minh', text)
        self.assertIn('Thiếu nội dung bắt buộc', text)
        self.assertNotIn('Không thấy nội dung về bảo hiểm', text)  # 'bảo hiem xã hội' counts as present

    def test_gender_is_not_matched_by_the_word_year_once_marks_are_ignored(self):
        self.assertFalse(legal.tolerant_search(r'\bnam\b', 'ký năm 2025', exact_only=True))
        self.assertTrue(legal.tolerant_search(r'bảo hiểm xã hội', 'bao hiem xa hoi'))
        self.assertTrue(legal.tolerant_search(r'người sử dụng', 'NGƯỜI SỬDỤNG'))

    def test_suggestion_stays_empty_rather_than_guessing(self):
        values = insights.suggest('Biên bản họp nội bộ ngày hôm nay, không có số liệu nào đáng kể.')
        self.assertEqual((values['contract_code'], values['title'], values['contract_value'], values['end_date']), ('', '', None, ''))


if __name__ == '__main__':
    unittest.main()
