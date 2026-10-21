import json
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase, override_settings
from contracts.tests.test_intelligence import ContractIntelligenceTests
from ai_extract.models import LayoutExtractionRun
from NewIdea.services.knowledge_answer_service import answer_from_sources, generation_coverage, generate_checked_answer
from NewIdea.services.search_job_service import process_next_job


class KnowledgeAnswerChecks(SimpleTestCase):
    def test_demo_hits_cannot_consume_the_seed_budget_for_real_document_evidence(self):
        from NewIdea.services.knowledge_answer_service import eligible_answer_sources
        from NewIdea.services.search_evidence_service import select_retrieval_seeds
        demo=dict(chunk_id='demo',text='Sample combined answer.',is_demo=True,
            retrieval_hints=[dict(part=1,rank=1),dict(part=2,rank=1)],retrieval_ranks=[dict(rank=1)])
        setup=dict(chunk_id='setup',text='Setup requires a workstation.',
            retrieval_hints=[dict(part=1,rank=2)],retrieval_ranks=[dict(rank=2)])
        operation=dict(chunk_id='operation',text='Operation needs only the controller.',
            retrieval_hints=[dict(part=2,rank=3)],retrieval_ranks=[dict(rank=3)])
        selected=select_retrieval_seeds(eligible_answer_sources('Setup and operation?',
            [demo,setup,operation]),limit=2)
        self.assertEqual({s['chunk_id'] for s in selected},{'setup','operation'})
        self.assertEqual(eligible_answer_sources('Review demo advice',[demo]),[demo])
        self.assertEqual(eligible_answer_sources('Question',[setup,operation]),[setup,operation])

    def test_verification_does_not_expand_unrelated_sources_through_shared_parent(self):
        from copy import deepcopy
        from NewIdea.services.knowledge_answer_service import claim_verification_context
        graph=dict(nodes=[dict(id=1,kind='evidence',evidence_ids=['E1']),
            dict(id=2,kind='section',evidence_ids=['E1','E2']),
            dict(id=3,kind='evidence',evidence_ids=['E2']),
            dict(id=4,kind='table_cell',evidence_ids=['E1'],row=1,column=2,rowspan=2)],edges=[
            dict(from_id=2,to_id=1,type='HAS_EVIDENCE',evidence_ids=['E1']),
            dict(from_id=2,to_id=3,type='HAS_EVIDENCE',evidence_ids=['E2']),
            dict(from_id=2,to_id=4,type='HAS_CELL',evidence_ids=['E1'],review_status='unreviewed')])
        original=deepcopy(graph)
        sources=[dict(evidence_id='E1',text='Selected fact.'),dict(evidence_id='E2',text='Other fact.')]
        focused,passages=claim_verification_context(graph,sources,[dict(evidence_ids=['E1'])])
        self.assertEqual(passages,sources[:1])
        self.assertEqual({n['id'] for n in focused['nodes']},{1,2,4})
        self.assertEqual(focused['edges'],[graph['edges'][0],graph['edges'][2]])
        self.assertEqual(next(n for n in focused['nodes'] if n['id']==4)['rowspan'],2)
        self.assertEqual(graph,original)

    def test_each_part_receives_ranked_source_hints_without_cutting_other_context(self):
        sources=[dict(evidence_id='E1',text='Context.',retrieval_hints=[dict(part=1,rank=2)]),
                 dict(evidence_id='E2',text='Direct explanation.',retrieval_hints=[dict(part=1,rank=1)])]
        calls=[]
        def model(task,sent):
            calls.append(sent)
            return dict(supported=True) if task=='verify_answer' else dict(answer='Explanation [E2].',
                citation_claims=[dict(text='Explanation.',evidence_ids=['E2'],part_ids=['P1'])])
        generate_checked_answer(dict(query='Why?',evidence=sources,coverage=dict(requested_parts=['Why?'])),request_model=model)
        self.assertEqual(calls[0]['answer_parts'][0]['source_ids'],['E2','E1'])
        self.assertEqual(calls[0]['evidence'],sources)

    def test_missing_part_is_reported_inline_without_an_extra_model_call(self):
        calls=[]
        def model(task,sent):
            calls.append(task)
            return dict(answer='First fact [E1].',citation_claims=[dict(text='First fact.',evidence_ids=['E1'],part_ids=['P1'])],
                answer_part_coverage=[dict(id='P1',question='First?',status='answered'),
                    dict(id='P2',question='Second?',status='unavailable')],
                answer_notes=[dict(text='Second detail is not established.',evidence_ids=[])])
        result=generate_checked_answer(dict(query='Both?',evidence=[dict(evidence_id='E1',text='First fact.')],
            coverage=dict(requested_parts=['First?','Second?'])),request_model=model)
        self.assertEqual(calls,['contract_qa'])
        self.assertEqual(result['answer_text'],'First fact.')
        self.assertEqual(result['generation_diagnostics']['completeness_warning']['missing_parts'],['Second?'])
        self.assertIn('Second detail',result['generation_diagnostics']['review_warning']['reason'])

    def test_reconsidered_abstention_still_allows_one_focused_missing_part_repair(self):
        requests=[]
        def model(task,sent):
            if task=='verify_answer':return dict(supported=True)
            requests.append(sent)
            if len(requests)==1:return dict(answer='No evidence.',insufficient_evidence=True)
            part='P1' if len(requests)==2 else 'P2'
            return dict(answer='Supported fact [E1].',citation_claims=[dict(
                text='First fact.' if part=='P1' else 'Second fact.',evidence_ids=['E1'],part_ids=[part])],
                answer_part_coverage=[dict(id='P1',question='First?',status='answered'),
                    dict(id='P2',question='Second?',status='unavailable')] if part=='P1' else [
                    dict(id='P2',question='Second?',status='answered')])
        result=generate_checked_answer(dict(query='Both?',evidence=[dict(evidence_id='E1',text='Both facts.')],
            coverage=dict(requested_parts=['First?','Second?'])),request_model=model)
        self.assertEqual(len(requests),2)
        self.assertEqual(result['answer_text'],'First fact.')
        self.assertEqual(result['generation_diagnostics']['completeness_warning']['missing_parts'],['Second?'])

    def test_atomic_question_facets_survive_shared_retrieval_and_one_generation(self):
        sources=[dict(evidence_id='E1',version_id=1,text='Setup requires a workstation.',retrieval_hints=[dict(part=1,rank=1)]),
                 dict(evidence_id='E2',version_id=2,text='Operation needs a controller.',retrieval_hints=[dict(part=2,rank=1)])]
        planned=[dict(question='Setup?',query_scope=dict(subject='Application',attribute='requirements',phase='setup')),
                 dict(question='Operation?',query_scope=dict(subject='Application',attribute='requirements',phase='operation'))]
        sent=[]
        def model(task,payload):
            self.assertEqual(task,'contract_qa');sent.append(payload)
            return dict(answer='Setup requires a workstation [E1]. Operation needs a controller [E2].')
        result=generate_checked_answer(dict(query='Both?',evidence=sources,coverage=dict(answer_parts=planned)),request_model=model)
        self.assertEqual(len(sent),1)
        packets=sent[0]['source_packets']
        self.assertEqual([p['query_scope']['phase'] for p in packets['parts']],['setup','operation'])
        self.assertEqual([p['direct_source_ids'] for p in packets['parts']],[['E1'],['E2']])
        self.assertEqual(len(packets['source_scopes']),2)
        self.assertEqual(result['generation_status'],'generated')

    def test_contract_answer_compacts_diagnostics_without_removing_source_or_graph(self):
        source=dict(evidence_id='E1',text='Payment within 30 days.')
        graph=dict(nodes=[dict(id='source')],edges=[])
        coverage=dict(mode='structural',graph_context=graph,knowledge_analysis={'trace':'x'*10000})
        calls=[]
        def model(task,sent):
            calls.append(sent)
            return dict(supported=True) if task=='verify_answer' else dict(answer='Payment within 30 days [E1].')
        result=generate_checked_answer(dict(query='payment',evidence=[source],coverage=coverage,graph_context=graph),request_model=model)
        self.assertEqual(result['generation_status'],'generated')
        for sent in calls:
            self.assertEqual(sent['evidence'],[source])
            self.assertEqual(sent['graph_context'],graph)
            self.assertNotIn('knowledge_analysis',sent['coverage'])
            self.assertNotIn('graph_context',sent['coverage'])
        self.assertIn('knowledge_analysis',coverage)

    def test_partial_answer_stays_visible_with_its_inline_limitation(self):
        calls=[]
        def model(task,sent):
            calls.append(task)
            return dict(answer='Supported answer [E1].',answer_notes=[dict(text='More detail is unavailable.',evidence_ids=['E1'])])
        result=generate_checked_answer(dict(query='Explain.',evidence=[dict(evidence_id='E1',text='Source.')]),request_model=model)
        self.assertEqual(result['generation_status'],'generated')
        self.assertEqual(result['answer'],'Supported answer [E1].')
        self.assertEqual(calls,['contract_qa'])
        self.assertIn('More detail',result['generation_diagnostics']['review_warning']['reason'])

    def test_display_prose_is_separate_from_model_selected_citations(self):
        claims=[dict(text='First explanation.',evidence_ids=['E2']),
                dict(text='A qualification.',evidence_ids=['E2','E1'])]
        def model(task,sent):
            return dict(supported=True) if task=='verify_answer' else dict(
                answer='First explanation [E2].\nA qualification [E2] [E1].',citation_claims=claims)
        result=generate_checked_answer(dict(query='Explain.',evidence=[
            dict(evidence_id='E1',text='Source one.'),dict(evidence_id='E2',text='Source two.')]),request_model=model)
        self.assertEqual(result['answer_text'],'First explanation.\n\nA qualification.')
        self.assertEqual(result['answer_source_ids'],['E2','E1'])
        self.assertIn('[E2]',result['answer'])

    def test_contained_document_sentence_is_not_a_second_independent_citation(self):
        from NewIdea.services.knowledge_answer_service import distinct_document_passages
        short = dict(evidence_id='E1', version_id=1, page_number=1, heading_path=['Features'], text='Two components.')
        full = dict(short, evidence_id='E2', text='Two components. Guidance runs on a PC.')
        other = dict(short, evidence_id='E3', version_id=2)
        self.assertEqual(distinct_document_passages([short, full, other]), [full, other])
        self.assertEqual(distinct_document_passages([dict(short, heading_path=['Other section']), full]),
                         [dict(short, heading_path=['Other section']), full])

    def test_inline_uncertainty_does_not_suppress_or_regenerate_answer(self):
        calls=[]
        def model(task,sent):
            calls.append(task)
            return dict(answer='Guidance runs on a PC [E1].',answer_notes=[dict(
                text='The setup scope needs review.',evidence_ids=['E1'])])
        result=generate_checked_answer(dict(query='Guidance',evidence=[dict(evidence_id='E1',text='Guidance runs on a PC.')]),request_model=model)
        self.assertEqual(calls,['contract_qa'])
        self.assertIn('Guidance runs',result['answer_text'])
        self.assertIn('setup scope',result['generation_diagnostics']['review_warning']['reason'])
        self.assertNotIn('semantic_check',result['citation_check'])

    def test_raw_outputs_survive_answer_repair_and_verification(self):
        payload=dict(query='payment',evidence=[dict(evidence_id='E1',text='Payment within 30 days.')])
        answers=iter(('Payment within 90 days [E99].','Payment within 30 days [E1].'))
        count=0
        def model(task,sent):
            nonlocal count
            count+=1
            raw=dict(task=task,response=dict(id=f'call-{count}',choices=[dict(message=dict(content='raw'))]))
            if task=='verify_answer':
                return dict(supported=True,qwen_outputs=[raw])
            return dict(answer=next(answers),qwen_outputs=[raw])
        result=generate_checked_answer(payload,request_model=model)
        self.assertEqual(result['generation_status'],'generated')
        self.assertEqual([item['stage'] for item in result['qwen_outputs']],['answer','citation_repair'])
        self.assertEqual([item['response']['id'] for item in result['qwen_outputs']],['call-1','call-2'])
        self.assertNotIn('semantic_check',result['citation_check'])

    def test_citation_repair_keeps_same_sources_and_graph_before_verification(self):
        source = dict(evidence_id='E1', text='Payment within 30 days.')
        payload = dict(query='payment', evidence=[source], instruction='Use source citations.',
                       graph_context=dict(nodes=[dict(id='n1')], edges=[]))
        calls = []

        def model(task, sent):
            calls.append((task, sent))
            if task == 'verify_answer':
                return dict(supported=True)
            return dict(answer='Payment within 90 days [E99].' if len(calls) == 1
                        else 'Payment within 30 days [E1].')

        result = generate_checked_answer(payload, request_model=model)
        self.assertEqual(result['generation_status'], 'generated')
        self.assertEqual([task for task, _ in calls], ['contract_qa', 'contract_qa'])
        for _, sent in calls:
            self.assertEqual(sent['evidence'], payload['evidence'])
            self.assertEqual(sent['graph_context'], payload['graph_context'])
        self.assertEqual(result['generation_calls'][1]['stage'], 'citation_repair')
        self.assertEqual(payload['instruction'], 'Use source citations.')

    def test_repeated_invalid_claim_stops_after_one_repair_without_verification(self):
        payload = dict(query='payment', evidence=[dict(evidence_id='E1', text='Payment within 30 days.')])
        with patch('NewIdea.services.knowledge_answer_service.request_qwen',
                   return_value=dict(answer='Payment within 90 days [E99].')) as model:
            result = generate_checked_answer(payload)
        self.assertEqual(model.call_count, 2)
        self.assertTrue(all(call.args[0] == 'contract_qa' for call in model.call_args_list))
        self.assertEqual(result['generation_status'], 'source_excerpt')
        self.assertNotIn('90 days', result['answer'])
        self.assertFalse(result['citation_check']['valid'])

    def test_demo_advice_does_not_pad_ordinary_document_answers(self):
        sources=[dict(evidence_id='E1',text='Guidance runs on a PC.'),
                 dict(evidence_id='E2',text='Guidance advice sample.',is_demo=True,evidence_kind='expert_opinion')]
        seen=[]
        def model(task,payload):
            seen.append([e['evidence_id'] for e in payload['evidence']])
            return dict(supported=True) if task=='verify_answer' else dict(answer='Guidance runs on a PC [E1].')
        with patch('NewIdea.services.knowledge_answer_service.request_qwen',side_effect=model):
            answer_from_sources('Guidance PC',sources,{})
            self.assertTrue(all(ids==['E1'] for ids in seen))
            seen.clear()
            answer_from_sources('Guidance advice',sources,{})
            self.assertTrue(all(ids==['E1','E2'] for ids in seen))

    def test_generation_and_verification_receive_source_bound_graph(self):
        source=dict(evidence_id='E1',version_id=1,chunk_id='leaf1',text='Guidance runs on a PC.')
        graph=dict(state='ready',version_id=1,nodes=[
            dict(id='v1:n1',kind='section',label='Setup',source_leaf_ids=['leaf1']),
            dict(id='v1:n2',kind='evidence',label='Guidance',source_leaf_ids=['leaf1'])],
            edges=[dict(from_id='v1:n1',to_id='v1:n2',type='HAS_EVIDENCE',source_leaf_ids=[])])
        calls=[]
        def model(task,payload):
            calls.append(payload)
            return dict(supported=True) if task=='verify_answer' else dict(answer='Guidance runs on a PC [E1].')
        with patch('NewIdea.services.knowledge_answer_service.request_qwen',side_effect=model):
            result=answer_from_sources('Guidance PC',[source],dict(version_details=[dict(coverage=dict(graph_context=graph))]))
        self.assertEqual(result['generation_status'],'generated')
        self.assertEqual(len(calls),1)
        self.assertTrue(all(c['graph_context']['edges'][0]['evidence_ids']==['E1'] for c in calls))
        self.assertNotIn('graph_context',calls[0]['coverage'])
        self.assertEqual(calls[0]['answer_detail'],'explanatory')

    def test_verbose_retrieval_diagnostics_do_not_fill_qwen_context(self):
        coverage = dict(mode='knowledge_discovery', partial=True, versions_scanned=4,
            version_details=[dict(coverage=dict(structure_analysis={'large': 'x' * 10000},
                unresolved_document_references=['Appendix X']))])
        compact = generation_coverage(coverage)
        self.assertNotIn('version_details', compact)
        self.assertTrue(compact['partial'])
        self.assertEqual(compact['unresolved_document_references'], ['Appendix X'])
        self.assertLess(len(json.dumps(compact)), 500)
        self.assertIn('version_details', coverage)

    def test_irrelevant_candidates_are_not_presented_as_an_answer(self):
        source = dict(evidence_id='E1', text='Replace the E17 sensor.', source_location='Page 1')
        with patch('NewIdea.services.knowledge_answer_service.request_qwen') as model:
            result = answer_from_sources('EVP2 Guidance Runtime PC', [source], {})
        self.assertEqual(result['generation_status'], 'abstained')
        self.assertNotIn('Replace', result['answer'])
        model.assert_not_called()

    def test_unsupported_claim_remains_visible_with_advisory_warning(self):
        source = dict(evidence_id='E1', text='The contract price is 120 VND.', source_location='Page 1')
        def model(task, payload):
            self.assertEqual(payload['answer_format'], 'cited_claims')
            self.assertEqual(task,'contract_qa')
            return dict(answer='The penalty is 120 VND [E1].',answer_notes=[dict(
                text='The source states a price, not a penalty.',evidence_ids=['E1'])])
        with patch('NewIdea.services.knowledge_answer_service.request_qwen', side_effect=model):
            result = answer_from_sources('contract price', [source], {})
        self.assertEqual(result['generation_status'], 'generated')
        self.assertIn('The penalty is', result['answer'])
        self.assertIn('review_warning', result['generation_diagnostics'])

    def test_review_timeout_does_not_discard_generated_answer(self):
        from ai_extract.services.contract_pipeline_service import QwenGatewayError
        calls=[]
        def model(task,payload):
            calls.append(task)
            if task=='verify_answer':raise QwenGatewayError('review timeout')
            return dict(answer='Payment within 30 days [E1].')
        result=generate_checked_answer(dict(query='payment',evidence=[
            dict(evidence_id='E1',text='Payment within 30 days.')]),request_model=model)
        self.assertEqual(calls,['contract_qa'])
        self.assertEqual(result['generation_status'],'generated')
        self.assertIn('Payment within 30 days',result['answer_text'])
        self.assertNotIn('review_warning',result['generation_diagnostics'])
        self.assertNotIn('semantic_check',result['citation_check'])


