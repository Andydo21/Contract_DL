"""Clause-by-clause risk analysis against retrieved law, then the contract as a whole."""
from django.test import SimpleTestCase

from NewIdea.services import clause_risk_service as risk

CLAUSES = [
    dict(id=0, title='Điều 1. Đối tượng', content='Điều 1. Đối tượng\nBên A bán cho Bên B 100 tấn thép.'),
    dict(id=1, title='Điều 5. Phạt vi phạm', content='Điều 5. Phạt vi phạm\nBên B chịu phạt 20% giá trị hợp đồng nếu chậm thanh toán.',
         mentions_clause_ids=[0]),
]
PENALTY_LAW = dict(evidence_id='E7', original_name='LAW-1 — Luật Thương mại số 36/2005/QH11', legal_note='Hết hiệu lực một phần',
                   heading_path=['Luật Thương mại', 'Chương VII', 'Điều 301. Mức phạt vi phạm'], clause_title='Điều 301. Mức phạt vi phạm',
                   text='Điều 301. Mức phạt vi phạm\nMức phạt không quá 8% giá trị phần nghĩa vụ hợp đồng bị vi phạm.',
                   expansion_reason='query_match')


def search(query, planning):
    """Ranks the penalty article for the penalty clause's question only (query 2: after the main query and clause 1)."""
    return dict(results=[dict(PENALTY_LAW, retrieval_ranks=[dict(query=2, rank=1)]),
                         dict(PENALTY_LAW, evidence_id='E9', expansion_reason='neo4j_source_relation', retrieval_ranks=[dict(query=1, rank=1)])])


class Model:
    """Answers each call by its instruction; records the briefs it read."""
    LAW_WORDS = 'Mức phạt không quá 8% giá trị phần nghĩa vụ hợp đồng bị vi phạm'

    def __init__(self, risks, verdict=True, overall=None, summary_verdict=True):
        self.summary_verdict = summary_verdict
        self.risks, self.verdict, self.overall, self.briefs = risks, verdict, overall or dict(summary='Rủi ro tập trung ở điều phạt.', risks=[]), []

    def __call__(self, task, payload):
        self.briefs.append(payload['contract'])
        if payload['instruction'] is risk.CLAUSE_RULES:
            penalty = '[C1]' in payload['contract'] and 'Điều khoản cần phân tích [C1]' in payload['contract']
            return dict(clause_summary='Tóm tắt.', risks=self.risks if penalty else [])
        if payload['instruction'] is risk.VERIFY_RULES:
            if '## Nhận định chung đề xuất' in payload['contract']:
                return dict(supported=self.summary_verdict, reason='ok')
            return dict(reason='ok', supported=self.verdict)
        return self.overall


def penalty_risk(**changes):
    return dict(dict(category='Mức phạt vượt trần', risk_level='HIGH', explanation='Mức phạt 20% vượt trần 8%.',
                     recommendation='Giảm mức phạt xuống tối đa 8%.', disadvantaged_party='Bên B',
                     contract_quote='Bên B chịu phạt 20% giá trị hợp đồng', law_ids=['L1'], law_quote=Model.LAW_WORDS,
                     kind='conflict', related_clause_ids=[]), **changes)


