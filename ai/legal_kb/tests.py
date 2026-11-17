from datetime import date

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from .models import LegalDocument, LegalProvision, LegalRelation
from .parser import fold, parse
from .repositories.legal_repository import index_documents
from .services import search_service as search
from .services.import_service import gaps

TAGGED = """
<p>Căn cứ Hiến pháp;</p>
<p class="MsoNormal prov-chapter"><b>Chương III<br></b><b>HỢP ĐỒNG LAO ĐỘNG</b></p>
<p class="prov-section">Mục 1. GIAO KẾT</p>
<p class="prov-article"><strong>Điều 25. Thời gian thử việc</strong></p>
<p class="prov-content">Thời gian thử việc do hai bên thỏa thuận:</p>
<p class="prov-clause">1. Không quá 180 ngày đối với người quản lý doanh nghiệp;</p>
<p class="prov-clause">2. Không quá 60 ngày đối với công việc cần trình độ cao đẳng trở lên;</p>
<p class="prov-clause">Điều 26. Tiền lương thử việc</p>
<p class="prov-clause">1. Ít nhất bằng 85% mức lương của công việc đó.</p>
<table><tr><td><p class="prov-content">Vùng I</p></td><td><p class="prov-content">5.310.000</p></td></tr></table>
<p class="prov-item">a) điểm của khoản 1.</p>
<p>Bộ luật này được Quốc hội khóa XIV, kỳ họp thứ 8 thông qua ngày 20 tháng 11 năm 2019.</p>
<table><tr><td><div>CHỦ TỊCH QUỐC HỘI</div></td></tr></table>
"""

UNTAGGED = """
<p>NGHỊ ĐỊNH</p>
<p>Chương I</p><p>QUY ĐỊNH CHUNG</p>
<p>Điều 1. Phạm vi điều chỉnh</p>
<p>Nghị định này quy định mức lương tối thiểu.</p>
<p>Điều 2. Đối tượng áp dụng</p>
<p>1. Người lao động.</p>
<p>a) làm việc theo hợp đồng lao động;</p>
<p>2. Người sử dụng lao động.</p>
<p>Nơi nhận:</p><p>- Ban Bí thư;</p>
<p>PHỤ LỤC I</p><p>DANH MỤC ĐỊA BÀN</p><p>1. Vùng I gồm các phường thuộc Hà Nội.</p>
"""


class ParserTests(SimpleTestCase):
    def test_tagged_document(self):
        provisions = parse(TAGGED)
        self.assertEqual([p.ref for p in provisions],
                         ['Điều 25', 'Khoản 1 Điều 25', 'Khoản 2 Điều 25', 'Khoản 1 Điều 26'])
        intro, first = provisions[0], provisions[1]
        self.assertEqual(intro.text, 'Thời gian thử việc do hai bên thỏa thuận:')
        self.assertEqual(first.heading, 'Thời gian thử việc')
        self.assertEqual(first.chapter, 'Chương III HỢP ĐỒNG LAO ĐỘNG')
        self.assertEqual(first.section, 'Mục 1. GIAO KẾT')

    def test_article_heading_tagged_as_clause_starts_an_article(self):
        self.assertEqual(parse(TAGGED)[-1].heading, 'Tiền lương thử việc')

    def test_tables_and_points_stay_in_their_clause_and_the_signature_is_dropped(self):
        self.assertEqual(parse(TAGGED)[-1].text,
                         '1. Ít nhất bằng 85% mức lương của công việc đó.\nVùng I | 5.310.000\na) điểm của khoản 1.')

    def test_untagged_document_is_split_on_its_text(self):
        provisions = parse(UNTAGGED)
        self.assertEqual([p.ref for p in provisions], ['Điều 1', 'Khoản 1 Điều 2', 'Khoản 2 Điều 2', 'Phụ lục I'])
        self.assertEqual(provisions[1].text, '1. Người lao động.\na) làm việc theo hợp đồng lao động;')
        self.assertEqual(provisions[0].chapter, 'Chương I QUY ĐỊNH CHUNG')
        self.assertNotIn('Ban Bí thư', ' '.join(p.text for p in provisions))
        self.assertIn('Vùng I gồm', provisions[-1].text)

    def test_reference_to_an_article_is_not_an_article(self):
        provisions = parse('<p>Điều 1. Phạm vi</p><p>Điều 21 của Bộ luật này được áp dụng.</p>')
        self.assertEqual(len(provisions), 1)
        self.assertIn('Điều 21 của Bộ luật', provisions[0].text)

    def test_fold(self):
        self.assertEqual(fold('Lương TỐI THIỂU đồng'), 'luong toi thieu dong')

    def test_gaps(self):
        self.assertEqual(gaps(parse('<p>Điều 1. A</p><p>x</p><p>Điều 3. C</p><p>y</p>')),
                         ['Thiếu Điều 2 trong nội dung nguồn.'])
        self.assertEqual(gaps(parse('<p>Điều 1. A</p><p>1. Danh mục tại Phụ lục I.</p>')),
                         ['Văn bản dẫn tới phụ lục/danh mục kèm theo nhưng nội dung nguồn không có.'])
        self.assertEqual(gaps(parse(UNTAGGED)), [])


class SearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        def document(source_id, number, start, end, provisions):
            doc = LegalDocument.objects.create(
                source_id=source_id, number=number, title=number, doc_type='Nghị định', domain='labour',
                effective_from=start, effective_to=end, content_hash='x')
            for i, (article, clause, heading, text) in enumerate(provisions):
                LegalProvision.objects.create(document=doc, position=i, article=article, clause=clause,
                                              heading=heading, text=text)
            return doc

        cls.old = document('1', '74/2024/NĐ-CP', date(2024, 7, 1), date(2026, 1, 1), [
            ('3', '1', 'Mức lương tối thiểu', '1. Vùng I | 4.960.000'),
            ('4', '1', 'Áp dụng', '1. Mức lương tối thiểu tháng là mức lương thấp nhất.'),
        ])
        cls.new = document('2', '293/2025/NĐ-CP', date(2026, 1, 1), None, [
            ('3', '1', 'Mức lương tối thiểu', '1. Vùng I | 5.310.000'),
            ('3', '2', 'Mức lương tối thiểu', '2. Danh mục địa bàn tại Phụ lục.'),
        ])
        document('3', '45/2019/QH14', date(2021, 1, 1), None, [
            ('25', '', 'Thời gian thử việc', 'Thời gian thử việc do hai bên thỏa thuận.'),
            ('90', '1', 'Tiền lương', '1. Tiền lương là số tiền trả cho người lao động.'),
        ])
        LegalRelation.objects.create(actor_source_id='2', actor_number='293/2025/NĐ-CP', effect='replaces',
                                     subject_source_id='1', subject_number='74/2024/NĐ-CP', label='Thay thế',
                                     actor_effective_from=date(2026, 1, 1))
        index_documents(LegalDocument.objects.values_list('pk', flat=True))

    def setUp(self):
        search._stats.clear()

    def test_only_documents_in_force_on_the_date_are_searched(self):
        now = search.search('lương tối thiểu vùng', date(2026, 3, 1))
        self.assertEqual([(r['document'], r['ref']) for r in now][:1], [('293/2025/NĐ-CP', 'Khoản 1 Điều 3')])
        self.assertNotIn('74/2024/NĐ-CP', {r['document'] for r in now})
        before = search.search('lương tối thiểu vùng', date(2025, 3, 1))
        self.assertEqual(before[0]['document'], '74/2024/NĐ-CP')

    def test_one_result_per_article_with_the_clauses_that_matched(self):
        results = search.search('mức lương tối thiểu', date(2026, 3, 1))
        self.assertEqual([r['ref'] for r in results if r['document'] == '293/2025/NĐ-CP'], ['Khoản 1 Điều 3'])
        self.assertEqual(results[0]['matched_clauses'], ['Khoản 1 Điều 3', 'Khoản 2 Điều 3'])

    def test_diacritics_are_optional(self):
        self.assertEqual(search.search('thoi gian thu viec', date(2026, 3, 1))[0]['ref'], 'Điều 25')

    def test_changes_are_reported_from_their_effective_date(self):
        self.assertEqual(search.search('lương', date(2025, 3, 1))[0]['changed_by'], [])
        self.assertEqual(search.article('74/2024/NĐ-CP', '3', date(2026, 3, 1))['changed_by'][0]['number'],
                         '293/2025/NĐ-CP')

    def test_article(self):
        found = search.article('293/2025/nđ-cp', '3')
        self.assertEqual([c['ref'] for c in found['clauses']], ['Khoản 1 Điều 3', 'Khoản 2 Điều 3'])
        self.assertIsNone(search.article('293/2025/NĐ-CP', '99'))

    def test_api(self):
        url = '/api/legal/search/?q=thử+việc&date=2026-03-01'
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(get_user_model().objects.create_user(username='hr'))
        self.assertEqual(self.client.get(url).json()['results'][0]['ref'], 'Điều 25')
        self.assertEqual(self.client.get('/api/legal/search/').status_code, 400)
        self.assertEqual(self.client.get('/api/legal/article/?doc=45/2019/QH14&article=1').status_code, 404)
        documents = self.client.get('/api/legal/documents/?date=2026-03-01').json()['documents']
        self.assertEqual({d['document']: d['in_force'] for d in documents}['74/2024/NĐ-CP'], False)
