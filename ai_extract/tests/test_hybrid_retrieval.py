from types import SimpleNamespace
from unittest.mock import patch
from unittest import SkipTest
from django.test import SimpleTestCase, override_settings
from ai_extract.services.contract_pipeline_service import build_structure
from ai_extract.services.contract_pipeline_service import HybridBackend, hydrate, retrieve_hybrid
from ai_extract.services.contract_pipeline_service import validate_answer, retrieval_gate
from shared.retrieval import query_policy, LexicalOnlyReranker


def version():
    run=SimpleNamespace(pk=7)
    return SimpleNamespace(pk=3,contract_id=2,contract=SimpleNamespace(company_id=1),
        layout_extraction_runs=SimpleNamespace(filter=lambda **kw:SimpleNamespace(first=lambda:run)))


class HybridTests(SimpleTestCase):
    @override_settings(A3_HYBRID_ENABLED=True)
    def test_retired_entity_vectors_are_not_searched_even_if_old_run_metadata_says_completed(self):
        from unittest.mock import Mock
        from ai_extract.services.contract_pipeline_service import retrieve_hybrid_candidates
        tree=dict(leaves=[dict(chunk_id='u',text='OPC UA interfaces',heading_path=[])])
        run=SimpleNamespace(pk=7,dense_index_status='COMPLETED',colpali_index_status='SKIPPED',
            structure=dict(entity_index=dict(status='COMPLETED',points=100)))
        backend=Mock();backend.dense.return_value=[]
        with patch('ai_extract.repositories.layout_repository.latest_run',return_value=run):
            _,coverage=retrieve_hybrid_candidates('OPC UA',tree,version(),backend)
        backend.entity.assert_not_called()
        self.assertNotIn('entity',coverage['retrieval_streams'])

    def test_retired_entity_points_are_not_hydrated_as_source_evidence(self):
        point=self.point(leaf_id='u',source_kind='entity')
        self.assertEqual(hydrate([point],[dict(chunk_id='u',text='Original sentence.')],version(),7),[])

    @override_settings(A3_HYBRID_ENABLED=True)
    def test_expanded_structural_context_is_not_deleted_by_query_relevance_scores(self):
        seed=dict(chunk_id='a',text='Main obligation.',heading_path=[],expansion_reason='query_match')
        condition=dict(chunk_id='b',text='Only after acceptance.',heading_path=[],expansion_reason='neo4j_source_relation')
        unrelated=dict(chunk_id='c',text='Another products functions.',heading_path=[],expansion_reason='parent_context')
        class Backend:
            def rerank(self, query, rows):
                scores={'a':2.,'b':-5.,'c':-4.}
                return sorted([dict(row,neural_logit=scores[row['chunk_id']]) for row in rows],
                              key=lambda row:row['neural_logit'],reverse=True)
        with patch('ai_extract.services.contract_pipeline_service.retrieve_hybrid_candidates',return_value=([seed],{})), \
             patch('ai_extract.services.contract_pipeline_service.expand_retrieval_context',
                   return_value=([seed,condition,unrelated],{})):
            selected,coverage=retrieve_hybrid('When does the obligation apply?',{},version(),Backend())
        self.assertEqual({row['chunk_id'] for row in selected},{'a','b','c'})
        self.assertEqual(coverage['context_reranker_omitted'],0)
        self.assertEqual([row['chunk_id'] for row in selected],['a','c','b'])

    def test_cross_language_neural_relevance_can_pass_without_lexical_overlap(self):
        query='C\u1ea7n nh\u1eefng thi\u1ebft b\u1ecb g\u00ec khi v\u1eadn h\u00e0nh?'
        evidence=[dict(text='Runtime requires a controller and camera.',neural_logit=3.0)]
        gate=retrieval_gate(query,evidence,dict(reranker_state='ready'))
        self.assertTrue(gate['accepted'])
        self.assertTrue(gate['neural_relevance'])
        self.assertFalse(retrieval_gate(query,evidence,{})['accepted'])
        for changes in (dict(neural_logit=-1),dict(neural_logit=float('nan')),
                        dict(is_demo=True),dict(evidence_kind='expert_question')):
            self.assertFalse(retrieval_gate(query,[dict(evidence[0],**changes)],dict(reranker_state='ready'))['accepted'])

    def test_neural_relevance_does_not_bypass_missing_numbers_or_references(self):
        evidence=[dict(text='The voltage is 24 V.',neural_logit=3.0)]
        self.assertFalse(retrieval_gate('Is it 240 V?',evidence,dict(reranker_state='ready'))['accepted'])
        self.assertFalse(retrieval_gate('voltage',evidence,dict(reranker_state='ready',unresolved_article_references=['6.2']))['accepted'])
    @override_settings(RAG_INFERENCE_URL='', RAG_LOCAL_MODELS=True)
    def test_local_reranking_uses_shared_runtime_and_keeps_source_identity(self):
        candidates=[dict(chunk_id='first',text='ABC',heading_path=[]),
                    dict(chunk_id='second',text='DEF',heading_path=[])]
        backend=HybridBackend()
        with patch.object(HybridBackend,'_rerank_runtime',None), \
             patch('ai_extract.services.inference_runtime_service.TextModelRuntime') as runtime, \
             patch('ai_extract.services.inference_runtime_service.rerank_passages',return_value=[-1.0,2.0]) as score:
            first=backend.rerank('query',candidates)
            second=backend.rerank('query',candidates)
        runtime.assert_called_once()
        self.assertEqual(score.call_count,2)
        self.assertEqual([c['chunk_id'] for c in first],['second','first'])
        self.assertEqual(first,second)
        self.assertNotIn('neural_logit',candidates[0])

    def test_equal_weight_baseline_does_not_change_with_query_intent(self):
        for query in ('payment','E-404','hình vẽ','diagram'):
            policy=query_policy(query)
            self.assertEqual(set(policy['weights'].values()),{1.0})
            self.assertEqual(policy['version'],'equal-baseline-v2')
        self.assertEqual(query_policy('E-404')['intent'],'exact_identifier')
        self.assertEqual(query_policy('diagram')['intent'],'visual')

    def test_visual_page_is_bounded_and_relevant_late_chunk_is_selected(self):
        leaves=[dict(chunk_id=f'p1:{i}',source_chunk_id='block:20',page_number=1,text='Unrelated confidentiality text.',heading_path=[])
                for i in range(100)]
        leaves.append(dict(chunk_id='p1:payment',source_chunk_id='block:20',page_number=1,text='Payment within 30 days.',heading_path=[]))
        leaves.append(dict(chunk_id='p2:payment',source_chunk_id='block:20',page_number=2,text='Payment within 60 days.',heading_path=[]))
        points=[self.point(page_number=1),self.point(page_number=1),self.point(page_number=2)]
        selected=hydrate(points,leaves,version(),7,True,query='payment')
        self.assertEqual(len(selected),4)
        self.assertEqual(selected[0]['chunk_id'],'p1:payment')
        self.assertEqual([s['colpali_page_rank'] for s in selected],[1,1,1,3])
        self.assertEqual([s['colpali_chunk_rank'] for s in selected],[1,2,3,1])
        # Duplicate page hits neither double credit nor consume more slots.
        self.assertEqual(len({s['chunk_id'] for s in selected}),len(selected))

    def test_visual_page_rank_is_independent_of_preceding_page_chunk_count(self):
        page1=[dict(chunk_id=f'p1:{i}',source_chunk_id='block:20',page_number=1,text='Payment.',heading_path=[]) for i in range(3)]
        page2=dict(chunk_id='p2',source_chunk_id='block:20',page_number=2,text='Payment.',heading_path=[])
        points=[self.point(page_number=1),self.point(page_number=2)]
        scores=[]
        for leaves in ([page1[0],page2],page1+[page2]):
            candidates=hydrate(points,leaves,version(),7,True,query='payment')
            fused=LexicalOnlyReranker.reciprocal_rank_fusion({'colpali':candidates})
            second=next(c for c in fused if c['chunk_id']=='p2')
            scores.append(second['rrf_score'])
            self.assertEqual(second['colpali_page_rank'],2)
        self.assertEqual(scores,[1/62,1/62])

    def test_fusion_retains_visual_provenance_when_lexical_hit_came_first(self):
        original=dict(chunk_id='same',page_number=1,text='Payment.')
        visual=dict(original,colpali_page_rank=5,colpali_page_score=9.0,colpali_chunk_rank=2)
        fused=LexicalOnlyReranker.reciprocal_rank_fusion({'keyword':[original],'colpali':[visual,visual]})
        self.assertEqual(len(fused),1)
        self.assertAlmostEqual(fused[0]['rrf_score'],1/61+1/65)
        self.assertEqual(fused[0]['colpali_page_rank'],5)
        self.assertEqual(fused[0]['retrieval_streams'],['keyword','colpali'])

    @override_settings(RAG_INFERENCE_URL='http://inference.example')
    def test_long_document_embeddings_are_batched_without_losing_order(self):
        calls=[]
        def post(url, json, **kwargs):
            calls.append(json['texts'])
            vectors=[[float(int(t)+1)]+[0.0]*1023 for t in json['texts']]
            return SimpleNamespace(status_code=200,raise_for_status=lambda:None,
                json=lambda:dict(model='BAAI/bge-m3',embeddings=vectors))
        with patch('ai_extract.services.contract_pipeline_service.requests.post',side_effect=post):
            vectors=HybridBackend().embedding([str(i) for i in range(70)])
        self.assertEqual([len(c) for c in calls],[16,16,16,16,6])
        self.assertEqual([v[0] for v in vectors],list(range(1,71)))

    def test_dense_leaf_hit_does_not_expand_to_every_leaf_of_source_block(self):
        leaves=self.tree()['leaves']
        wanted=leaves[0]
        point=self.point(leaf_id=wanted['chunk_id'])
        selected=hydrate([point],leaves,version(),7)
        self.assertEqual([l['chunk_id'] for l in selected],[wanted['chunk_id']])

    def test_dense_index_stores_small_source_leaves_and_company_scope(self):
        self.check_dense_index(False)

    def test_embedding_outage_preserves_existing_dense_index(self):
        self.check_dense_index(True)

    def test_page_dense_write_never_deletes_previous_points(self):
        self.check_dense_index(False, page_number=1)

    def test_invalid_or_duplicate_dense_sources_never_mutate_vector_store(self):
        from ai_extract.services.contract_pipeline_service import PlanACollectionIndexer
        from unittest.mock import Mock
        page=SimpleNamespace(page_number=1,blocks=Mock())
        page.blocks.all.return_value=[]
        pages=Mock();pages.prefetch_related.return_value.order_by.return_value=[page]
        leaf=dict(chunk_id='one',source_chunk_id='block:1',text='Original source',heading_path=[],
                  node_id='root',ancestor_ids=['root'])
        run=SimpleNamespace(id=7,version=version(),version_id=3,pages=pages,structure=dict(leaves=[leaf]))
        indexer=object.__new__(PlanACollectionIndexer);indexer.client=Mock()
        for vector in ([float('nan')]*1024,[0.]*1024,[True]+[0.]*1023,[1.,0.]):
            with patch('ai_extract.services.contract_pipeline_service._BgeM3Embedding.embed_batch',return_value=[vector]):
                result=indexer.index_dense(run)
            self.assertEqual(result.status,'FAILED')
            self.assertIn('Invalid dense source vector',result.error)
        run.structure['leaves']=[leaf,dict(leaf)]
        with patch('ai_extract.services.contract_pipeline_service._BgeM3Embedding.embed_batch') as embed:
            result=indexer.index_dense(run)
        self.assertIn('Duplicate dense source IDs',result.error)
        embed.assert_not_called()
        run.structure['leaves']=[dict(leaf,structure_metadata=dict(ocr_status='failed'))]
        with patch('ai_extract.services.contract_pipeline_service._BgeM3Embedding.embed_batch') as embed:
            result=indexer.index_dense(run)
        self.assertEqual(result.status,'SKIPPED')
        embed.assert_not_called()
        self.assertEqual(indexer.client.mock_calls,[])

    @override_settings(RAG_INFERENCE_URL='',RAG_LOCAL_MODELS=False)
    def test_dense_model_is_not_loaded_when_local_inference_is_disabled(self):
        from ai_extract.services.contract_pipeline_service import _BgeM3Embedding
        with patch('ai_extract.services.inference_runtime_service.TextModelRuntime') as runtime:
            with self.assertRaisesRegex(RuntimeError,'Dense inference is not configured'):
                _BgeM3Embedding.embed_batch(['Original source'])
            runtime.assert_not_called()

    def test_new_run_full_index_preserves_previous_run_points(self):
        self.check_dense_index(False, replace_existing=False)

    def test_large_document_is_written_to_qdrant_in_batches(self):
        """The Civil Code's 2,856 leaves in one write timed out; every point still arrives once."""
        try:
            import qdrant_client
        except ImportError:
            raise SkipTest('Qdrant client is installed in the Docker runtime')
        from ai_extract.services.contract_pipeline_service import PlanACollectionIndexer
        from unittest.mock import Mock
        page=SimpleNamespace(page_number=1,image_path='')
        blocks=[SimpleNamespace(pk=i,id=i,page=page,bbox=[0,0,100,100],layout_type='Text',structure_metadata={},
                                text=f'Article {i}. Payment within {i} days.') for i in range(1,8)]
        page.blocks=SimpleNamespace(all=lambda:blocks)
        pages=SimpleNamespace(prefetch_related=lambda *a:SimpleNamespace(order_by=lambda *a:[page]))
        v=version(); v.contract.title='Example'; v.contract.contract_code='C001'; v.contract.id=2
        run=SimpleNamespace(id=7,version=v,version_id=3,pages=pages,structure={})
        client=Mock();client.get_collections.return_value=SimpleNamespace(collections=[])
        with patch('ai_extract.services.contract_pipeline_service.PlanAQdrantClient.get',return_value=client), \
             patch('ai_extract.services.contract_pipeline_service.DENSE_WRITE_BATCH',3), \
             patch('ai_extract.services.contract_pipeline_service._BgeM3Embedding.embed_batch',
                   side_effect=lambda texts:[[1.0]+[0.0]*1023 for _ in texts]):
            result=PlanACollectionIndexer().index_dense(run,replace_existing=False)
        self.assertEqual(result.status,'COMPLETED',result.error)
        sizes=[len(call.kwargs['points']) for call in client.upsert.call_args_list]
        self.assertTrue(all(size<=3 for size in sizes))
        ids=[point.id for call in client.upsert.call_args_list for point in call.kwargs['points']]
        self.assertEqual(len(ids),result.indexed_count)
        self.assertEqual(len(set(ids)),len(ids))
        self.assertGreater(len(sizes),1)

    def check_dense_index(self, fail, page_number=None, replace_existing=True):
        try:
            import qdrant_client
        except ImportError:
            raise SkipTest('Qdrant client is installed in the Docker runtime')
        from ai_extract.services.contract_pipeline_service import PlanACollectionIndexer
        from unittest.mock import Mock
        v=version(); v.contract.title='Example'; v.contract.contract_code='C001'; v.contract.id=2
        page=SimpleNamespace(page_number=1,image_path='')
        block=SimpleNamespace(pk=10,id=10,page=page,bbox=[0,0,100,100],layout_type='Text',
            structure_metadata={},text='Article 1. Payment\n'+('The buyer pays within 30 days.\n'*150))
        page.blocks=SimpleNamespace(all=lambda:[block])
        pages=SimpleNamespace(prefetch_related=lambda *a:SimpleNamespace(order_by=lambda *a:[page]))
        pages.filter = lambda **kwargs: pages
        run=SimpleNamespace(id=7,version=v,version_id=3,pages=pages,structure={})
        client=Mock();client.get_collections.return_value=SimpleNamespace(collections=[])
        def embed(texts):
            if fail: raise RuntimeError('Model unavailable')
            return [[1.0]+[0.0]*1023 for _ in texts]
        with patch('ai_extract.services.contract_pipeline_service.PlanAQdrantClient.get',return_value=client), \
             patch('ai_extract.services.contract_pipeline_service._BgeM3Embedding.embed_batch',side_effect=embed):
            result=PlanACollectionIndexer().index_dense(run, page_number=page_number, replace_existing=replace_existing)
        if fail:
            self.assertEqual(result.status,'FAILED')
            client.delete.assert_not_called()
            client.upsert.assert_not_called()
        else:
            self.assertEqual(result.status,'COMPLETED')
            if page_number is not None or not replace_existing:
                client.delete.assert_not_called()
            points=client.upsert.call_args.kwargs['points']
            self.assertGreater(len(points),1)
            for point in points:
                self.assertEqual(point.payload['company_id'],1)
                self.assertTrue(point.payload['leaf_id'])
                self.assertLessEqual(len(point.payload['text']),900)

    def tree(self):
        tree=build_structure([dict(chunk_id='block:10',layout_type='title',structure_metadata=dict(heading_level=1,structure_kind='article'),page_number=1,text='Article 1. Payment\nPay within 30 days.'),
            dict(chunk_id='block:20',layout_type='title',structure_metadata=dict(heading_level=1,structure_kind='article'),page_number=2,text='Article 2. Termination\nNotice follows Article 3.'),
            dict(chunk_id='block:30',layout_type='title',structure_metadata=dict(heading_level=1,structure_kind='article'),page_number=3,text='Article 3. Notice\nWritten notice is 60 days.')])
        a,b=tree['leaves'][1:3]
        a['graph_related_chunk_ids']=[b['chunk_id']]
        return tree

    def point(self, **updates):
        scope=dict(source_app='contract_dl',company_id=1,contract_id=2,version_id=3,
                   contract_dl_run_id=7,chunk_id=20,page_number=2,
                   visual_scope='figure',visual_block_id=20,image_path='figure20.png')
        scope.update(updates)
        return SimpleNamespace(id=20,payload=scope,score=.9)

    def test_foreign_company_version_and_stale_run_are_rejected(self):
        for updates in [dict(company_id=9),dict(version_id=4),dict(contract_dl_run_id=6),dict(source_app='legacy')]:
            self.assertEqual(hydrate([self.point(**updates)],self.tree()['leaves'],version(),7),[])

    def test_visual_page_hydrates_current_source_not_vector_text(self):
        result=hydrate([self.point(text='Forged 999 days')],self.tree()['leaves'],version(),7,True)
        self.assertTrue(result)
        self.assertNotIn('999',str(result))

    @override_settings(A3_HYBRID_ENABLED=True)
    def test_dense_visual_rrf_rerank_and_reference_expansion(self):
        owner=self
        class Backend:
            def dense(self,*args):return [owner.point()]
            def colpali(self,*args):return [owner.point()]
            def rerank(self,q,candidates):return sorted(candidates,key=lambda c:c.get('page_number')!=2)
        result,coverage=retrieve_hybrid('termination',self.tree(),version(),Backend())
        self.assertIn('60 days',' '.join(r['text'] for r in result))
        self.assertEqual(coverage['retrieval_mode'],'hybrid')
        self.assertEqual(coverage['reranker_state'],'ready')
        self.assertEqual(coverage['fusion'],'equal_weight_rrf')
        self.assertEqual(coverage['fusion_weights'],dict(keyword=1.0,dense=1.0,colpali=1.0))
        self.assertEqual(coverage['retrieval_streams']['colpali']['rank_unit'],'page')

    @override_settings(A3_HYBRID_ENABLED=True)
    def test_missing_models_report_degraded_mode(self):
        class Backend:
            def dense(self,*args):raise RuntimeError('Offline')
            def colpali(self,*args):raise RuntimeError('Offline')
            def rerank(self,*args):raise RuntimeError('Offline')
        result,coverage=retrieve_hybrid('payment',self.tree(),version(),Backend())
        self.assertTrue(result)
        self.assertEqual(coverage['retrieval_mode'],'lexical_structural')
        self.assertEqual(coverage['retrieval_streams']['colpali']['state'],'unavailable')

    def test_unknown_question_does_not_open_generation_gate(self):
        selected=self.tree()['leaves']
        self.assertFalse(retrieval_gate('Which arbitration institution?',selected,{})['accepted'])

    def test_numeric_meaning_is_deferred_to_model_verification(self):
        sources=[dict(evidence_id='E1',text='Payment within 30 days.')]
        self.assertTrue(validate_answer('Payment within 90 days [E1]',sources)['valid'])
        self.assertTrue(validate_answer('Payment within 30 days [E1]',sources)['valid'])

    def test_uncited_claim_is_rejected(self):
        sources=[dict(evidence_id='E1',text='Payment within 30 days.')]
        self.assertFalse(validate_answer('Payment within 30 days [E1]\nThe buyer may terminate immediately.',sources)['valid'])


