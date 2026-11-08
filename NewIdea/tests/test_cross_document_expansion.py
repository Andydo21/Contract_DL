"""At question time, seeds reach other documents through citations and GLiNER2-confirmed entities."""
from types import SimpleNamespace

from django.test import SimpleTestCase

from NewIdea.services.knowledge_search_service import cross_document_context


def run(pk, entities, links=(), entity_links=()):
    return SimpleNamespace(pk=pk, structure=dict(
        knowledge_graph=dict(entities=[dict(name=n, source_ids=[s]) for n, s in entities]),
        cross_document_links=dict(links=list(links), entity_links=list(entity_links))))


class Backend:
    def __init__(self, scores):
        self.scores = scores

    def rerank(self, query, sources):
        return [dict(s, neural_logit=self.scores.get(s['chunk_id'], -5.)) for s in sources]


TREES = {10: dict(leaves=[dict(chunk_id='d1', text='Theo khoản 1 Điều 16 của Luật Hộ tịch, người đi đăng ký khai sinh nộp tờ khai.')]),
         20: dict(leaves=[dict(chunk_id='l16', text='1. Người đi đăng ký khai sinh nộp tờ khai theo mẫu.'),
                          dict(chunk_id='l70', text='Bộ Tư pháp giúp Chính phủ quản lý nhà nước về hộ tịch.'),
                          dict(chunk_id='l71', text='Bộ Tư pháp ban hành biểu mẫu hộ tịch.')])}
CITATION = dict(from_run=1, to_run=2, source_leaf_id='d1', target_source_leaf_id='l16')


class CrossDocumentExpansionTests(SimpleTestCase):
    def test_a_seed_brings_the_provision_it_cites_in_another_law(self):
        runs = {10: run(1, [], [CITATION]), 20: run(2, [])}
        kept, info = cross_document_context('thủ tục khai sinh', [dict(version_id=10, chunk_id='d1')], TREES, runs, Backend({'l16': 4.}))
        self.assertEqual([(s['version_id'], s['chunk_id'], s['expansion_reason']) for s in kept], [(20, 'l16', 'cross_document_citation')])

    def test_a_cited_provision_brings_the_passage_citing_it(self):
        runs = {10: run(1, [], [CITATION]), 20: run(2, [])}
        kept, _ = cross_document_context('thủ tục khai sinh', [dict(version_id=20, chunk_id='l16')], TREES, runs, Backend({'d1': 2.}))
        self.assertEqual([s['chunk_id'] for s in kept], ['d1'])

    def test_a_confirmed_shared_entity_brings_passages_of_the_other_document(self):
        runs = {10: run(1, [('Bộ Tư pháp', 'd1')], entity_links=[dict(name_key='bộ tư pháp', runs=[1, 2])]),
                20: run(2, [('Bộ Tư pháp', 'l70'), ('bộ tư pháp', 'l71')])}
        kept, _ = cross_document_context('biểu mẫu hộ tịch', [dict(version_id=10, chunk_id='d1')], TREES, runs, Backend({'l71': 3., 'l70': -1.}))
        self.assertEqual([(s['chunk_id'], s['expansion_reason']) for s in kept], [('l71', 'cross_document_entity')])

    def test_a_shared_name_gliner2_did_not_confirm_brings_nothing(self):
        runs = {10: run(1, [('Bộ Tư pháp', 'd1')]), 20: run(2, [('Bộ Tư pháp', 'l70')])}
        kept, info = cross_document_context('biểu mẫu', [dict(version_id=10, chunk_id='d1')], TREES, runs, Backend({'l70': 9.}))
        self.assertEqual((kept, info['state']), ([], 'no_candidates'))

    def test_passages_the_reranker_finds_irrelevant_are_left_out(self):
        runs = {10: run(1, [], [CITATION]), 20: run(2, [])}
        kept, info = cross_document_context('thuế', [dict(version_id=10, chunk_id='d1')], TREES, runs, Backend({'l16': -.5}))
        self.assertEqual((kept, info['kept']), ([], 0))
