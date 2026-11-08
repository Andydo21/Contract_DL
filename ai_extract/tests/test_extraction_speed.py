"""Work the extraction avoids without changing who decides: the page sample and the entity comparisons."""
from types import SimpleNamespace
from django.test import SimpleTestCase
from ai_extract.services.gliner_identity_classifier import resolve_identities
from ai_extract.services.surya_inference_service import language_sample

PAGE = 1000*1000


def box(width, height):
    return SimpleNamespace(bbox=[0, 0, width, height])


class LanguageSampleTests(SimpleTestCase):
    def test_the_shortest_blocks_that_hold_words_are_read(self):
        small, line, para, big = box(100, 20), box(800, 30), box(800, 60), box(800, 600)
        self.assertEqual(language_sample([big, small, para, line], PAGE), [line, para])

    def test_a_page_of_tiny_blocks_falls_back_to_the_largest(self):
        a, b, c = box(50, 10), box(100, 10), box(200, 10)
        self.assertEqual(language_sample([a, b, c], PAGE), [c, b])

    def test_a_page_without_text_samples_nothing(self):
        self.assertEqual(language_sample([], PAGE), [])


CONTEXT = 'cơ quan xét xử có thẩm quyền theo quy định của pháp luật hiện hành trong vụ việc số {}'


def tree(names):
    leaves, entities = [], []
    for index, name in enumerate(names):
        text = f'{name} {CONTEXT.format(index)}'
        leaves.append(dict(chunk_id=f'b{index}', text=text, page_number=1, bbox=[0, 0, 1, 1]))
        entities.append(dict(key=f'e{index:03}', name=name, source_ids=[f'b{index}'], start=0))
    return dict(leaves=leaves, knowledge_graph=dict(entities=entities), source_fingerprint='f')


def model(verdict):
    """verdict(left source id, right source id) -> same or different."""
    calls = []

    def request(batch):
        rows = []
        for pair in batch:
            calls.append((pair['left']['scope']['source_id'], pair['right']['scope']['source_id']))
            same = verdict(*calls[-1])
            rows.append(dict(id=pair['id'], status='same' if same else 'different', same=.95 if same else .01, different=.01 if same else .95))
        return dict(decisions=rows)
    return request, calls


def resolve(names, verdict, propose=lambda names: []):
    request, calls = model(verdict)
    data = tree(names)
    run = SimpleNamespace(pk=1, version_id=1, version=SimpleNamespace(contract=SimpleNamespace(company_id=1)))
    return resolve_identities(run, data, request, propose), calls, data['knowledge_graph']['entities']


def first_two(score):
    """Stands in for fusion and the reranker scoring the first two names as look-alikes."""
    return lambda names: [(names[0][0], names[1][0], score)]


class SameNameComparisonTests(SimpleTestCase):
    def test_one_thing_named_often_takes_one_comparison_per_mention(self):
        result, calls, entities = resolve(['Tòa án']*60, lambda a, b: True)
        self.assertEqual(len(calls), 59)
        self.assertEqual(len({e['canonical_key'] for e in entities}), 1)
        self.assertEqual(result['linked'], 60)

    def test_two_things_with_one_name_stay_apart(self):
        group = {f'b{i}': i % 2 for i in range(20)}
        result, calls, entities = resolve(['Tòa án']*20, lambda a, b: group[a] == group[b])
        kinds = {}
        for entity in entities:
            kinds.setdefault(group[entity['source_ids'][0]], set()).add(entity['canonical_key'])
        self.assertEqual([len(keys) for keys in kinds.values()], [1, 1])
        self.assertNotEqual(kinds[0], kinds[1])
        self.assertLess(len(calls), 40)

    def test_different_names_never_reach_the_model(self):
        _, calls, _ = resolve(['Tòa án', 'Viện kiểm sát', 'Bộ Tư pháp'], lambda a, b: True)
        self.assertEqual(calls, [])

    def test_a_name_seen_once_needs_no_comparison(self):
        result, calls, _ = resolve(['Tòa án'], lambda a, b: True)
        self.assertEqual((calls, result['canonical_entities']), ([], 1))