class ClauseRiskTests(SimpleTestCase):
    def test_a_clause_risk_quotes_the_clause_and_cites_the_retrieved_law(self):
        model = Model([penalty_risk()])
        result = risk.analyze_clauses(CLAUSES, 'Hợp đồng mua bán thép', ['Công ty A', 'Công ty B'], model, search)
        [found] = result['findings']
        self.assertEqual((found['clause_title'], found['risk_level'], found['law_sources']), ('Điều 5. Phạt vi phạm', 'HIGH', ['E7']))
        self.assertIn('Trích điều khoản: “Bên B chịu phạt 20% giá trị hợp đồng”', found['explanation'])
        self.assertIn('Căn cứ pháp lý: Điều 301 — LAW-1 — Luật Thương mại số 36/2005/QH11 (Hết hiệu lực một phần)', found['explanation'])
        self.assertIn(f'Trích luật: “{Model.LAW_WORDS}”', found['explanation'])
        self.assertEqual((result['overall_score'], result['risk_level']), (30, 'HIGH'))

    def test_the_brief_is_markdown_with_the_clause_its_references_and_the_law(self):
        model = Model([])
        risk.analyze_clauses(CLAUSES, 'Hợp đồng mua bán thép', [], model, search)
        brief = next(b for b in model.briefs if 'Điều khoản cần phân tích [C1]' in b)
        self.assertIn('#### Điều 5. Phạt vi phạm', brief)
        self.assertIn('### [C0] Điều 1. Đối tượng — được điều khoản này dẫn chiếu', brief)
        self.assertIn('### [L1] Điều 301. Mức phạt vi phạm — Luật Thương mại số 36/2005/QH11 — Hết hiệu lực một phần', brief)
        self.assertNotIn('LAW-1', brief)
        self.assertIn('Vị trí: Chương VII', brief)
        # A provision reached only by graph expansion is not offered as law.
        self.assertNotIn('[L2]', brief)

    def test_a_risk_without_a_literal_quote_or_with_an_unsupplied_law_is_dropped(self):
        for bad in (penalty_risk(contract_quote='Bên B bị phạt nặng'), penalty_risk(law_ids=['L4']), penalty_risk(related_clause_ids=[7])):
            result = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([bad]), search)
            self.assertEqual((result['findings'], result['rejected']), ([], 1))

    def test_a_clause_risk_needs_no_second_model_call(self):
        model = Model([penalty_risk()], verdict=False)
        result = risk.analyze_clauses(CLAUSES, 'HĐ', [], model, search, )
        self.assertEqual(len(result['findings']), 1)
        self.assertFalse([b for b in model.briefs if '## Rủi ro đề xuất' in b])

    def test_contract_wide_risks_name_their_clauses(self):
        overall = dict(summary='Bên B chịu phần lớn rủi ro.', risks=[
            dict(category='Một bên chịu rủi ro', risk_level='MEDIUM', explanation='Bên B chịu phạt mà Bên A không chịu gì.',
                 recommendation='Cân bằng nghĩa vụ.', disadvantaged_party='Bên B', clause_ids=[0, 1]),
            dict(category='Một điều', risk_level='MEDIUM', explanation='Chỉ dựa vào Điều 1.', recommendation='', disadvantaged_party=None, clause_ids=[0]),
            dict(category='Thiếu thời hạn', risk_level='MEDIUM', explanation='Không có thời hạn giao.', recommendation='', disadvantaged_party=None, clause_ids=[]),
            dict(category='Sai số điều', risk_level='LOW', explanation='Điều không có.', recommendation='', disadvantaged_party=None, clause_ids=[0, 9])])
        result = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([penalty_risk()], overall=overall), search)
        # Only a risk between two or more real clauses is kept: one clause repeats its review, a gap is not reported.
        [_, found] = result['findings']
        self.assertEqual((found['clause_title'], found['risk_level']), ('', 'MEDIUM'))
        self.assertIn('Liên quan: Điều 1. Đối tượng; Điều 5. Phạt vi phạm.', found['explanation'])
        self.assertTrue(result['summary'].startswith('Bên B chịu phần lớn rủi ro.'))

    def test_progress_reports_law_retrieval_each_clause_and_the_whole_contract(self):
        seen = []
        risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([]), search, progress=lambda stage, done, total: seen.append((stage, done, total)))
        self.assertEqual(seen, [('retrieving_law', 0, 2), ('clauses', 1, 2), ('clauses', 2, 2), ('whole_contract', 2, 2)])


    def test_a_quote_may_differ_from_the_clause_only_in_letter_case(self):
        result = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([penalty_risk(contract_quote='bên B CHỊU phạt 20% giá trị hợp đồng')]), search)
        self.assertEqual(len(result['findings']), 1)

    def test_an_overall_summary_the_second_reading_does_not_confirm_is_not_shown(self):
        overall = dict(summary='Hợp đồng không ghi giá.', risks=[])
        result = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([], overall=overall, summary_verdict=False), search)
        self.assertNotIn('không ghi giá', result['summary'])
        self.assertTrue(result['summary'].startswith('Chưa phát hiện rủi ro được xác nhận.'))


