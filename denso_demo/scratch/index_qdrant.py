import os
import sys
import json
import django

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Chunk, Case, Knowledge
from core.services import QdrantVectorService, EmbeddingService

print("=== 1. KHỞI TẠO QDRANT VECTOR SERVICE ===")
qdrant_svc = QdrantVectorService()
print(f"Collections in Qdrant: {[c.name for c in qdrant_svc.client.get_collections().collections]}")

print("\n=== 2. INDEXING CHUNKS VÀO QDRANT ('denso_chunks') ===")
chunks = Chunk.objects.select_related('page__document').all()
indexed_chunks = 0
for ch in chunks:
    vec = json.loads(ch.embedding_json) if ch.embedding_json else EmbeddingService.embed_text(f"{ch.chunk_type} {ch.content}")
    if vec:
        payload = {
            'document_title': ch.page.document.title,
            'doc_code': ch.page.document.doc_code,
            'page_number': ch.page.page_number,
            'chunk_type': ch.chunk_type,
            'content': ch.content,
            'bbox': ch.get_bbox(),
            'image_url': ch.page.image_path.url if ch.page.image_path else ''
        }
        qdrant_svc.upsert_chunk(ch.id, vec, payload)
        indexed_chunks += 1
print(f"-> Indexed {indexed_chunks} Chunks into Qdrant.")

print("\n=== 3. INDEXING CASES VÀO QDRANT ('denso_cases') ===")
cases = Case.objects.select_related('expert').all()
indexed_cases = 0
for cs in cases:
    vec = json.loads(cs.embedding_json) if cs.embedding_json else EmbeddingService.embed_text(f"{cs.title} {cs.machine} {cs.symptom} {cs.root_cause} {cs.solution}")
    if vec:
        payload = {
            'case_code': cs.case_code,
            'title': cs.title,
            'machine': cs.machine,
            'part_code': cs.part_code,
            'symptom': cs.symptom,
            'root_cause': cs.root_cause,
            'solution': cs.solution,
            'expert_name': cs.expert.name if cs.expert else 'DENSO Expert'
        }
        qdrant_svc.upsert_case(cs.id, vec, payload)
        indexed_cases += 1
print(f"-> Indexed {indexed_cases} Cases into Qdrant.")

print("\n=== 4. INDEXING KNOWLEDGE RULES VÀO QDRANT ('denso_knowledge') ===")
rules = Knowledge.objects.select_related('approved_by').all()
indexed_rules = 0
for r in rules:
    vec = json.loads(r.embedding_json) if r.embedding_json else EmbeddingService.embed_text(f"{r.title} {r.content}")
    if vec:
        payload = {
            'knowledge_code': r.knowledge_code,
            'title': r.title,
            'content': r.content,
            'status': r.status,
            'approved_by': r.approved_by.name if r.approved_by else 'DENSO Line Master'
        }
        qdrant_svc.upsert_knowledge(r.id, vec, payload)
        indexed_rules += 1
print(f"-> Indexed {indexed_rules} Knowledge Rules into Qdrant.")

print("\n=== KIỂM TRA POINT COUNTS TRONG QDRANT ===")
for col in [qdrant_svc.COLLECTION_CHUNKS, qdrant_svc.COLLECTION_CASES, qdrant_svc.COLLECTION_KNOWLEDGE]:
    info = qdrant_svc.client.get_collection(col)
    print(f"Collection '{col}': {info.points_count} points, status: {info.status}")

print("\n=== HOÀN TẤT ĐỒNG BỘ QDRANT VECTOR DB! ===")