class LookAlikeNameTests(SimpleTestCase):
    def test_a_high_rerank_merges_unless_gliner2_refuses(self):
        result, calls, entities = resolve(['Ủy ban nhân dân', 'Uy ban nhân dân', 'Bộ Tư pháp'], lambda a, b: True, first_two(9.5))
        self.assertEqual(calls, [('b0', 'b1')])
        self.assertEqual(entities[0]['canonical_key'], entities[1]['canonical_key'])
        self.assertNotEqual(entities[0]['canonical_key'], entities[2]['canonical_key'])
        self.assertEqual(result['look_alike'][0]['gliner2'], 'same')

    def test_gliner2_refusal_keeps_the_names_apart(self):
        _, calls, entities = resolve(['Hội đồng trọng tài', 'Hiệp hội trọng tài'], lambda a, b: False, first_two(9.5))
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(entities[0]['canonical_key'], entities[1]['canonical_key'])

    def test_a_low_rerank_is_never_sent_to_gliner2(self):
        _, calls, entities = resolve(['Hội đồng trọng tài', 'Hiệp hội trọng tài'], lambda a, b: True, first_two(8.8))
        self.assertEqual(calls, [])
        self.assertNotEqual(entities[0]['canonical_key'], entities[1]['canonical_key'])

    def test_gliner2_reads_the_second_passage_under_the_first_name(self):
        result, _, _ = resolve(['Toà án', 'Tòa án'], lambda a, b: True, first_two(10.))
        pair = result['pairs'][0]
        self.assertEqual(pair['left']['name'], pair['right']['name'])
        right = pair['right']
        start = right['scope']['mention_start']-right['scope']['quote_start']
        self.assertEqual(right['context'][start:start+len(right['name'])], right['name'])
        self.assertTrue(right['context'].endswith(CONTEXT.format(1)))


class LookAlikeGraphCheckTests(SimpleTestCase):
    def tree(self, merged):
        from ai_extract.services.document_graph_service import PREGRAPH_PIPELINE_SCHEMA
        stage = dict(status='complete', source_fingerprint='f')
        entities = [dict(entity_type='ENTITY', canonical_key='c', name=name) for name in ('Ủy ban nhân dân', 'Uy ban nhân dân')]
        return dict(source_fingerprint='f', pregraph_analysis=dict(schema=PREGRAPH_PIPELINE_SCHEMA, status='complete', source_fingerprint='f'),
                    reading_analysis=stage, knowledge_graph=dict(entities=entities),
                    identity_resolution=dict(stage, look_alike=[dict(names=['Ủy ban nhân dân', 'Uy ban nhân dân'], merged=merged)]))

    def test_an_accepted_look_alike_may_share_a_node(self):
        from ai_extract.services.document_graph_service import validate_prepared
        validate_prepared(self.tree(True))

    def test_names_without_an_accepted_merge_may_not(self):
        from ai_extract.services.document_graph_service import validate_prepared
        with self.assertRaisesRegex(ValueError, 'Different entity names'):
            validate_prepared(self.tree(False))


class ClauseHeadingTests(SimpleTestCase):
    def test_each_passage_is_headed_by_its_own_clause(self):
        from ai_extract.services.contract_clause_service import attach_clause_headings
        stale = 'Điều 12. Gửi thông báo'
        tree = dict(leaves=[dict(chunk_id='a', heading_path=['Luật', stale]), dict(chunk_id='b', heading_path=['Luật', stale]),
                            dict(chunk_id='c', heading_path=['Luật'])])
        clauses = [dict(title='Điều 12.  Gửi\nthông báo', source_ids=['a']), dict(title='Điều 18. Thoả thuận trọng tài vô hiệu', source_ids=['b'])]
        attach_clause_headings(tree, clauses)
        self.assertEqual([l['heading_path'] for l in tree['leaves']],
                         [['Luật', 'Điều 12. Gửi thông báo'], ['Luật', 'Điều 18. Thoả thuận trọng tài vô hiệu'], ['Luật']])


class TextEngineTests(SimpleTestCase):
    def test_only_automatic_engines_are_accepted(self):
        """The language is told by fastText on every page; Tesseract and a chosen language are gone."""
        from ai_extract.services.surya_inference_service import surya_page
        with self.assertRaisesRegex(ValueError, 'text_engine'):
            surya_page(None, SimpleNamespace(), text_engine='tesseract')
