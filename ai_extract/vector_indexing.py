"""Parallel indexing into the two Qdrant collections used by PlanA."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from uuid import NAMESPACE_URL, uuid5
import base64
import os

import requests
from django.conf import settings


DENSE_COLLECTION = "denso_document_vectors"
COLPALI_COLLECTION = "denso_colpali_visual_patches"
DENSE_DIM = 1024
COLPALI_DIM = 128
NGROK_HEADERS = {"ngrok-skip-browser-warning": "true"}


@dataclass
class IndexResult:
    status: str
    indexed_count: int = 0
    error: str = ""


class _BgeM3Embedding:
    _tokenizer = None
    _model = None
    _device = "cpu"
    _load_attempted = False
    _lock = Lock()

    @classmethod
    def embed_batch(cls, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        cls._ensure_loaded()
        if cls._model is None or cls._tokenizer is None:
            raise RuntimeError("BAAI/bge-m3 is unavailable; dense indexing was not performed")
        import torch
        import torch.nn.functional as functional

        inputs = cls._tokenizer(
            [(text or "").strip() or "empty layout" for text in texts],
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        if cls._device == "cuda":
            inputs = {key: value.to(cls._device) for key, value in inputs.items()}
        with torch.no_grad():
            outputs = cls._model(**inputs)
            embeddings = functional.normalize(outputs.last_hidden_state[:, 0], p=2, dim=1)
        return embeddings.cpu().float().tolist()

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._load_attempted:
            return
        with cls._lock:
            if cls._load_attempted:
                return
            cls._load_attempted = True
            try:
                import torch
                from transformers import AutoModel, AutoTokenizer

                model_name = os.environ.get("DENSE_EMBEDDING_MODEL", "BAAI/bge-m3")
                try:
                    cls._tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
                    cls._model = AutoModel.from_pretrained(model_name, local_files_only=True)
                except Exception:
                    token = os.environ.get("HF_TOKEN") or None
                    cls._tokenizer = AutoTokenizer.from_pretrained(model_name, token=token)
                    cls._model = AutoModel.from_pretrained(model_name, token=token)
                cls._device = "cuda" if torch.cuda.is_available() else "cpu"
                cls._model.eval().to(cls._device)
                if cls._device == "cuda":
                    cls._model.half()
            except Exception:
                cls._tokenizer = None
                cls._model = None

class PlanAQdrantClient:
    _client = None
    _lock = Lock()

    @classmethod
    def get(cls):
        if cls._client is not None:
            return cls._client
        with cls._lock:
            if cls._client is not None:
                return cls._client
            from qdrant_client import QdrantClient

            qdrant_url = os.environ.get("QDRANT_URL", "").rstrip("/")
            if qdrant_url:
                cls._client = QdrantClient(
                    url=qdrant_url,
                    api_key=os.environ.get("QDRANT_API_KEY") or None,
                )
            else:
                storage_path = Path(settings.BASE_DIR) / "PlanAProject" / "qdrant_storage"
                storage_path.mkdir(parents=True, exist_ok=True)
                cls._client = QdrantClient(path=str(storage_path))
            return cls._client


class PlanACollectionIndexer:
    def __init__(self):
        self.client = PlanAQdrantClient.get()

    def index_dense(self, run) -> IndexResult:
        try:
            from qdrant_client.models import Distance, PointStruct, VectorParams

            self._ensure_collection(
                DENSE_COLLECTION,
                VectorParams(size=DENSE_DIM, distance=Distance.COSINE),
                expected_size=DENSE_DIM,
                require_multivector=False,
            )
            self._delete_version_points(DENSE_COLLECTION, run.version_id)
            blocks = list(run.pages.prefetch_related("blocks").order_by("page_number"))
            block_rows = [block for page in blocks for block in page.blocks.all()]
            texts = [self._dense_text(run, block) for block in block_rows]
            vectors = _BgeM3Embedding.embed_batch(texts)
            points = []
            for block, text, vector in zip(block_rows, texts, vectors):
                points.append(
                    PointStruct(
                        id=str(uuid5(NAMESPACE_URL, f"contract-dl:dense:{run.id}:{block.id}")),
                        vector=vector,
                        payload=self._payload(run, block.page, block, text),
                    )
                )
            if points:
                self.client.upsert(collection_name=DENSE_COLLECTION, points=points, wait=True)
            return IndexResult("COMPLETED", len(points))
        except Exception as exc:
            return IndexResult("FAILED", error=str(exc))

    def index_colpali(self, run) -> IndexResult:
        base_url = self._colpali_url()
        if not base_url:
            return IndexResult("SKIPPED", error="COLPALI_BASE_URL is not configured")
        try:
            from qdrant_client.models import (
                Distance,
                MultiVectorComparator,
                MultiVectorConfig,
                PointStruct,
                VectorParams,
            )

            self._ensure_collection(
                COLPALI_COLLECTION,
                VectorParams(
                    size=COLPALI_DIM,
                    distance=Distance.COSINE,
                    multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                ),
                expected_size=COLPALI_DIM,
                require_multivector=True,
            )
            self._delete_version_points(COLPALI_COLLECTION, run.version_id)
            pending_points = []
            indexed_count = 0
            errors = []
            for page in run.pages.order_by("page_number"):
                if not page.image_path:
                    continue
                image_path = Path(settings.MEDIA_ROOT) / page.image_path
                if not image_path.exists():
                    errors.append(f"page {page.page_number}: image is missing")
                    continue
                try:
                    image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
                    response = requests.post(
                        f"{base_url}/embed_page",
                        json={"image_base64": image_base64},
                        headers=NGROK_HEADERS,
                        timeout=180,
                    )
                    response.raise_for_status()
                    embeddings = response.json().get("embeddings", [])
                    if not embeddings or any(len(vector) != COLPALI_DIM for vector in embeddings):
                        raise ValueError("invalid 128-dimensional multi-vector response")
                    pending_points.append(
                        PointStruct(
                            id=str(uuid5(NAMESPACE_URL, f"contract-dl:colpali:{run.id}:{page.id}")),
                            vector=embeddings,
                            payload=self._payload(run, page, None, f"Visual page {page.page_number}"),
                        )
                    )
                    if len(pending_points) >= 5:
                        self.client.upsert(
                            collection_name=COLPALI_COLLECTION,
                            points=pending_points,
                            wait=True,
                        )
                        indexed_count += len(pending_points)
                        pending_points = []
                except Exception as exc:
                    errors.append(f"page {page.page_number}: {exc}")
            if pending_points:
                self.client.upsert(
                    collection_name=COLPALI_COLLECTION, points=pending_points, wait=True
                )
                indexed_count += len(pending_points)
            if indexed_count and errors:
                return IndexResult("PARTIAL", indexed_count, "; ".join(errors))
            if errors:
                return IndexResult("FAILED", error="; ".join(errors))
            if not indexed_count:
                return IndexResult("SKIPPED", error="No rendered pages are available for ColPali")
            return IndexResult("COMPLETED", indexed_count)
        except Exception as exc:
            return IndexResult("FAILED", error=str(exc))

    def _ensure_collection(self, name, vector_config, expected_size: int, require_multivector: bool) -> None:
        existing = {collection.name for collection in self.client.get_collections().collections}
        if name not in existing:
            self.client.create_collection(collection_name=name, vectors_config=vector_config)
            return
        info = self.client.get_collection(name)
        vectors = info.config.params.vectors
        size = getattr(vectors, "size", None)
        multivector = getattr(vectors, "multivector_config", None)
        if size != expected_size or bool(multivector) != require_multivector:
            raise ValueError(
                f"Qdrant collection {name} has incompatible schema "
                f"(size={size}, multivector={bool(multivector)})"
            )

    def _delete_version_points(self, collection_name: str, version_id: int) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        self.client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(key="source_app", match=MatchValue(value="contract_dl")),
                    FieldCondition(key="version_id", match=MatchValue(value=version_id)),
                ]
            ),
            wait=True,
        )

    @staticmethod
    def _dense_text(run, block) -> str:
        contract = run.version.contract
        return (
            f"Hợp đồng: {contract.title} | Mã: {contract.contract_code} | "
            f"Trang {block.page.page_number} | Loại: {block.layout_type}\n{block.text}"
        )

    @staticmethod
    def _payload(run, page, block, text: str) -> dict:
        contract = run.version.contract
        return {
            "source_app": "contract_dl",
            "contract_dl_run_id": run.id,
            "document_id": f"contract-version-{run.version_id}",
            "contract_id": contract.id,
            "version_id": run.version_id,
            "document_title": contract.title,
            "original_name": contract.title,
            "doc_code": contract.contract_code,
            "category": "contract",
            "page_number": page.page_number,
            "chunk_id": block.id if block else page.id,
            "layout_type": block.layout_type if block else "colpali_full_page_vlm",
            "text": text,
            "content": text,
            "bbox": block.bbox if block else [0, 0, 1000, 1000],
            "has_image": bool(page.image_path),
            "image_url": f"/{settings.MEDIA_URL.strip('/')}/{page.image_path}" if page.image_path else "",
        }

    @staticmethod
    def _colpali_url() -> str:
        configured = os.environ.get("COLPALI_BASE_URL") or getattr(settings, "COLPALI_BASE_URL", "")
        if configured:
            return configured.rstrip("/")
        vllm_url = os.environ.get("VLLM_BASE_URL") or getattr(settings, "VLLM_BASE_URL", "")
        return vllm_url.rstrip("/").removesuffix("/v1") + "/colpali" if vllm_url else ""
