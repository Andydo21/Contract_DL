"""GLiNER reads clause numbers and parties, GLiNER2 links roles; only clauses and parties reach the database."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from ai_extract.models import Clause, ExtractedEntity
from ai_extract.services.contract_clause_service import (
    CLAUSE_LABEL, PARTY_LABEL, REFERENCE_LABEL, ROLE_OPTIONS, SCHEMA, assign_roles, build_clauses, clause_starts,
    find_clause_numbers, find_parties, infer_contract_clauses, link_roles, prepare_contract_clauses, read_role_markers,
    source_text)
from ai_extract.services.document_graph_service import projection
from ai_extract.services.gliner_identity_classifier import merge_contract_names
from contracts.models import Company, Contract, ContractVersion

TEXT = ('BÊN A: CÔNG TY MINH ANH. BÊN B: CÔNG TY HÒA BÌNH. '
        'Điều 1. Đối tượng. Bên B bán thép theo Điều 3 của hợp đồng này. '
        'Điều 2. Thanh toán. Bên A trả trong 30 ngày. '
        'Điều 3. Giao hàng. Bên B giao trước tháng 12.')


def number(digit, occurrence=0):
    position = -1
    for _ in range(occurrence+1):
        position = TEXT.index('Điều '+digit, position+1)
    start = position+len('Điều ')
    return dict(label=CLAUSE_LABEL, text=digit, start=start, end=start+1, confidence=.99)


def party(role, name, confidence=.99):
    start = TEXT.index(name)
    return dict(role=role, name=name, start=start, end=start+len(name), confidence=confidence)


SPANS = dict(schema=SCHEMA, starts=[number('1'), number('3'), number('2'), number('3', 1)],
             parties=[party('A', 'CÔNG TY MINH ANH'), party('B', 'CÔNG TY HÒA BÌNH')])


class ClauseBoundaryTests(SimpleTestCase):
    def test_inline_reference_does_not_start_a_clause(self):
        self.assertEqual([span['text'] for span in clause_starts(SPANS['starts'], TEXT)], ['1', '2', '3'])

    def test_a_heading_beats_an_earlier_citation_of_the_same_number(self):
        text = 'Điều 1. Hàng\nGiao theo Điều 2 của hợp đồng.\nĐiều 2. Giá\nĐiều 3. Giao'
        spans = [dict(text=t, start=text.index(t, offset)) for t, offset in (('Điều 1', 0), ('Điều 2', 0), ('Điều 2', 30), ('Điều 3', 0))]
        self.assertEqual([s['start'] for s in clause_starts(spans, text)], [0, text.index('Điều 2. Giá'), text.index('Điều 3')])

    def test_clause_runs_until_the_next_detected_clause(self):
        result = build_clauses(TEXT, [], SPANS)
        self.assertEqual([c['title'] for c in result['clauses']],
                         ['Thông tin các bên', 'Điều 1. Đối tượng', 'Điều 2. Thanh toán', 'Điều 3. Giao hàng'])
        self.assertIn('theo Điều 3', result['clauses'][1]['content'])
        self.assertTrue(result['clauses'][2]['content'].startswith('Điều 2.'))
        self.assertTrue(result['clauses'][2]['content'].endswith('30 ngày.'))
        self.assertEqual(result['clauses'][0]['clause_type'], 'preamble')

    def test_tax_codes_and_amounts_do_not_extend_the_clause_sequence(self):
        spans = [dict(text=text, start=index) for index, text in enumerate(
            ['0101234567', 'Điều 1', 'Điều 2', 'Điều 3', '24 tháng', '12/2026'])]
        self.assertEqual([s['text'] for s in clause_starts(spans, TEXT)], ['Điều 1', 'Điều 2', 'Điều 3'])

    def test_one_heading_the_model_missed_does_not_split_the_sequence(self):
        spans = [dict(text=text, start=index) for index, text in enumerate(['Article 1', 'Article 2', 'Article 4', 'Article 5'])]
        self.assertEqual(len(clause_starts(spans, TEXT)), 4)

    def test_clause_numbers_are_read_in_other_languages_and_numeral_systems(self):
        for headings in (['Article 1', 'Article 2', 'Article 3'], ['ARTICLE I', 'ARTICLE II', 'ARTICLE IV'], ['第一条', '第二条', '第十二条'][:2],
                         ['第1条', '第2条', '第3条'], ['제1조', '제2조', '제3조'], ['Статья 1', 'Статья 2', 'Статья 3'],
                         ['§ 1', '§ 2', '§ 3'], ['Cláusula 1', 'Cláusula 2', 'Cláusula 3']):
            with self.subTest(headings=headings):
                reference = dict(text=headings[-1], start=1)
                spans = [dict(text=headings[0], start=0), reference]+[dict(text=text, start=index) for index, text in enumerate(headings[1:], 2)]
                self.assertEqual([s['text'] for s in clause_starts(spans, TEXT)], headings)

    def test_han_tens_keep_their_value(self):
        spans = [dict(text=text, start=index) for index, text in enumerate(['第十条', '第十一条', '第十二条', '第二十条'])]
        self.assertEqual([s['text'] for s in clause_starts(spans, TEXT)], ['第十条', '第十一条', '第十二条'])

    def test_document_without_clauses_is_not_split(self):
        for starts in ([], [number('1')]):
            with self.subTest(starts=len(starts)):
                result = build_clauses(TEXT, [], dict(starts=starts, parties=SPANS['parties']))
                self.assertEqual(result['status'], 'no_clauses')
                self.assertEqual(result['clauses'], [])

    def test_a_contract_is_split_even_when_its_parties_are_misread(self):
        for parties in ([], [party('B', 'CÔNG TY HÒA BÌNH')]):
            with self.subTest(parties=len(parties)):
                result = build_clauses(TEXT, [], dict(SPANS, parties=parties))
                self.assertEqual((result['status'], len(result['parties'])), ('complete', len(parties)))
                self.assertTrue(result['clauses'])

    def test_a_law_keeps_its_articles_and_no_parties(self):
        result = build_clauses(TEXT, [], SPANS, is_contract=False)
        self.assertEqual((result['status'], result['parties']), ('complete', []))

    def test_unresolved_role_keeps_the_party_name(self):
        result = build_clauses(TEXT, [], dict(SPANS, parties=[party(None, 'CÔNG TY MINH ANH'), party('B', 'CÔNG TY HÒA BÌNH')]))
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([(p['role'], p['name']) for p in result['parties']],
                         [(None, 'CÔNG TY MINH ANH'), ('B', 'CÔNG TY HÒA BÌNH')])

    def test_gliner_names_parties_without_role_words_or_duplicates(self):
        spans = [dict(label=PARTY_LABEL, text='CÔNG TY B', start=20, end=29, score=.9),
                 dict(label=REFERENCE_LABEL, text='BÊN A', start=0, end=5, score=.99),
                 dict(label=PARTY_LABEL, text='Công ty A', start=8, end=17, score=.8),
                 dict(label=PARTY_LABEL, text='CÔNG TY A', start=40, end=49, score=.95)]
        network = SimpleNamespace(inference=lambda **options: [spans])
        self.assertEqual([(p['name'], p['confidence']) for p in find_parties('x', network)],
                         [('CÔNG TY B', .9), ('CÔNG TY A', .95)])

    def named(self, text, *names):
        return [dict(name=name, start=text.index(name), end=text.index(name)+len(name), confidence=.9) for name in names]

    def test_role_words_are_read_in_any_language_and_either_order(self):
        for text, first, second, roles in (
                ('Bên A: Minh Anh\nBên B: Hòa Bình', 'Minh Anh', 'Hòa Bình', ['A', 'B']),
                ('BÊN B: Minh Anh\nBÊN A: Hòa Bình', 'Minh Anh', 'Hòa Bình', ['B', 'A']),
                ('Minh Anh (sau đây gọi là Bên A) và Hòa Bình (sau đây gọi là Bên B) cùng ký.', 'Minh Anh', 'Hòa Bình', ['A', 'B']),
                ('Minh Anh\n(sau đây gọi là Bên A)\nHòa Bình\n(sau đây gọi là Bên B)', 'Minh Anh', 'Hòa Bình', ['A', 'B']),
                ('Party A: Sunrise JSC, tax code 01.\nParty B: Blue Ocean Ltd.', 'Sunrise JSC', 'Blue Ocean Ltd', ['A', 'B']),
                ('Between Northwind Inc ("Party A") and Harbor LLC ("Party B").', 'Northwind Inc', 'Harbor LLC', ['A', 'B']),
                ('Partie A : Soleil SARL.\nPartie B : Mer Bleue SA.', 'Soleil SARL', 'Mer Bleue SA', ['A', 'B']),
                ('Parte A: Sol S.A.\nParte B: Mar S.L.', 'Sol S.A', 'Mar S.L', ['A', 'B']),
                ('Partei A: Nord GmbH.\nPartei B: Blau AG.', 'Nord GmbH', 'Blau AG', ['A', 'B']),
                ('Сторона А: ООО Север.\nСторона Б: АО Вода.', 'ООО Север', 'АО Вода', ['A', 'B']),
                ('甲方:北京光明公司\n乙方:上海海洋公司', '北京光明公司', '上海海洋公司', ['A', 'B']),
                ('甲:日の出商事\n乙:青海ソフト', '日の出商事', '青海ソフト', ['A', 'B']),
                ('갑: 한빛상사\n을: 푸른바다', '한빛상사', '푸른바다', ['A', 'B'])):
            with self.subTest(text=text):
                parties = self.named(text, first, second)
                read_role_markers(text, parties)
                self.assertEqual([p['role'] for p in parties], roles)

    def test_preamble_mentions_do_not_override_the_role_on_a_partys_own_line(self):
        text = 'Giữa Bên A và Bên B thỏa thuận:\nBên A: Minh Anh\nBên B: Hòa Bình'
        parties = self.named(text, 'Minh Anh', 'Hòa Bình')
        self.assertEqual([p['role'] for p in link_roles(text, parties)], ['A', 'B'])

    def test_representative_does_not_take_the_role_from_the_company(self):
        text = 'Bên A: Minh Anh\nĐại diện: Ông Bình\nBên B: Hòa Bình'
        parties = self.named(text, 'Minh Anh', 'Ông Bình', 'Hòa Bình')
        self.assertEqual([p['role'] for p in link_roles(text, parties)], ['A', None, 'B'])

    def test_contract_without_role_words_does_not_invent_a_and_b(self):
        text = 'Seller: Minh Anh\nBuyer: Hòa Bình'
        parties = self.named(text, 'Minh Anh', 'Hòa Bình')
        predictor = SimpleNamespace(classify_text=lambda *args: self.fail('no role word to link'))
        self.assertEqual([p['role'] for p in link_roles(text, parties, predictor)], [None, None])

    def test_gliner2_links_only_when_written_role_words_are_ambiguous(self):
        text = 'Minh Anh, Hòa Bình, Bên A, Bên B'
        parties = self.named(text, 'Minh Anh', 'Hòa Bình')
        label = {v: k for k, v in ROLE_OPTIONS.items()}
        answers = iter([label['B'], label['A']])
        linked = link_roles(text, parties, SimpleNamespace(classify_text=lambda t, o: dict(role=next(answers))))
        self.assertEqual([p['role'] for p in linked], ['B', 'A'])

    def test_common_korean_particle_and_han_words_are_not_role_words(self):
        for text in ('계약을 체결한다', '甲骨文公司', '甲乙双方'):
            with self.subTest(text=text):
                self.assertEqual(read_role_markers(text, []), set())

    def test_roles_need_exactly_one_a_and_one_b(self):
        text = 'Công ty A. Công ty B.'
        parties = [dict(name='Công ty A', start=0, end=9, confidence=.9), dict(name='Công ty B', start=11, end=20, confidence=.9)]
        label = {v: k for k, v in ROLE_OPTIONS.items()}
        answers = iter([label[None], label['A']])
        linked = assign_roles(text, parties, SimpleNamespace(classify_text=lambda t, o: dict(role=next(answers))))
        self.assertEqual([p['role'] for p in linked], [None, None])

    def test_gliner2_only_links_roles_and_a_role_claimed_twice_stays_unresolved(self):
        text = 'Bên A: Công ty A. Bên B: Công ty B.'
        parties = [dict(name='Công ty A', start=7, end=16, confidence=.9), dict(name='Công ty B', start=25, end=34, confidence=.9)]
        label = {v: k for k, v in ROLE_OPTIONS.items()}
        answers = iter([label['A'], label['B']])
        linked = assign_roles(text, [dict(p) for p in parties], SimpleNamespace(classify_text=lambda t, o: dict(role=next(answers))))
        self.assertEqual([p['role'] for p in linked], ['A', 'B'])
        same = assign_roles(text, [dict(p) for p in parties], SimpleNamespace(classify_text=lambda t, o: dict(role=label['B'])))
        self.assertEqual([p['role'] for p in same], [None, None])

    def test_each_source_block_is_read_separately_with_document_offsets(self):
        seen = []
        def inference(texts, labels, **options):
            if labels != [CLAUSE_LABEL]:
                return [[]]
            seen.extend(texts)
            return [[dict(text='Điều 1', start=0, end=6, score=.9)] for _ in texts]
        text = 'mã số thuế 0101\nĐiều 1. Giá'
        result = infer_contract_clauses(text, [[0, 15], [16, len(text)]], network=SimpleNamespace(inference=inference))
        self.assertEqual(seen, ['mã số thuế 0101', 'Điều 1. Giá'])
        self.assertEqual([s['start'] for s in result['starts']], [0, 16])

    def test_page_furniture_is_not_clause_text(self):
        text, sources = source_text(dict(leaves=[
            dict(chunk_id='h', text='Trang 1', layout_type='page_header'),
            dict(chunk_id='x', text='Ẩn', retrieval_excluded=True),
            dict(chunk_id='a', text='Điều 1. A'), dict(chunk_id='b', text='Điều 2. B')]))
        self.assertEqual(text, 'Điều 1. A\nĐiều 2. B')
        self.assertEqual([s[2] for s in sources], ['a', 'b'])

    def test_long_block_is_read_in_windows_with_document_offsets(self):
        windows = []
        def inference(texts, labels, **options):
            windows.extend(texts)
            return [[dict(text='Điều 9', start=text.find('Điều 9'), end=text.find('Điều 9')+6, score=.99)] if 'Điều 9' in text else [] for text in texts]
        long_text = 'từ '*200+'Điều 9. '+'từ '*200
        starts = find_clause_numbers(long_text, [[0, len(long_text)]], SimpleNamespace(inference=inference))
        self.assertEqual([s['start'] for s in starts], [long_text.index('Điều 9')])
        self.assertGreater(len(windows), 2)


class ClausePersistenceTests(TestCase):
    def setUp(self):
        company = Company.objects.create(company_name='Tenant', tax_code='T1') if hasattr(Company, 'tax_code') else Company.objects.create(company_name='Tenant')
        self.contract = Contract.objects.create(title='Sale', contract_code='C-1', company=company)
        self.version = ContractVersion.objects.create(contract=self.contract, version_number=1)
        self.tree = dict(source_fingerprint='fp', leaves=[dict(chunk_id='a', text=TEXT)],
                         nodes=[dict(id='root', kind='document', title='Sale')])

    def prepare(self):
        with patch('ai_extract.repositories.layout_repository.ensure_write_connection'):
            return prepare_contract_clauses(self.tree, self.version, requester=lambda text, units: SPANS)

    def test_clauses_reach_the_database_and_entities_are_the_gliner_ones_of_each_clause(self):
        from ai_extract.repositories.extraction_repository import replace_clause_entities
        self.prepare()
        self.assertEqual(Clause.objects.filter(version=self.version).count(), 4)
        # The party names the clause step read are kept; a GLiNER rerun replaces only the other entities.
        parties = [('PARTY_A', 'CÔNG TY MINH ANH'), ('PARTY_B', 'CÔNG TY HÒA BÌNH')]
        self.assertEqual(sorted(ExtractedEntity.objects.values_list('entity_type', 'entity_value')), parties)
        clauses = self.tree['contract_clauses']['clauses']
        # All clauses here come from one block, so the name decides which of them it belongs to.
        entities = [dict(name='30 ngày', identity_name_key='30 ngày', entity_type='ENTITY', confidence=0.8, source_ids=['a'])]
        self.assertEqual(replace_clause_entities(self.version, clauses, entities), 1)
        self.assertEqual(replace_clause_entities(self.version, clauses, entities), 1)
        self.assertEqual(sorted(ExtractedEntity.objects.filter(entity_type__startswith='PARTY').values_list('entity_type', 'entity_value')), parties)
        [row] = ExtractedEntity.objects.filter(entity_type='ENTITY')
        self.assertEqual((row.clause.clause_title, row.entity_type, row.entity_value), ('Điều 2. Thanh toán', 'ENTITY', '30 ngày'))

    def test_contract_api_exposes_parties_and_clause_type_for_the_frontend(self):
        from contracts.services.contract_service import ContractService
        self.prepare()
        details = ContractService().get_contract_details(self.contract.pk, version_id=self.version.pk)
        # Parties are the ones the user enters; the names the clause step read are not shown as parties.
        self.assertEqual(details['parties'], [])
        self.assertEqual(details['clauses'][0]['clause_type'], 'preamble')

    def test_contract_api_shows_the_parties_the_user_entered(self):
        from contracts.services.contract_service import ContractService
        from contracts.models import ContractParty
        self.prepare()
        ContractParty.objects.create(contract=self.contract, party_type='Bên A', party_name='CÔNG TY MINH ANH', tax_code='0101')
        details = ContractService().get_contract_details(self.contract.pk, version_id=self.version.pk)
        self.assertEqual([(p['label'], p['name'], p['tax_code']) for p in details['parties']], [('Bên A', 'CÔNG TY MINH ANH', '0101')])

    def test_each_clause_links_to_its_original_pages(self):
        from contracts.services.contract_service import ContractService
        from ai_extract.models import LayoutExtractionRun
        first, second = TEXT[:TEXT.index('Điều 3. Giao')].strip(), TEXT[TEXT.index('Điều 3. Giao'):]
        self.tree['leaves'] = [dict(chunk_id='a', text=first, page_number=1), dict(chunk_id='b', text=second, page_number=2)]
        spans = dict(SPANS, starts=[dict(s) for s in SPANS['starts']])
        with patch('ai_extract.repositories.layout_repository.ensure_write_connection'):
            prepare_contract_clauses(self.tree, self.version, requester=lambda text, units: spans)
        LayoutExtractionRun.objects.create(version=self.version, status='COMPLETED', structure=self.tree)
        details = ContractService().get_contract_details(self.contract.pk, version_id=self.version.pk)
        self.assertEqual({c['title']: c['source_pages'] for c in details['clauses']}, {
            'Thông tin các bên': [1], 'Điều 1. Đối tượng': [1], 'Điều 2. Thanh toán': [1], 'Điều 3. Giao hàng': [2]})

    def test_rerun_replaces_instead_of_duplicating(self):
        self.prepare()
        self.prepare()
        self.assertEqual(Clause.objects.filter(version=self.version).count(), 4)
        self.assertEqual(ExtractedEntity.objects.count(), 2)

    def test_no_clause_result_keeps_existing_rows(self):
        self.prepare()
        with patch('ai_extract.repositories.layout_repository.ensure_write_connection'):
            result = prepare_contract_clauses(self.tree, self.version, requester=lambda text, units: dict(starts=[], parties=[]))
        self.assertEqual(result['status'], 'no_clauses')
        self.assertEqual(Clause.objects.filter(version=self.version).count(), 4)

    def test_clauses_and_parties_are_projected_to_neo4j_with_evidence(self):
        self.prepare()
        run = SimpleNamespace(pk=9, version_id=self.version.pk, version=self.version)
        _, nodes, edges = projection(run, self.tree, include_review=False)
        self.assertEqual(sum(n.get('category') == 'contract_clause' for n in nodes), 4)
        self.assertEqual({n['name'] for n in nodes if n.get('is_party')}, {'CÔNG TY MINH ANH', 'CÔNG TY HÒA BÌNH'})
        kinds = [e['type'] for e in edges]
        self.assertEqual(kinds.count('HAS_CLAUSE'), 4)
        self.assertEqual(kinds.count('NAMES_PARTY'), 2)
        self.assertEqual(kinds.count('HAS_EVIDENCE'), 4)

    def projected_entities(self, *names):
        self.prepare()
        self.tree['knowledge_graph'] = dict(entities=[dict(key=f'k{i}', name=name, source_ids=[], entity_type='ENTITY', canonical_key=f'c{i}')
                                                      for i, name in enumerate(names)])
        run = SimpleNamespace(pk=9, version_id=self.version.pk, version=self.version)
        return [n for n in projection(run, self.tree, include_review=False)[1] if n.get('category') == 'entity']

    def test_party_name_and_role_word_share_one_node_with_the_party(self):
        role = next(p for p in self.prepare_parties() if p['name'] == 'CÔNG TY MINH ANH')['role']
        nodes = self.projected_entities('công ty minh anh', f'Bên {role}', 'BÊN '+role, 'Tòa án')
        party = next(n for n in nodes if n['name'] == 'CÔNG TY MINH ANH')
        self.assertEqual((party['is_party'], party['occurrence_count'], party['role']), (True, 3, role))
        self.assertEqual(sorted(n['name'] for n in nodes), sorted(['CÔNG TY MINH ANH', 'CÔNG TY HÒA BÌNH', 'Tòa án']))

    def test_party_the_entity_step_missed_still_gets_a_node(self):
        self.assertEqual(sum(n.get('is_party', False) for n in self.projected_entities('Tòa án')), 2)

    def prepare_parties(self):
        self.prepare()
        return self.tree['contract_clauses']['parties']

    def projected_with_blocks(self, leaves, spans):
        self.tree['leaves'] = leaves
        with patch('ai_extract.repositories.layout_repository.ensure_write_connection'):
            prepare_contract_clauses(self.tree, self.version, requester=lambda text, units: spans)
        run = SimpleNamespace(pk=9, version_id=self.version.pk, version=self.version)
        return projection(run, self.tree, include_review=False)

    def test_block_contains_every_clause_it_holds_and_order_stays_on_the_clause_nodes(self):
        box = dict(bbox=[10, 10, 500, 500], page_number=1, source_chunk_id='block:7')
        scope, nodes, edges = self.projected_with_blocks([dict(chunk_id='a', text=TEXT, **box)], SPANS)
        block = scope['key']+':layout-block:1:block:7'
        self.assertEqual(sum(e['type'] == 'CONTAINS' and e['from_key'] == block and ':clause:' in e['to_key'] for e in edges), 4)
        self.assertEqual(sorted(n['ordinal'] for n in nodes if n.get('category') == 'contract_clause'), [0, 1, 2, 3])
        self.assertNotIn('NEXT_CLAUSE', {e['type'] for e in edges})

    def test_stale_clauses_are_not_projected(self):
        self.prepare()
        self.tree['contract_clauses']['source_fingerprint'] = 'old'
        run = SimpleNamespace(pk=9, version_id=self.version.pk, version=self.version)
        _, nodes, _ = projection(run, self.tree, include_review=False)
        self.assertFalse(any(n.get('category') == 'contract_clause' for n in nodes))


class MergeContractNameTests(SimpleTestCase):
    def tree(self, decisions=(), status='complete'):
        entities = [dict(key=f'k{i}', name=name, source_id=f's{i}', start=0, canonical_key=f'c{i}', identity_resolution_status='unresolved')
                    for i, name in enumerate(('Bên A', 'bên a', 'Bên A', 'Tòa án'))]
        pairs = [dict(id='p', left=dict(scope=dict(source_id='s0', mention_start=0)), right=dict(scope=dict(source_id='s2', mention_start=0)))]
        return dict(contract_clauses=dict(status=status), knowledge_graph=dict(entities=entities),
                    identity_resolution=dict(status='complete', pairs=pairs, decisions=list(decisions)))

    def keys(self, tree):
        return [e['canonical_key'] for e in tree['knowledge_graph']['entities']]

    def test_repeated_name_becomes_one_entity(self):
        tree = self.tree([dict(id='p', status='unresolved')])
        self.assertEqual(merge_contract_names(tree), 2)
        self.assertEqual(self.keys(tree), ['c0', 'c0', 'c0', 'c3'])
        self.assertEqual(tree['identity_resolution']['canonical_entities'], 2)

    def test_explicit_different_keeps_them_apart(self):
        tree = self.tree([dict(id='p', status='different')])
        merge_contract_names(tree)
        self.assertEqual(self.keys(tree), ['c0', 'c0', 'c2', 'c3'])

    def test_rerun_changes_nothing(self):
        tree = self.tree()
        merge_contract_names(tree)
        self.assertEqual(merge_contract_names(tree), 0)
        self.assertEqual(self.keys(tree), ['c0', 'c0', 'c0', 'c3'])

    def test_document_that_is_not_a_contract_is_left_alone(self):
        tree = self.tree(status='no_clauses')
        self.assertEqual(merge_contract_names(tree), 0)
        self.assertEqual(self.keys(tree), ['c0', 'c1', 'c2', 'c3'])
