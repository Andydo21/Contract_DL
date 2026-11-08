"""The risk review reads the whole contract through its graph and stores only complete results."""
import json
from decimal import Decimal
from unittest.mock import Mock, patch

from types import SimpleNamespace

import requests
from django.test import SimpleTestCase, TestCase

from ai_extract.models import Clause
from ai_extract.services.contract_pipeline_service import QwenContextLimitError, QwenGatewayError
from NewIdea.services.risk_review_service import CHECKS, RiskReviewUnavailable, analyze_contract, contract_from_graph
from contracts.models import AIAnalysis, Company, Contract, ContractVersion, RiskFinding, RiskRule
from contracts.repositories import RiskRepository
from contracts.services import ContractService


def contract(*contents):
    return [dict(title=f'Điều {index}', content=text) for index, text in enumerate(contents, 1)]


def fake_model(answers=None, supported=True, default_quote=None):
    """Answer each checklist question by its category, and every verification the same way."""
    answers = answers or {}
    def ask(task, payload):
        if 'supported' in payload['schema']['properties']:
            return dict(supported=supported, reason='')
        for check in CHECKS:
            if check.get('question', check.get('presence')) in payload['instruction']:
                answer = answers.get(check['category'])
                if isinstance(answer, Exception):
                    raise answer
                if answer:
                    return answer
                return dict(status='present', clause_id=0) if 'presence' in check else dict(status='none', matches=[])
        raise AssertionError('Unknown question')
    return ask


def no_law(law, article):
    return ''


def match(*evidence, explanation='Giải thích', party=None):
    return dict(status='found', matches=[dict(evidence=[dict(clause_id=c, quote=q) for c, q in evidence], explanation=explanation, disadvantaged_party=party)])


