import os
import io
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
from django.conf import settings
from qdrant_client.models import Distance, VectorParams, PointStruct, MultiVectorConfig, MultiVectorComparator
from documents.services.vector_db_service import QdrantVectorDBService


class ColPaliVisualIndexer:
    """
    ColPali Engine Remote Client (Kaggle GPU T4 x 2):
    - 100% sử dụng mô hình ColPali gốc (vidore/colpali-v1.2 trên nền PaliGemma-3B)
    - Nhận diện trực tiếp từ ma trận điểm ảnh (Pixels) nguyên bản của tài liệu PDF/Bản vẽ CAD (No-OCR)
    - Sinh ra ma trận 1024 Visual Multi-Vectors (128 chiều) cho mỗi trang tài liệu
    - Lưu trữ và tính toán Late Interaction MaxSim Score trực tiếp trên Qdrant Multi-Vector Engine
    - Tuyệt đối KHÔNG sử dụng all-MiniLM hay CLIP!
    """
    COLLECTION_NAME = "denso_colpali_visual_patches"
    VECTOR_DIM = 128

    def __init__(self):
        self.output_img_dir = Path(settings.MEDIA_ROOT) / 'extracted_images'
        self.output_img_dir.mkdir(parents=True, exist_ok=True)
        self.client = QdrantVectorDBService.get_client()

        # URL ColPali Server trên Kaggle (ngrok)
        self.colpali_base_url = (
            os.environ.get("COLPALI_BASE_URL")
            or getattr(settings, "COLPALI_BASE_URL", "")
            or os.environ.get("VLLM_BASE_URL", "").replace("/v1", "/colpali")
        ).rstrip("/")

        self._ensure_collection_exists()

    def _ensure_collection_exists(self):
        if not self.client:
            return

        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.COLLECTION_NAME for c in collections)

            if exists:
                coll_info = self.client.get_collection(self.COLLECTION_NAME)
                vec_size = coll_info.config.params.vectors.size
                is_multivec = bool(getattr(coll_info.config.params.vectors, 'multivector_config', None))
                # Nếu collection cũ chưa phải là Multi-Vector 128 chiều của ColPali -> Tái tạo
                if vec_size != self.VECTOR_DIM or not is_multivec:
                    print(f"[ColPali] Recreating Collection to ColPali Multi-Vector 128-dim (MaxSim)...")
                    self.client.delete_collection(self.COLLECTION_NAME)
                    exists = False

            if not exists:
                self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.VECTOR_DIM,
                        distance=Distance.COSINE,
                        multivector_config=MultiVectorConfig(
                            comparator=MultiVectorComparator.MAX_SIM
                        )
                    )
                )
                print(f"[ColPali] Initialized Qdrant Collection ColPali Multi-Vector 128-dim (MaxSim): {self.COLLECTION_NAME}")
        except Exception as e:
            print("[ColPali Collection Error]", str(e))

    def index_document_colpali(self, doc_file) -> Dict[str, Any]:
        """
        Nạp ảnh trang tài liệu lên ColPali Engine (Kaggle) -> Nhận về 1024 Multi-Vectors -> Lưu vào Qdrant
        """
        if not self.colpali_base_url:
            raise ConnectionError("Chưa cấu hình COLPALI_BASE_URL trong file .env! Hãy khởi động ColPali trên Kaggle.")

        file_path = doc_file.file.path
        doc_id = doc_file.id
        category = doc_file.category

        pages_data = []
        if category == 'pdf':
            pages_data = self._render_pdf_pages(file_path, doc_id)
        elif category == 'image':
            pages_data = [{
                'page_number': 1,
                'image_url': doc_file.file.url if doc_file.file else "",
                'image_path': file_path
            }]
        else:
            pages_data = [{
                'page_number': 1,
                'image_url': doc_file.file.url if doc_file.file else "",
                'image_path': file_path
            }]

        points = []
        headers = {"ngrok-skip-browser-warning": "true"}

        for page in pages_data:
            page_num = page['page_number']
            img_path = Path(page.get('image_path', ''))

            if not img_path.exists():
                continue

            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            # Gửi ảnh nguyên bản sang ColPali VLM Engine trên Kaggle để sinh Multi-Vectors
            try:
                res = requests.post(
                    f"{self.colpali_base_url}/embed_page",
                    json={"image_base64": img_b64},
                    headers=headers,
                    timeout=90
                )
                if res.status_code == 200:
                    data = res.json()
                    multi_vectors = data.get("embeddings", []) # 1024 vectors x 128 dim
                    point_id = doc_id * 10000 + page_num

                    payload = {
                        "document_id": doc_id,
                        "original_name": doc_file.original_name,
                        "category": category,
                        "page_number": page_num,
                        "layout_type": "colpali_full_page_vlm",
                        "image_url": page.get('image_url', ''),
                        "full_page_url": page.get('image_url', ''),
                        "text": f"[ColPali VLM] Trang {page_num} của tài liệu '{doc_file.original_name}'"
                    }

                    points.append(PointStruct(
                        id=point_id,
                        vector=multi_vectors,
                        payload=payload
                    ))
                else:
                    print(f"[ColPali Index Error] Page {page_num} HTTP {res.status_code}: {res.text}")
            except Exception as req_err:
                print(f"[ColPali Index Request Error] Page {page_num}: {req_err}")

        if points and self.client:
            try:
                self.client.upsert(
                    collection_name=self.COLLECTION_NAME,
                    points=points
                )
            except Exception as e:
                print("[ColPali Upsert Error]", str(e))

        return {
            "doc_id": doc_id,
            "total_pages": len(pages_data),
            "indexed_pages": len(points)
        }

    def _render_pdf_pages(self, file_path: str, doc_id: int) -> List[Dict[str, Any]]:
        pages = []
        try:
            import fitz
            pdf_doc = fitz.open(file_path)

            for page_num in range(len(pdf_doc)):
                page = pdf_doc[page_num]

                # Ưu tiên tái sử dụng ảnh trang đã render từ Shared Ingestion Router / Layout Extractor
                shared_filename = f"pdf_page_{doc_id}_p{page_num+1}.png"
                shared_path = self.output_img_dir / shared_filename

                if shared_path.exists():
                    img_filename = shared_filename
                    img_save_path = shared_path
                else:
                    img_filename = f"colpali_pdf_{doc_id}_p{page_num+1}.png"
                    img_save_path = self.output_img_dir / img_filename
                    if not img_save_path.exists():
                        pix = page.get_pixmap(dpi=150)
                        pix.save(str(img_save_path))

                img_url = f"{settings.MEDIA_URL}extracted_images/{img_filename}"
                pages.append({
                    'page_number': page_num + 1,
                    'image_url': img_url,
                    'image_path': str(img_save_path)
                })

            pdf_doc.close()
        except Exception as e:
            print(f"[ColPali Render Error] {e}")

        return pages

    def colpali_maxsim_search(self, query_text: str, top_k: int = 5, doc_id_filter=None) -> List[Dict[str, Any]]:
        """
        Tìm kiếm Late Interaction MaxSim trực tiếp với ColPali Engine (Kaggle):
        - Chiếu câu hỏi văn bản qua ColPali thành Multi-Vector (seq_len x 128)
        - Qdrant tính toán hàm MaxSim: sum_i(max_j(q_i . d_j))
        - Trả về danh sách trang bản vẽ/sơ đồ có điểm tương đồng thị giác cao nhất
        """
        if not self.client:
            return []

        if not self.colpali_base_url:
            print("[ColPali] Chưa cấu hình COLPALI_BASE_URL trong .env")
            return []

        headers = {"ngrok-skip-browser-warning": "true"}

        try:
            # 1. Gửi câu hỏi lên ColPali Kaggle để lấy Multi-Vector (seq_len x 128)
            res = requests.post(
                f"{self.colpali_base_url}/embed_query",
                json={"query": query_text},
                headers=headers,
                timeout=30
            )

            if res.status_code != 200:
                print(f"[ColPali Query Embed Error] HTTP {res.status_code}: {res.text}")
                return []

            query_multi_vector = res.json().get("embeddings", [])
            if not query_multi_vector:
                return []

            # 2. Truy vấn trực tiếp trên Qdrant với thuật toán MaxSim
            search_filter = None
            if doc_id_filter:
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                search_filter = Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=int(doc_id_filter))
                        )
                    ]
                )

            response = self.client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_multi_vector,
                limit=top_k,
                query_filter=search_filter
            )

            raw_points = getattr(response, 'points', response)
            results = []

            for hit in raw_points:
                payload = getattr(hit, 'payload', {}) or {}
                score = getattr(hit, 'score', 0.0)

                doc_id = payload.get('document_id')
                page_num = payload.get('page_number', 1)
                img_url = payload.get('image_url', '')

                # Chuẩn hóa điểm MaxSim sang thang phần trăm 0 - 100%
                match_pct = round(float(score) * 10.0, 2) if score < 10 else round(float(score), 2)
                match_pct = min(100.0, max(0.0, match_pct))

                results.append({
                    "document_id": doc_id,
                    "original_name": payload.get("original_name"),
                    "category": payload.get("category"),
                    "page_number": page_num,
                    "maxsim_score": match_pct,
                    "score": match_pct,
                    "bbox": [0, 0, 1000, 1000],
                    "image_url": img_url,
                    "full_page_url": img_url,
                    "text": payload.get("text", ""),
                    "layout_type": "colpali_vlm_maxsim"
                })

            results.sort(key=lambda x: x['score'], reverse=True)
            return results

        except Exception as e:
            print("[ColPali MaxSim Search Error]", str(e))
            return []
