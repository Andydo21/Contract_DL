from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from ai_extract.services.document_structure_service import build_document_structure
from ai_extract.services.document_graph_service import projection
from ai_extract.services.gliner_entity_service import (
    infer_entities, extract_graph_entities, document_context_units, enrich_document_relations,CONTEXT_SEPARATOR,
)


def region(identity,text,rank,kind='paragraph',page=1,parent=None,level=None):
    metadata=dict(chunk_policy='surya_layout_region',layout_source='surya',surya_region_id=identity,
        reading_order=rank,reading_order_source='surya_full_page_model',reading_order_scope=parent or 'page')
    if parent:metadata['surya_parent_region_id']=parent
    if level:metadata.update(heading_level=level,heading_source='surya_html')
    return dict(chunk_id=identity,text=text,layout_type=kind,page_number=page,image_path=f'page{page}.png',
                bbox=[0,0,500,500],structure_metadata=metadata)


def project(tree):
    run=SimpleNamespace(pk=1,version_id=2,version=SimpleNamespace(contract=SimpleNamespace(pk=3,company_id=4)))
    return projection(run,dict(tree,source_fingerprint='test'))


class ReadingStreamsTests(SimpleTestCase):
    def test_region_branch_and_supplement_do_not_pollute_main_next(self):
        rows=[region('h','A heading',0,'title',level=1),region('a','Before figure.',1),
              region('picture','',2,'figure'),region('inside','Text in figure.',0,parent='picture'),
              region('after','After figure.',3),region('footer','A footer',4,'page_footer')]
        tree=build_document_structure(rows)
        by_source={l['source_chunk_id']:l for l in tree['leaves']}
        self.assertEqual(by_source['inside']['parent_reading_stream_id'],by_source['picture']['reading_stream_id'])
        self.assertNotEqual(by_source['footer']['reading_stream_id'],by_source['a']['reading_stream_id'])
        self.assertLess(by_source['picture']['reading_document_position'],by_source['inside']['reading_document_position'])
        self.assertLess(by_source['inside']['reading_document_position'],by_source['after']['reading_document_position'])
        _,nodes,edges=project(tree)
        blocks={n['key']:n for n in nodes if n.get('category')=='layout_block'}
        for edge in [e for e in edges if e['type']=='NEXT']:
            a,b=blocks[edge['from_key']],blocks[edge['to_key']]
            self.assertEqual(a['reading_stream_id'],b['reading_stream_id'])
            self.assertNotEqual(a['reading_stream_kind'],'page_footer')

    def test_heading_ownership_survives_page_boundary_without_paragraph_continuation(self):
        tree=build_document_structure([region('title','Payment',0,'title',level=1),
                                       region('a','A condition',1),region('b','Another clause',0,page=2)])
        a,b=[l for l in tree['leaves'] if l['source_chunk_id'] in {'a','b'}]
        self.assertEqual(a['node_id'],b['node_id'])
        self.assertNotEqual(a['reading_stream_id'],b['reading_stream_id'])
        _,_,edges=project(tree)
        self.assertFalse(any(e['type']=='REFERENCES' for e in edges))
        self.assertTrue(all(e.get('origin')!='semantic_continuation' for e in edges))

    def test_unknown_ranks_and_cyclic_parent_scopes_never_authorize_next(self):
        for rows in [[region('a','A',0),region('b','B',0)],
                     [region('a','A',0,parent='b'),region('b','B',0,parent='a')]]:
            tree=build_document_structure(rows)
            self.assertTrue(all(s['status']=='unresolved' for s in tree['reading_streams']))
            self.assertEqual(len(tree['leaves']),2)
            self.assertFalse(any(e['type']=='NEXT' for e in project(tree)[2]))

    def test_table_keeps_separate_owner_and_native_grid(self):
        row=region('table','A table',0,'table')
        row['structure_metadata']['table_rows']=[['Item','Amount'],['A','10']]
        tree=build_document_structure([row])
        leaf=tree['leaves'][0]
        self.assertEqual(next(n for n in tree['nodes'] if n['id']==leaf['node_id'])['kind'],'table')
        edges=project(tree)[2]
        self.assertEqual(sum(e['type']=='HAS_ROW' for e in edges),2)
        self.assertEqual(sum(e['type']=='HAS_CELL' for e in edges),4)
        nodes=project(tree)[1]
        tables=[n for n in nodes if n.get('kind')=='table' and n.get('category')=='structure']
        self.assertEqual(len(tables),1)
        self.assertFalse(any(n.get('category')=='table' for n in nodes))
        owner=tables[0]['key']
        self.assertTrue(any(e['type']=='HAS_ROW' and e['from_key']==owner for e in edges))
        self.assertEqual(sum(e['type']=='HAS_EVIDENCE' and e['from_key']==owner for e in edges),1)


