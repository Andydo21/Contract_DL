"""Register the inference gateway's HTTP routes over the A3 model services."""
import base64
import io
import threading
from ai_extract.services.inference_runtime_service import gpu_stage

def register_contract_rag(app):
    from fastapi import HTTPException
    from ai_extract.services.surya_inference_service import create_surya_predictor, surya_page
    ocr_lock = threading.Lock()
    models = {}
    from ai_extract.services.inference_runtime_service import TextModelRuntime, model_inputs, run_batches
    runtime = TextModelRuntime()
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
                    dependency_available=importlib.util.find_spec('gliner') is not None,
                    checkpoint_available=(path/'gliner_config.json').is_file() and (path/'model.safetensors').is_file(),task='entity_relation_proposals')

    @app.post('/rag/gliner_entities')
    def gliner_entities(data: dict):
        from ai_extract.services import gliner_entity_service as service
        try:
            units=data.get('units')
            if (not isinstance(units,list) or len(units)>16 or any(not isinstance(u,dict)
                    or not isinstance(u.get('id'),str) or not isinstance(u.get('text'),str) for u in units)
                    or len({u['id'] for u in units})!=len(units)):
                raise ValueError('Invalid GLiNER source batch')
            import torch
            with gpu_stage(), torch.inference_mode(), torch.autocast('cuda',dtype=torch.float16):
                from ai_extract.services.surya_inference_service import release_surya_backend
                release_surya_backend();runtime.park()
                return service.infer_entities(units)
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('GLiNER source extraction failed')
            raise HTTPException(503,f'GLiNER unavailable: {type(error).__name__}') from error


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
            with gpu_stage(), torch.inference_mode(), torch.autocast('cuda',dtype=torch.float16):
                from ai_extract.services.surya_inference_service import release_surya_backend
                release_surya_backend();runtime.park()
                return service.infer_structure_pairs(data.get('pairs'))
        except ValueError as error:
            raise HTTPException(400,'Invalid structure sources') from error
        except Exception as error:
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
        path = Path(os.getenv('QWEN_TOKENIZER_PATH', 'scratch/a3-models/qwen-tokenizer'))
        try:
            manifest = json.loads((path/'tokenizer-manifest.json').read_text(encoding='utf-8'))
            if data.get('model') != manifest['model']:
                raise HTTPException(400, 'Tokenizer model mismatch')
            messages = data.get('messages')
            if not isinstance(messages,list) or not messages or any(not isinstance(m,dict)
                or not isinstance(m.get('content'),(str,list)) for m in messages):
                raise HTTPException(400, 'Invalid tokenizer messages')
            if any(isinstance(m['content'],list) and any(not isinstance(p,dict)
                or p.get('type')!='text' for p in m['content']) for m in messages):
                raise HTTPException(400, 'Use the serving multimodal tokenizer for image requests')
            with tokenizer_lock:
                from transformers import AutoTokenizer
                if 'qwen' not in text_tokenizers:
                    text_tokenizers['qwen'] = AutoTokenizer.from_pretrained(path,local_files_only=True)
                ids = text_tokenizers['qwen'].apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=False)
            return dict(model=manifest['model'],revision=manifest['revision'],count=len(ids))
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(503, f'Text tokenizer unavailable: {type(error).__name__}') from error

    @app.post('/rag/embed')
    def embed(data: dict):
        texts = data.get('texts', [])
        if not isinstance(texts, list) or not 0 < len(texts) <= 32 or any((not isinstance(t, str) or len(t) > 20000 for t in texts)):
            raise HTTPException(400, 'Invalid embedding batch')
        try:
            import torch
            with gpu_stage(), torch.inference_mode():
                from ai_extract.services.gliner_entity_service import unload as unload_gliner
                unload_gliner()
                from ai_extract.services.surya_inference_service import release_surya_backend
                release_surya_backend()
                import os
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
                               and all(isinstance(t, str) for t in p)
                               and len(p[0]) <= 3000 and len(p[1]) <= 10000 for p in pairs))
        if (pairs is not None and not valid_pairs) or (pairs is None and (not isinstance(query, str) or len(query) > 3000 or (not isinstance(passages, list)) or (not 0 < len(passages) <= 30) or any((not isinstance(p, str) or len(p) > 10000 for p in passages)))):
            raise HTTPException(400, 'Invalid reranking batch')
        try:
            import torch
            with gpu_stage(), torch.inference_mode():
                from ai_extract.services.gliner_entity_service import unload as unload_gliner
                unload_gliner()
                from ai_extract.services.surya_inference_service import release_surya_backend
                release_surya_backend()
                import os
                from ai_extract.services.inference_runtime_service import rerank_passages, rerank_pairs
                scores = rerank_pairs(runtime, pairs) if pairs is not None else rerank_passages(runtime, query, passages)
                return dict(model='BAAI/bge-reranker-v2-m3', scores=scores)
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('BGE reranking failed')
            raise HTTPException(503, f'BGE reranker unavailable: {type(error).__name__}: {error}') from error

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
            with gpu_stage(), ocr_lock:
                from ai_extract.services.gliner_entity_service import unload as unload_gliner
                unload_gliner()
                runtime.park()
                if 'surya' not in models:
                    models['surya'] = create_surya_predictor()
                return surya_page(image, models['surya'], high_resolution_image=sharp) if sharp is not None else surya_page(image,models['surya'])
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception('Surya page inference failed')
            raise HTTPException(503, f'Page extraction unavailable: {type(error).__name__}') from error

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