class ChecklistTests(SimpleTestCase):
    def test_a_literal_quote_that_is_confirmed_becomes_a_warning_with_fixed_level_and_category(self):
        answers = {'Chấm dứt một chiều': match((1, 'Bên B được chấm dứt'), party='Bên A')}
        result = analyze_contract(contract('Mở đầu', 'Bên B được chấm dứt bất cứ lúc nào'), no_law, fake_model(answers))
        finding = result['findings'][0]
        self.assertEqual((finding['clause_title'], finding['risk_category'], finding['risk_level'], finding['disadvantaged_party']),
                         ('Điều 2', 'Chấm dứt một chiều', 'HIGH', 'Bên A'))
        self.assertIn('Bên B được chấm dứt', finding['explanation'])

    def test_same_quotes_repeated_by_the_model_count_once(self):
        repeated = match((0, 'A'))
        repeated['matches'] = repeated['matches']*2
        result = analyze_contract(contract('A'), no_law, fake_model({'Chấm dứt một chiều': repeated}))
        self.assertEqual((len(result['findings']), result['overall_score']), (1, 30))

    def test_a_quote_not_in_the_contract_is_rejected(self):
        answers = {'Chấm dứt một chiều': match((0, 'câu không có thật'))}
        result = analyze_contract(contract('Nội dung khác'), no_law, fake_model(answers))
        self.assertEqual(result['findings'], [])
        self.assertIn('Đã loại 1', result['summary'])

    def test_quote_tolerates_ocr_line_breaks_but_not_changed_words(self):
        rows = contract('Bên A trả\ntrong 30 ngày')
        self.assertEqual(len(analyze_contract(rows, no_law, fake_model({'Thanh toán không rõ': match((0, 'Bên A trả trong 30 ngày'))}))['findings']), 1)
        self.assertEqual(analyze_contract(rows, no_law, fake_model({'Thanh toán không rõ': match((0, 'Bên A trả trong 60 ngày'))}))['findings'], [])

    def test_contradiction_needs_quotes_from_two_clauses(self):
        rows = contract('Trả trong 30 ngày', 'Trả trong 90 ngày')
        one = {'Mâu thuẫn về thời hạn': match((0, 'Trả trong 30 ngày'))}
        two = {'Mâu thuẫn về thời hạn': match((0, 'Trả trong 30 ngày'), (1, 'Trả trong 90 ngày'))}
        self.assertEqual(analyze_contract(rows, no_law, fake_model(one))['findings'], [])
        self.assertEqual(len(analyze_contract(rows, no_law, fake_model(two))['findings']), 1)

    def test_a_warning_the_second_call_does_not_confirm_is_dropped(self):
        answers = {'Chấm dứt một chiều': match((0, 'Nội dung'))}
        result = analyze_contract(contract('Nội dung'), no_law, fake_model(answers, supported=False))
        self.assertEqual(result['findings'], [])

    def test_missing_clause_needs_confirmation_and_has_no_clause_title(self):
        answers = {'Thiếu điều khoản giải quyết tranh chấp': dict(status='absent', clause_id=None)}
        result = analyze_contract(contract('Nội dung'), no_law, fake_model(answers))
        self.assertEqual([(f['clause_title'], f['risk_level']) for f in result['findings']], [('', 'MEDIUM')])
        self.assertEqual(analyze_contract(contract('Nội dung'), no_law, fake_model(answers, supported=False))['findings'], [])

    def test_present_clause_that_does_not_exist_is_reported_as_unchecked(self):
        answers = {'Thiếu điều khoản chấm dứt': dict(status='present', clause_id=99)}
        result = analyze_contract(contract('Nội dung'), no_law, fake_model(answers))
        self.assertIn('Chưa kiểm tra được: Thiếu điều khoản chấm dứt', result['summary'])

    def test_score_comes_from_the_confirmed_warnings_only(self):
        answers = {'Chấm dứt một chiều': match((0, 'A')), 'Thời hạn thực hiện không rõ': match((0, 'A')),
                   'Thiếu điều khoản bất khả kháng': dict(status='absent', clause_id=None)}
        self.assertEqual(analyze_contract(contract('A'), no_law, fake_model(answers))['overall_score'], 50)
        self.assertEqual(analyze_contract(contract('A'), no_law, fake_model())['overall_score'], 0)

    def test_score_is_capped_at_100(self):
        answers = {c['category']: match((0, 'A')) for c in CHECKS if 'question' in c and c['level'] == 'HIGH' and not c.get('min_clauses')}
        answers.update({c['category']: match((0, 'A'), (1, 'B')) for c in CHECKS if c.get('min_clauses')})
        self.assertEqual(analyze_contract(contract('A', 'B'), no_law, fake_model(answers))['overall_score'], 100)

    def test_penalty_warning_says_it_depends_on_commercial_law_and_cites_the_stored_article(self):
        answers = {'Mức phạt trên 8%': match((0, 'phạt 50%'))}
        finding = analyze_contract(contract('phạt 50%'), lambda law, article: 'Nội dung điều luật', fake_model(answers))['findings'][0]
        self.assertIn('hợp đồng thương mại', finding['explanation'])
        self.assertIn('Luật Thương mại 2005 Điều 301', finding['recommendation'])

    def test_an_article_not_found_is_not_cited(self):
        answers = {'Mức phạt trên 8%': match((0, 'phạt 50%'))}
        self.assertNotIn('Điều 301', analyze_contract(contract('phạt 50%'), no_law, fake_model(answers))['findings'][0]['recommendation'])

    def test_every_check_sees_the_whole_contract_title_and_parties(self):
        seen = []
        inner = fake_model()
        def ask(task, payload):
            seen.append(json.loads(payload['contract']))
            return inner(task, payload)
        analyze_contract(contract('A', 'B'), no_law, ask, 'Hợp đồng', [dict(role='A', name='Minh Anh')])
        self.assertEqual(len(seen), len(CHECKS))
        self.assertTrue(all(s['contract_title'] == 'Hợp đồng' and len(s['clauses']) == 2 and s['parties'][0]['name'] == 'Minh Anh' for s in seen))

    def test_question_the_model_cannot_answer_is_reported_not_treated_as_clean(self):
        answers = {'Chấm dứt một chiều': QwenContextLimitError(1000, 990, 100)}
        result = analyze_contract(contract('A'), no_law, fake_model(answers))
        self.assertIn('Chưa kiểm tra được: Chấm dứt một chiều', result['summary'])

    def test_no_answer_at_all_fails_the_review(self):
        answers = {c['category']: ValueError('bad') for c in CHECKS}
        with self.assertRaises(ValueError):
            analyze_contract(contract('A'), no_law, fake_model(answers))

    def test_qwen_outage_stops_the_review(self):
        answers = {'Chấm dứt một chiều': QwenGatewayError('down')}
        with self.assertRaises(QwenGatewayError):
            analyze_contract(contract('A'), no_law, fake_model(answers))

    def test_checklist_matches_the_approved_list(self):
        self.assertEqual(len(CHECKS), 13)
        self.assertEqual([c['level'] for c in CHECKS], ['HIGH']*6+['MEDIUM']*5+['LOW']*2)


