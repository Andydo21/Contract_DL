"""Figure-only visual indexing and source identity across Qdrant, graph and A2."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from PIL import Image
from django.test import SimpleTestCase, override_settings

from ai_extract.services.layout_extractor import visual_sources, colpali_point_id
from ai_extract.services.contract_pipeline_service import hydrate, IndexResult, PlanACollectionIndexer
from ai_extract.services.document_graph_service import projection
from ai_extract.tests.test_document_graph import fixture
from ai_extract.tests.test_hybrid_retrieval import version
from shared.retrieval import LexicalOnlyReranker


class ColPaliFigureTests(SimpleTestCase):
    @override_settings(COLPALI_ENABLED=False)
    def test_disabled_colpali_skips_without_remote_or_database_calls(self):
        indexer = object.__new__(PlanACollectionIndexer)
        with patch('ai_extract.services.contract_pipeline_service.requests.post') as post:
            result = indexer.index_colpali(NS(id=7), page_number=1)
        self.assertEqual(result.status, 'SKIPPED')
        self.assertEqual(indexer._colpali_url(), '')
        post.assert_not_called()

    def run_with(self, blocks, path='page.png'):
        page = NS(id=8, pk=8, page_number=1, image_path=path, blocks=Mock())
        page.blocks.all.return_value = blocks
        run = NS(id=7, pk=7, pages=Mock())
        run.pages.prefetch_related.return_value.order_by.return_value = [page]
        run.pages.filter.return_value = run.pages
        return run, page

    def test_png_is_exact_figure_crop_and_text_table_blocks_are_not_indexed(self):
        blocks = [NS(pk=10,layout_type='figure',bbox=[200,100,600,900]),
                  NS(pk=11,layout_type='paragraph'), NS(pk=12,layout_type='table')]
        run, _ = self.run_with(blocks)
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            image = Image.new('RGB',(100,100),'red')
            image.paste('blue',(20,10,60,90)); image.save(Path(directory)/'page.png')
            sources = list(visual_sources(run))
            self.assertEqual(len(sources),1)
            self.assertEqual(sources[0].block.pk,10)
            with Image.open(Path(directory)/sources[0].image_path) as crop:
                self.assertEqual(crop.format,'PNG')
                self.assertEqual(crop.size,(40,80))
                self.assertEqual(crop.getpixel((0,0)),(0,0,255))

    def test_text_only_page_has_no_full_page_fallback(self):
        run, _ = self.run_with([NS(pk=1,layout_type='paragraph')])
        self.assertEqual(list(visual_sources(run)),[])

    def test_full_page_input_cannot_reach_remote_embed(self):
        indexer = object.__new__(PlanACollectionIndexer)
        indexer.client = Mock()
        with patch.object(indexer,'_colpali_url',return_value='http://test'), \
             patch.object(indexer,'_ensure_collection'), \
             patch('ai_extract.services.contract_pipeline_service.requests.post') as post:
            result = indexer.index_colpali(NS(id=7),page_number=1,
                visuals=[NS(page=NS(page_number=1),block=None,image_path='page.png')])
        self.assertEqual(result.status,'FAILED')
        post.assert_not_called()

    def test_written_point_keeps_figure_bbox_and_graph_identity(self):
        block = NS(id=10,pk=10,layout_type='figure',bbox=[200,100,600,900],
                   text='',structure_metadata={})
        run, page = self.run_with([block])
        run.version_id = 3
        run.version = NS(contract=NS(id=2,company_id=1,title='Manual',contract_code='C'))
        indexer = object.__new__(PlanACollectionIndexer)
        indexer.client = Mock()
        response = Mock()
        response.json.return_value = {'embeddings':[[1.0]*128]}
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory,MEDIA_URL='/media/'), \
             patch.object(indexer,'_colpali_url',return_value='http://test'), \
             patch.object(indexer,'_ensure_collection'), \
             patch('ai_extract.services.contract_pipeline_service.requests.post',return_value=response):
            Image.new('RGB',(100,100)).save(Path(directory)/'page.png')
            sources = list(visual_sources(run))
            result = indexer.index_colpali(run,page_number=1,visuals=sources)
        point = indexer.client.upsert.call_args.kwargs['points'][0]
        self.assertEqual(result.status,'COMPLETED')
        self.assertEqual(result.point_ids,(colpali_point_id(7,8,10),))
        self.assertEqual(point.payload['visual_block_id'],10)
        self.assertEqual(point.payload['bbox'],block.bbox)
        self.assertEqual(point.payload['visual_node_id'],'layout-block:1:block:10')
        self.assertEqual(point.payload['image_path'],sources[0].image_path)
        self.assertEqual(point.payload['visual_scope'],'figure')

    def test_graph_link_only_exists_for_acknowledged_figure_point(self):
        run, tree = fixture()
        leaf = tree['leaves'][0]
        leaf.update(layout_type='figure',image_path='crop.png',page_image_path='page.png')
        block = NS(pk=10,layout_type='figure')
        fake, page = self.run_with([block])
        run.pages = fake.pages
        point_id = colpali_point_id(run.pk,page.pk,block.pk)
        for ids in ([],[point_id]):
            tree['colpali_point_ids'] = ids
            _,nodes,edges = projection(run,tree)
            links = [e for e in edges if e['type']=='HAS_EMBEDDING']
            self.assertEqual(len(links),len(ids))
            if ids:
                vector = next(n for n in nodes if n['category']=='visual_embedding')
                self.assertEqual(vector['point_id'],point_id)
                self.assertEqual(vector['storage'],'qdrant')
                self.assertTrue(links[0]['from_key'].endswith('layout-block:1:block:10'))

    def test_same_page_figures_do_not_hydrate_other_regions_or_legacy_page_hits(self):
        leaves = [dict(chunk_id=f'leaf{i}',source_chunk_id=f'block:{i}',page_number=1,
                       text='',heading_path=[],image_path='page.png') for i in (10,11,12)]
        scope = dict(source_app='contract_dl',company_id=1,contract_id=2,version_id=3,
                     contract_dl_run_id=7,page_number=1,visual_scope='figure')
        points = [NS(id=str(i),score=.9,payload=dict(scope,visual_block_id=i,image_path=f'crop{i}.png'))
                  for i in (10,11)]
        points.append(NS(id='old',score=.9,payload=dict(scope,visual_scope='page')))
        result = hydrate(points,leaves,version(),7,True)
        self.assertEqual([r['chunk_id'] for r in result],['leaf10','leaf11'])
        self.assertEqual([r['image_path'] for r in result],['crop10.png','crop11.png'])
        fused = LexicalOnlyReranker.reciprocal_rank_fusion({'keyword':[leaves[0]],'colpali':result})
        self.assertEqual(fused[0]['image_path'],'crop10.png')
        self.assertEqual(fused[0]['colpali_point_id'],'10')

    def test_skipped_text_pages_do_not_mark_successful_figure_index_partial(self):
        result = IndexResult.combine([IndexResult('SKIPPED'),IndexResult('COMPLETED',1,point_ids=('x',))])
        self.assertEqual(result.status,'COMPLETED')
        self.assertEqual(result.point_ids,('x',))
