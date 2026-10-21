from unittest.mock import patch
from copy import deepcopy
from django.test import SimpleTestCase, override_settings
from ai_extract.services.contract_pipeline_service import QwenContextLimitError
from NewIdea.services.knowledge_answer_service import request_answer_with_context_retry


class ContextRetryTests(SimpleTestCase):
    def payload(self):
        return dict(query='Explain all parts',evidence=[dict(evidence_id=f'E{i}',text=f'Passage {i}') for i in range(4)],
            graph_context=dict(nodes=[],edges=[]))

    def test_retries_with_less_output_without_removing_sources(self):
        payload=self.payload();original=deepcopy(payload);calls=[]
        def model(task,data):
            calls.append(data)
            if len(calls)==1:raise QwenContextLimitError(16384,14000,8192)
            return dict(answer='complete')
        self.assertEqual(request_answer_with_context_retry(model,payload)['answer'],'complete')
        self.assertEqual(calls[1]['max_output_tokens'],2048)
        self.assertEqual(calls[1]['evidence'],original['evidence'])
        self.assertEqual(payload,original)

    def test_oversized_input_reads_every_passage_then_merges_real_claims(self):
        payload=self.payload();original=deepcopy(payload);delivered=[]
        def model(task,data):
            if task=='verify_answer':
                return dict(claim_checks=[dict(check_id=str(i),supported=True) for i,_ in enumerate(data['citation_claims'])])
            if len(data['evidence'])>2:raise QwenContextLimitError(16384,16385,8192)
            delivered.extend(data['evidence'])
            return dict(answer='Batch answer',citation_claims=[dict(text=s['text'],evidence_ids=[s['evidence_id']]) for s in data['evidence']])
        result=request_answer_with_context_retry(model,payload)
        self.assertEqual(delivered,original['evidence'])
        self.assertEqual(len(result['citation_claims']),4)
        self.assertEqual(result['generation_input']['context_retry'],'shorter_output_then_source_batches')
        self.assertEqual(payload,original)

    def test_batch_merge_keeps_claims_without_per_batch_verification_calls(self):
        payload=self.payload()
        def model(task,data):
            if task=='verify_answer':
                self.fail('Batch processing must defer review until the merged answer')
            if len(data['evidence'])>2:raise QwenContextLimitError(16384,16385,8192)
            return dict(answer='Batch answer',citation_claims=[dict(text=s['text'],evidence_ids=[s['evidence_id']]) for s in data['evidence']])
        result=request_answer_with_context_retry(model,payload)
        self.assertEqual([c['evidence_ids'] for c in result['citation_claims']],[['E0'],['E1'],['E2'],['E3']])

    def test_single_oversized_passage_is_never_silently_cut(self):
        payload=self.payload();payload['evidence']=payload['evidence'][:1]
        def model(task,data):raise QwenContextLimitError(16384,16385,8192)
        with self.assertRaises(QwenContextLimitError):request_answer_with_context_retry(model,payload)

    def test_stops_when_all_parts_are_verified_and_records_unread_sources(self):
        payload=self.payload();payload['answer_parts']=[dict(id='P1',question='Explain')]
        delivered=[]
        def model(task,data):
            if task=='verify_answer':return dict(claim_checks=[dict(check_id='0',supported=True)])
            if len(data['evidence'])>2:raise QwenContextLimitError(16384,16385,8192)
            delivered.extend(data['evidence'])
            return dict(answer='Supported answer',citation_claims=[dict(text='Passage 0',evidence_ids=['E0'],part_ids=['P1'])])
        result=request_answer_with_context_retry(model,payload)
        self.assertEqual([s['evidence_id'] for s in delivered],['E0','E1'])
        self.assertEqual(result['generation_input']['unread_source_ids'],['E2','E3'])


class TokenPreflightTests(SimpleTestCase):
    @override_settings(QWEN_TOKEN_PREFLIGHT=True)
    def test_budget_is_reduced_before_generation_without_removing_source_text(self):
        from ai_extract.services.contract_pipeline_service import _chat
        from unittest.mock import Mock
        reply = Mock(status_code=200)
        reply.json.return_value = dict(choices=[dict(finish_reason='stop',message=dict(content='Done'))])
        messages=[dict(role='user',content='Full source text')]
        with patch('ai_extract.services.contract_pipeline_service._chat_token_budget',return_value=(15000,16384)), \
             patch('ai_extract.services.contract_pipeline_service.requests.post',return_value=reply) as http:
            self.assertEqual(_chat('http://model/v1',messages,max_tokens=8192),'Done')
        body=http.call_args.kwargs['json']
        self.assertEqual(body['max_tokens'],1320)
        self.assertEqual(body['messages'],messages)

    @override_settings(QWEN_TOKEN_PREFLIGHT=True)
    def test_oversized_input_never_reaches_generation_endpoint(self):
        from ai_extract.services.contract_pipeline_service import _chat
        with patch('ai_extract.services.contract_pipeline_service._chat_token_budget',return_value=(17000,16384)), \
             patch('ai_extract.services.contract_pipeline_service.requests.post') as http:
            with self.assertRaises(QwenContextLimitError) as error:
                _chat('http://model/v1',[dict(role='user',content='Full source text')],max_tokens=8192)
        self.assertTrue(error.exception.preflight)
        http.assert_not_called()

    def test_preflight_overflow_splits_sources_without_repeating_full_prompt(self):
        calls=[]
        payload=dict(query='Both facts',evidence=[dict(evidence_id='E1',text='first'),dict(evidence_id='E2',text='second')])
        def model(task,data):
            calls.append((task,len(data['evidence'])))
            if len(data['evidence'])>1:
                error=QwenContextLimitError(16384,17000,8192)
                error.preflight=True
                raise error
            return dict(answer='No source-supported fact',citation_claims=[],insufficient_evidence=True)
        request_answer_with_context_retry(model,payload)
        self.assertEqual(calls,[('contract_qa',2),('contract_qa',1),('contract_qa',1)])


class FocusedBatchTests(SimpleTestCase):
    def test_second_batch_answers_only_parts_not_already_verified(self):
        sources=[dict(evidence_id='E'+str(i),text='Source '+str(i)) for i in range(4)]
        payload=dict(query='Explain both',evidence=sources,graph_context={},answer_parts=[
            dict(id='P1',question='First?'),dict(id='P2',question='Second?')],coverage={})
        batches=[]
        def model(task,data):
            if task=='verify_answer':return dict(claim_checks=[dict(check_id='0',supported=True)])
            if len(data['evidence'])>2:raise QwenContextLimitError(16384,17000,8192)
            batches.append(data)
            part='P1' if len(batches)==1 else 'P2'
            return dict(answer='Answer',citation_claims=[dict(text='Supported '+part,evidence_ids=[data['evidence'][0]['evidence_id']],part_ids=[part])])
        result=request_answer_with_context_retry(model,payload)
        self.assertEqual([p['id'] for p in batches[0]['answer_parts']],['P1','P2'])
        self.assertEqual([p['id'] for p in batches[1]['answer_parts']],['P2'])
        self.assertEqual([p['status'] for p in result['answer_part_coverage']],['answered','answered'])
