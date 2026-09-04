import os
import math
import hashlib
from pathlib import Path
from django.conf import settings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

class NeuralEmbeddingEngine:
    """
    Bộ khởi tạo Neural Embedding Transformer Model:
    Sử dụng Mạng nơ-ron Transformer với LayerNorm + L2 Normalization
    """
    _tokenizer = None
    _model = None

    @classmethod
    def get_neural_embedding(cls, text):
        cleaned_text = (text or "").strip()
        if not cleaned_text:
            cleaned_text = "empty chunk"

        try:
            import torch
            import torch.nn.functional as F
            from transformers import AutoTokenizer, AutoModel

            if cls._tokenizer is None or cls._model is None:
                os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
                model_name = "sentence-transformers/all-MiniLM-L6-v2"
                cls._tokenizer = AutoTokenizer.from_pretrained(model_name)
                cls._model = AutoModel.from_pretrained(model_name)
                cls._model.eval()

            inputs = cls._tokenizer(cleaned_text, padding=True, truncation=True, max_length=256, return_tensors='pt')
            with torch.no_grad():
                outputs = cls._model(**inputs)
                # Mean Pooling qua các hidden states (đã trải qua LayerNorm bên trong Transformer)
                embeddings = outputs.last_hidden_state.mean(dim=1)
                # L2 Normalization đưa vector về độ dài = 1.0 cho Cosine Similarity
                embeddings = F.normalize(embeddings, p=2, dim=1)

            return embeddings[0].tolist()
        except Exception as e:
            # Fallback sang Hashing Vectorizer khi offline
            return None


class QdrantVectorDBService:
    """
    Dịch vụ lưu trữ & truy vấn Vector Database (Qdrant Vector Engine):
    - Sử dụng QdrantClient Singleton
    - Hỗ trợ cả Neural Transformer Embeddings (LayerNorm + L2) và Fallback Embedding
    - Lưu trữ Vector Embedding kèm Metadata (Text, LayoutLM Bounding Box, Hình ảnh sơ đồ)
    """
    COLLECTION_NAME = "denso_document_vectors"
    VECTOR_DIM = 384  # 384 dimensions cho Transformer all-MiniLM-L6-v2 (hoặc 128)
    _client_instance = None

    def __init__(self):
        self.storage_dir = Path(settings.BASE_DIR) / 'qdrant_storage'
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.client = self.get_client()
        self._ensure_collection_exists()

    @classmethod
    def get_client(cls):
        if cls._client_instance is None:
            try:
                qdrant_host = os.getenv('QDRANT_HOST', None)
                if qdrant_host:
                    cls._client_instance = QdrantClient(host=qdrant_host, port=int(os.getenv('QDRANT_PORT', 6333)))
                else:
                    storage_path = Path(settings.BASE_DIR) / 'qdrant_storage'
                    cls._client_instance = QdrantClient(path=str(storage_path))
            except Exception as e:
                print("[Qdrant Init Error]", str(e))
                cls._client_instance = QdrantClient(":memory:")
        return cls._client_instance

    def _ensure_collection_exists(self):
        if not self.client:
            return

        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.COLLECTION_NAME for c in collections)

            if not exists:
                self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.VECTOR_DIM,
                        distance=Distance.COSINE
                    )
                )
                print(f"[Qdrant] Collection initialized: {self.COLLECTION_NAME}")
        except Exception as e:
            print("[Qdrant Collection Error]", str(e))

    def generate_embedding(self, text, layout_type="paragraph", bbox=None):
        """
        Sinh Neural Vector Embedding từ Mạng Nơ-ron Transformer (LayerNorm + L2 Normalized)
        """
        neural_vector = NeuralEmbeddingEngine.get_neural_embedding(text)
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

        for idx, chunk in enumerate(chunks):
            text = chunk.get('text', '')
            layout_type = chunk.get('layout_type', 'paragraph')
            bbox = chunk.get('bbox', [100, 100, 900, 900])
            page_number = chunk.get('page_number', 1)
            has_image = chunk.get('has_image', False)
            image_url = chunk.get('image_url', None)

            vector = self.generate_embedding(text, layout_type, bbox)
            point_id = doc_id * 10000 + (idx + 1)

            payload = {
                "document_id": doc_id,
                "original_name": original_name,
                "category": category,
                "chunk_id": chunk.get('chunk_id', idx + 1),
                "layout_type": layout_type,
                "text": text,
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

    def vector_search(self, query_text, top_k=5, category_filter=None, doc_id_filter=None):
        if not self.client:
            return []

        query_vector = self.generate_embedding(query_text)

        must_conditions = []
        if category_filter and category_filter != 'all':
            must_conditions.append(FieldCondition(key="category", match=MatchValue(value=category_filter)))
        if doc_id_filter:
            must_conditions.append(FieldCondition(key="document_id", match=MatchValue(value=int(doc_id_filter))))

        search_filter = Filter(must=must_conditions) if must_conditions else None

        try:
            response = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_vector,
                limit=top_k,
                query_filter=search_filter
            )

            formatted_results = []
            points = getattr(response, 'points', response)

            for hit in points:
                payload = getattr(hit, 'payload', {}) or {}
                score = getattr(hit, 'score', 0.0)

                formatted_results.append({
                    "score": round(score * 100, 2),
                    "document_id": payload.get("document_id"),
                    "original_name": payload.get("original_name"),
                    "category": payload.get("category"),
                    "chunk_id": payload.get("chunk_id"),
                    "layout_type": payload.get("layout_type"),
                    "text": payload.get("text"),
                    "bbox": payload.get("bbox"),
                    "page_number": payload.get("page_number"),
                    "has_image": payload.get("has_image"),
                    "image_url": payload.get("image_url"),
                    "file_url": payload.get("file_url")
                })

            return formatted_results
        except Exception as e:
            print("[Qdrant Search Error]", str(e))
            return []
