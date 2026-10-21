from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from ai_extract.services.gliner_entity_service import infer_entities,extract_graph_entities,validate_mentions,text_windows,mention_key
from ai_extract.services.document_graph_service import projection


class GLiNEREntityTests(SimpleTestCase):
    def test_structure_review_preserves_direction_and_rejects_ungrounded_endpoints(self):
        from ai_extract.services.gliner_entity_service import infer_structure_pairs,CONTEXT_SEPARATOR
        predictor=Mock();left='Pump A';right='Motor B';offset=len(left)+len(CONTEXT_SEPARATOR)
        relation=dict(relation='reading follows',score=.98,head=dict(start=0,end=len(left),text=left),
                      tail=dict(start=offset,end=offset+len(right),text=right))
        predictor.inference.return_value=([],[[relation]])
        pairs=[dict(id='next',kind='NEXT',left=left,right=right)]
        self.assertEqual(infer_structure_pairs(pairs,predictor)['decisions'][0]['status'],'disputed')
        relation['relation']='reading precedes'
        self.assertEqual(infer_structure_pairs(pairs,predictor)['decisions'][0]['status'],'supported')
        relation['tail']['text']='Wrong region'
        self.assertEqual(infer_structure_pairs(pairs,predictor)['decisions'][0]['status'],'unresolved')

    def test_identity_pairs_require_exact_names_in_both_sources(self):
        from ai_extract.services.gliner_entity_service import infer_identity_pairs,CONTEXT_SEPARATOR
        predictor=Mock()
        left='ABC supplies components.';right='ABC Ltd supplies components.'
        offset=len(left)+len(CONTEXT_SEPARATOR)
        predictor.inference.return_value=([],[[dict(relation='same entity as',score=.96,
            head=dict(start=0,end=3,text='ABC'),tail=dict(start=offset,end=offset+7,text='ABC Ltd'))]])
        result=infer_identity_pairs([dict(id='1',left=dict(name='ABC',context=left),right=dict(name='ABC Ltd',context=right))],predictor)
        self.assertEqual(result['decisions'][0]['status'],'same')
        predictor.inference.return_value[1][0][0]['tail']['start']=0
        result=infer_identity_pairs([dict(id='1',left=dict(name='ABC',context=left),right=dict(name='ABC Ltd',context=right))],predictor)
        self.assertEqual(result['decisions'][0]['status'],'unresolved')

    def test_identity_name_absent_from_source_never_reaches_model(self):
        from ai_extract.services.gliner_entity_service import infer_identity_pairs
        predictor=Mock()
        with self.assertRaises(ValueError):
            infer_identity_pairs([dict(id='1',left=dict(name='ABC',context='Different company.'),
                                      right=dict(name='ABC',context='ABC supplies components.'))],predictor)
        predictor.inference.assert_not_called()

    def test_ner_reads_valid_headers_even_when_retrieval_excludes_them(self):
        request=Mock(return_value=dict(entities=[],relations=[]))
        tree=dict(leaves=[dict(chunk_id='header',text='Robot Vision',retrieval_excluded=True,
                              structure_metadata={'ocr_status':'completed'}),
                          dict(chunk_id='bad',text='Unreliable OCR',structure_metadata={'ocr_status':'rejected'})])
        result=extract_graph_entities(tree,request)
        self.assertEqual(request.call_args.args[0],[dict(id='header',text='Robot Vision')])
        self.assertEqual(result['source_coverage']['completed_ids'],['header'])
        self.assertEqual(result['source_coverage']['without_entity_ids'],['header'])
        self.assertEqual(result['source_coverage']['excluded_ocr_ids'],['bad'])
    def test_batch_keeps_surya_regions_as_independent_texts(self):
        predictor=Mock(device='cuda:0')
        mention=dict(start=0,end=3,text='ABC',label='organization',score=.9)
        predictor.inference.return_value=([[mention],[mention]],[[],[]])
        result=infer_entities([dict(id='region-a',text='ABC supplier'),
                               dict(id='region-b',text='ABC customer')],predictor)
        self.assertEqual(predictor.inference.call_args.kwargs['texts'],['ABC supplier','ABC customer'])
        self.assertEqual({e['source_id'] for e in result['entities']},{'region-a','region-b'})
        self.assertEqual(len(result['entities']),2)

    def test_enrichment_preserves_sources_and_indexes(self):
        from ai_extract.services.layout_service import enrich_entity_graph
        tree=dict(source_fingerprint='x', nodes=[{'id':'root'}], leaves=[{'chunk_id':'u1','text':'ABC'}],
                  knowledge_graph={'relations':[{'predicate':'references'}],'source_relations':[]})
        run=SimpleNamespace(id=29,status='COMPLETED',total_pages=1,structure=tree,dense_points_count=129)
        extracted=dict(provider='gliner',status='complete',entities=[{'key':'mention'}],errors=[])
        with patch('ai_extract.services.gliner_entity_service.extract_graph_entities',return_value=extracted), \
             patch('ai_extract.services.gliner_entity_service.enrich_document_relations',return_value=extracted), \
             patch('ai_extract.services.document_graph_service.sync_graph',return_value={'status':'ready'}) as sync, \
             patch('ai_extract.services.layout_service.layout_repository.save_run') as save:
            enrich_entity_graph(run)
        for key,value in tree['leaves'][0].items():self.assertEqual(run.structure['leaves'][0][key],value)
        self.assertEqual(run.structure['nodes'],tree['nodes'])
        self.assertEqual(run.structure['knowledge_graph']['relations'],tree['knowledge_graph']['relations'])
        self.assertEqual(run.dense_points_count,129)
        self.assertEqual(run.status,'COMPLETED')
        sync.assert_called_once_with(run,review_structure=True)
        save.assert_called_once_with(run,['structure'])

    def test_partial_enrichment_does_not_replace_saved_graph(self):
        from ai_extract.services.layout_service import enrich_entity_graph
        tree=dict(source_fingerprint='x')
        run=SimpleNamespace(id=29,status='COMPLETED',total_pages=1,structure=tree)
        with patch('ai_extract.services.gliner_entity_service.extract_graph_entities',return_value=dict(status='partial',errors=['offline'])), \
             patch('ai_extract.services.document_graph_service.sync_graph') as sync, \
             patch('ai_extract.services.layout_service.layout_repository.save_run') as save:
            with self.assertRaises(RuntimeError):enrich_entity_graph(run)
        self.assertIs(run.structure,tree)
        sync.assert_not_called()
        save.assert_not_called()

    def test_source_offset_is_preserved_without_generating_relations(self):
        text='Công ty ABC không phải thanh toán 100 triệu đồng.'
        start=text.index('ABC')
        predictor=Mock(device='cuda:0')
        predictor.inference.return_value=([[dict(start=start,end=start+3,text='ABC',label='organization',score=.9)]],[[]])
        result=infer_entities([dict(id='u1',text=text)],predictor)
        self.assertEqual(result['entities'][0]['name'],'ABC')
        self.assertEqual(result['entities'][0]['start'],start)
        self.assertEqual(result['relations'],[])

    def test_hallucinated_label_span_and_low_confidence_are_rejected(self):
        rows=[dict(start=0,end=3,text='XYZ',label='organization',score=.9),
              dict(start=0,end=3,text='ABC',label='pays_to',score=.9),
              dict(start=0,end=3,text='ABC',label='organization',score=.4)]
        self.assertEqual(validate_mentions('ABC',rows),[])

    def test_same_spelling_at_different_positions_does_not_merge(self):
        leaf=dict(chunk_id='u1',text='ABC và ABC',node_id='root',ancestor_ids=['root'])
        items=[dict(source_id='u1',start=a,end=a+3,name='ABC',entity_type='ORGANIZATION',confidence=.9) for a in (0,7)]
        tree=dict(nodes=[dict(id='root',kind='document',parent_id=None)],leaves=[leaf],source_fingerprint='x')
        tree['knowledge_graph']=extract_graph_entities(tree,lambda batch:dict(entities=items,relations=[]))
        self.assertEqual(len({e['key'] for e in tree['knowledge_graph']['entities']}),2)
        run=SimpleNamespace(pk=1,version_id=2,version=SimpleNamespace(contract=SimpleNamespace(pk=3,company_id=4)))
        _,nodes,edges=projection(run,tree)
        mentions=[n for n in nodes if n.get('category')=='entity']
        self.assertEqual([n['entity_type'] for n in mentions],['ORGANIZATION','ORGANIZATION'])
        self.assertEqual(sum(e['type']=='MENTIONS' for e in edges),2)
        self.assertTrue(all(e['source_leaf_id']=='u1' for e in edges if e.get('origin')=='gliner_source_span'))
        self.assertFalse(any(e['type']=='RELATED' for e in edges))

    def test_ner_cannot_smuggle_generated_semantic_relations(self):
        tree=dict(leaves=[dict(chunk_id='u1',text='ABC pays DEF.')])
        result=extract_graph_entities(tree,lambda batch:dict(entities=[],relations=[dict(predicate='pays_to')]))
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['entities'],[])

    def test_allowlisted_relation_has_exact_endpoints_and_source_quote(self):
        source='ABC requires XYZ.'
        items=[dict(source_id='u1',start=a,end=a+3,name=name,entity_type='PRODUCT',confidence=.9)
               for a,name in ((0,'ABC'),(13,'XYZ'))]
        link=dict(source_id='u1',from_key=mention_key(items[0]),to_key=mention_key(items[1]),
                  predicate='depends_on',quote=source,confidence=.9)
        result=extract_graph_entities(dict(leaves=[dict(chunk_id='u1',text=source)]),
            lambda batch:dict(entities=items,relations=[link]))
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['relations'][0]['predicate'],'depends_on')
        self.assertEqual(result['relations'][0]['scope_quote'],source)
        self.assertEqual(result['relations'][0]['review_status'],'unreviewed')

    def test_relex_cannot_link_entities_from_different_surya_regions(self):
        items=[dict(source_id=source,start=0,end=3,name=name,entity_type='PRODUCT',confidence=.9)
               for source,name in (('a','ABC'),('b','XYZ'))]
        link=dict(source_id='a',from_key=mention_key(items[0]),to_key=mention_key(items[1]),
                  predicate='depends_on',quote='ABC',confidence=.9)
        result=extract_graph_entities(dict(leaves=[dict(chunk_id='a',text='ABC'),dict(chunk_id='b',text='XYZ')]),
            lambda batch:dict(entities=items,relations=[link]))
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(result['relations'],[])

    def test_relation_survives_projection_with_predicate_confidence_and_source(self):
        source='ABC requires XYZ.'
        items=[dict(source_id='u1',start=a,end=a+3,name=name,entity_type='PRODUCT',confidence=.9)
               for a,name in ((0,'ABC'),(13,'XYZ'))]
        link=dict(source_id='u1',from_key=mention_key(items[0]),to_key=mention_key(items[1]),
                  predicate='depends_on',quote=source,confidence=.9)
        tree=dict(nodes=[dict(id='root',kind='document',parent_id=None)],source_fingerprint='x',
                  leaves=[dict(chunk_id='u1',text=source,node_id='root',ancestor_ids=['root'])])
        tree['knowledge_graph']=extract_graph_entities(tree,lambda batch:dict(entities=items,relations=[link]))
        run=SimpleNamespace(pk=1,version_id=2,version=SimpleNamespace(contract=SimpleNamespace(pk=3,company_id=4)))
        _,_,edges=projection(run,tree)
        relation=next(e for e in edges if e['type']=='DEPENDS_ON')
        self.assertEqual((relation['predicate'],relation['confidence'],relation['source_leaf_id']),('depends_on',.9,'u1'))
        self.assertEqual(relation['quote'],source)
        self.assertEqual(relation['review_status'],'unreviewed')

    def test_boolean_score_and_self_relations_are_rejected(self):
        source='ABC requires XYZ.'
        items=[dict(source_id='u1',start=a,end=a+3,name=name,entity_type='PRODUCT',confidence=.9)
               for a,name in ((0,'ABC'),(13,'XYZ'))]
        link=dict(source_id='u1',from_key=mention_key(items[0]),to_key=mention_key(items[1]),
                  predicate='depends_on',quote=source,confidence=.9)
        for bad in (dict(link,confidence=True),dict(link,to_key=link['from_key'])):
            with self.subTest(relation=bad):
                result=extract_graph_entities(dict(leaves=[dict(chunk_id='u1',text=source)]),
                    lambda batch:dict(entities=items,relations=[bad]))
                self.assertEqual(result['status'],'unavailable')
                self.assertEqual(result['relations'],[])
        self.assertEqual(validate_mentions('ABC',[dict(start=0,end=3,text='ABC',label='organization',score=True)]),[])

    def test_long_source_is_fully_windowed_without_changing_text(self):
        text=' '.join('word'+str(i) for i in range(500))
        windows=list(text_windows(text))
        self.assertGreater(len(windows),1)
        self.assertEqual(windows[0][0],0)
        self.assertEqual(windows[-1][0]+len(windows[-1][1]),len(text))
        self.assertTrue(all(text[offset:offset+len(part)]==part for offset,part in windows))
        self.assertTrue(all(windows[i+1][0]<windows[i][0]+len(windows[i][1]) for i in range(len(windows)-1)))

    def test_unavailable_runtime_does_not_retry_every_source_batch(self):
        tree=dict(leaves=[dict(chunk_id=str(i),text='ABC') for i in range(40)])
        request=Mock(side_effect=RuntimeError('Model not installed'))
        result=extract_graph_entities(tree,request)
        request.assert_called_once()
        self.assertEqual(result['status'],'unavailable')