@override_settings(A3_HYBRID_ENABLED=False)
class CorpusKnowledgeAnswers(TestCase):
    setUp = ContractIntelligenceTests.setUp

    def test_raw_qwen_output_is_persisted_and_job_access_remains_scoped(self):
        from NewIdea.services.search_job_service import reserve_search, finish_search
        raw=[dict(task='contract_qa',stage='answer',response=dict(id='raw-output',choices=[dict(message=dict(content='{"claims":[]}'))]))]
        receipt=reserve_search(self.user,'Question',generated=True,scope='knowledge')
        finish_search(receipt,dict(answer='Answer',qwen_outputs=raw))
        self.client.force_login(self.user)
        response=self.client.get('/api/newidea/jobs/',dict(id=receipt.pk))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['result']['qwen_outputs'],raw)
        self.client.force_login(self.outsider)
        response=self.client.get('/api/newidea/jobs/',dict(id=receipt.pk))
        self.assertIn(response.status_code,(403,404))

    def post(self, path='/api/newidea/search/', **body):
        return self.client.post(path, json.dumps({'query': 'payment', 'generate': True, **body}), content_type='application/json')

    def model(self, task, payload):
        return {'supported': True} if task == 'verify_answer' else {'answer': 'Payment within 60 days [E1].'}

    def index(self):
        return LayoutExtractionRun.objects.create(version=self.new_version, status='COMPLETED', dense_index_status='COMPLETED')

    def foreign_index(self):
        from ai_extract.models import LayoutExtractionPage, LayoutExtractionBlock
        run = LayoutExtractionRun.objects.create(version=self.foreign_version, status='COMPLETED', dense_index_status='COMPLETED')
        page = LayoutExtractionPage.objects.create(run=run, page_number=1)
        LayoutExtractionBlock.objects.create(page=page, block_order=1, text='EVP2 Guidance configures on a PC. EVP2 Runtime uses the controller and camera.')

    def test_admin_discovers_indexed_knowledge_in_another_company(self):
        self.foreign_index()
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        result = self.post(query='EVP2', generate=False).json()
        self.assertEqual(result['context_coverage']['access_scope'], 'all_companies')
        self.assertEqual({c['version_id'] for c in result['citations']}, {self.foreign_version.pk})

    def test_regular_user_cannot_discover_foreign_knowledge(self):
        self.foreign_index()
        result = self.post(query='EVP2', generate=False).json()
        self.assertEqual(result['citations'], [])

    def test_named_product_excludes_unrelated_runtime_document(self):
        from ai_extract.models import Clause
        self.foreign_index()
        self.index()
        Clause.objects.create(version=self.new_version, clause_title='Runtime', clause_content='Runtime for machine AX-203 uses a controller and camera.')
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        result = self.post(query='EVP2 Runtime controller camera', generate=False).json()
        self.assertEqual({c['version_id'] for c in result['citations']}, {self.foreign_version.pk})
        self.assertIn(self.foreign_version.pk, result['context_coverage']['identifier_matched_versions'])

    def test_comparison_keeps_documents_for_both_requested_identifiers(self):
        from ai_extract.models import Clause
        self.foreign_index()
        self.index()
        Clause.objects.create(version=self.new_version, clause_title='Runtime', clause_content='AX-203 runtime uses a controller.')
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        result = self.post(query='EVP2 versus AX-203 runtime', generate=False).json()
        self.assertEqual({c['version_id'] for c in result['results']}, {self.foreign_version.pk, self.new_version.pk})

    def test_admin_without_company_can_queue_and_read_corpus_job(self):
        self.foreign_index()
        self.user.company = None
        self.user.is_superuser = True
        self.user.save(update_fields=['company', 'is_superuser'])
        queued = self.post('/api/newidea/jobs/', scope='knowledge', query='EVP2')
        self.assertEqual(queued.status_code, 202)
        pk = queued.json()['search_id']
        self.assertEqual(self.client.get('/api/newidea/jobs/', {'id': pk}).status_code, 200)
        with patch('NewIdea.services.knowledge_answer_service.request_qwen', side_effect=lambda task, payload:
                   {'supported': True} if task == 'verify_answer' else {'answer': 'EVP2 Runtime uses the controller and camera [E1].'}):
            process_next_job(lambda *args, **kwargs: self.fail('Unexpected version job'))
        receipt = self.client.get('/api/newidea/jobs/', {'id': pk}).json()
        self.assertEqual(receipt['status'], 'COMPLETED')
        self.assertEqual({c['version_id'] for c in receipt['result']['sources']}, {self.foreign_version.pk})

    def test_revoking_admin_access_hides_corpus_job_and_prevents_execution(self):
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        pk = self.post('/api/newidea/jobs/', scope='knowledge').json()['search_id']
        self.user.is_superuser = False
        self.user.save(update_fields=['is_superuser'])
        with patch('NewIdea.services.knowledge_search_service.search_knowledge') as search:
            process_next_job(lambda *args, **kwargs: self.fail('Unexpected version job'))
        search.assert_not_called()
        self.assertEqual(self.client.get('/api/newidea/jobs/', {'id': pk}).status_code, 404)

    def test_answers_without_contract_selection_and_only_from_indexed_knowledge(self):
        self.index()
        with patch('ai_extract.services.contract_pipeline_service.request_qwen', side_effect=RuntimeError('Structure offline')), patch('NewIdea.services.knowledge_answer_service.request_qwen', side_effect=self.model):
            response = self.post()
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['generation_status'], 'generated')
        self.assertIn('60 days', result['answer'])
        self.assertTrue(all(c['version_id'] == self.new_version.pk for c in result['citations']))

    def test_available_text_is_searchable_even_without_vector_index(self):
        with patch('NewIdea.services.knowledge_answer_service.request_qwen',side_effect=self.model) as model:
            result = self.post().json()
        self.assertEqual(result['generation_status'], 'generated')
        self.assertIn('60 days',result['answer'])
        self.assertFalse(result['context_coverage']['indexed_only'])
        self.assertEqual(result['context_coverage']['versions_scanned'],result['context_coverage']['versions_total'])
        self.assertTrue(model.called)

    def test_company_job_is_queued_and_readable_without_version(self):
        self.index()
        response = self.post('/api/newidea/jobs/', scope='company')
        self.assertEqual(response.status_code, 202)
        pk = response.json()['search_id']
        self.assertEqual(self.client.get('/api/newidea/jobs/', {'id':pk}).status_code, 200)
        with patch('ai_extract.services.contract_pipeline_service.request_qwen', side_effect=RuntimeError('Structure offline')), patch('NewIdea.services.knowledge_answer_service.request_qwen', side_effect=self.model):
            process_next_job(lambda *args, **kwargs: self.fail('Version worker must not run for company job'))
        receipt = self.client.get('/api/newidea/jobs/', {'id':pk}).json()
        self.assertEqual(receipt['status'], 'COMPLETED')
        self.assertEqual(receipt['result']['response']['generation_status'], 'generated')
        self.user.company = self.other
        self.user.save(update_fields=['company'])
        self.assertEqual(self.client.get('/api/newidea/jobs/', {'id':pk}).status_code, 404)

    def test_company_change_before_worker_prevents_execution(self):
        pk = self.post('/api/newidea/jobs/', scope='company').json()['search_id']
        self.user.company = self.other
        self.user.save(update_fields=['company'])
        with patch('NewIdea.services.knowledge_search_service.search_knowledge') as search:
            process_next_job(lambda *args, **kwargs: self.fail('Unexpected version job'))
        search.assert_not_called()
        from contracts.models import KnowledgeSearchLog
        self.assertEqual(KnowledgeSearchLog.objects.get(pk=pk).status, 'FAILED')

    def test_approved_expert_case_reaches_generation_and_stale_case_is_excluded(self):
        pk = ContractIntelligenceTests.write_case(self).json()['case']['id']
        self.client.force_login(self.manager)
        self.assertEqual(ContractIntelligenceTests.action(self, 'approve', pk).status_code, 200)
        self.client.force_login(self.user)
        self.index()
        payloads = []
        def model(task, payload):
            payloads.append(payload)
            return self.model(task, payload)
        with patch('NewIdea.services.knowledge_answer_service.request_qwen', side_effect=model):
            result = self.post().json()
        opinions = [c for c in result['citations'] if c.get('evidence_kind') == 'expert_opinion']
        self.assertEqual(len(opinions), 1)
        self.assertEqual(opinions[0]['applicability'], self.fields['applicability'])
        self.assertTrue(any(c.get('evidence_kind') == 'expert_opinion' for c in payloads[0]['evidence']))
        from ai_extract.models import Clause
        Clause.objects.filter(version=self.version).update(clause_content='Replaced source')
        with patch('NewIdea.services.knowledge_answer_service.request_qwen', side_effect=model):
            changed = self.post().json()
        self.assertFalse(any(c.get('evidence_kind') == 'expert_opinion' for c in changed['citations']))
