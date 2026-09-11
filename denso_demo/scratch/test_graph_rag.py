import os
import sys
import django

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.services import KnowledgeIntelligenceService, Neo4jGraphService

print("=== 1. KIỂM THỬ NEO4J GRAPH SERVICE MULTI-HOP TRAVERSAL ===")
graph_svc = Neo4jGraphService()
status_str = "CONNECTED" if graph_svc.is_connected() else "OFFLINE"
print(f"Neo4j Status: {status_str}")

query1 = "Trục M12 bị quá nhiệt trên 40 độ"
g_text, g_cits = graph_svc.format_graph_context(query1)
print(f"\n[Multi-Hop Graph Result for: '{query1}']")
print(g_text)
print(f"Graph Citations: {len(g_cits)}")

print("\n=== 2. KIỂM THỬ END-TO-END HYBRID RAG (VECTOR RAG + GRAPH RAG) ===")
service = KnowledgeIntelligenceService()
res = service.process_chat("Mức rung cho phép của trục chính máy M12 và quy trình bảo dưỡng vòng bi")
print(f"Has Gap: {res['has_gap']}")
print(f"Citations Total: {len(res['citations'])}")
print("Citations types:", [c.get('type') for c in res['citations']])
print(f"Answer Preview:\n{res['answer'][:350]}...")

print("\n=== HOÀN TẤT KIỂM THỬ GRAPH RAG! ===")
