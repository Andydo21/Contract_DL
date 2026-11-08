"""Register the inference gateway's HTTP routes over the A3 model services."""
import base64
import io
import os
import threading
from ai_extract.services.inference_runtime_service import gpu_stage

def register_contract_rag(app):
    from fastapi import HTTPException
    from ai_extract.services.surya_inference_service import create_surya_predictor, surya_page
    ocr_lock = threading.Lock()
    models = {}
    from ai_extract.services.inference_runtime_service import TextModelRuntime, model_inputs, run_batches, configure_idle_model_cleanup
    runtime = TextModelRuntime()
    def release_idle_models():
        from ai_extract.services.surya_inference_service import release_surya_backend
        from ai_extract.services.gliner_entity_service import unload
        from ai_extract.services import vietocr_service
        try:
            release_surya_backend()
        finally:
            try:
                unload()
                vietocr_service.unload()
            finally:
                runtime.unload_all()
    configure_idle_model_cleanup(release_idle_models, float(os.getenv('RAG_IDLE_UNLOAD_SECONDS', '120')))
    @app.get('/rag/structure_health')
    def structure_health():
        return dict(provider='source', model=None, loaded=False,
                    task='model_source_structure_projection', checkpoint_available=True)
    @app.get('/rag/entities_health')
    def entities_health():
        import os
        import importlib.util
        from pathlib import Path
        from ai_extract.services import gliner_entity_service as service
        path=Path(os.getenv('GLINER_MODEL_PATH','scratch/a3-models/gliner-relex-multi-v1.0'))
        return dict(provider='gliner',model=service.MODEL_ID,loaded=service._runtime is not None,
                    entity_schema=service.ENTITY_SCHEMA,entity_threshold=float(os.getenv('GLINER_ENTITY_THRESHOLD','.5')),
                    semantic_relations_enabled=False,
                    dependency_available=importlib.util.find_spec('gliner') is not None,
                    checkpoint_available=(path/'gliner_config.json').is_file() and (path/'model.safetensors').is_file(),task='entity_extraction_only')

    @app.post('/rag/gliner_entities')
    def gliner_entities(data: dict):
        from ai_extract.services import gliner_entity_service as service
        try:
            units=data.get('units')
            if (not isinstance(units,list) or len(units)>service.ENTITY_SOURCE_BATCH_SIZE or any(not isinstance(u,dict)
                    or not isinstance(u.get('id'),str) or not isinstance(u.get('text'),str) for u in units)
                    or len({u['id'] for u in units})!=len(units)):
                raise ValueError('Invalid GLiNER source batch')
            import torch
            with gpu_stage(), torch.inference_mode(), torch.autocast('cuda',dtype=torch.float16):
                from ai_extract.services.surya_inference_service import release_surya_backend
                release_surya_backend();runtime.park()
                result=service.infer_entities(units,include_relations=False)
                service.unload()
                return result
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('GLiNER source extraction failed')
            raise HTTPException(503,f'GLiNER unavailable: {type(error).__name__}') from error


    @app.post('/rag/gliner2_passages')
    def gliner2_passages(data:dict):
        from ai_extract.services.gliner_identity_classifier import infer_passage_links
        try:
            import torch
            with gpu_stage(),torch.inference_mode():
                from ai_extract.services.surya_inference_service import release_surya_backend
                from ai_extract.services.gliner_entity_service import unload
                release_surya_backend();runtime.park();unload()
                return infer_passage_links(data.get('pairs'))
        except ValueError as error:
            raise HTTPException(400,'Invalid passage source pairs') from error
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Passage review failed')
            raise HTTPException(503,'Passage review unavailable: '+type(error).__name__) from error

    @app.post('/rag/passage_mentions')
    def passage_mentions(data:dict):
        from ai_extract.services.passage_reference_service import infer_mentions
        try:
            import torch
            with gpu_stage(),torch.inference_mode():
                from ai_extract.services.surya_inference_service import release_surya_backend
                from ai_extract.services.gliner_entity_service import unload
                release_surya_backend();runtime.park();unload()
                return infer_mentions(data.get('units'))
        except ValueError as error:
            raise HTTPException(400,'Invalid passage units') from error
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Passage mention inference failed')
            raise HTTPException(503,'Passage mentions unavailable: '+type(error).__name__) from error

    @app.post('/rag/contract_clauses')
    def contract_clauses(data:dict):
        from ai_extract.services.contract_clause_service import infer_contract_clauses
        try:
            import torch
            with gpu_stage(),torch.inference_mode():
                from ai_extract.services.surya_inference_service import release_surya_backend
                from ai_extract.services.gliner_entity_service import unload
                release_surya_backend();runtime.park();unload()
                return infer_contract_clauses(data.get('text'),data.get('units'))
        except ValueError as error:
            raise HTTPException(400,'Invalid contract text') from error
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Contract clause inference failed')
            raise HTTPException(503,'Contract clauses unavailable: '+type(error).__name__) from error

    @app.get('/rag/gliner2_identity_health')
    def gliner2_identity_health():
        import os
        from pathlib import Path
        from ai_extract.services.gliner_identity_classifier import MODEL_ID,MODEL_PATH,REVISION,SCHEMA
        path=Path(os.getenv('GLINER2_MODEL_PATH',MODEL_PATH))
        return dict(model=MODEL_ID,revision=REVISION,schema=SCHEMA,
                    checkpoint_available=(path/'model.safetensors').is_file())

    @app.post('/rag/heading_roles')
    def heading_roles(data: dict):
        from ai_extract.services.heading_role_service import infer_roles
        try:
            import torch
            with gpu_stage(),torch.inference_mode():
                # GLiNER2 loads beside nothing else on a 4 GB GPU, as for identity pairs.
                from ai_extract.services.surya_inference_service import release_surya_backend
                from ai_extract.services.gliner_entity_service import unload
                release_surya_backend();runtime.park();unload()
                return infer_roles(data.get('units'),task=data.get('task','role'))
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except TimeoutError as error:
            raise HTTPException(503,'GPU stage busy; retry after the current page') from error
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Heading role inference failed')
            raise HTTPException(503, 'Heading roles unavailable: '+type(error).__name__) from error

    @app.post('/rag/gliner2_identity')
    def gliner2_identity(data: dict):
        from ai_extract.services.gliner_identity_classifier import infer_pairs
        try:
            import torch
            with gpu_stage(),torch.inference_mode():
                from ai_extract.services.surya_inference_service import release_surya_backend
                from ai_extract.services.gliner_entity_service import unload
                release_surya_backend();runtime.park();unload()
                return infer_pairs(data.get('pairs'))
        except ValueError as error:
            raise HTTPException(400,'Invalid identity sources') from error
        except TimeoutError as error:
            raise HTTPException(503,'GPU stage busy; retry after the current page',
                                headers={'Retry-After':'30'}) from error
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('GLiNER2 identity inference failed')
            raise HTTPException(503,f'GLiNER2 unavailable: {type(error).__name__}') from error

    @app.post('/rag/gliner2_references')
    def gliner2_references(data: dict):
        from ai_extract.services.gliner_entity_service import infer_reference_pairs,unload
        try:
            pairs=data.get('pairs')
            if (not isinstance(pairs,list) or any(not isinstance(p,dict)
                    or not isinstance(p.get('context_group'),dict) for p in pairs)):
                raise ValueError('Reference inference requires complete layout candidate groups')
            import torch
            with gpu_stage(),torch.inference_mode():
                from ai_extract.services.surya_inference_service import release_surya_backend
                release_surya_backend();runtime.park();unload()
                return infer_reference_pairs(pairs)
        except ValueError as error:
            raise HTTPException(400,'Invalid described reference sources or output') from error
        except TimeoutError as error:
            raise HTTPException(503,'GPU stage busy',headers={'Retry-After':'30'}) from error
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('GLiNER2 described reference inference failed')
            raise HTTPException(503,f'Described reference inference unavailable: {type(error).__name__}') from error

    @app.post('/rag/gliner_identity')
    def gliner_identity(data: dict):
        from ai_extract.services import gliner_entity_service as service
        try:
            import torch
            with gpu_stage(), torch.inference_mode(), torch.autocast('cuda',dtype=torch.float16):
                from ai_extract.services.surya_inference_service import release_surya_backend
                release_surya_backend();runtime.park()
                return service.infer_identity_pairs(data.get('pairs'))
        except ValueError as error:
            raise HTTPException(400,'Invalid identity sources') from error
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('GLiNER identity inference failed')
            raise HTTPException(503,f'Identity inference unavailable: {type(error).__name__}') from error

    @app.post('/rag/gliner_structure')
    def gliner_structure(data: dict):
        from ai_extract.services import gliner_entity_service as service
        try:
            import torch
            with gpu_stage(), torch.inference_mode():
                from ai_extract.services.surya_inference_service import release_surya_backend
                release_surya_backend();runtime.park();service.unload()
                return service.infer_structure_pairs(data.get('pairs'))
        except ValueError as error:
            raise HTTPException(400,'Invalid structure sources') from error
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('GLiNER structure pair classification failed')
            raise HTTPException(503,f'Structure review unavailable: {type(error).__name__}') from error

    @app.get('/rag/health')
    def health():
        import importlib.util
        return dict(model_family='contract-a3', loaded=list(models) + list(runtime.models), text_runtime=runtime.health(), dependencies={name: importlib.util.find_spec(name) is not None for name in ('torch', 'transformers', 'surya')})

    tokenizer_lock = threading.Lock()
    text_tokenizers = {}

    @app.post('/rag/tokenize')
    def tokenize(data: dict):
        from pathlib import Path
        import json
        import os
        # One tokenizer per served model (scratch/a3-models/tokenizers/<org>--<name>); the older single folder stays
        # as the fallback for the model it was saved for.
        model = str(data.get('model') or '')
        path = Path('scratch/a3-models/tokenizers')/model.replace('/','--')
        if not model or '..' in model or not (path/'tokenizer-manifest.json').is_file():
            path = Path(os.getenv('QWEN_TOKENIZER_PATH', 'scratch/a3-models/qwen-tokenizer'))
        try:
            manifest = json.loads((path/'tokenizer-manifest.json').read_text(encoding='utf-8'))
            if model != manifest['model']:
                raise HTTPException(400, 'Tokenizer model mismatch')
            options = data.get('chat_template_kwargs') or {}
            if not isinstance(options, dict) or set(options) - {'enable_thinking'}:
                raise HTTPException(400, 'Unsupported chat template options')
            messages = data.get('messages')
            if not isinstance(messages,list) or not messages or any(not isinstance(m,dict)
                or not isinstance(m.get('content'),(str,list)) for m in messages):
                raise HTTPException(400, 'Invalid tokenizer messages')
            if any(isinstance(m['content'],list) and any(not isinstance(p,dict)
                or p.get('type')!='text' for p in m['content']) for m in messages):
                raise HTTPException(400, 'Use the serving multimodal tokenizer for image requests')
            with tokenizer_lock:
                from transformers import AutoTokenizer
                if model not in text_tokenizers:
                    text_tokenizers[model] = AutoTokenizer.from_pretrained(path,local_files_only=True)
                ids = text_tokenizers[model].apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
                                                                 return_dict=False,**options)
            return dict(model=manifest['model'],revision=manifest['revision'],count=len(ids))
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(503, f'Text tokenizer unavailable: {type(error).__name__}') from error

    query_runtime = {}
    query_lock = threading.Lock()

    def embed_queries(texts):
        """Questions are a few short lines: a CPU copy of BGE-M3 embeds them without taking the GPU
        from OCR or the reranker, which each question otherwise unloaded and reloaded."""
        import torch
        from ai_extract.services.inference_runtime_service import TextModelRuntime
        with query_lock, torch.inference_mode():
            if 'bge' not in query_runtime:
                query_runtime['bge'] = TextModelRuntime(device='cpu')
            tokenizer, network = query_runtime['bge'].get('BAAI/bge-m3')
            batch = tokenizer(texts, padding=True, truncation=True, max_length=1024, return_tensors='pt')
            vectors = torch.nn.functional.normalize(network(**model_inputs(batch, network)).last_hidden_state[:, 0], p=2, dim=1)
            return vectors.float().tolist()

    @app.post('/rag/embed')
    def embed(data: dict):
        texts = data.get('texts', [])
        if not isinstance(texts, list) or not 0 < len(texts) <= 32 or any((not isinstance(t, str) or len(t) > 20000 for t in texts)):
            raise HTTPException(400, 'Invalid embedding batch')
        if data.get('purpose') not in (None, 'query', 'document'):
            raise HTTPException(400, 'Invalid embedding purpose')
        try:
            import torch
            if data.get('purpose') == 'query' and os.getenv('RAG_QUERY_EMBED_DEVICE', 'cpu') == 'cpu':
                return dict(model='BAAI/bge-m3', embeddings=embed_queries(texts), device='cpu')
            with gpu_stage(), torch.inference_mode():
                from ai_extract.services.gliner_entity_service import unload as unload_gliner
                unload_gliner()
                from ai_extract.services.surya_inference_service import release_surya_backend
                release_surya_backend()
                tokenizer, network = runtime.get('BAAI/bge-m3')
                def encode(chunk):
                    batch = tokenizer(chunk, padding=True, truncation=True, max_length=1024, return_tensors='pt')
                    vectors = torch.nn.functional.normalize(network(**model_inputs(batch, network)).last_hidden_state[:, 0], p=2, dim=1)
                    return vectors.cpu().float().tolist()
                return dict(model='BAAI/bge-m3', embeddings=run_batches(texts, 8, encode, torch))
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('BGE embedding failed')
            raise HTTPException(503, f'BGE embedding unavailable: {type(error).__name__}: {error}') from error

    @app.post('/rag/rerank')
    def rerank(data: dict):
        passages = data.get('passages', [])
        query = data.get('query', '')
        pairs = data.get('pairs')
        valid_pairs = (isinstance(pairs, list) and 0 < len(pairs) <= 120
                       and all(isinstance(p, (list, tuple)) and len(p) == 2
                               and all(isinstance(t, str) for t in p) for p in pairs))
        if (pairs is not None and not valid_pairs) or (pairs is None and (not isinstance(query, str) or (not isinstance(passages, list)) or (not 0 < len(passages) <= 30) or any(not isinstance(p, str) for p in passages))):
            raise HTTPException(400, 'Invalid reranking batch')
        try:
            import torch
            with gpu_stage(), torch.inference_mode():
                from ai_extract.services.gliner_entity_service import unload as unload_gliner
                unload_gliner()
                from ai_extract.services.surya_inference_service import release_surya_backend
                release_surya_backend()
                from ai_extract.services.inference_runtime_service import rerank_passages, rerank_pairs
                scores = rerank_pairs(runtime, pairs) if pairs is not None else rerank_passages(runtime, query, passages)
                return dict(model='BAAI/bge-reranker-v2-m3', scores=scores)
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('BGE reranking failed')
            raise HTTPException(503, f'BGE reranker unavailable: {type(error).__name__}: {error}') from error

    @app.post('/rag/table_cells')
    def table_cells(data: dict):
        """Bounded physical-cell OCR used before source persistence."""
        try:
            from PIL import Image
            from ai_extract.services.surya_inference_service import recognize_physical_table
            encoded=data.get('image_base64','');source_cells=data.get('source_cells',[])
            vietocr_scale=data.get('vietocr_scale',1.0)
            if type(vietocr_scale) not in (int,float) or not .25<=vietocr_scale<=1:raise ValueError('Invalid VietOCR scale')
            if (not isinstance(encoded,str) or len(encoded)>16000000
                    or not isinstance(source_cells,list) or len(source_cells)>2048
                    or any(not isinstance(c,dict) or not isinstance(c.get('text',''),str)
                           or len(c.get('text',''))>32000
                           or any(type(c.get(k,1)) is not int or not 1<=c.get(k,1)<=2048
                                  for k in ('row','column','rowspan','colspan')) for c in source_cells)
                    or sum(len(c.get('text','')) for c in source_cells)>128000):
                raise ValueError('Invalid table crop')
            image=Image.open(io.BytesIO(base64.b64decode(encoded,validate=True))).convert('RGB')
            if image.width*image.height>16000000:raise ValueError('Table image too large')
            with gpu_stage(),ocr_lock:
                from ai_extract.services.gliner_entity_service import unload as unload_gliner
                unload_gliner();runtime.park()
                if 'surya' not in models:models['surya']=create_surya_predictor()
                models['surya'].manager.begin_page()
                return recognize_physical_table(image,models['surya'],source_cells,vietocr_scale=float(vietocr_scale))
        except ValueError as error:
            raise HTTPException(422,str(error)) from error
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Physical table OCR failed')
            raise HTTPException(503,f'Table OCR unavailable: {type(error).__name__}') from error

    @app.post('/rag/extract_page')
    def extract_page(data: dict):
        encoded = data.get('image_base64', '')
        if not isinstance(encoded, str) or len(encoded) > 16000000:
            raise HTTPException(400, 'Invalid image')
        try:
            from PIL import Image
            image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))).convert('RGB')
            sharp = decode_visual_source(data)
            if image.width * image.height > 16000000:
                raise ValueError('Image too large')
            text_engine = data.get('text_engine', 'surya')
            with gpu_stage(), ocr_lock:
                from ai_extract.services.gliner_entity_service import unload as unload_gliner
                unload_gliner()
                runtime.park()
                if 'surya' not in models:
                    models['surya'] = create_surya_predictor()
                options = {} if sharp is None else dict(high_resolution_image=sharp)
                if text_engine != 'surya':
                    options['text_engine'] = text_engine
                return surya_page(image, models['surya'], **options)
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Surya page inference failed')
            raise HTTPException(503, f'Page extraction unavailable: {type(error).__name__}') from error

    @app.post('/rag/page_orientation')
    def page_orientation(data: dict):
        encoded = data.get('image_base64', '')
        if not isinstance(encoded, str) or not encoded or len(encoded) > 16000000:
            raise HTTPException(400, 'Invalid image')
        try:
            from PIL import Image
            image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True)))
            if image.width*image.height > 16000000:
                raise ValueError('Image too large')
        except Exception as error:
            raise HTTPException(400, f'Invalid image: {type(error).__name__}') from error
        try:
            from ai_extract.services.page_orientation_service import infer
            return infer(image)
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Page orientation failed')
            raise HTTPException(503, f'Page orientation unavailable: {type(error).__name__}') from error

    @app.post('/rag/ocr_visual_regions')
    def ocr_visual_regions(data: dict):
        """Upgrade an exact-image OCR cache by reading only its visual regions."""
        try:
            from PIL import Image
            encoded, layout = data.get('image_base64',''),data.get('layout')
            if not isinstance(encoded,str) or len(encoded)>16000000 or not isinstance(layout,list) or len(layout)>300:
                raise ValueError('Invalid visual OCR request')
            image = Image.open(io.BytesIO(base64.b64decode(encoded,validate=True))).convert('RGB')
            sharp = decode_visual_source(data)
            if image.width*image.height>16000000: raise ValueError('Image too large')
            from ai_extract.services.surya_inference_service import surya_visual_page
            with gpu_stage(),ocr_lock:
                from ai_extract.services.gliner_entity_service import unload as unload_gliner
                unload_gliner()
                runtime.park()
                if 'surya' not in models: models['surya']=create_surya_predictor()
                return surya_visual_page(image,models['surya'],layout,high_resolution_image=sharp)
        except ValueError as error:
            raise HTTPException(400,'Invalid visual OCR request') from error
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Surya visual OCR failed')
            raise HTTPException(503,f'Visual OCR unavailable: {type(error).__name__}') from error


def decode_visual_source(data):
    """Optional sharper rendering of the same page; never a PDF text layer."""
    from PIL import Image
    encoded=data.get('high_resolution_image_base64')
    if encoded is None:return None
    if not isinstance(encoded,str) or len(encoded)>32000000:raise ValueError('Invalid visual source image')
    image=Image.open(io.BytesIO(base64.b64decode(encoded,validate=True))).convert('RGB')
    if image.width*image.height>24000000:raise ValueError('Visual source image too large')
    return image