class GraphRetrievalTests(SimpleTestCase):
    def setUp(self):
        self.tree = dict(source_fingerprint='fp', graph_index=dict(status='ready', fingerprint='fp'), contract_clauses=dict(
            source_fingerprint='fp', clauses=[dict(title='Điều 1', content='Nội dung một'), dict(title='Điều 2', content='Nội dung hai')]))
        self.outline = dict(parties=[dict(role='A', name='Minh Anh')], related_passages=[('a', 'b'), ('a', 'a2'), ('a', 'other')], clauses=[
            dict(ordinal=0, title='Điều 1', leaf_ids=['a', 'a2'], entities=['Thép CT3'], blocks=['p1']),
            dict(ordinal=1, title='Điều 2', leaf_ids=['b'], entities=[], blocks=['p1', 'p2'])])
        for target, value in (('NewIdea.repositories.contract_repository.completed_extraction_run', Mock(return_value=SimpleNamespace(structure=self.tree))),
                              ('ai_extract.services.document_graph_service.graph_scope', Mock(return_value=dict(fingerprint='fp', key='k'))),
                              ('ai_extract.repositories.document_graph_repository.contract_outline', Mock(side_effect=lambda scope: self.outline))):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_order_parties_entities_and_links_come_from_the_graph(self):
        clauses, parties = contract_from_graph(None)
        self.assertEqual(parties, [dict(role='A', name='Minh Anh')])
        self.assertEqual([(c['id'], c['entities'], c['related_clause_ids']) for c in clauses],
                         [(0, ['Thép CT3'], [1]), (1, [], [0])])

    def test_block_containment_and_reading_order_come_from_the_graph(self):
        clauses, _ = contract_from_graph(None)
        self.assertEqual([(c['next_clause_id'], c['same_block_clause_ids']) for c in clauses], [(1, [1]), (None, [0])])

    def test_clause_outside_any_block_has_no_block_neighbours(self):
        self.outline['clauses'][0]['blocks'] = []
        self.assertEqual(contract_from_graph(None)[0][0]['same_block_clause_ids'], [])

    def test_passage_references_become_directed_clause_mentions(self):
        self.outline['references'] = [('b', 'a'), ('a', 'a2'), ('b', 'other')]
        clauses, _ = contract_from_graph(None)
        self.assertEqual([c['mentions_clause_ids'] for c in clauses], [[], [0]])

    def test_text_comes_from_the_extraction_not_the_graph(self):
        self.assertEqual(contract_from_graph(None)[0][0]['content'], 'Nội dung một')

    def test_contract_without_a_ready_graph_is_refused_with_a_clear_reason(self):
        self.tree['graph_index']['status'] = 'unavailable'
        with self.assertRaisesRegex(RiskReviewUnavailable, 'chưa có đồ thị'):
            contract_from_graph(None)

    def test_stale_graph_is_refused(self):
        self.tree['graph_index']['fingerprint'] = 'old'
        with self.assertRaisesRegex(RiskReviewUnavailable, 'cũ'):
            contract_from_graph(None)

    def test_graph_missing_a_clause_is_refused_instead_of_reviewing_part_of_the_contract(self):
        self.outline['clauses'].pop()
        with self.assertRaisesRegex(RiskReviewUnavailable, 'không có đủ'):
            contract_from_graph(None)

    def test_clause_titles_must_match_their_extraction(self):
        self.outline['clauses'][1]['title'] = 'Điều khác'
        with self.assertRaises(RiskReviewUnavailable):
            contract_from_graph(None)