class SecondReadingTests(SimpleTestCase):
    """Clause risks are checked against the supplied text; a contract-wide claim gets a second reading of its clauses."""
    def claims(self, model):
        return [b for b in model.briefs if '## Rủi ro' in b and 'Điều khoản cần phân tích' not in b]

    def test_a_contract_wide_risk_is_checked_on_the_clauses_it_names(self):
        overall = dict(summary='', risks=[dict(category='Mâu thuẫn', risk_level='LOW', explanation='Điều 5 mâu thuẫn Điều 1.',
                                               recommendation='', disadvantaged_party=None, clause_ids=[0, 1])])
        model = Model([], overall=overall)
        risk.analyze_clauses(CLAUSES, 'HĐ', [], model, search)
        [claim] = [c for c in self.claims(model) if '## Rủi ro chung đề xuất' in c]
        self.assertIn('Bên A bán cho Bên B 100 tấn thép', claim)
        self.assertIn('Bên B chịu phạt 20%', claim)

    def test_a_risk_is_kept_only_when_it_copies_words_that_are_in_the_cited_law(self):
        joined = 'Điều 301. Mức phạt vi phạm. Mức phạt không quá 8% giá trị phần nghĩa vụ hợp đồng bị vi phạm.'
        invented = 'Mức phạt không quá 8% giá trị phần nghĩa vụ hợp đồng bị vi phạm. Mức phạt không vượt thiệt hại thực tế.'
        for words, kept in ((Model.LAW_WORDS, 1), (joined, 1), (invented, 0),
                            ('lãi chậm trả không quá 150% lãi suất', 0), ('8%', 0), ('', 0)):
            with self.subTest(words=words):
                result = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([penalty_risk(law_quote=words)]), search)
                self.assertEqual(len(result['findings']), kept)

    def test_a_risk_citing_no_law_is_a_drafting_suggestion_outside_the_score(self):
        result = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([penalty_risk(law_ids=[], law_quote='', risk_level='HIGH')],
                                                              overall=dict(summary='', risks=[])), search)
        self.assertEqual([(f['risk_level'], f['suggestion']) for f in result['findings']], [('LOW', True)])
        self.assertEqual((result['overall_score'], result['risk_level']), (0, 'LOW'))
        self.assertIn('Có 1 gợi ý soạn thảo (không tính vào điểm rủi ro).', result['summary'])
        self.assertTrue(result['summary'].startswith('Chưa phát hiện rủi ro được xác nhận.'))

    def test_a_risk_the_model_reads_as_unclear_is_a_suggestion_that_keeps_its_citation(self):
        result = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([penalty_risk(kind='unclear', risk_level='MEDIUM')],
                                                              overall=dict(summary='', risks=[])), search)
        [found] = result['findings']
        self.assertEqual((found['risk_level'], found['suggestion'], found['law_sources']), ('LOW', True, ['E7']))
        self.assertEqual((result['overall_score'], result['risk_level']), (0, 'LOW'))
        # An unclear point whose law quote is not in the law keeps no citation, but is still shown as a suggestion.
        loose = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([penalty_risk(kind='unclear', law_quote='không có')],
                                                             overall=dict(summary='', risks=[])), search)
        self.assertEqual([(f['suggestion'], f['law_sources']) for f in loose['findings']], [(True, [])])

    def test_a_contract_wide_risk_is_no_graver_than_the_legal_risks_it_joins(self):
        wide = lambda: dict(summary='', risks=[dict(category='Một bên chịu rủi ro', risk_level='HIGH', explanation='Bên B gánh rủi ro.',
                                                    recommendation='', disadvantaged_party='Bên B', clause_ids=[0, 1])])
        backed = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([penalty_risk(risk_level='MEDIUM')], overall=wide()), search)
        self.assertEqual([(f['clause_title'], f['risk_level'], f['suggestion']) for f in backed['findings']],
                         [('Điều 5. Phạt vi phạm', 'MEDIUM', False), ('', 'MEDIUM', False)])
        drafting = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([penalty_risk(law_ids=[], law_quote='')], overall=wide()), search)
        self.assertEqual([(f['risk_level'], f['suggestion']) for f in drafting['findings']], [('LOW', True), ('LOW', True)])

    def test_the_answer_schema_allows_only_the_ids_the_brief_supplies(self):
        schema = risk.clause_schema(2, {0, 4})['properties']['risks']['items']['properties']
        self.assertEqual((schema['law_ids']['items']['enum'], schema['related_clause_ids']['items']['enum']), (['L1', 'L2'], [0, 4]))
        self.assertEqual(risk.clause_schema(0, set())['properties']['risks']['items']['properties']['law_ids']['maxItems'], 0)


