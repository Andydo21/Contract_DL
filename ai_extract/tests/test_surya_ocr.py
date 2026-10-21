from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
import hashlib
import io
from django.test import SimpleTestCase, override_settings
from PIL import Image
from ai_extract.services.contract_pipeline_service import surya_page, remote_page
from ai_extract.services.layout_extractor import SuryaExtractor
from ai_extract.services.surya_inference_service import VISUAL_OCR_POLICY, BODY_OCR_POLICY
from ai_extract.repositories import page_inference_cache_repository as cache


class SuryaOCRTests(SimpleTestCase):
    def test_rejected_ocr_cannot_publish_table_cells_from_discarded_html(self):
        from ai_extract.services.document_graph_service import append_layout_edges
        nodes=[]
        leaf=dict(chunk_id='bad',text='',bbox=[10,10,100,100],layout_type='table',
            structure_metadata=dict(ocr_status='unresolved',table_rows=[['Invented']],
                table_cells=[dict(row=1,column=1,text='Invented')]))
        append_layout_edges(dict(leaves=[leaf]),lambda key,**props:nodes.append(props),lambda *args,**props:None)
        self.assertFalse(any(n['category'] in {'table','table_row','table_cell'} for n in nodes))

    def test_picture_text_requires_cross_prompt_agreement_on_same_pixels(self):
        from ai_extract.services.surya_inference_service import SuryaStreamManager,surya_visual_page
        for second_text,expected_count in [('<div>HSR</div>',1),('<div>Unrelated invented text</div>',0)]:
            manager=SuryaStreamManager(Mock())
            manager.generate=Mock(return_value=[SimpleNamespace(error=False,raw=second_text)])
            child=self.block(0,'<p>HSR</p>')
            predictor=Mock(manager=manager,return_value=[SimpleNamespace(blocks=[child])])
            with patch('ai_extract.services.surya_inference_service._visual_layout',return_value=[SimpleNamespace(error=False,bboxes=[])]),patch.dict(
                    'sys.modules',{'surya.inference.schema':SimpleNamespace(BatchInputItem=SimpleNamespace)}):
                result=surya_visual_page(Image.new('RGB',(400,400)),predictor,
                    [dict(label='Picture',bbox=[0,0,400,400],region_id='figure')])
            root=result['regions'][0]
            self.assertEqual(len(root['ocr_lines']),expected_count)
            self.assertEqual(root['children'][0]['ocr_status'],'completed' if expected_count else 'unresolved')
            self.assertEqual(manager.generate.call_args.args[0][0].prompt_type,'high_accuracy_bbox')

    def test_native_html_retains_heading_and_merged_table_cells(self):
        from ai_extract.services.surya_inference_service import source_html_metadata
        self.assertEqual(source_html_metadata('<h3>Robot specifications</h3>')['heading_level'],3)
        metadata=source_html_metadata('<table><tr><th rowspan="2">Item</th><th colspan="2">Models</th></tr>'
            '<tr><td>A</td><td>B</td></tr><tr><td>Load</td><td colspan="2">8 kg</td></tr></table>')
        cells=metadata['table_cells']
        self.assertEqual(cells[0]['rowspan'],2)
        self.assertEqual(cells[2]['column'],2)
        self.assertEqual(cells[-1]['colspan'],2)
        self.assertEqual(metadata['table_rows'][-1],['Load','8 kg',''])
        self.assertEqual(metadata['table_header_origin'],'surya_html_unreviewed')
        self.assertNotIn('heading_level',source_html_metadata('<p>5.1 Any text</p>'))

    def test_old_body_cache_cannot_skip_improved_ocr(self):
        from ai_extract.services.contract_pipeline_service import _cached_page
        old_key=hashlib.sha256(b'old-body').hexdigest();new_key=hashlib.sha256(b'new-body').hexdigest()
        cache.write(old_key,dict(layout=[],ocr_lines=[],metrics={}))
        infer=Mock(return_value=dict(layout=[],ocr_lines=[],cacheable=True))
        upgrade=Mock()
        _cached_page(SimpleNamespace(),'image',new_key,'_page',infer,legacy_key=old_key,upgrade=upgrade)
        infer.assert_called_once();upgrade.assert_not_called()

    def test_visual_text_duplicate_requires_matching_source_position(self):
        from ai_extract.services.surya_inference_service import merge_visual_ocr
        import copy
        page=dict(layout=[dict(label='Text',bbox=[10,10,100,30],region_id='text'),
                          dict(label='Picture',bbox=[0,0,200,200],region_id='image')],
                  ocr_lines=[dict(text='EVP2',bbox=[10,10,100,30],region_id='text')])
        def supplement(box):
            return dict(regions=[dict(index=1,bbox=[0,0,200,200],label='Picture',status='completed',error_type='',
                children=[dict(region_id='image/0',parent_region_id='image',label='Text',bbox=box)],
                ocr_lines=[dict(region_id='image/0',parent_region_id='image',text='EVP2',bbox=box)])],
                metrics=dict(elapsed_s=1),cacheable=True)
        duplicate=merge_visual_ocr(copy.deepcopy(page),supplement([10,10,100,30]))
        self.assertEqual(len(duplicate['ocr_lines']),1)
        self.assertEqual(len(duplicate['layout']),2)
        elsewhere=merge_visual_ocr(copy.deepcopy(page),supplement([10,100,100,120]))
        self.assertEqual(len(elsewhere['ocr_lines']),2)
        self.assertEqual(len(elsewhere['layout']),3)

    def test_failed_visual_text_cannot_enter_lexical_retrieval(self):
        from ai_extract.services.document_structure_service import build_document_structure
        from shared.retrieval import lexical_search
        tree=build_document_structure([dict(chunk_id='bad',text='Bangladesh invented text',layout_type='figure',
            bbox=[0,0,100,100],page_number=1,structure_metadata={'visual_ocr_status':'failed'})])
        self.assertTrue(tree['leaves'][0]['retrieval_excluded'])
        self.assertEqual(lexical_search('Bangladesh',tree['leaves']),[])

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override = override_settings(A3_PAGE_CACHE_ROOT=Path(directory.name))
        override.enable()
        self.addCleanup(override.disable)

    def block(self, order, html, **extra):
        return SimpleNamespace(reading_order=order, html=html, bbox=[10,20,200,100],
            label='Text', confidence=.88, skipped=False, error=False, **extra)

    def test_html_preserves_contract_lines_table_cells_and_reading_order(self):
        predictor = Mock(return_value=[SimpleNamespace(blocks=[
            self.block(1, '<table><tr><td>300</td><td>USD</td></tr><tr><td>15</td><td>days</td></tr></table>'),
            self.block(0, '<h2>Article 1</h2><p>Payment &amp; delivery</p>')])])
        image = Image.new('RGB', (400,400))
        page = surya_page(image, predictor)
        predictor.assert_called_once_with([image], full_page=True)
        self.assertEqual(page['model'], 'surya-ocr-v2')
        self.assertEqual(page['ocr_lines'][0]['text'], 'Article 1\nPayment & delivery')
        self.assertEqual(page['ocr_lines'][1]['text'], '300\tUSD\n15\tdays')
        self.assertEqual(page['ocr_lines'][1]['bbox'], [10,20,200,100])

    def test_failed_block_keeps_bbox_but_never_partial_text_or_success_cache(self):
        block = self.block(0, '')
        block.error = True
        page=surya_page(Image.new('RGB',(20,20)), Mock(return_value=[SimpleNamespace(blocks=[block])]))
        self.assertEqual(page['ocr_lines'],[])
        self.assertEqual(page['layout'][0]['ocr_status'],'failed')
        self.assertFalse(page['cacheable'])

    def visual_prediction(self, raw, error=False, child_box=None, sharp=None):
        body=self.block(0,'<p>Body source</p>')
        body.bbox=[10,250,200,300]
        visual=self.block(1,''); visual.label='Picture'; visual.skipped=True
        child=self.block(0,raw);child.bbox=child_box or [0,0,190,80];child.error=error
        predictor=Mock(manager=SimpleNamespace(),side_effect=[
            [SimpleNamespace(blocks=[body,visual])],[SimpleNamespace(blocks=[child])]])
        with patch('ai_extract.services.surya_inference_service._visual_layout',return_value=[SimpleNamespace(error=False)]):
            page=surya_page(Image.new('RGB',(400,400)),predictor,sharp)
        return page,predictor

    def test_visual_crop_masks_page_text_and_rejects_clipped_duplicate(self):
        from ai_extract.services.surya_inference_service import surya_visual_page
        page=Image.new('RGB',(140,100),'black')
        sharp=Image.new('RGB',(280,200),'black')
        duplicate=self.block(0,'<p>clipped page text</p>');duplicate.bbox=[5,2,18,16]
        inside=self.block(1,'<p>Inside image</p>');inside.bbox=[70,40,120,60]
        predictor=Mock(manager=SimpleNamespace(),return_value=[SimpleNamespace(blocks=[duplicate,inside])])
        def layout(crops,manager):
            self.assertEqual(crops[0].getpixel((10,10)),(255,255,255))
            self.assertEqual(crops[0].getpixel((100,100)),(0,0,0))
            return [SimpleNamespace(error=False)]
        with patch('ai_extract.services.surya_inference_service._visual_layout',side_effect=layout):
            result=surya_visual_page(page,predictor,[
                dict(label='Text',bbox=[0,0,60,20],region_id='text'),
                dict(label='Picture',bbox=[40,0,140,100],region_id='image')],high_resolution_image=sharp)
        self.assertEqual([l['text'] for l in result['regions'][0]['ocr_lines']],['Inside image'])
        self.assertEqual(result['regions'][0]['excluded_page_text'],1)
        self.assertEqual(result['regions'][0]['status'],'completed')
        self.assertEqual(sharp.getpixel((100,10)),(0,0,0))

    def test_skipped_picture_is_read_without_changing_parent_layout_or_bbox(self):
        page,predictor=self.visual_prediction('<p>AX-203</p><p>24 V</p>')
        self.assertEqual(page['layout'][1]['label'],'Picture')
        self.assertEqual(page['layout'][1]['bbox'],[10,20,200,100])
        self.assertEqual(page['layout'][2]['parent_region_id'],'surya:1')
        self.assertEqual(page['ocr_lines'][-1]['region_id'],'surya:1/0')
        self.assertEqual(page['ocr_lines'][-1]['text'],'AX-203\n24 V')
        self.assertEqual(page['ocr_lines'][-1]['bbox'],[10,20,200,100])
        self.assertEqual(page['ocr_lines'][-1]['text_bbox_scope'],'surya_layout_region')
        self.assertFalse(predictor.call_args.kwargs['full_page'])

    def test_graphic_description_is_rejected_as_source_text(self):
        page,_=self.visual_prediction('<img alt="A diagram"/><p>The diagram illustrates a system.</p>')
        self.assertTrue(page['cacheable'])
        self.assertEqual(page['layout'][1]['visual_ocr_status'],'unresolved')
        self.assertEqual([l['text'] for l in page['ocr_lines']],['Body source'])

    def test_child_ocr_maps_sharper_pixels_to_original_page_coordinates(self):
        page,_=self.visual_prediction('<p>AX-203</p>',child_box=[6,8,40,32],sharp=Image.new('RGB',(800,800)))
        self.assertEqual(page['ocr_lines'][-1]['text'],'AX-203')
        self.assertEqual(page['ocr_lines'][-1]['bbox'],[13,24,30,36])
        self.assertTrue(page['cacheable'])

    def test_visual_failure_retains_body_without_accepting_partial_text(self):
        page,_=self.visual_prediction('<p>unfinished',error=True)
        self.assertEqual([l['text'] for l in page['ocr_lines']],['Body source'])
        self.assertFalse(page['cacheable'])
        self.assertEqual(page['layout'][1]['visual_ocr_status'],'failed')

    def test_text_label_is_not_dropped_by_arbitrary_font_height(self):
        page,_=self.visual_prediction('<p>EVP2</p>',child_box=[3,4,45,10])
        self.assertEqual(page['ocr_lines'][-1]['text'],'EVP2')
        self.assertEqual(page['layout'][-1]['ocr_status'],'completed')

    def test_picture_without_text_remains_successful_empty_visual(self):
        page,_=self.visual_prediction('<p></p>')
        self.assertTrue(page['cacheable'])
        self.assertEqual(page['layout'][1]['visual_ocr_status'],'no_text')
        self.assertEqual(len(page['ocr_lines']),1)

    def test_failed_child_does_not_erase_readable_sibling(self):
        from ai_extract.services.surya_inference_service import surya_visual_page
        good=self.block(0,'<p>EVP2 Runtime</p>');good.bbox=[5,5,195,30]
        bad=self.block(1,'<p>unfinished');bad.bbox=[5,80,195,105];bad.error=True
        predictor=Mock(manager=SimpleNamespace(),return_value=[SimpleNamespace(blocks=[good,bad])])
        with patch('ai_extract.services.surya_inference_service._visual_layout',return_value=[SimpleNamespace(error=False)]):
            result=surya_visual_page(Image.new('RGB',(400,400)),predictor,
                [dict(label='Picture',bbox=[0,0,200,150])])
        row=result['regions'][0]
        self.assertEqual(row['status'],'partial')
        self.assertEqual(row['text'],'')  # Parent is an image, not a text chunk.
        self.assertEqual(row['ocr_lines'][0]['text'],'EVP2 Runtime')
        self.assertEqual(len(row['ocr_lines']),1)
        self.assertFalse(result['cacheable'])

    def test_inner_picture_is_ignored_without_deeper_layout_or_ocr(self):
        from ai_extract.services.surya_inference_service import surya_visual_page
        nested=self.block(0,'');nested.label='Picture';nested.skipped=True;nested.bbox=[10,20,110,120]
        child=self.block(0,'<p>Camera</p>');child.bbox=[5,8,80,30]
        predictor=Mock(manager=SimpleNamespace(),side_effect=[
            [SimpleNamespace(blocks=[nested])],[SimpleNamespace(blocks=[child])]])
        with patch('ai_extract.services.surya_inference_service._visual_layout',side_effect=[
                [SimpleNamespace(error=False)],[SimpleNamespace(error=False)]]) as detect:
            result=surya_visual_page(Image.new('RGB',(400,400)),predictor,
                [dict(label='Picture',bbox=[100,100,300,300])])
        self.assertEqual(detect.call_count,1)
        row=result['regions'][0]
        self.assertEqual(row['ocr_lines'],[])
        self.assertEqual(row['children'],[])
        self.assertEqual(row['status'],'no_text')
        predictor.assert_called_once()

    def test_identical_picture_layout_stops_instead_of_recursing_forever(self):
        from ai_extract.services.surya_inference_service import surya_visual_page
        nested=self.block(0,'');nested.label='Picture';nested.skipped=True;nested.bbox=[0,0,200,200]
        predictor=Mock(manager=SimpleNamespace(),return_value=[SimpleNamespace(blocks=[nested])])
        with patch('ai_extract.services.surya_inference_service._visual_layout',return_value=[SimpleNamespace(error=False)]) as detect:
            result=surya_visual_page(Image.new('RGB',(400,400)),predictor,
                [dict(label='Picture',bbox=[100,100,300,300])])
        self.assertEqual(detect.call_count,1)
        self.assertEqual(result['regions'][0]['status'],'no_text')

    def test_small_image_frame_preserves_pixels_and_remaps_layout_boxes(self):
        from ai_extract.services.surya_inference_service import _visual_layout
        inside=SimpleNamespace(bbox=[210,235,280,265],polygon=[])
        outside=SimpleNamespace(bbox=[0,0,50,50],polygon=[])
        layout=SimpleNamespace(bboxes=[inside,outside],image_bbox=[0,0,512,512])
        def detect(frames):
            self.assertEqual(frames[0].getpixel((206,231)),(0,0,0))
            self.assertEqual(frames[0].getpixel((0,0)),(255,255,255))
            return [layout]
        with patch.dict('sys.modules',{'surya.layout':SimpleNamespace(LayoutPredictor=Mock(return_value=detect))}):
            results=_visual_layout([Image.new('RGB',(100,50),'black')],SimpleNamespace())
        self.assertEqual(results[0].bboxes,[inside])
        self.assertEqual(inside.polygon,[[4,4],[74,4],[74,34],[4,34]])
        self.assertEqual(results[0].image_bbox,[0,0,100,50])

    def test_unreadably_small_picture_labels_are_not_sent_to_ocr_or_marked_failed(self):
        from ai_extract.services.surya_inference_service import surya_visual_page
        tiny=SimpleNamespace(label='Text',bbox=[0,0,25,3])
        readable=SimpleNamespace(label='Text',bbox=[0,10,160,28])
        layout=SimpleNamespace(error=False,bboxes=[tiny,readable])
        block=self.block(0,'<p>Readable label</p>');block.bbox=readable.bbox
        def recognize(images,layout_results,full_page):
            self.assertEqual(layout_results[0].bboxes,[readable])
            return [SimpleNamespace(blocks=[block])]
        predictor=Mock(manager=SimpleNamespace(),side_effect=recognize)
        with patch('ai_extract.services.surya_inference_service._visual_layout',return_value=[layout]):
            result=surya_visual_page(Image.new('RGB',(1241,1755)),predictor,
                [dict(label='Picture',bbox=[0,0,500,500],region_id='image')])
        self.assertEqual(result['metrics']['ignored_tiny_text_regions'],1)
        self.assertEqual(result['metrics']['failed'],0)
        self.assertEqual(result['metrics']['unreadable_regions'],0)
        self.assertEqual(result['regions'][0]['ocr_lines'][0]['text'],'Readable label')

    def test_failed_image_layout_is_retried_once_without_repeating_healthy_siblings(self):
        from ai_extract.services.surya_inference_service import _visual_layout
        for retry_failed in (False,True):
            good=SimpleNamespace(error=False,bboxes=[],image_bbox=[0,0,300,200])
            bad=SimpleNamespace(error=True,bboxes=[],image_bbox=[0,0,300,200])
            box=SimpleNamespace(bbox=[42,52,82,72],polygon=[])
            rescued=SimpleNamespace(error=retry_failed,bboxes=[box],image_bbox=[0,0,364,264])
            detect=Mock(side_effect=[[good,bad],[rescued]])
            with self.subTest(retry_failed=retry_failed), patch.dict('sys.modules',{'surya.layout':SimpleNamespace(LayoutPredictor=Mock(return_value=detect))}):
                result=_visual_layout([Image.new('RGB',(300,200),'black') for _ in range(2)],SimpleNamespace())
            self.assertEqual(detect.call_count,2)
            self.assertEqual(len(detect.call_args_list[1].args[0]),1)
            self.assertIs(result[0],good)
            self.assertEqual(result[1].error,retry_failed)
            self.assertEqual(box.polygon,[[10,20],[50,20],[50,40],[10,40]])

    def test_extractor_keeps_one_chunk_per_region_without_bbox_text_leak(self):
        extractor=SuryaExtractor.__new__(SuryaExtractor)
        regions=[SimpleNamespace(region_id='surya:0',label='Picture',bbox=[0,0,300,300],chunk_policy='surya_layout_region'),
                 SimpleNamespace(region_id='surya:0/0',parent_region_id='surya:0',label='Text',bbox=[10,10,100,100],chunk_policy='surya_layout_region'),
                 SimpleNamespace(region_id='surya:0/1',parent_region_id='surya:0',label='Text',bbox=[10,10,100,100],chunk_policy='surya_layout_region')]
        text='First source\n'+('Long original source '*150)
        extractor._ocr_png_image=Mock(return_value=[dict(region_id='surya:0/0',text=text,bbox=[10,10,100,100]),
            dict(region_id='surya:0/1',text='Different source',bbox=[10,10,100,100])])
        extractor.surya_layout_model=Mock(return_value=[SimpleNamespace(bboxes=regions)])
        extractor._draw_visual_bbox_crop=Mock(return_value='/media/figure.png')
        chunks,count=extractor._extract_chunks_from_page_image(Image.new('RGB',(400,400)),1,1,'test',Path('page.png'),'/media/page.png')
        self.assertEqual(count,4)
        self.assertEqual([c['text'] for c in chunks],['',text,'Different source'])
        self.assertEqual(chunks[1]['surya_parent_region_id'],'surya:0')

    def test_unbound_ocr_is_preserved_without_guessing_paragraph_groups(self):
        extractor=SuryaExtractor.__new__(SuryaExtractor)
        extractor.surya_layout_model=None
        extractor._ocr_png_image=Mock(return_value=[
            dict(region_id='missing',text='First source',bbox=[0,0,100,20]),
            dict(text='Adjacent different source',bbox=[0,20,100,40])])
        chunks,count=extractor._extract_chunks_from_page_image(
            Image.new('RGB',(200,200)),1,1,'test',Path('page.png'),'/media/page.png')
        self.assertEqual([c['text'] for c in chunks],['First source','Adjacent different source'])
        self.assertEqual(count,3)
        self.assertTrue(all(c['reading_order_unresolved'] for c in chunks))
        extractor._ocr_png_image.assert_called_once()

    def test_atomic_chunks_keep_multiline_text_and_image_scope_in_graph(self):
        from ai_extract.services.document_structure_service import build_document_structure
        text='1. Label inside image\n'+('Original source '*100)
        def region(key,parent,kind,content):
            return dict(chunk_id=key,text=content,layout_type=kind,page_number=1,image_path='page.png',bbox=[10,10,500,500],
                structure_metadata=dict(chunk_policy='surya_layout_region',surya_region_id=key,surya_parent_region_id=parent,
                                        reading_order=0,ocr_status='completed'))
        records=[region('heading',None,'title','Document heading'),region('figure',None,'figure',''),
                 region('inside','figure','title',text),region('after',None,'paragraph','Outside image')]
        tree=build_document_structure(records,child_chars=64)
        self.assertEqual(len(tree['leaves']),4)
        inside=next(l for l in tree['leaves'] if l['source_chunk_id']=='inside')
        self.assertEqual(inside['text'],text)
        nodes={n['id']:n for n in tree['nodes']}
        self.assertEqual(nodes[nodes[inside['node_id']]['parent_id']]['kind'],'figure')
        after=next(l for l in tree['leaves'] if l['source_chunk_id']=='after')
        self.assertEqual(nodes[after['node_id']]['title'],'Document heading')

    @override_settings(RAG_INFERENCE_URL='http://inference.test')
    def test_legacy_cache_reads_only_visual_crops_and_reuses_one_page_response(self):
        image=Image.new('RGB',(400,400))
        buffer=io.BytesIO(); image.save(buffer,format='PNG')
        digest=hashlib.sha256(buffer.getvalue()).hexdigest()
        old_key=hashlib.sha256(('surya-v2-cache1:http://inference.test:'+digest).encode()).hexdigest()
        layout=[dict(label='Picture',bbox=[10,20,200,100])]
        cache.write(old_key,dict(model='surya-ocr-v2',layout=layout,metrics=dict(body_ocr_policy=BODY_OCR_POLICY),ocr_lines=[dict(text='Body source',bbox=[0,200,300,300])]))
        response=Mock()
        response.json.return_value=dict(regions=[dict(index=0,label='Picture',bbox=[10,20,200,100],text='AX-203',
            status='completed',error_type='',confidence=.9,
            children=[dict(region_id='surya:0/0',parent_region_id='surya:0',label='Text',bbox=[10,20,200,100],confidence=.9,chunk_policy='surya_layout_region')],
            ocr_lines=[dict(text='AX-203',bbox=[10,20,200,100],region_id='surya:0/0')])],cacheable=True,
            metrics=dict(policy=VISUAL_OCR_POLICY,elapsed_s=.1,regions=1,failed=0))
        extractor=SimpleNamespace()
        with patch('ai_extract.services.contract_pipeline_service.requests.post',return_value=response) as post:
            result=remote_page(extractor,image)
            self.assertEqual([l['text'] for l in result['ocr_lines']],['Body source','AX-203'])
            self.assertTrue(result['body_cache_hit'])
            self.assertTrue(result['visual_cache_upgraded'])
            self.assertTrue(post.call_args.args[0].endswith('/rag/ocr_visual_regions'))
            remote_page(extractor,image)
            self.assertEqual(post.call_count,1)

    @override_settings(RAG_INFERENCE_URL='http://inference.test')
    def test_failed_cache_upgrade_keeps_body_and_retries_next_extraction(self):
        import requests
        image=Image.new('RGB',(400,400)); buffer=io.BytesIO(); image.save(buffer,format='PNG')
        digest=hashlib.sha256(buffer.getvalue()).hexdigest()
        cache.write(hashlib.sha256(('surya-v2-cache1:http://inference.test:'+digest).encode()).hexdigest(),
            dict(model='surya-ocr-v2',layout=[dict(label='Picture',bbox=[10,20,200,100])],
                 metrics=dict(body_ocr_policy=BODY_OCR_POLICY),
                 ocr_lines=[dict(text='Body source',bbox=[0,200,300,300])]))
        with patch('ai_extract.services.contract_pipeline_service.requests.post',side_effect=requests.ReadTimeout()) as post:
            result=remote_page(SimpleNamespace(),image)
            self.assertEqual(result['ocr_lines'][0]['text'],'Body source')
            self.assertFalse(result['cacheable'])
            remote_page(SimpleNamespace(),image)
            self.assertEqual(post.call_count,2)

    @override_settings(RAG_INFERENCE_URL='')
    def test_local_layout_and_ocr_share_cached_prediction(self):
        predictor = Mock(return_value=[SimpleNamespace(blocks=[self.block(0,'<p>Payment</p>')])])
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=Path(directory)), \
             patch.object(SuryaExtractor, '_shared_ocr_predictor', None), \
             patch('ai_extract.services.surya_inference_service.create_surya_predictor', return_value=predictor):
            extractor = SuryaExtractor()
            image = Image.new('RGB',(400,400))
            lines = extractor._ocr_png_image(image)
            layout = extractor.surya_layout_model([image])[0]
            self.assertEqual(lines[0]['text'], 'Payment')
            self.assertEqual(layout.bboxes[0].bbox, lines[0]['bbox'])
            predictor.assert_called_once()

    @override_settings(RAG_INFERENCE_URL='http://inference.test')
    def test_remote_requires_new_surya_protocol(self):
        response = Mock()
        response.json.return_value = dict(model='legacy-ocr', layout=[], ocr_lines=[])
        with patch('ai_extract.services.contract_pipeline_service.requests.post', return_value=response):
            with self.assertRaises(ValueError):
                remote_page(SimpleNamespace(), Image.new('RGB',(20,20)))