REVIEW = 'NewIdea.services.clause_risk_service.review_version'


class StoredFindingTests(TestCase):
    def setUp(self):
        company = Company.objects.create(company_name='Tenant')
        self.contract = Contract.objects.create(title='Sale', contract_code='C-1', company=company)
        self.version = ContractVersion.objects.create(contract=self.contract, version_number=1)
        for title in ('Điều 1', 'Điều 10'):
            Clause.objects.create(version=self.version, clause_title=title, clause_content='Nội dung')
        closing = patch('django.db.connection.close')
        closing.start()
        self.addCleanup(closing.stop)

    def analyze(self, findings):
        with patch(REVIEW, return_value=dict(overall_score=60, summary='S', findings=findings)):
            ContractService().analyze_contract(self.contract.pk, user=object())

    def row(self, title, **fields):
        return dict(dict(clause_title=title, risk_category='Phạt', risk_level='HIGH', explanation='E', recommendation='R'), **fields)

    def test_finding_goes_only_to_the_clause_with_that_exact_title(self):
        self.analyze([self.row('Điều 1')])
        self.assertEqual([f.clause.clause_title for f in RiskFinding.objects.all()], ['Điều 1'])

    def test_warning_for_the_whole_contract_is_stored_without_a_clause(self):
        self.analyze([self.row('')])
        self.assertIsNone(RiskFinding.objects.get().clause)

    def test_finding_for_an_unknown_clause_is_kept_for_the_reviewer(self):
        self.analyze([self.row('Không có')])
        self.assertIsNone(RiskFinding.objects.get().clause)

    def test_findings_are_filed_under_the_administrator_rules_and_unknown_codes_under_other(self):
        RiskRule.objects.create(rule_code='PENALTY_CAP', rule_name='Mức phạt vượt trần', severity='HIGH')
        self.analyze([self.row('Điều 1', rule_code='PENALTY_CAP', risk_category='Mức phạt vượt trần'),
                      self.row('Điều 10', rule_code='MADE_UP', risk_category='Thanh toán không rõ')])
        filed = {f.rule.rule_code: f for f in RiskFinding.objects.all()}
        self.assertEqual(set(filed), {'PENALTY_CAP', 'OTHER'})
        self.assertTrue(filed['OTHER'].explanation.startswith('Thanh toán không rõ: '))
        # No rule is invented from a category name.
        self.assertEqual(RiskRule.objects.count(), 2)

    def test_failure_message_does_not_expose_the_service_address(self):
        refused = QwenGatewayError('http://internal-host:8000 refused')
        with patch(REVIEW, side_effect=refused), self.assertRaises(RuntimeError) as caught:
            ContractService().analyze_contract(self.contract.pk, user=object())
        self.assertNotIn('internal-host', str(caught.exception))

    def test_a_storage_failure_leaves_the_previous_analysis_intact(self):
        previous = AIAnalysis.objects.create(version=self.version, model_name='old', overall_score=Decimal('5.0'), summary='Cũ')
        answer = dict(overall_score=60, summary='S', findings=[self.row('Điều 1')])
        with patch(REVIEW, return_value=answer), \
             patch('contracts.repositories.RiskFindingRepository.create_finding', side_effect=RuntimeError('db')), \
             self.assertRaises(RuntimeError):
            ContractService().analyze_contract(self.contract.pk, user=object())
        self.assertEqual(list(AIAnalysis.objects.filter(version=self.version)), [previous])

    def test_repository_keeps_an_existing_category(self):
        first, _ = RiskRepository.get_or_create_risk('Phạt', defaults=dict(severity_level='HIGH'))
        second, created = RiskRepository.get_or_create_risk('phạt', defaults=dict(severity_level='LOW'))
        self.assertEqual((first.pk, created), (second.pk, False))
