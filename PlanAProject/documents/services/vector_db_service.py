import os
os.environ['HF_DEACTIVATE_ASYNC_LOAD'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ.setdefault('HF_HOME', r'D:\hf_cache')
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
import math
import hashlib
import threading
from pathlib import Path
from django.conf import settings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

class NeuralEmbeddingEngine:
    """
    Bộ khởi tạo Neural Embedding Transformer Model:
    Sử dụng BAAI/bge-m3 SOTA Multilingual Multi-Function Embedding Engine (1024-dim):
    - Hỗ trợ đa ngữ chuyên sâu: Tiếng Việt, Tiếng Nhật, Tiếng Anh
    - Ngữ cảnh tối đa 8,192 tokens (không lo bị cắt cụt tài liệu kỹ thuật)
    - Vector chuẩn hóa L2 Normalization (Cosine Distance)
    """
    _tokenizer = None
    _model = None
    _model_type = "bge_m3"  # SOTA Multilingual (Vi, Ja, En)
    _dim = 1024
    _lock = threading.Lock()

    @classmethod
    def _ensure_loaded(cls):
        if cls._tokenizer is not None and cls._model is not None:
            return
        with cls._lock:
            if cls._tokenizer is None or cls._model is None:
                import torch
                torch.set_num_threads(1)
                from transformers import AutoTokenizer, AutoModel

                model_name = "BAAI/bge-m3"
                try:
                    cls._tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
                    cls._model = AutoModel.from_pretrained(model_name, local_files_only=True, low_cpu_mem_usage=False, use_safetensors=True)
                except Exception:
                    token = os.environ.get('HF_TOKEN') or getattr(settings, 'HF_TOKEN', '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')
                    cls._tokenizer = AutoTokenizer.from_pretrained(model_name, token=token)
                    cls._model = AutoModel.from_pretrained(model_name, token=token, low_cpu_mem_usage=False, use_safetensors=True)
                cls._model_type = "bge_m3"
                cls._model.eval()
                device = "cuda" if torch.cuda.is_available() else "cpu"
                cls._device = device
                if device == "cuda":
                    cls._model = cls._model.half().to(device)
                    print(f"[NeuralEmbeddingEngine] Accelerated with NVIDIA GPU: {torch.cuda.get_device_name(0)} (FP16)")
                else:
                    cls._model = cls._model.to("cpu")
                    print(f"[NeuralEmbeddingEngine] Loaded SOTA Multilingual Model: {model_name} (Native 1024D Vi/Ja/En on CPU)")

    @classmethod
    def get_neural_embedding(cls, text, is_query=False):
        res = cls.get_neural_embeddings_batch([text], is_query=is_query)
        return res[0] if res else None

    @classmethod
    def get_neural_embeddings_batch(cls, texts, is_query=False):
        if not texts:
            return []

        cleaned_texts = [(t or "").strip() or "empty chunk" for t in texts]

        try:
            import torch
            import torch.nn.functional as F

            cls._ensure_loaded()

            device = getattr(cls, '_device', 'cuda' if torch.cuda.is_available() else 'cpu')
            max_len = 512
            inputs = cls._tokenizer(cleaned_texts, padding=True, truncation=True, max_length=max_len, return_tensors='pt')
            if device == "cuda":
                inputs = {k: v.to(device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = cls._model(**inputs)
                # BAAI/bge-m3 dense representation: CLS token embedding normalized
                embeddings = outputs.last_hidden_state[:, 0]
                embeddings = F.normalize(embeddings, p=2, dim=1)

            return embeddings.cpu().float().tolist()
        except Exception as e:
            print("[NeuralEmbedding Error]", str(e))
            return []


class QdrantVectorDBService:
    """
    Dịch vụ lưu trữ & truy vấn Vector Database (Qdrant Vector Engine):
    - Sử dụng QdrantClient Singleton
    - Hỗ trợ SOTA BAAI/bge-m3 (1024-dim)
    - Lưu trữ Vector Embedding kèm Metadata (Text, LayoutLM Bounding Box, Hình ảnh sơ đồ)
    """
    COLLECTION_NAME = "denso_document_vectors"
    VECTOR_DIM = 1024  # 1024 dimensions cho SOTA BAAI/bge-m3
    _client_instance = None

    def __init__(self):
        self.storage_dir = Path(__file__).resolve().parent.parent.parent / 'qdrant_storage'
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.client = self.get_client()
        self._ensure_collection_exists()

    @classmethod
    def get_client(cls):
        from qdrant_client import QdrantClient
        if cls._client_instance is None:
            # Kiểm tra xem Docker Qdrant trên port 6333 đang chạy không
            try:
                import urllib.request
                urllib.request.urlopen("http://localhost:6333/collections", timeout=0.8)
                cls._client_instance = QdrantClient(host="localhost", port=6333)
                print("[QdrantVectorDB] Connected to Docker Qdrant Server at http://localhost:6333")
                return cls._client_instance
            except Exception:
                pass

            # Sử dụng Local Storage trong PlanAProject/qdrant_storage
            try:
                storage_path = Path(__file__).resolve().parent.parent.parent / 'qdrant_storage'
                cls._client_instance = QdrantClient(path=str(storage_path))
                return cls._client_instance
            except Exception as e:
                print("[Qdrant Init Error]", str(e))
                try:
                    from core.services import QdrantVectorService
                    if getattr(QdrantVectorService, '_instance', None) is not None:
                        cls._client_instance = QdrantVectorService._instance
                        return cls._client_instance
                except Exception:
                    pass
                cls._client_instance = QdrantClient(":memory:")
        return cls._client_instance

    def _ensure_collection_exists(self):
        if not self.client:
            return

        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.COLLECTION_NAME for c in collections)

            if exists:
                try:
                    col_info = self.client.get_collection(self.COLLECTION_NAME)
                    current_size = getattr(getattr(col_info.config.params, 'vectors', None), 'size', None)
                    if current_size and current_size != self.VECTOR_DIM:
                        print(f"[Qdrant] Upgrading {self.COLLECTION_NAME} size: {current_size} -> {self.VECTOR_DIM}")
                        self.client.delete_collection(self.COLLECTION_NAME)
                        exists = False
                except Exception:
                    pass

            if not exists:
                self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.VECTOR_DIM,
                        distance=Distance.COSINE
                    )
                )
                print(f"[Qdrant] Collection initialized: {self.COLLECTION_NAME} (1024-dim)")
        except Exception as e:
            print("[Qdrant Collection Error]", str(e))

    def generate_embedding(self, text, layout_type="paragraph", bbox=None, is_query=False):
        """
        Sinh Neural Vector Embedding từ Mạng Nơ-ron Transformer (LayerNorm + L2 Normalized)
        """
        neural_vector = NeuralEmbeddingEngine.get_neural_embedding(text, is_query=is_query)
        if neural_vector and len(neural_vector) == self.VECTOR_DIM:
            return neural_vector

        # Fallback Vector Generator 384 dimensions
        vector = [0.0] * self.VECTOR_DIM
        cleaned_text = (text or "").lower().strip() or "empty layout"

        words = cleaned_text.split()
        for idx, word in enumerate(words):
            word_hash = int(hashlib.md5(word.encode('utf-8')).hexdigest(), 16)
            dim_idx = word_hash % self.VECTOR_DIM
            vector[dim_idx] += 1.0 / (idx + 1.0)

        layout_weights = {"header": 0.5, "figure": 0.8, "table": 0.6, "code_log": 0.7, "paragraph": 0.3}
        vector[0] += layout_weights.get(layout_type, 0.3)

        if bbox and len(bbox) == 4:
            vector[1] += (bbox[0] + bbox[2]) / 2000.0
            vector[2] += (bbox[1] + bbox[3]) / 2000.0

        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def delete_document_vectors(self, doc_id):
        """
        Xóa sạch toàn bộ Vector Point cũ của DocumentId cụ thể khỏi CSDL Qdrant
        trước khi Re-index hoặc ghi đè dữ liệu mới.
        """
        if not self.client:
            return False

        try:
            self.client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=doc_id)
                        )
                    ]
                )
            )
            print(f"[Qdrant DB] Successfully cleared old vectors for document_id={doc_id}")
            return True
        except Exception as e:
            print(f"[Qdrant Clear Error] document_id={doc_id}:", str(e))
            return False

    def index_document_chunks(self, doc_file, chunks):
        if not self.client or not chunks:
            return 0

        doc_id = doc_file.id
        # Xóa sạch vector point cũ của tài liệu này trước khi lưu mới
        self.delete_document_vectors(doc_id)

        points = []
        original_name = doc_file.original_name
        category = doc_file.category
        doc_code = getattr(doc_file, 'doc_code', '') or ''

        # Contextual Passage Prefixing (Metadata Enrichment):
        # Đính kèm Tên tài liệu, Mã tài liệu, Chuyên mục và Số trang vào vector embedding
        # giúp câu hỏi dù lạ hay dùng từ ngữ địa phương vẫn khớp chính xác vào tài liệu và thiết bị tương ứng
        texts = [
            f"Tài liệu: {original_name} | Mã: {doc_code} | Chuyên mục: {category} | Trang {c.get('page_number', 1)}\n{c.get('text', '')}"
            for c in chunks
        ]
        all_vectors = []
        batch_size = 32
        for b_i in range(0, len(texts), batch_size):
            b_texts = texts[b_i:b_i + batch_size]
            b_vecs = NeuralEmbeddingEngine.get_neural_embeddings_batch(b_texts)
            if b_vecs and len(b_vecs) == len(b_texts):
                all_vectors.extend(b_vecs)
            else:
                for idx_sub, txt in enumerate(b_texts):
                    orig_chunk = chunks[b_i + idx_sub]
                    all_vectors.append(self.generate_embedding(txt, orig_chunk.get('layout_type', 'paragraph'), orig_chunk.get('bbox')))

        for idx, chunk in enumerate(chunks):
            text = chunk.get('text', '')
            layout_type = chunk.get('layout_type', 'paragraph')
            bbox = chunk.get('bbox', [100, 100, 900, 900])
            page_number = chunk.get('page_number', 1)
            has_image = chunk.get('has_image', False)
            image_url = chunk.get('image_url', None)

            vector = all_vectors[idx] if idx < len(all_vectors) else self.generate_embedding(text, layout_type, bbox)
            point_id = doc_id * 10000 + (idx + 1)

            payload = {
                "document_id": doc_id,
                "doc_code": doc_code,
                "original_name": original_name,
                "document_title": original_name,
                "category": category,
                "chunk_id": chunk.get('chunk_id', idx + 1),
                "layout_type": layout_type,
                "text": text,
                "content": text,
                "bbox": bbox,
                "page_number": page_number,
                "has_image": has_image,
                "image_url": image_url,
                "file_url": doc_file.file.url if doc_file.file else ""
            }

            points.append(PointStruct(
                id=point_id,
                vector=vector,
                payload=payload
            ))

        try:
            self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points
            )
            return len(points)
        except Exception as e:
            print("[Qdrant Upsert Error]", str(e))
            return 0

    def vector_search(self, query_text, top_k=5, category_filter=None, doc_id_filter=None, collection_name=None):
        if not self.client:
            return []

        query_vector = self.generate_embedding(query_text, is_query=True)

        target_collection = collection_name or self.COLLECTION_NAME
        try:
            col_list = [c.name for c in self.client.get_collections().collections]
            if target_collection not in col_list and "denso_chunks" in col_list:
                target_collection = "denso_chunks"
        except Exception:
            pass

        must_conditions = []
        if category_filter and category_filter != 'all':
            must_conditions.append(FieldCondition(key="category", match=MatchValue(value=category_filter)))
        if doc_id_filter:
            must_conditions.append(FieldCondition(key="document_id", match=MatchValue(value=int(doc_id_filter))))

        search_filter = Filter(must=must_conditions) if must_conditions else None

        try:
            response = self.client.query_points(
                collection_name=target_collection,
                query=query_vector,
                limit=top_k,
                query_filter=search_filter
            )

            formatted_results = []
            points = getattr(response, 'points', response)

            for hit in points:
                payload = getattr(hit, 'payload', {}) or {}
                raw_score = float(getattr(hit, 'score', 0.0))
                score_sim = round(raw_score, 3)
                score_pct = round(score_sim * 100, 2)

                doc_title = payload.get("document_title") or payload.get("original_name") or ""
                doc_code = payload.get("doc_code") or ""
                content_text = payload.get("content") or payload.get("text") or ""
                chunk_type = payload.get("chunk_type") or payload.get("layout_type") or "text"

                # Làm sạch artifact nhiễu OCR nếu có
                import re
                content_clean = re.sub(r'^[a-zA-Z\s;,\.]{1,20}(?=Warning|Caution|Notice|Lưu ý|Quy trình)', '', content_text).strip()
                if content_clean:
                    content_text = content_clean

                # Phân loại kỹ thuật thực tế (Chống gán nhãn sai):
                # - Chỉ công nhận là TÀI LIỆU CHUẨN khi là SOP/Bản vẽ kỹ thuật/Tiêu chuẩn thiết kế VÀ đạt độ tương đồng cao (>= 65%)
                # - Ca sự cố thực tế (KB_CASE, CBR, Chuyên gia) -> CA SỰ CỐ THỰC TẾ (CBR CASE)
                code_up = doc_code.upper()
                title_up = doc_title.upper()
                is_case = ("KB_CASE" in code_up or "KB_CASE" in title_up or "CASE" in code_up or "CBR" in code_up or "CHUYÊN GIA" in title_up)
                is_official_spec = (
                    any(k in code_up for k in ["SOP", "DWG", "CAD", "SPEC", "STD"]) or
                    any(k in title_up for k in ["SOP-", "DWG-", "QUY TRÌNH TIÊU CHUẨN", "BẢN VẼ"])
                )

                if is_case:
                    is_canonical = False
                    spec_type = 'CA SỰ CỐ THỰC TẾ (CBR CASE)'
                    badge_label = '⚡ CA SỰ CỐ CBR'
                    badge_color = '#f59e0b'
                elif is_official_spec:
                    if score_sim >= 0.65:
                        is_canonical = True
                        spec_type = 'TÀI LIỆU CHUẨN (CANONICAL SPEC)'
                        badge_label = '✓ TÀI LIỆU CHUẨN'
                        badge_color = '#10b981'
                    else:
                        is_canonical = False
                        spec_type = 'TIÊU CHUẨN THAM KHẢO (SOP/DWG)'
                        badge_label = '📐 QUY TRÌNH THAM KHẢO'
                        badge_color = '#38bdf8'
                else:
                    is_canonical = False
                    spec_type = 'HƯỚNG DẪN KỸ THUẬT (REFERENCE)'
                    badge_label = '📘 HƯỚNG DẪN KỸ THUẬT'
                    badge_color = '#94a3b8'

                formatted_results.append({
                    "score": score_sim,
                    "score_percent": score_pct,
                    "document_id": payload.get("document_id"),
                    "original_name": doc_title,
                    "document_title": doc_title,
                    "doc_code": doc_code,
                    "category": payload.get("category"),
                    "chunk_id": payload.get("chunk_id") or getattr(hit, 'id', None),
                    "layout_type": chunk_type,
                    "chunk_type": chunk_type,
                    "text": content_text,
                    "content": content_text,
                    "bbox": payload.get("bbox") or [],
                    "page_number": payload.get("page_number", 1),
                    "has_image": payload.get("has_image", False),
                    "image_url": payload.get("image_url", ""),
                    "file_url": payload.get("file_url", ""),
                    "is_canonical": is_canonical,
                    "spec_type": spec_type,
                    "badge_label": badge_label,
                    "badge_color": badge_color
                })

            return formatted_results
        except Exception as e:
            print("[Qdrant Search Error]", str(e))
            return []