class RiskRuleTests(SimpleTestCase):
    RULES = [dict(code='PENALTY_CAP', name='Mức phạt vượt trần', severity='HIGH', description='Phạt quá mức luật cho phép')]

    def test_the_brief_lists_the_rules_and_the_parties_the_user_entered(self):
        model = Model([])
        risk.analyze_clauses(CLAUSES, 'HĐ', ['Bên A: Công ty An Phát, MST 0101'], model, search, rules=self.RULES)
        brief = next(b for b in model.briefs if 'Điều khoản cần phân tích [C1]' in b)
        self.assertIn('- PENALTY_CAP: Mức phạt vượt trần (mức HIGH) — Phạt quá mức luật cho phép', brief)
        self.assertIn('- OTHER: rủi ro không thuộc mục nào ở trên', brief)
        self.assertIn('Các bên: Bên A: Công ty An Phát, MST 0101', brief)

    def test_a_finding_keeps_a_listed_rule_code_and_an_unknown_one_becomes_other(self):
        for code, filed in (('penalty_cap', 'PENALTY_CAP'), ('INVENTED', 'OTHER'), (None, 'OTHER')):
            result = risk.analyze_clauses(CLAUSES, 'HĐ', [], Model([penalty_risk(rule_code=code)]), search, rules=self.RULES)
            self.assertEqual(result['findings'][0]['rule_code'], filed)


class ReferencedProvisionTests(SimpleTestCase):
    """A retrieved provision brings the articles it cites, marked with the provision that cites them."""
    def index(self):
        from types import SimpleNamespace
        civil = dict(version=SimpleNamespace(pk=1), document='LAW-2 — Bộ luật Dân sự', status='Còn hiệu lực',
                     clauses=[dict(title='Điều 466. Nghĩa vụ trả nợ', content='Điều 466...', source_ids=['a1', 'a2']),
                              dict(title='Điều 468. Lãi suất', content='Điều 468. Lãi suất\nKhông vượt quá 20%/năm.', source_ids=['b1'])],
                     relations=[dict(kind='references', from_id='a2', to_id='b1', mention='Điều 468 của Bộ luật này')],
                     links=[dict(source_leaf_id='a1', target_source_leaf_id='c1', to_run=9)])
        trade = dict(version=SimpleNamespace(pk=2), document='LAW-3 — Luật Thương mại', status='Hết hiệu lực một phần',
                     clauses=[dict(title='Điều 301. Mức phạt', content='Điều 301...', source_ids=['c1'])], relations=[], links=[])
        return lambda version_id=None, run_id=None: civil if version_id == 1 else trade if run_id == 9 else None

    def test_cited_articles_in_the_same_and_another_document_are_added_once(self):
        seeds = [dict(version_id=1, clause_title='Điều 466. Nghĩa vụ trả nợ', leaf_ids=['a1', 'a2'])]
        added = risk.referenced_provisions(seeds, self.index())
        self.assertEqual([(a['clause_title'], a['document'], a['cited_by']) for a in added],
                         [('Điều 468. Lãi suất', 'LAW-2 — Bộ luật Dân sự', 1), ('Điều 301. Mức phạt', 'LAW-3 — Luật Thương mại', 1)])
        # An article already retrieved is not added again.
        both = seeds + [dict(version_id=1, clause_title='Điều 468. Lãi suất', leaf_ids=['b1'])]
        self.assertEqual([a['clause_title'] for a in risk.referenced_provisions(both, self.index())], ['Điều 301. Mức phạt'])

    def test_the_brief_says_which_provision_cites_an_added_one(self):
        model = Model([])
        cited = dict(source_id='ref:1:1', document='LAW-2 — Bộ luật Dân sự', status='Còn hiệu lực', heading='',
                     clause_title='Điều 468. Lãi suất', text='Điều 468. Lãi suất', cited_by=1)
        risk.analyze_clauses(CLAUSES, 'HĐ', [], model, search, references=lambda provisions: [cited])
        brief = next(b for b in model.briefs if 'Điều khoản cần phân tích [C1]' in b)
        self.assertIn('### [L2] Điều 468. Lãi suất — Bộ luật Dân sự — Còn hiệu lực — được [L1] dẫn chiếu', brief)
