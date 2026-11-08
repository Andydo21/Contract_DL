"""Citations between documents are linked both ways whenever either document is extracted."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from ai_extract.services import cross_document_service as cross


def document(pk, title, leaves=(), clauses=(), citations=()):
    tree = dict(source_fingerprint=f'fp{pk}', graph_index=dict(status='ready'),
                leaves=[dict(chunk_id=i, text=t) for i, t in leaves],
                contract_clauses=dict(status='complete', clauses=[dict(title=t, source_ids=s) for t, s in clauses]),
                knowledge_graph=dict(document_relations=dict(outside_citations=list(citations))))
    contract = SimpleNamespace(pk=pk, company_id=1, title=title)
    return SimpleNamespace(pk=pk, structure=tree, version=SimpleNamespace(contract=contract, contract_id=pk))


def citation(source, law, articles=(), paragraphs=()):
    return dict(source_id=source, mention=law, law=law, articles=list(articles), paragraphs=list(paragraphs))


def civil_code():
    return document(10, 'Bộ luật Dân sự số 91/2015/QH13',
                    leaves=[('h117', 'Điều 117. Điều kiện có hiệu lực'), ('p1', '1. Giao dịch dân sự có hiệu lực khi...'),
                            ('p2', '2. Hình thức của giao dịch...')],
                    clauses=[('Điều 117. Điều kiện có hiệu lực', ['h117', 'p1', 'p2'])])


def family_law(citations=()):
    return document(20, 'Luật Hôn nhân và gia đình số 52/2014/QH13', leaves=[('a', 'Theo khoản 2 Điều 117 Bộ luật Dân sự.')],
                    clauses=[('Điều 1. Phạm vi', ['a'])], citations=citations)


def reranker(pairs):
    """Scores a cited law high only against a title that contains its words."""
    return [9. if all(w in title for w in law.split()) else -5. for law, title in pairs]


def scope(run, tree):
    return dict(key=f'snap{run.pk}')


class CrossDocumentTests(SimpleTestCase):
    def setUp(self):
        # Every document in these tests is a legal text unless a test says otherwise.
        patcher = patch('ai_extract.repositories.layout_repository.is_legal_contract', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_contract_links_to_no_document_and_loses_old_links(self):
        run = family_law([citation('a', 'Bộ luật Dân sự', [117], [2])])
        written = []
        with patch('ai_extract.repositories.layout_repository.is_legal_contract', return_value=False),                 patch.object(cross, 'library', return_value=[civil_code()]),                 patch('ai_extract.services.document_graph_service.graph_scope', side_effect=scope):
            summary = cross.link_documents(run, reranker, lambda key, edges: written.append((key, edges)) or len(edges))
        self.assertEqual(written, [('snap20', [])])
        self.assertEqual(summary['status'], 'not_applicable')
        self.assertEqual(run.structure['cross_document_links']['links'], [])

    def link(self, run, others):
        written = []
        with patch.object(cross, 'library', return_value=others), \
                patch('ai_extract.services.document_graph_service.graph_scope', side_effect=scope):
            summary = cross.link_documents(run, reranker, lambda key, edges: written.append((key, edges)) or len(edges))
        return summary, written[0]

    def test_a_cited_paragraph_of_another_law_is_linked(self):
        run = family_law([citation('a', 'Bộ luật Dân sự', [117], [2])])
        summary, (key, edges) = self.link(run, [civil_code()])
        self.assertEqual(key, 'snap20')
        self.assertEqual([(e['from_key'], e['to_key']) for e in edges], [('snap20:leaf:a', 'snap10:leaf:p2')])
        self.assertEqual((summary['outgoing'], summary['incoming']), (1, 0))

    def test_extracting_the_cited_law_rebuilds_the_link_from_the_citing_one(self):
        # The Civil Code is extracted again: the family law, untouched, still cites it.
        citing = family_law([citation('a', 'Bộ luật Dân sự', [117], [2])])
        summary, (key, edges) = self.link(civil_code(), [citing])
        self.assertEqual(key, 'snap10')
        self.assertEqual([(e['from_key'], e['to_key']) for e in edges], [('snap20:leaf:a', 'snap10:leaf:p2')])
        self.assertEqual((summary['outgoing'], summary['incoming']), (0, 1))

    def test_a_bulk_rerun_leaves_documents_still_waiting_to_link_back_themselves(self):
        # The Civil Code waits later in the same bulk rerun: no edge to it now, and its citation is not unresolved.
        run = family_law([citation('a', 'Bộ luật Dân sự', [117], [2])])
        written = []
        with patch.object(cross, 'library', return_value=[civil_code()]), \
                patch('ai_extract.services.document_graph_service.graph_scope', side_effect=scope):
            summary = cross.link_documents(run, reranker, lambda key, edges: written.append(edges) or len(edges),
                                           deferred_contract_ids={10})
        self.assertEqual(written, [[]])
        self.assertEqual((summary['unresolved_laws'], summary['documents'], summary['deferred_documents']), ([], 0, 1))
        # When the Civil Code's turn comes, it builds the same link from its side.
        _, (_, edges) = self.link(civil_code(), [family_law([citation('a', 'Bộ luật Dân sự', [117], [2])])])
        self.assertEqual([(e['from_key'], e['to_key']) for e in edges], [('snap20:leaf:a', 'snap10:leaf:p2')])

    def test_a_waiting_version_still_decides_which_version_a_citation_names(self):
        # Hộ tịch 2014 waits; a citation of it must not fall to the 2026 law being linked now.
        old = document(30, 'Luật Hộ tịch số 60/2014/QH13', leaves=[('r', 'Điều 1.')], clauses=[('Điều 1. Phạm vi', ['r'])])
        new = document(40, 'Luật Hộ tịch số 03/2026/QH16', leaves=[('n', 'Điều 1.')], clauses=[('Điều 1. Phạm vi', ['n'])])
        citing = document(50, 'Nghị định số 123/2015/NĐ-CP', leaves=[('c', 'theo Luật Hộ tịch')],
                          citations=[citation('c', 'Luật Hộ tịch 60/2014/QH13')])
        written = []
        with patch.object(cross, 'library', return_value=[old, citing]), \
                patch('ai_extract.services.document_graph_service.graph_scope', side_effect=scope):
            cross.link_documents(new, lambda pairs: [9.]*len(pairs), lambda key, edges: written.append(edges) or len(edges),
                                 deferred_contract_ids={30})
        self.assertEqual(written, [[]])

    def test_a_law_named_without_an_article_links_to_the_whole_document(self):
        run = family_law([citation('a', 'Bộ luật Dân sự')])
        _, (_, edges) = self.link(run, [civil_code()])
        self.assertEqual([(e['to_key'], e['reference_type']) for e in edges], [('snap10:node:root', 'references_whole_document')])

    def test_a_law_not_in_the_library_stays_unresolved(self):
        run = family_law([citation('a', 'Luật Đất đai', [5])])
        summary, (_, edges) = self.link(run, [civil_code()])
        self.assertEqual((edges, summary['unresolved_laws']), ([], ['Luật Đất đai']))

    def test_a_written_document_number_must_agree_with_the_title(self):
        old = document(30, 'Luật Hộ tịch số 60/2014/QH13')
        self.assertEqual(cross.match_documents(['Luật Hộ tịch 03/2026/QH16'], [old], reranker), {})
        self.assertEqual(cross.match_documents(['Luật Hộ tịch 60/2014/QH13'], [old], lambda pairs: [9.]*len(pairs)),
                         {'Luật Hộ tịch 60/2014/QH13': old})

    def test_two_equally_likely_titles_leave_the_citation_unresolved(self):
        a, b = document(31, 'Luật Hộ tịch số 60/2014/QH13'), document(32, 'Luật Hộ tịch số 03/2026/QH16')
        self.assertEqual(cross.match_documents(['Luật Hộ tịch'], [a, b], lambda pairs: [9.]*len(pairs)), {})

    def test_versions_of_one_law_resolve_to_the_one_the_citing_document_could_cite(self):
        a, b = document(31, 'Luật Hộ tịch số 60/2014/QH13'), document(32, 'Luật Hộ tịch số 03/2026/QH16')
        scores = lambda pairs: [9., 8.8]
        self.assertEqual(cross.match_documents(['Luật Hộ tịch'], [a, b], scores, citing_year=2015), {'Luật Hộ tịch': a})
        self.assertEqual(cross.match_documents(['Luật Hộ tịch'], [a, b], scores, citing_year=2026), {'Luật Hộ tịch': b})
        self.assertEqual(cross.match_documents(['Luật Hộ tịch'], [a, b], scores, citing_year=2010), {})

    def test_two_different_laws_scoring_alike_are_not_treated_as_versions(self):
        a, b = document(33, 'Luật Hộ tịch số 60/2014/QH13'), document(34, 'Luật Công chứng số 46/2024/QH15')
        self.assertEqual(cross.match_documents(['luật'], [a, b], lambda pairs: [9., 8.8], citing_year=2025), {})

    def test_a_law_naming_its_own_field_is_not_linked_to_another_version_of_itself(self):
        earlier, later = document(36, 'Luật Hộ tịch số 60/2014/QH13'), document(35, 'Luật Hộ tịch số 03/2026/QH16')
        self.assertEqual(cross.match_documents(['pháp luật về hộ tịch'], [later], lambda pairs: [9.]*len(pairs),
                                               citing_year=2014, citing=earlier), {})

    def test_a_later_law_replacing_the_cited_one_is_still_linked(self):
        # The 2014 family law cites "Bộ luật dân sự"; the library holds the 2015 code that replaced the 2005 one.
        run = family_law([citation('a', 'Bộ luật Dân sự', [117], [2])])
        _, (_, edges) = self.link(run, [civil_code()])
        self.assertEqual(len(edges), 1)

    def test_a_passage_naming_a_law_twice_gives_one_link(self):
        run = family_law([citation('a', 'Bộ luật Dân sự'), citation('a', 'Bộ luật Dân sự')])
        _, (_, edges) = self.link(run, [civil_code()])
        self.assertEqual(len(edges), 1)


def mentioning(pk, title, name, context):
    run = document(pk, title)
    start = context.index(name)
    run.structure['identity_resolution'] = dict(source_mentions=[dict(name=name, context=context, scope=dict(
        source_id='x', mention_start=start, mention_end=start+len(name), quote_start=0))])
    return run


class SharedEntityTests(SimpleTestCase):
    def test_same_name_entities_confirmed_by_gliner2_are_kept_with_one_spelling(self):
        a = mentioning(1, 'Luật A số 1/2014/QH13', 'Bộ Tư pháp', 'Bộ Tư pháp hướng dẫn đăng ký hộ tịch.')
        b = mentioning(2, 'Nghị định B số 2/2015/NĐ-CP', 'bộ tư pháp', 'Giao bộ tư pháp hướng dẫn thi hành.')
        seen = []
        def model(pairs):
            seen.extend(pairs)
            return dict(decisions=[dict(id=p['id'], status='same') for p in pairs])
        links, asked = cross.confirm_shared_entities(a, [b], model)
        self.assertEqual((links, asked), ([dict(name_key='bộ tư pháp', runs=[1, 2])], 1))
        self.assertEqual(seen[0]['left']['name'], seen[0]['right']['name'])

    def test_a_pair_gliner2_does_not_confirm_is_not_kept(self):
        a = mentioning(1, 'Luật A', 'Hội đồng', 'Hội đồng trọng tài vụ việc.')
        b = mentioning(2, 'Luật B', 'Hội đồng', 'Hội đồng nhân dân tỉnh.')
        links, _ = cross.confirm_shared_entities(a, [b], lambda pairs: dict(decisions=[dict(id=p['id'], status='different') for p in pairs]))
        self.assertEqual(links, [])
