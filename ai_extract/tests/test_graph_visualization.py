"""Graph preview preserves actual snapshot scope and source links."""
from unittest.mock import patch
from django.test import SimpleTestCase
from django.template.loader import render_to_string
from ai_extract.services.graph_visualization_service import graph_payload
from ai_extract.tests.test_document_graph import fixture


class GraphVisualizationTests(SimpleTestCase):
    def test_default_page_filter_requests_entity_mentions(self):
        run,_=fixture()
        run.structure['graph_index']=dict(status='ready')
        actual=dict(status='ready',nodes=[],edges=[],counts={},total_nodes=0,
                    total_edges=0,matched_edges=0,offset=0,limit=60)
        with patch('ai_extract.services.graph_visualization_service.document_graph_repository.visualization',return_value=actual) as read:
            graph_payload(run,2,3,page=1)
        self.assertIn('MENTIONS',read.call_args.args[1])
        self.assertIn('APPLIES_TO',read.call_args.args[1])
        self.assertIn('HAS_DEADLINE',read.call_args.args[1])

    def test_embedded_graph_json_escapes_document_text(self):
        html=render_to_string('ai_extract/graph_visualization.html',dict(
            graph_visualization=dict(status='ready',nodes=[dict(label='</script><script>alert(1)</script>')],edges=[],counts={}),
            pages=[]))
        self.assertNotIn('</script><script>alert(1)</script>',html)
        self.assertIn('\\u003C/script\\u003E',html)

    def test_filter_validation_precedes_network_access(self):
        run, _ = fixture()
        with patch('ai_extract.services.graph_visualization_service.document_graph_repository.visualization') as read:
            for args in ({'relation':'DELETE'}, {'page':'-1'}, {'offset':'-1'}):
                with self.assertRaises(ValueError):
                    graph_payload(run,2,3,**args)
            read.assert_not_called()

    def test_database_graph_keeps_scope_and_source_provenance(self):
        run, _ = fixture()
        run.structure['graph_index']=dict(status='ready')
        actual=dict(status='ready',nodes=[dict(key='actual-key',category='evidence',text='Source',page_number=1,source_id='block:10')],
                    edges=[dict(type='RELATED',from_key='actual-key',to_key='other',source_leaf_id='u1',origin='stored-origin')],
                    counts={'RELATED':70},total_nodes=40,total_edges=70,matched_edges=70,offset=0,limit=60)
        with patch('ai_extract.services.graph_visualization_service.document_graph_repository.visualization',return_value=actual) as read, \
             patch('ai_extract.services.graph_visualization_service.layout_repository.graph_source_blocks',return_value={}):
            result=graph_payload(run,2,3,page='1',relation='RELATED')
        scope,kinds,page,offset=read.call_args.args
        self.assertEqual((scope['company_id'],scope['contract_id'],scope['version_id'],scope['run_id']),(1,2,3,7))
        self.assertEqual((kinds,page,offset),(('RELATED',),1,0))
        self.assertEqual(result['nodes'][0]['key'],'actual-key')
        self.assertEqual(result['edges'][0]['origin'],'stored-origin')
        self.assertTrue(result['edges'][0]['source_url'].endswith('version_id=3#block-10'))
        self.assertTrue(result['has_next'])

    def test_missing_snapshot_does_not_generate_projection(self):
        run,_=fixture();run.structure={}
        with patch('ai_extract.services.graph_visualization_service.document_graph_repository.visualization') as read:
            result=graph_payload(run,2,3)
        read.assert_not_called()
        self.assertEqual(result['nodes'],[])
        self.assertEqual(result['status'],'not_indexed')


class GraphTextFromPostgresTests(SimpleTestCase):
    """Neo4j keeps ids; the viewer reads the words from the extraction stored in PostgreSQL."""
    def test_snapshot_written_to_neo4j_carries_no_source_text(self):
        from ai_extract.repositories import document_graph_repository as repository
        nodes = repository.without_text([dict(key='k', leaf_id='u1', text='Pump A', content='x', name='Pump')], repository.NODE_TEXT_FIELDS)
        edges = repository.without_text([dict(type='RELATED', quote='Pump A', target_quote='Motor', source_leaf_id='u1')], repository.EDGE_TEXT_FIELDS)
        self.assertEqual((nodes, edges), ([dict(key='k', leaf_id='u1', name='Pump')], [dict(type='RELATED', source_leaf_id='u1')]))

    def test_evidence_and_table_cells_take_their_text_from_the_run(self):
        run, _ = fixture()
        run.structure['graph_index'] = dict(status='ready')
        run.structure['leaves'].append(dict(chunk_id='t1', node_id='t1', page_number=2, text='',
                                            structure_metadata=dict(table_rows=[['Mã', 'Giá'], ['KĐ.10', '1,25']])))
        actual = dict(status='ready', counts={}, total_nodes=2, total_edges=0, matched_edges=0, offset=0, limit=60, edges=[],
                      nodes=[dict(key='s:leaf:u1', category='evidence', leaf_id='u1'),
                             dict(key='s:t:row:2:cell:2', category='table_cell', table_leaf_id='t1', row_index=2, column_index=2)])
        with patch('ai_extract.services.graph_visualization_service.document_graph_repository.visualization', return_value=actual), \
             patch('ai_extract.services.graph_visualization_service.layout_repository.graph_source_blocks', return_value={}):
            result = graph_payload(run, 2, 3)
        self.assertEqual([n['text'] for n in result['nodes']], ['Pump A contains Motor B.', '1,25'])
        self.assertEqual(result['nodes'][1]['label'], '1,25')
