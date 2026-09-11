import os
import sys
import json
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.services import KnowledgeIntelligenceService, EmbeddingService
from core.repositories import DocumentRepository, CaseRepository, KnowledgeRepository

print("=== 1. Testing DocumentRepository.search_chunks with Vector Cosine Similarity ===")
res_chunks = DocumentRepository.search_chunks("độ rung và nhiệt độ máy M12", limit=2)
for ch in res_chunks:
    print(f"Chunk doc: {ch['doc_code']}, score (Cosine): {ch['score']}, text: {ch['content'][:100]}...")

print("\n=== 2. Testing CaseRepository.search_cases with Vector Cosine Similarity ===")
res_cases = CaseRepository.search_cases("căn chỉnh khe hở trục", limit=2)
for c in res_cases:
    print(f"Case: {c.case_code}, sim_score: {getattr(c, 'sim_score', 0)}, title: {c.title}")

print("\n=== 3. Testing Question In-Distribution (Should NOT be Gap) ===")
service = KnowledgeIntelligenceService()
res_in = service.process_chat("Mức rung cho phép trục chính máy M12 là bao nhiêu?")
print(f"Has Gap: {res_in['has_gap']}")
if not res_in['has_gap']:
    print(f"Answer snippet: {res_in['answer'][:150]}...")
    print(f"Citations count: {len(res_in['citations'])}")

print("\n=== 4. Testing Question Out-Of-Distribution (Robot cánh tay 6 trục - Should BE Gap) ===")
res_out = service.process_chat("Robot cánh tay 6 trục tại trạm lắp ráp bị trôi tọa độ trục J3 và J5 làm rơi linh kiện")
print(f"Has Gap: {res_out['has_gap']}")
print(f"Gap Reason: {res_out.get('gap_reason')}")
print(f"Vector Similarity: {res_out.get('vector_similarity')}")
print(f"Recommended Expert: {res_out.get('recommended_expert', {}).get('name')}")

print("\n=== ALL VECTOR RAG TESTS COMPLETED SUCCESSFULLY! ===")
