import json
import time
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from documents.services.colpali_service import ColPaliVisualIndexer
from documents.services.vector_db_service import QdrantVectorDBService
from documents.services.reranker_service import BGERerankerService

class Command(BaseCommand):
    help = 'Run A3 Benchmark evaluation suite for 25 test questions'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== RUNNING 100% REAL A3 MULTIMODAL RAG BENCHMARK (25 QUESTIONS) ==="))

        test_questions = [
            # Group 1: PDF Schematics & Images (ColPali Visual Engine)
            {"id": 1, "query": "Emergency Stop schematic diagram", "category": "pdf_scan", "expected_doc": "Robot_DENSO_Manual.pdf"},
            {"id": 2, "query": "ECU Controller wiring diagram", "category": "pdf_scan", "expected_doc": "SOP_ECU_Wiring_Diagram.docx"},
            {"id": 3, "query": "Temperature sensor location RC8", "category": "image", "expected_doc": "Sensor_Schematic_Diagram.png"},
            {"id": 4, "query": "Mainboard layout components", "category": "pdf_scan", "expected_doc": "Robot_DENSO_Manual.pdf"},
            {"id": 5, "query": "RS485 connector DENSO Controller", "category": "image", "expected_doc": "Sensor_Schematic_Diagram.png"},
            
            # Group 2: Tables (Surya-Table Parser)
            {"id": 6, "query": "Supply Voltage 24V DC specification", "category": "table_excel", "expected_doc": "Biet_du_lieu_thong_so_Controller.xlsx"},
            {"id": 7, "query": "Rated Current 5.5A specification", "category": "table_excel", "expected_doc": "Biet_du_lieu_thong_so_Controller.xlsx"},
            {"id": 8, "query": "Operating Temp -10C to +60C", "category": "table_excel", "expected_doc": "Biet_du_lieu_thong_so_Controller.xlsx"},
            {"id": 9, "query": "Motor Speed 3000 RPM", "category": "table_excel", "expected_doc": "Biet_du_lieu_thong_so_Controller.xlsx"},
            {"id": 10, "query": "Voltage Tolerance +/- 5%", "category": "table_excel", "expected_doc": "Biet_du_lieu_thong_so_Controller.xlsx"},

            # Group 3: Logs & Error Codes
            {"id": 11, "query": "Error code E-404 Motor Overheat", "category": "log", "expected_doc": "System_Error_Logs_2026.log"},
            {"id": 12, "query": "RS485 communication timeout error", "category": "log", "expected_doc": "System_Error_Logs_2026.log"},
            {"id": 13, "query": "24V Line Drop voltage drop cause", "category": "log", "expected_doc": "System_Error_Logs_2026.log"},
            {"id": 14, "query": "Payload Exceeded overload warning", "category": "log", "expected_doc": "System_Error_Logs_2026.log"},
            {"id": 15, "query": "Reset Emergency state recovery", "category": "log", "expected_doc": "System_Error_Logs_2026.log"},

            # Group 4: Multilingual (Japanese - Vietnamese - English)
            {"id": 16, "query": "Robot Controller Specs", "category": "multilingual", "expected_doc": "Biet_du_lieu_thong_so_Controller.xlsx"},
            {"id": 17, "query": "Emergency Stop Schematic", "category": "multilingual", "expected_doc": "Robot_DENSO_Manual.pdf"},
            {"id": 18, "query": "Error log analysis 2026", "category": "multilingual", "expected_doc": "System_Error_Logs_2026.log"},
            {"id": 19, "query": "ECU Wiring Diagram", "category": "multilingual", "expected_doc": "SOP_ECU_Wiring_Diagram.docx"},
            {"id": 20, "query": "Sensor position and thermal limits", "category": "multilingual", "expected_doc": "Sensor_Schematic_Diagram.png"},

            # Group 5: Inspect-to-repair SOP
            {"id": 21, "query": "ECU wiring inspection procedure", "category": "sop", "expected_doc": "SOP_ECU_Wiring_Diagram.docx"},
            {"id": 22, "query": "Motor Overheat E-404 repair procedure", "category": "sop", "expected_doc": "System_Error_Logs_2026.log"},
            {"id": 23, "query": "Servo motor voltage level check", "category": "table_excel", "expected_doc": "Biet_du_lieu_thong_so_Controller.xlsx"},
            {"id": 24, "query": "Speed control knob location on robot", "category": "image", "expected_doc": "Sensor_Schematic_Diagram.png"},
            {"id": 25, "query": "DENSO Robot periodic maintenance manual", "category": "pdf_scan", "expected_doc": "Robot_DENSO_Manual.pdf"}
        ]

        colpali = ColPaliVisualIndexer()
        vec_service = QdrantVectorDBService()
        reranker = BGERerankerService()

        results = []
        total_latencies = []
        hits = 0

        for q in test_questions:
            q_id = q["id"]
            query = q["query"]
            expected = q["expected_doc"].lower()

            t0 = time.time()
            c_hits = colpali.colpali_maxsim_search(query, top_k=5)
            v_hits = vec_service.vector_search(query, top_k=5)

            all_cands = c_hits + v_hits
            top_ranked = reranker.rerank(query, all_cands, top_k=3)

            latency = round((time.time() - t0) * 1000, 2)
            total_latencies.append(latency)

            top_doc = top_ranked[0].get("original_name") if top_ranked else "N/A"
            top_score = top_ranked[0].get("rerank_score", 0.0) if top_ranked else 0.0

            # Hit thực sự khi tên tài liệu được trích xuất trùng khớp với expected_doc
            is_hit = False
            if top_ranked and top_doc and expected in top_doc.lower():
                is_hit = True
                hits += 1

            results.append({
                "id": q_id,
                "query": query,
                "category": q["category"],
                "expected_doc": q["expected_doc"],
                "retrieved_doc": top_doc,
                "score": top_score,
                "latency_ms": latency,
                "status": "PASS" if is_hit else "FAIL"
            })

            status_str = "PASS" if is_hit else "FAIL"
            safe_query = query.encode('ascii', 'ignore').decode('ascii')
            self.stdout.write(f"Question #{q_id:02d}: '{safe_query[:32]}...' -> Doc: {top_doc} | Score: {top_score}% [{status_str}]")

        avg_latency = round(sum(total_latencies) / len(total_latencies), 2)
        accuracy = round((hits / len(test_questions)) * 100, 1)

        summary = {
            "total_questions": len(test_questions),
            "hits": hits,
            "accuracy_percent": accuracy,
            "avg_latency_ms": avg_latency,
            "benchmark_results": results
        }

        out_file = settings.MEDIA_ROOT / 'benchmark_a3_results.json'
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        self.stdout.write(self.style.SUCCESS("\n=================================================="))
        self.stdout.write(self.style.SUCCESS("REAL A3 MULTIMODAL RAG BENCHMARK RESULTS:"))
        self.stdout.write(self.style.SUCCESS(f"  - Total Test Questions: {len(test_questions)}"))
        self.stdout.write(self.style.SUCCESS(f"  - True Retrieval Hits: {hits} / {len(test_questions)}"))
        self.stdout.write(self.style.SUCCESS(f"  - Real Accuracy: {accuracy}%"))
        self.stdout.write(self.style.SUCCESS(f"  - Avg Latency: {avg_latency} ms"))
        self.stdout.write(self.style.SUCCESS(f"  - JSON Report: {out_file}"))
        self.stdout.write(self.style.SUCCESS("==================================================\n"))