class RuntimeBusyRetryTests(SimpleTestCase):
    def test_busy_gpu_is_waited_for_and_other_errors_are_returned_at_once(self):
        from unittest.mock import Mock
        from ai_extract.services import contract_pipeline_service as service
        busy = Mock(status_code=503, text='{"detail":"BGE reranker unavailable: TimeoutError: GPU stage busy; retry after the current page"}')
        ready, broken = Mock(status_code=200), Mock(status_code=503, text='{"detail":"BGE reranker unavailable: CUDA out of memory"}')
        with patch.object(service.requests, 'post', side_effect=[busy, busy, ready]) as post, patch.object(service.time, 'sleep') as sleep:
            self.assertIs(service.runtime_post('http://runtime/rag/rerank', {'pairs': []}), ready)
        self.assertEqual(post.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4])
        with patch.object(service.requests, 'post', return_value=broken) as post, patch.object(service.time, 'sleep'):
            self.assertIs(service.runtime_post('http://runtime/rag/rerank', {'pairs': []}), broken)
        self.assertEqual(post.call_count, 1)
        with patch.object(service.requests, 'post', return_value=busy) as post, patch.object(service.time, 'sleep'):
            self.assertIs(service.runtime_post('http://runtime/rag/rerank', {'pairs': []}), busy)
        self.assertEqual(post.call_count, len(service.RUNTIME_BUSY_WAITS)+1)


