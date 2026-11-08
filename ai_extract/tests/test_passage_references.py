"""A contract passage links to the passage it mentions; outside references never link into the contract."""
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings

from ai_extract.services.passage_reference_service import LAW_MENTION_LABEL, MENTION_LABEL, ORIGIN, attach_document_references, infer_mentions, link_references


def tree():
    leaves = [('h1', 'Điều 1. Hàng hóa'), ('a', 'Bên B bán hàng theo Điều 3 của hợp đồng này.'),
              ('h2', 'Điều 2. Thanh toán'), ('b', 'Bên A trả theo điều khoản giao hàng.'),
              ('h3', 'Điều 3. Giao hàng'), ('c', 'Bên B giao trước ngày 15/12.')]
    titles = {'Điều 1. Hàng hóa': ['h1', 'a'], 'Điều 2. Thanh toán': ['h2', 'b'], 'Điều 3. Giao hàng': ['h3', 'c']}
    return dict(leaves=[dict(chunk_id=i, text=t) for i, t in leaves], knowledge_graph=dict(status='complete', entities=[1], source_relations=[]),
                contract_clauses=dict(status='complete', clauses=[dict(title=t, source_ids=s) for t, s in titles.items()]))


def span(text, start=0):
    return dict(text=text, start=start, end=start+len(text), confidence=.9)


def answer(**mentions):
    """Mentions and laws per passage id; passages not named have none."""
    def requester(units):
        return [dict(id=unit['id'], mentions=mentions.get(unit['id'], ([], []))[0], laws=mentions.get(unit['id'], ([], []))[1]) for unit in units]
    return requester


