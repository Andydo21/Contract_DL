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

    def check_health(self) -> bool:
        """
        Kiểm tra trạng thái ColPali Engine (Kaggle).
        Trả về True nếu ColPali đang hoạt động bình thường, False nếu offline.
        """
        if not self.colpali_base_url:
            return False
        headers = {"ngrok-skip-browser-warning": "true"}
        for ep, method in [("/health", "GET"), ("/docs", "GET"), ("/embed_query", "POST")]:
            try:
                if method == "POST":
                    r = requests.post(f"{self.colpali_base_url}{ep}", json={"query": "ping"}, headers=headers, timeout=4.0)
                else:
                    r = requests.get(f"{self.colpali_base_url}{ep}", headers=headers, timeout=4.0)
                if r.status_code == 200:
                    return True
            except Exception:
                continue
        return False

    def index_document_colpali(self, doc_file) -> Dict[str, Any]:
        """
        Nạp ảnh trang tài liệu lên ColPali Engine (Kaggle) -> Nhận về 1024 Multi-Vectors -> Lưu vào Qdrant
        Nếu ColPali offline (ngrok hết hạn/chưa bật): Ghi log thông báo và tiếp tục, không chặn luồng Surya.
        """
        if not self.check_health():
            print("[ColPali Notice] ColPali VLM Engine dang offline (ngrok het han/chua bat). Bo qua buoc Visual Multi-Vector, khong chan luong Surya.")
            return {
                "doc_id": getattr(doc_file, 'id', 0),
                "total_pages": 0,
                "indexed_pages": 0,
                "status": "skipped"
            }

        file_path = doc_file.file.path
        doc_id = doc_file.id
        category = doc_file.category

        pages_data = []
        if category == 'pdf':
            pages_data = self._render_pdf_pages(file_path, doc_id)
        elif category == 'image':
            pages_data = [{
                'page_number': 1,
                'image_url': doc_file.file.url if getattr(doc_file, 'file', None) else "",
                'image_path': file_path
            }]
        elif category in ['docx', 'doc']:
            pages_data = self._render_docx_pages(file_path, doc_id)
        elif category in ['xlsx', 'xls', 'csv']:
            pages_data = self._render_excel_pages(file_path, doc_id)
        else:
            pages_data = self._render_text_pages(file_path, doc_id)

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
                # Phân mảnh batch tối đa 5 trang / lần gửi để không vượt ngưỡng 32MB JSON payload của Qdrant
                BATCH_SIZE = 5
                for b_idx in range(0, len(points), BATCH_SIZE):
                    sub_batch = points[b_idx:b_idx + BATCH_SIZE]
                    self.client.upsert(
                        collection_name=self.COLLECTION_NAME,
                        points=sub_batch
                    )
            except Exception as e:
                print("[ColPali Upsert Error]", str(e))

        return {
            "doc_id": doc_id,
            "total_pages": len(pages_data),
            "indexed_pages": len(points)
        }

    @staticmethod
    def _setup_page_font(page):
        fontfile = "C:/Windows/Fonts/arial.ttf" if os.path.exists("C:/Windows/Fonts/arial.ttf") else None
        if fontfile:
            try:
                page.insert_font(fontname="arial_uni", fontfile=fontfile)
                return "arial_uni"
            except Exception:
                pass
        return "helv"

    def _render_pdf_pages(self, file_path: str, doc_id: int) -> List[Dict[str, Any]]:
        pages = []
        try:
            import fitz
            try:
                pdf_doc = fitz.open(file_path)
            except Exception:
                # Tuyệt đối không tạo file PDF giả lập hay ảnh mới nếu file không phải là PDF thực tế
                return []

            for page_num in range(len(pdf_doc)):
                page = pdf_doc[page_num]

                # 1. Tìm file PNG có sẵn trên toàn bộ hệ thống đĩa (PlanA & denso_demo) - LẤY LUÔN, TUYỆT ĐỐI KHÔNG TẠO MỚI!
                search_dirs = [
                    self.output_img_dir,
                    Path(str(settings.BASE_DIR).replace('PlanAProject', 'denso_demo')) / "media" / "extracted_images",
                    Path(str(settings.BASE_DIR).replace('PlanAProject', 'denso_demo')) / "media" / "visual_pages",
                    self.output_img_dir.parent / "visual_pages"
                ]
                existing_candidates = [
                    f"pdf_page_{doc_id}_p{page_num+1}.png",
                    f"colpali_pdf_{doc_id}_p{page_num+1}.png",
                    f"annotated_doc_{doc_id}_p{page_num+1}.png",
                    f"img_doc_{doc_id}.png",
                ]

                found_path = None
                for s_dir in search_dirs:
                    if not s_dir.exists():
                        continue
                    for cand in existing_candidates:
                        p = s_dir / cand
                        if p.exists() and p.stat().st_size > 0:
                            found_path = p
                            break
                    if found_path:
                        break

                if found_path:
                    img_url = f"{settings.MEDIA_URL}extracted_images/{found_path.name}"
                    pages.append({
                        'page_number': page_num + 1,
                        'image_url': img_url,
                        'image_path': str(found_path)
                    })
                # Nếu không có ảnh sẵn trên đĩa: Tuyệt đối không tạo ảnh mới (không gọi pix.save)

            pdf_doc.close()
        except Exception as e:
            print(f"[ColPali Render Error] {e}")

        return pages

    def _render_docx_pages(self, file_path: str, doc_id: int) -> List[Dict[str, Any]]:
        """Lấy file PNG trang DOCX đã có sẵn trên đĩa, tuyệt đối không tạo ảnh mới"""
        existing = sorted(self.output_img_dir.glob(f"docx_page_{doc_id}_p*.png"))
        pages = []
        for idx, p in enumerate(existing):
            if p.stat().st_size > 0:
                pages.append({
                    'page_number': idx + 1,
                    'image_url': f"{settings.MEDIA_URL}extracted_images/{p.name}",
                    'image_path': str(p)
                })
        return pages

    def _render_excel_pages(self, file_path: str, doc_id: int) -> List[Dict[str, Any]]:
        """Lấy file PNG trang Excel đã có sẵn trên đĩa, tuyệt đối không tạo ảnh mới"""
        existing = sorted(self.output_img_dir.glob(f"excel_page_{doc_id}_s*.png"))
        pages = []
        for idx, p in enumerate(existing):
            if p.stat().st_size > 0:
                pages.append({
                    'page_number': idx + 1,
                    'image_url': f"{settings.MEDIA_URL}extracted_images/{p.name}",
                    'image_path': str(p)
                })
        return pages

    def _render_text_pages(self, file_path: str, doc_id: int) -> List[Dict[str, Any]]:
        """Tài liệu Text/Markdown: Tuyệt đối không tạo ảnh mới, hiển thị trực tiếp dạng văn bản"""
        return []


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
                timeout=2.0
            )

            if res.status_code != 200:
                print(f"[ColPali Query Embed Notice] Server offline (HTTP {res.status_code})")
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