class ContextRelationTests(SimpleTestCase):
    def pair(self):
        a='ABC references XYZ.';b='XYZ is a specification.'
        unit=dict(id='a',text=a,context_windows=[dict(offset=0,text=a,contexts=[dict(id='b',offset=0,text=b)])])
        predictor=Mock(device='cuda:0')
        tail=len(a)+len(CONTEXT_SEPARATOR)
        mentions=[dict(start=0,end=3,text='ABC',label='product',score=.95),
                  dict(start=tail,end=tail+3,text='XYZ',label='product',score=.95)]
        link=dict(head=dict(start=0,end=3,text='ABC',type='product'),
                  tail=dict(start=tail,end=tail+3,text='XYZ',type='product'),relation='references',score=.95)
        predictor.inference.return_value=([mentions],[[link]])
        result=infer_entities([unit],predictor)
        return a,b,unit,result

    def test_context_mentions_keep_native_offsets_and_cross_page_reference_has_two_sources(self):
        a,b,unit,result=self.pair()
        self.assertEqual([(e['source_id'],e['start'],e['end']) for e in result['entities']],[('a',0,3),('b',0,3)])
        tree=dict(nodes=[dict(id='root',kind='document',parent_id=None)],leaves=[
            dict(chunk_id='a',text=a,page_number=1,node_id='root',ancestor_ids=['root']),
            dict(chunk_id='b',text=b,page_number=8,node_id='root',ancestor_ids=['root'])])
        tree['knowledge_graph']=extract_graph_entities(tree,lambda units:result,context_units=[unit])
        self.assertEqual(tree['knowledge_graph']['status'],'complete')
        self.assertEqual(len(tree['knowledge_graph']['source_relations']),1)
        edges=project(tree)[2]
        refs=[e for e in edges if e['type']=='REFERENCES']
        self.assertEqual(len(refs),1)
        self.assertEqual(refs[0]['source_leaf_id'],'a')
        self.assertEqual(refs[0]['target_source_leaf_id'],'b')
        self.assertEqual(refs[0]['quote'],a)
        self.assertEqual(refs[0]['target_quote'],b)
        self.assertEqual(refs[0]['to_char_start'],0)
        self.assertEqual(refs[0]['review_status'],'unreviewed')

    def test_context_never_relabels_other_region_text_as_the_target(self):
        a,b,unit,result=self.pair()
        tree=dict(leaves=[dict(chunk_id='a',text=a),dict(chunk_id='b',text=b)])
        result['entities'][1]['source_id']='a'
        output=extract_graph_entities(tree,lambda units:result,context_units=[unit])
        self.assertEqual(output['status'],'unavailable')
        self.assertEqual(output['entities'],[])

    def test_candidate_similarity_does_not_create_a_reference(self):
        tree=build_document_structure([region('a','Payment is due later.',0,page=1),
                                       region('b','Payment is due later.',0,page=9)])
        empty=dict(status='complete',entities=[],relations=[],source_relations=[],source_coverage={})
        request=Mock(return_value=dict(entities=[],relations=[],metrics={}))
        output=enrich_document_relations(tree,empty,request,embedding=lambda texts:[[1.,0.] for _ in texts])
        self.assertTrue(request.called)
        self.assertEqual(output['source_relations'],[])
        self.assertEqual(output['document_relations']['candidate_search']['state'],'dense_and_lexical')
        units=request.call_args.args[0]
        self.assertTrue(any(c['id']!=u['id'] for u in units for w in u['context_windows'] for c in w['contexts']))

    def test_candidate_search_failure_is_explicit_and_no_qwen_is_used(self):
        tree=build_document_structure([region('a','Alpha.',0),region('b','Beta.',1)])
        with patch('ai_extract.services.contract_pipeline_service.request_qwen') as qwen:
            units,state=document_context_units(tree,embedding=Mock(side_effect=RuntimeError('Offline')))
        qwen.assert_not_called()
        self.assertTrue(units)  # Native neighbors are still available as candidates.
        self.assertEqual(state['state'],'lexical_only')
        self.assertEqual(state['dense_error'],'RuntimeError')

    def test_context_offsets_are_absolute_even_for_a_middle_source_window(self):
        a,b,unit,_=self.pair()
        prefix='Preface. '
        unit['context_windows'][0]['contexts'][0]['offset']=len(prefix)
        predictor=Mock(device='cuda:0')
        start=len(a)+len(CONTEXT_SEPARATOR)
        predictor.inference.return_value=([[dict(start=start,end=start+3,text='XYZ',label='product',score=.95)]],[[]])
        result=infer_entities([unit],predictor)
        entity=result['entities'][0]
        self.assertEqual((entity['source_id'],entity['start'],entity['end']),('b',len(prefix),len(prefix)+3))
        output=extract_graph_entities(dict(leaves=[dict(chunk_id='a',text=a),dict(chunk_id='b',text=prefix+b)]),
                                      lambda units:result,context_units=[unit])
        self.assertEqual(output['status'],'complete')

    def test_a_span_crossing_the_source_boundary_cannot_be_an_entity(self):
        a,b,unit,_=self.pair()
        combined=a+CONTEXT_SEPARATOR+b
        predictor=Mock(device='cuda:0')
        start=len(a)-2;end=len(a)+len(CONTEXT_SEPARATOR)+2
        predictor.inference.return_value=([[dict(start=start,end=end,text=combined[start:end],label='product',score=.99)]],[[]])
        self.assertEqual(infer_entities([unit],predictor)['entities'],[])

    def test_dense_candidates_can_reach_a_distant_different_language_region(self):
        tree=build_document_structure([region('a','Payment obligations',0,page=1),
            region('unrelated','Operating temperature',0,page=2),region('b','Nghĩa vụ thanh toán',0,page=19)])
        embed=lambda texts:[[0.,1.] if text=='Operating temperature' else [1.,0.] for text in texts]
        with patch.dict('os.environ',{'GLINER_DOCUMENT_CANDIDATES':'1'}):
            units,state=document_context_units(tree,embedding=embed)
        a=next(u for u in units if u['id'].startswith('a:'))
        self.assertTrue(any(c['id'].startswith('b:') for w in a['context_windows'] for c in w['contexts']))
        self.assertEqual(state['state'],'dense_and_lexical')