class StructureReviewOrderTests(SimpleTestCase):
    def test_disputed_next_cannot_restore_native_order_as_confirmed(self):
        from NewIdea.services.knowledge_answer_service import graph_source_order
        sources=[dict(version_id=1,chunk_id='a',reading_document_position=1,reading_stream_status='model_predicted'),
                 dict(version_id=1,chunk_id='b',reading_document_position=0,reading_stream_status='model_predicted')]
        context=dict(state='ready',version_id=1,nodes=[dict(id='a',source_leaf_ids=['a']),dict(id='b',source_leaf_ids=['b'])],
                     edges=[dict(from_id='b',to_id='a',type='NEXT',review_status='model_disputed')])
        self.assertEqual(graph_source_order([context],sources),sources)



class FocusedRepairIntegrationTests(SimpleTestCase):
    def test_packets_keep_direct_dependencies_without_shared_scope_fanout(self):
        sources=[dict(evidence_id='E1',text='First source.',retrieval_hints=[dict(part=1,rank=1)]),
                 dict(evidence_id='E2',text='Second source.',retrieval_hints=[dict(part=2,rank=1)]),
                 dict(evidence_id='E3',text='Applicability condition.')]
        graph=dict(nodes=[dict(id=i,evidence_ids=['E'+str(i)]) for i in (1,2,3)],
                   edges=[dict(type='DEPENDS_ON',from_id=2,to_id=3)])
        calls=[]
        def model(task,sent):
            calls.append((task,sent))
            return dict(answer='First answer [E1]. Second answer under its condition [E2] [E3].')
        result=generate_checked_answer(dict(query='Both?',evidence=sources,graph_context=graph,
            coverage=dict(requested_parts=['First?','Second?'])),request_model=model)
        self.assertEqual(len(calls),1)
        packets=calls[0][1]['source_packets']['parts']
        self.assertEqual(packets[0]['direct_source_ids'],['E1'])
        self.assertEqual(packets[0]['related_source_ids'],[])
        self.assertEqual(packets[1]['direct_source_ids'],['E2'])
        self.assertEqual(packets[1]['related_source_ids'],['E3'])
        self.assertEqual(calls[0][1]['graph_context'],graph)
        self.assertEqual(result['generation_status'],'generated')