class LinkReferenceTests(SimpleTestCase):
    def test_numbered_mention_links_to_the_body_of_that_clause(self):
        links, document = link_references(tree(), answer(a=([span('Điều 3')], [])), Mock())
        self.assertEqual([(l['from_id'], l['to_id'], l['reference_type']) for l in links], [('a', 'c', 'references_clause_number')])
        self.assertEqual(document['accepted_reference_relations'], 1)

    def test_link_keeps_both_passages_as_evidence_and_stays_unreviewed(self):
        link = link_references(tree(), answer(a=([span('Điều 3')], [])), Mock())[0][0]
        self.assertEqual((link['from_quote'], link['to_quote']), ('Bên B bán hàng theo Điều 3 của hợp đồng này.', 'Bên B giao trước ngày 15/12.'))
        self.assertEqual((link['origin'], link['review_status'], link['kind']), (ORIGIN, 'unreviewed', 'references'))

    def test_only_body_passages_are_read_so_headings_do_not_mention_themselves(self):
        seen = []
        def requester(units):
            seen.extend(unit['id'] for unit in units)
            return []
        link_references(tree(), requester, Mock())
        self.assertEqual(seen, ['a', 'b', 'c'])

    def test_a_clause_does_not_reference_itself(self):
        self.assertEqual(link_references(tree(), answer(a=([span('Điều 1')], [])), Mock())[0], [])

    def test_law_article_after_a_number_stays_outside_the_contract(self):
        links, document = link_references(tree(), answer(a=([span('Điều 3')], [span('Luật Thương mại 2005', 8)])), Mock())
        self.assertEqual(links, [])
        self.assertEqual(document['outside_mentions'], ['Điều 3'])

    def test_a_law_far_from_the_number_does_not_block_the_link(self):
        links, _ = link_references(tree(), answer(a=([span('Điều 3')], [span('Luật Thương mại 2005', 100)])), Mock())
        self.assertEqual(len(links), 1)

    def test_law_label_on_the_mention_itself_does_not_block_the_link(self):
        links, _ = link_references(tree(), answer(a=([span('Điều 3')], [span('Điều 3')])), Mock())
        self.assertEqual(len(links), 1)

    def test_court_a_few_words_later_does_not_block_the_link(self):
        links, _ = link_references(tree(), answer(a=([span('Điều 3')], [span('Tòa án có thẩm quyền', 25)])), Mock())
        self.assertEqual(len(links), 1)

    def test_law_label_extending_past_the_number_stays_outside(self):
        links, _ = link_references(tree(), answer(a=([span('Điều 3')], [span('3 Luật Thương mại 2005', 5)])), Mock())
        self.assertEqual(links, [])

    def test_number_first_span_naming_a_law_stays_outside(self):
        mention = span('3 Luật Thương mại 2005')
        links, _ = link_references(tree(), answer(a=([mention], [dict(mention)])), Mock())
        self.assertEqual(links, [])

    @override_settings(A3_DESCRIBED_REFERENCES_ENABLED=True)
    def test_described_mention_with_a_law_label_on_itself_is_still_reranked(self):
        mention = span('điều khoản giao hàng')
        links, _ = link_references(tree(), answer(b=([mention], [dict(mention)])), Mock(return_value=[-2.0, 1.5]))
        self.assertEqual([(l['from_id'], l['to_id']) for l in links], [('b', 'c')])

    def test_number_written_with_another_word_is_not_a_clause_number(self):
        for text in ('tháng 3', '03 bản', 'ngày 03 hằng tháng', 'khoản 3 Điều 1', '3'):
            self.assertEqual(link_references(tree(), answer(a=([span(text)], [])), Mock())[0], [], text)

    def test_a_passage_opening_with_a_number_is_numbering_itself(self):
        data = tree()
        data['leaves'][1]['text'] = 'Điều 3 của bản này nói về hàng.'
        self.assertEqual(link_references(data, answer(a=([span('Điều 3')], [])), Mock())[0], [])

    def test_a_bare_sub_number_inside_a_passage_is_not_a_citation(self):
        self.assertEqual(link_references(tree(), answer(a=([span('3.1', 8)], [])), Mock())[0], [])

    def test_a_clause_word_cites_a_title_written_differently(self):
        data = tree()
        data['contract_clauses']['clauses'][2]['title'] = '3. Delivery'
        data['leaves'][4]['text'] = '3. Delivery'
        links, _ = link_references(data, answer(a=([span('Section 3.2', 8)], [])), Mock())
        self.assertEqual([l['to_id'] for l in links], ['c'])

    def test_a_section_of_another_agreement_stays_outside_the_contract(self):
        data = tree()
        data['leaves'][1]['text'] = 'As set forth in Điều 3 of the China JV Operating Agreement.'
        mention = span('Điều 3', 16)
        links, document = link_references(data, answer(a=([mention], [])), Mock())
        self.assertEqual((links, document['outside_mentions']), ([], ['Điều 3']))

    def test_a_clause_of_this_contract_still_links(self):
        for tail in ('của hợp đồng này.', 'của Hợp đồng.', 'of the Agreement.', 'of this Agreement.'):
            data = tree()
            data['leaves'][1]['text'] = 'Theo Điều 3 '+tail
            links, _ = link_references(data, answer(a=([span('Điều 3', 5)], [])), Mock())
            self.assertEqual(len(links), 1, tail)

    def test_a_provision_of_this_law_still_links(self):
        for tail in ('của Luật này.', 'của Bộ luật này.', 'Nghị định này.', ', of this Law.'):
            data = tree()
            data['leaves'][1]['text'] = 'Theo Điều 3 '+tail
            law = span('Luật', 12)
            links, _ = link_references(data, answer(a=([span('Điều 3', 5)], [law])), Mock())
            self.assertEqual(len(links), 1, tail)

    def test_a_paragraph_of_another_article_links_to_that_article(self):
        data = tree()
        data['leaves'][1]['text'] = 'Theo khoản 2 Điều 3 của Luật này.'
        links, _ = link_references(data, answer(a=([span('khoản 2 Điều 3', 5)], [])), Mock())
        self.assertEqual([l['to_id'] for l in links], ['c'])

    def test_a_paragraph_of_this_article_is_not_a_link(self):
        reranker = Mock(return_value=[9.0, 9.0])
        data = tree()
        data['leaves'][1]['text'] = 'Theo khoản 2 Điều này.'
        links, _ = link_references(data, answer(a=([span('khoản 2 Điều này', 5)], [])), reranker)
        self.assertEqual(links, [])
        reranker.assert_not_called()

    def test_another_named_law_stays_outside(self):
        data = tree()
        data['leaves'][1]['text'] = 'Theo Điều 3 của Luật Thương mại 2005.'
        links, document = link_references(data, answer(a=([span('Điều 3', 5)], [span('Luật Thương mại 2005', 16)])), Mock())
        self.assertEqual((links, document['outside_mentions']), ([], ['Điều 3']))

    def test_a_contract_with_its_own_number_is_another_document(self):
        data = tree()
        data['leaves'][1]['text'] = 'Theo Điều 3 của Hợp đồng số 12.'
        self.assertEqual(link_references(data, answer(a=([span('Điều 3', 5)], [])), Mock())[0], [])

    def test_a_described_mention_must_name_a_provision(self):
        reranker = Mock(return_value=[1.5, 1.5])
        for text in ('Bên A', 'hợp đồng', 'A'):
            self.assertEqual(link_references(tree(), answer(b=([span(text)], [])), reranker)[0], [], text)
        reranker.assert_not_called()

    def test_clause_number_matches_in_any_letter_case(self):
        links, _ = link_references(tree(), answer(a=([span('ĐIỀU 3')], [])), Mock())
        self.assertEqual([l['to_id'] for l in links], ['c'])

    def test_number_not_in_this_contract_creates_no_link(self):
        links, document = link_references(tree(), answer(a=([span('Điều 301')], [])), Mock())
        self.assertEqual((links, document['outside_mentions']), ([], ['Điều 301']))

    @override_settings(A3_DESCRIBED_REFERENCES_ENABLED=True)
    def test_described_mention_goes_to_the_clause_with_the_matching_title(self):
        reranker = Mock(return_value=[-2.0, 1.5])
        links, _ = link_references(tree(), answer(b=([span('điều khoản giao hàng')], [])), reranker)
        self.assertEqual([p[1] for p in reranker.call_args.args[0]], ['Điều 1. Hàng hóa', 'Điều 3. Giao hàng'])
        self.assertEqual([(l['to_id'], l['rerank_logit'], l['matched_title']) for l in links], [('c', 1.5, 'Điều 3. Giao hàng')])

    def test_a_shared_entity_is_not_a_reference(self):
        data = tree()
        data['knowledge_graph']['entities'] = [dict(name='Bên B', source_ids=['c'])]
        reranker = Mock(return_value=[-3.0, -4.0])
        self.assertEqual(link_references(data, answer(b=([span('Bên B')], [])), reranker)[0], [])
        reranker.assert_not_called()

    @override_settings(A3_DESCRIBED_REFERENCES_ENABLED=True)
    def test_described_mention_below_the_reranker_floor_creates_no_link(self):
        links, _ = link_references(tree(), answer(b=([span('tiền thuê')], [])), Mock(return_value=[-2.0, -.1]))
        self.assertEqual(links, [])

    def test_a_citation_of_another_law_is_kept_with_its_law_and_numbers(self):
        data = tree()
        data['leaves'][1]['text'] = 'Theo khoản 2 Điều 17 của Luật Hộ tịch.'
        mention, law = span('khoản 2 Điều 17', 5), span('Luật Hộ tịch', 25)
        links, document = link_references(data, answer(a=([mention], [law])), Mock())
        self.assertEqual(links, [])
        [citation] = document['outside_citations']
        self.assertEqual((citation['source_id'], citation['law'], citation['articles'], citation['paragraphs']),
                         ('a', 'Luật Hộ tịch', [17], [2]))

    def test_a_law_named_without_an_article_cites_the_whole_document(self):
        data = tree()
        data['leaves'][1]['text'] = 'Thực hiện theo Bộ luật Dân sự.'
        links, document = link_references(data, answer(a=([], [span('Bộ luật Dân sự', 15)])), Mock())
        self.assertEqual([(c['law'], c['articles']) for c in document['outside_citations']], [('Bộ luật Dân sự', [])])

    def test_this_law_is_not_a_citation_of_another_document(self):
        data = tree()
        data['leaves'][1]['text'] = 'Theo quy định của Luật này.'
        _, document = link_references(data, answer(a=([], [span('Luật', 18)])), Mock())
        self.assertEqual(document['outside_citations'], [])

    def test_a_span_naming_another_law_after_its_numbers_cites_that_law(self):
        # GLiNER2 spans the whole "Khoản 1 Điều 3 của Luật Hộ tịch"; article 3 of this document must not be linked.
        data = tree()
        data['leaves'][1]['text'] = 'Theo Khoản 1 Điều 3 của Luật Hộ tịch.'
        mention = span('Khoản 1 Điều 3 của Luật Hộ tịch', 5)
        links, document = link_references(data, answer(a=([mention], [dict(mention)])), Mock())
        self.assertEqual(links, [])
        [citation] = document['outside_citations']
        self.assertEqual((citation['law'], citation['articles'], citation['paragraphs']), ('Luật Hộ tịch', [3], [1]))

    def test_a_span_ending_before_this_law_still_links_inside(self):
        data = tree()
        data['leaves'][1]['text'] = 'Theo Điều 3 của Luật này.'
        links, document = link_references(data, answer(a=([span('Điều 3 của Luật', 5)], [])), Mock())
        self.assertEqual([l['to_id'] for l in links], ['c'])
        self.assertEqual(document['outside_citations'], [])

    def test_described_mentions_are_off_by_default(self):
        reranker = Mock(return_value=[-2.0, 1.5])
        self.assertEqual(link_references(tree(), answer(b=([span('điều khoản giao hàng')], [])), reranker)[0], [])
        reranker.assert_not_called()

    def test_a_cited_paragraph_lands_on_that_paragraph(self):
        data = tree()
        data['leaves'][5:] = [dict(chunk_id='c1', text='1. Bên B giao trước ngày 15/12.'), dict(chunk_id='c2', text='2.Bên A nhận hàng tại kho.')]
        data['contract_clauses']['clauses'][2]['source_ids'] = ['h3', 'c1', 'c2']
        data['leaves'][1]['text'] = 'Theo khoản 2 Điều 3 của Luật này.'
        links, _ = link_references(data, answer(a=([span('khoản 2 Điều 3', 5)], [])), Mock())
        self.assertEqual([l['to_id'] for l in links], ['c2'])

    def test_a_listed_paragraph_missing_from_the_article_falls_back_to_the_article(self):
        data = tree()
        data['leaves'][1]['text'] = 'Theo khoản 7 Điều 3 của Luật này.'
        links, _ = link_references(data, answer(a=([span('khoản 7 Điều 3', 5)], [])), Mock())
        self.assertEqual([l['to_id'] for l in links], ['c'])

    def test_a_list_of_articles_links_each_of_them(self):
        data = tree()
        data['leaves'][3]['text'] = 'Áp dụng các Điều 1 và 3 của Luật này.'
        links, _ = link_references(data, answer(b=([span('các Điều 1 và 3', 8)], [])), Mock())
        self.assertEqual(sorted(l['to_id'] for l in links), ['a', 'c'])

    def test_document_that_is_not_a_contract_is_left_alone(self):
        requester = Mock()
        links, document = link_references(dict(leaves=[], contract_clauses=dict(status='no_clauses')), requester, Mock())
        self.assertEqual((links, document['status']), ([], 'not_applicable'))
        requester.assert_not_called()


