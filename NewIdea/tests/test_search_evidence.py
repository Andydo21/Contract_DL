from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from NewIdea.services.search_evidence_service import with_expert_evidence, matched_structure_nodes, select_answer_sources, select_retrieval_seeds
from NewIdea.services.knowledge_answer_service import answer_from_sources


def expert(status='approved'):
    return dict(status=status, evidence_id='A2:case:r1', case_id='case', revision=1,
        author='expert', reviewer='reviewer', title='Payment advice', issue='payment',
        reasoning='The trigger is missing.', resolution='Clarify payment trigger.',
        verification='Checked by reviewer.', applicability='Only supply contracts with this trigger.',
        contract_id=1, version_id=2,
        evidence_snapshot=dict(sha256='saved-source-digest', text='Payment within 30 days.',
                              chunk_id='block:1', source_location='Page 1', source_url='/source/'))


class SearchEvidenceTests(SimpleTestCase):
    def test_late_question_part_survives_global_seed_budget(self):
        sources=[dict(document_id='a',chunk_id=str(i),text=f'First topic {i}',
            retrieval_ranks=[dict(query=1,rank=i+1)],retrieval_hints=[dict(part=1,rank=i+1)]) for i in range(8)]
        sources.append(dict(document_id='b',chunk_id='late',text='Second topic condition',
            retrieval_ranks=[dict(query=2,rank=1)],retrieval_hints=[dict(part=2,rank=1)]))
        selected=select_retrieval_seeds(sources,limit=2)
        self.assertEqual({h['part'] for c in selected for h in c['retrieval_hints']},{1,2})
        self.assertIn('late',[c['chunk_id'] for c in selected])

    def test_redundancy_does_not_displace_new_relevant_document(self):
        sources=[dict(document_id='a',chunk_id=str(i),text='Identical general description',
            retrieval_ranks=[dict(query=0,rank=i+1)]) for i in range(2)]
        sources.append(dict(document_id='b',chunk_id='condition',text='Different operating conditions and exceptions',
            retrieval_ranks=[dict(query=0,rank=3)]))
        selected=select_retrieval_seeds(sources,limit=2)
        self.assertEqual([c['chunk_id'] for c in selected],['0','condition'])
        # Novelty is selection only: original candidates are not deleted/mutated.
        self.assertEqual(len(sources),3)

    def test_duplicate_passages_preserve_part_hints_without_merging_documents(self):
        sources=[dict(document_id='a',chunk_id='a1',text='Payment within 30 days.',
                      retrieval_hints=[dict(part=1,rank=1)]),
                 dict(document_id='a',chunk_id='a2',text='Payment within 30 days.',
                      retrieval_hints=[dict(part=2,rank=2)]),
                 dict(document_id='b',chunk_id='b1',text='Payment within 30 days.'),
                 dict(document_id='a',chunk_id='a3',text='Payment within 45 days.')]
        selected=select_answer_sources(sources)
        self.assertEqual([s['chunk_id'] for s in selected],['a1','b1','a3'])
        self.assertEqual({h['part'] for h in selected[0]['retrieval_hints']},{1,2})
        self.assertEqual(len(sources[0]['retrieval_hints']),1)

    def test_multiple_parts_of_same_document_are_not_cut_to_two_passages(self):
        sources=[dict(version_id=1,document_id='v1',chunk_id=str(i),text=f'Distinct passage {i}',expansion_reason='query_match') for i in range(5)]
        self.assertEqual(len(select_answer_sources(sources)),5)
    def test_graph_conditions_keep_reserved_room_when_many_documents_match(self):
        sources=[dict(version_id=i,document_id=f'v{i}',chunk_id=f'm{i}',
                      text=f'match {i}',expansion_reason='query_match') for i in range(12)]
        sources.append(dict(version_id=0,document_id='v0',chunk_id='condition',text='Only if wiring is verified.',
                            expansion_reason='expert_submission_context'))
        selected=select_answer_sources(sources,limit=10)
        self.assertEqual(len(selected),11)  # Ten seeds plus their source condition.
        self.assertIn('condition',[s['chunk_id'] for s in selected])

    def test_repeated_text_does_not_displace_answer_from_same_submission(self):
        sources=[dict(document_id='submission',chunk_id=str(i),text='Which PC?',
                      expansion_reason='query_match') for i in range(3)]
        sources.append(dict(document_id='submission',chunk_id='answer',text='Guidance runs on a PC.',
                            expansion_reason='expert_submission_context'))
        self.assertEqual([s['chunk_id'] for s in select_answer_sources(sources)],['0','answer'])

    def test_all_selected_source_text_and_more_than_thirteen_sources_reach_generation(self):
        evidence=[dict(evidence_id=f'E{i}',text='Guidance runs on a PC. '+ 'source condition '*120)
                  for i in range(1,17)]
        calls=[]
        def model(task,payload):
            calls.append(payload)
            return {'supported':True} if task=='verify_answer' else {'answer':'Guidance runs on a PC [E1].'}
        with patch('NewIdea.services.knowledge_answer_service.request_qwen',side_effect=model):
            answer_from_sources('Guidance PC',evidence,{})
        self.assertTrue(calls)
        self.assertEqual(len(calls[0]['evidence']),16)
        self.assertEqual(calls[0]['evidence'][0]['text'],evidence[0]['text'])

    @override_settings(A2_SOURCES_PER_DOCUMENT=2)
    def test_expanded_graph_context_survives_document_diversity_selection(self):
        sources=[dict(version_id=1,document_id='v1',chunk_id=str(i),text=f'part {i}',
                      expansion_reason='query_match') for i in range(4)]
        sources.append(dict(version_id=1,document_id='v1',chunk_id='related',text='condition',
                            expansion_reason='neo4j_source_relation'))
        sources.append(dict(version_id=2,document_id='v2',chunk_id='other',text='other match',
                            expansion_reason='query_match'))
        selected=select_answer_sources(sources)
        self.assertEqual([s['chunk_id'] for s in selected],['0','1','2','3','other','related'])
        self.assertEqual([s['evidence_id'] for s in selected],[f'E{i}' for i in range(1,7)])

    def test_all_related_conditions_survive_seed_budget(self):
        sources=[dict(document_id='v1',chunk_id='seed',text='Main fact',expansion_reason='query_match')]
        sources.extend(dict(document_id='v1',chunk_id=str(i),text=f'Condition {i}',
                            expansion_reason='neo4j_source_relation') for i in range(20))
        self.assertEqual(len(select_answer_sources(sources,limit=1)),21)

    def test_distinct_visuals_without_text_are_not_merged(self):
        sources=[dict(document_id='v1',chunk_id=str(i),text='',image_path=f'{i}.png') for i in range(2)]
        self.assertEqual(len(select_answer_sources(sources)),2)

    def test_demo_advice_is_labeled_in_evidence_sent_to_qwen(self):
        case = dict(expert(), is_demo=True, title='[DEMO] Payment advice')
        evidence = with_expert_evidence([], [case])
        self.assertTrue(evidence[0]['is_demo'])
        self.assertIn('DEMO sample answer', evidence[0]['text'])

    def test_expert_citation_preserves_full_conditions_and_distinguishes_opinion(self):
        evidence = with_expert_evidence([dict(evidence_id='E1', text='Payment.')], [expert()])
        self.assertEqual(evidence[1]['evidence_id'], 'E2')
        self.assertEqual(evidence[1]['evidence_kind'], 'expert_opinion')
        self.assertIn('Only supply contracts with this trigger.', evidence[1]['text'])
        self.assertEqual(evidence[1]['source_url'], '/source/')
        self.assertEqual(evidence[1]['author'], 'expert')

    def test_drafts_and_unbound_cases_are_not_answer_evidence(self):
        unbound = expert(); unbound['evidence_snapshot'] = {}
        self.assertEqual(with_expert_evidence([], [expert('draft'), unbound]), [])

    def test_generation_receives_expert_conditions_and_policy(self):
        case = expert(); case['reasoning'] = 'payment '*500
        evidence = with_expert_evidence([dict(evidence_id='E1', text='Payment within 30 days.')], [case])
        calls = []
        def model(task, payload):
            calls.append((task, payload))
            return {'supported': True} if task == 'verify_answer' else {'answer': 'Payment advice applies only to supply contracts [E2].'}
        with patch('NewIdea.services.knowledge_answer_service.request_qwen', side_effect=model):
            result = answer_from_sources('payment', evidence, {})
        self.assertEqual(result['generation_status'], 'generated')
        self.assertIn('Only supply contracts with this trigger.', calls[0][1]['evidence'][1]['text'])
        self.assertIn('conditional advice', calls[0][1]['expert_policy'])

    def test_structure_node_is_discovered_through_leaf_and_links_to_exact_graph(self):
        version = SimpleNamespace(pk=2, contract_id=1)
        tree = dict(nodes=[dict(id='root', kind='document', title='Manual'),
                           dict(id='n1', kind='section', title='5.1 Optimization')],
                    graph_index=dict(status='ready', fingerprint='fingerprint'))
        citation = dict(chunk_id='block:7:1:0', text='Dead data stack.', evidence_id='E1',
                        ancestor_ids=['root', 'n1'], page_number=8, source_url='/page8/')
        with patch('NewIdea.services.search_evidence_service.graph_scope', return_value=dict(key='snapshot', fingerprint='fingerprint')):
            nodes = matched_structure_nodes(tree, [citation], version, SimpleNamespace(dense_index_status='COMPLETED'))
        section = next(n for n in nodes if n['node_id'] == 'n1')
        self.assertFalse(section['independently_vectorized'])
        self.assertIn('snapshot%3Anode%3An1', section['graph_url'])
        self.assertEqual(section['evidence_ids'], ['E1'])
        self.assertNotIn('root', [n['node_id'] for n in nodes])

    def test_stale_snapshot_has_no_graph_link(self):
        tree = dict(nodes=[], graph_index=dict(status='ready', fingerprint='old'))
        with patch('NewIdea.services.search_evidence_service.graph_scope', return_value=dict(key='snapshot', fingerprint='new')):
            nodes = matched_structure_nodes(tree, [dict(chunk_id='x', text='text')], SimpleNamespace(pk=2, contract_id=1), object())
        self.assertNotIn('graph_url', nodes[0])