class AnswerNumberTests(SimpleTestCase):
    """Article and document numbers come from stored data; the model's prose may hold only numbers its sources state."""
    SOURCES = [dict(evidence_id='E1', heading_path=['Luật Trọng tài thương mại', 'Điều 41. Thành lập Hội đồng trọng tài vụ việc'],
                    clause_number='Điều 41', text='Trong thời hạn 30 ngày, kể từ ngày bị đơn nhận được đơn khởi kiện…',
                    legal_type='Luật', legal_number='54/2010/QH12', legal_note='Đã được sửa đổi hoặc bổ sung bởi: 75/2025/QH15.'),
               dict(evidence_id='E2', heading_path=['Luật Trọng tài thương mại', 'Điều 40. Thành lập Hội đồng trọng tài tại Trung tâm'],
                    clause_number='Điều 40', text='trong thời hạn 30 ngày', legal_type='Luật', legal_number='54/2010/QH12'),
               dict(evidence_id='E3', heading_path=['Luật Hộ tịch', 'Điều 16. Thủ tục đăng ký khai sinh'], text='trong ngày tiếp nhận',
                    original_name='Hợp đồng dịch vụ')]

    def check(self, answer, sources=None):
        from ai_extract.services.contract_pipeline_service import ungrounded_numbers
        return ungrounded_numbers(answer, sources or self.SOURCES)

    def test_naming_the_cited_article_or_document_passes_and_any_other_article_is_flagged(self):
        self.assertEqual(self.check('Theo Điều 41 Luật 54/2010/QH12, bị đơn có 30 ngày [E1].'), [])
        self.assertEqual(self.check('Theo Điều 40, bị đơn có 30 ngày [E1].'), ['40'])
        self.assertEqual(self.check('Theo Điều 40, bị đơn có 30 ngày [E1][E2].'), [])

    def test_numbers_from_the_source_body_or_legal_note_pass_in_any_language(self):
        for answer in ('Bị đơn có 30 ngày để chọn Trọng tài viên [E1].', 'The respondent has 30 days to choose an arbitrator [E1].',
                       'Luật đã được sửa đổi bởi 75/2025/QH15 [E1].'):
            with self.subTest(answer=answer):
                self.assertEqual(self.check(answer), [])

    def test_a_number_must_come_from_the_source_its_own_sentence_cites(self):
        self.assertEqual(self.check('Bị đơn có 30 ngày [E1]. Khai sinh được đăng ký trong 30 ngày [E3].'), ['30'])

    def test_leading_zeros_do_not_count_as_a_different_number(self):
        sources = [dict(evidence_id='E1', text='có hiệu lực từ ngày 01 tháng 01 năm 2016')]
        self.assertEqual(self.check('Nghị định có hiệu lực từ 1/1/2016 [E1].', sources), [])

    def test_labels_come_from_the_stored_article_and_document(self):
        from ai_extract.services.contract_pipeline_service import source_label
        self.assertEqual(source_label(self.SOURCES[0]), 'Điều 41, Luật 54/2010/QH12')
        self.assertEqual(source_label(self.SOURCES[2]), 'Điều 16. Thủ tục đăng ký khai sinh, Hợp đồng dịch vụ')

    def answer(self, *replies, unsupported=()):
        """replies are Qwen's successive answers; unsupported lists, per support check, the claim ids it rejects."""
        from NewIdea.services import knowledge_answer_service as answers
        evidence = [dict(source, chunk_id=f'c{i}') for i, source in enumerate(self.SOURCES)]
        sent, checks = [], []
        def model(task, payload):
            # One support check per claim; each reply here has one claim, so one check per answer.
            self.assertEqual(task, 'verify_claim')
            checks.append(payload)
            rejected = unsupported[min(len(checks), len(unsupported))-1] if unsupported else ()
            return dict(supported='0' not in rejected, reason='Điều 39 không quy định việc này.' if '0' in rejected else '')
        def answer(request_model, payload):
            sent.append(payload)
            return dict(replies[min(len(sent), len(replies))-1])
        with patch.object(answers, 'request_answer_with_context_retry', side_effect=answer):
            result = answers.generate_checked_answer(dict(query='Bị đơn có bao lâu?', evidence=evidence), request_model=model)
        return result, sent, checks

    @staticmethod
    def reply(text, ids=('E1',)):
        return dict(answer=text+' ['+']['.join(ids)+'].', citation_claims=[dict(text=text+'.', evidence_ids=list(ids), quotes=[])])

    def test_a_grounded_answer_is_labelled_from_data_after_one_support_check(self):
        result, sent, checks = self.answer(self.reply('Bị đơn có 30 ngày để chọn Trọng tài viên'))
        self.assertEqual((len(sent), len(checks)), (1, 1))
        self.assertEqual(result['generation_status'], 'generated')
        self.assertEqual(result['answer_text'], 'Bị đơn có 30 ngày để chọn Trọng tài viên. (Điều 41, Luật 54/2010/QH12)')
        self.assertEqual(result['answer_source_labels'], {'E1': 'Điều 41, Luật 54/2010/QH12'})

    def test_a_repaired_answer_stands_and_an_unrepaired_one_shows_the_law_itself(self):
        result, sent, _ = self.answer(self.reply('Theo Điều 39, bị đơn có 30 ngày'), self.reply('Bị đơn có 30 ngày'))
        self.assertEqual(len(sent), 2)
        self.assertIn('39', sent[1]['repair_feedback'])
        self.assertEqual(result['generation_status'], 'generated')
        result, sent, _ = self.answer(self.reply('Theo Điều 39, bị đơn có 30 ngày', ids=('E3',)))
        self.assertEqual(len(sent), 2)
        self.assertEqual(result['generation_status'], 'source_excerpt')
        self.assertEqual(result['generation_diagnostics'], dict(state='unsupported_content_withheld', numbers=['39', '30'], unsupported=[]))
        self.assertNotIn('Theo Điều 39', result['answer_text'])
        # The best-ranked articles lead, then the one Qwen cited.
        self.assertTrue(result['answer_text'].split('\n\n', 1)[1].startswith('Điều 41, Luật 54/2010/QH12\nTrong thời hạn 30 ngày'))
        self.assertEqual(result['answer_source_ids'], ['E1', 'E2', 'E3'])

    def test_a_paragraph_its_cited_article_does_not_support_is_repaired_with_the_reason(self):
        """Qwen cited Điều 39 for what Điều 42 says; the numbers matched, so only a support check finds it."""
        result, sent, checks = self.answer(self.reply('Bị đơn có 30 ngày', ids=('E2',)), self.reply('Bị đơn có 30 ngày'),
                                           unsupported=[('0',), ()])
        self.assertEqual((len(sent), len(checks)), (2, 2))
        self.assertIn('Điều 39 không quy định việc này.', sent[1]['repair_feedback'])
        self.assertIn('Bị đơn có 30 ngày', sent[1]['repair_feedback'])
        self.assertEqual(result['generation_status'], 'generated')

    def test_an_unsupported_paragraph_that_survives_repair_is_withheld(self):
        result, sent, checks = self.answer(self.reply('Bị đơn có 30 ngày', ids=('E2',)), unsupported=[('0',), ('0',)])
        self.assertEqual((len(sent), len(checks)), (2, 2))
        self.assertEqual(result['generation_status'], 'source_excerpt')
        self.assertEqual(result['generation_diagnostics'],
                         dict(state='unsupported_content_withheld', numbers=[], unsupported=['Điều 39 không quy định việc này.']))
        self.assertNotIn('Bị đơn có 30 ngày.', result['answer_text'])

    def test_the_support_check_sees_only_the_passages_the_claim_cites(self):
        _, _, checks = self.answer(self.reply('Bị đơn có 30 ngày', ids=('E1',)))
        self.assertEqual(checks[0], dict(claim='Bị đơn có 30 ngày.', passages=[
            dict(label='Điều 41, Luật 54/2010/QH12', text='Trong thời hạn 30 ngày, kể từ ngày bị đơn nhận được đơn khởi kiện…')]))

    def test_a_failed_support_check_never_shows_the_unchecked_prose(self):
        from NewIdea.services import knowledge_answer_service as answers
        from ai_extract.services.contract_pipeline_service import QwenGatewayError
        evidence = [dict(source, chunk_id=f'c{i}') for i, source in enumerate(self.SOURCES)]
        def model(task, payload):
            raise QwenGatewayError('gateway down')
        with patch.object(answers, 'request_answer_with_context_retry', return_value=self.reply('Bị đơn có 30 ngày')):
            result = answers.generate_checked_answer(dict(query='Bị đơn có bao lâu?', evidence=evidence), request_model=model)
        self.assertEqual(result['generation_status'], 'source_excerpt')
        self.assertNotIn('Bị đơn có 30 ngày.', result['answer_text'])