class AttachReferenceTests(SimpleTestCase):
    def test_rerun_replaces_earlier_references_and_keeps_other_links(self):
        data = tree()
        data['knowledge_graph']['source_relations'] = [dict(from_id='a', to_id='gone', origin=ORIGIN), dict(from_id='x', to_id='y', origin='other')]
        attach_document_references(data, answer(a=([span('Điều 3')], [])), Mock())
        self.assertEqual([(r['from_id'], r['to_id']) for r in data['knowledge_graph']['source_relations']], [('x', 'y'), ('a', 'c')])

    def test_failure_keeps_extraction_and_entity_status(self):
        data = tree()
        document = attach_document_references(data, Mock(side_effect=RuntimeError('down')), Mock())
        self.assertEqual(document['status'], 'unavailable')
        self.assertEqual((data['knowledge_graph']['status'], data['knowledge_graph']['entities']), ('complete', [1]))

    @override_settings(A3_DOCUMENT_REFERENCES_ENABLED=False)
    def test_setting_turns_the_step_off(self):
        self.assertEqual(attach_document_references(tree())['status'], 'disabled')

    def test_published_link_becomes_a_references_edge_between_passages(self):
        from ai_extract.services.document_graph_service import projection
        data = tree()
        data.update(source_fingerprint='fp', nodes=[dict(id='root', kind='document', title='T')])
        data['knowledge_graph']['entities'] = []
        for leaf in data['leaves']:
            leaf.update(page_number=1, ancestor_ids=['root'])
        attach_document_references(data, answer(a=([span('Điều 3')], [])), Mock())
        version = SimpleNamespace(contract=SimpleNamespace(company_id=1, pk=1))
        run = SimpleNamespace(pk=9, version_id=1, version=version)
        edges = [e for e in projection(run, data, include_review=False)[2] if e['type'] == 'REFERENCES']
        self.assertEqual([(e['source_leaf_id'], e['target_source_leaf_id'], e['reference_type']) for e in edges], [('a', 'c', 'references_clause_number')])
        self.assertEqual(edges[0]['mention'], 'Điều 3')

    @override_settings(A3_DESCRIBED_REFERENCES_ENABLED=True)
    def test_described_link_keeps_the_title_and_score_it_matched_on_the_edge(self):
        from ai_extract.services.document_graph_service import projection
        data = tree()
        data.update(source_fingerprint='fp', nodes=[dict(id='root', kind='document', title='T')])
        data['knowledge_graph']['entities'] = []
        for leaf in data['leaves']:
            leaf.update(page_number=1, ancestor_ids=['root'])
        attach_document_references(data, answer(b=([span('điều khoản giao hàng')], [])), Mock(return_value=[-2.0, 1.5]))
        version = SimpleNamespace(contract=SimpleNamespace(company_id=1, pk=1))
        run = SimpleNamespace(pk=9, version_id=1, version=version)
        edge = next(e for e in projection(run, data, include_review=False)[2] if e['type'] == 'REFERENCES')
        self.assertEqual((edge['mention'], edge['matched_title'], edge['rerank_logit']), ('điều khoản giao hàng', 'Điều 3. Giao hàng', 1.5))


class InferMentionTests(SimpleTestCase):
    def test_mentions_and_laws_are_read_separately(self):
        calls = []
        def extract(text, labels, **options):
            calls.append(labels[0])
            return dict(entities={labels[0]: [dict(text='Điều 3', start=0, end=6, confidence=.9)]})
        result = infer_mentions([dict(id='a', text='Điều 3')], SimpleNamespace(extract_entities=extract))
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[:2], [MENTION_LABEL, LAW_MENTION_LABEL])
        self.assertEqual([m['text'] for m in result['units'][0]['mentions']], ['Điều 3'])

    def test_a_span_inside_a_longer_one_is_dropped(self):
        from ai_extract.services.passage_reference_service import outermost
        spans = [dict(text='Điều 30', start=8, end=15, confidence=.9), dict(text='khoản 3 Điều 30', start=0, end=15, confidence=.5),
                 dict(text='Điều 2', start=40, end=46, confidence=.8)]
        self.assertEqual([s['text'] for s in outermost(spans)], ['khoản 3 Điều 30', 'Điều 2'])

    def test_invalid_units_are_rejected(self):
        with self.assertRaises(ValueError):
            infer_mentions([dict(id=1, text='x')], Mock())
