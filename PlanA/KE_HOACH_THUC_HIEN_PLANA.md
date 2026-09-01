# 🔬 KẾ HOẠCH THỰC HIỆN DỰ ÁN PLAN A — TRỌNG TÂM ĐỀ BÀI A3

> **Dự án:** DENSO VisionMind — Multimodal VLM-Native & On-Premise GraphRAG Engine  
> **Chủ đề Đề bài chọn thực hiện:** **A3 (P3 - Predictive & Knowledge AI)** — Ingest tự động tài liệu gốc PDF/ảnh/bảng/song ngữ & Chatbot RAG Tra cứu Đa phương thức kèm Visual Bounding Box  
> **Phiên bản:** Production Execution Plan v2.0 (A3 Dedicated)  
> **Xem bản kế hoạch A3 chuyên sâu đầy đủ:** [KE_HOACH_THUC_HIEN_A3.md](file:///d:/Django_project/DensoFactoryHack2026/PlanA/KE_HOACH_THUC_HIEN_A3.md)  

---

## 🎯 TÓM TẮT TRỌNG TÂM ĐỀ A3 (SPECIFICATION SUMMARY)

| Thành phần | Chi tiết Mô tả Đề bài A3 | Giải pháp Kỹ thuật Triển khai |
| :--- | :--- | :--- |
| **INPUT (Dữ liệu vào)** | Tài liệu PDF / Ảnh / Bảng thông số / Sơ đồ mạch song ngữ (JP-EN-VI) giữ nguyên cấu trúc gốc + 20-30 câu hỏi test có đáp án. | • Renderer: `Pdf2Image` @ 300 DPI.<br>• ColPali SigLIP ViT Tokenizer (5329 patches/trang).<br>• Bộ 30 Test Cases Benchmark DENSO. |
| **OUTPUT (Kết quả phải có)** | Ingest pipeline tự động + Multimodal RAG Chatbot + Đánh giá độ chính xác & độ trễ + Visual Bounding Box Citation. | • FastAPI Ingest Server.<br>• Chatbot phản hồi kèm Bounding Box `[x_min, y_min, x_max, y_max]`.<br>• Context Precision > 96.2%, Latency < 400ms. |
| **CÔNG NGHỆ SỬ DỤNG** | VLM - OCR / No-OCR - LayoutLM - Vector DB - Embedding Đa ngữ - Reranker | • **ColPali SigLIP-So400M** (Visual Patch Embedding).<br>• **Qdrant DB** (Scalar Quantization SQ8 uint8).<br>• **Neo4j GraphRAG** (Multi-hop Cypher Traversal).<br>• **BGE-Reranker-v2-m3** & **Qwen2.5-VL-7B (vLLM)**. |

---

## 📅 LỘ TRÌNH 8 GIAI ĐOẠN THỰC HIỆN ĐỀ A3 (10 NGÀY)

```text
Giai đoạn 1 (Day 1)   : Dựng Hạ tầng Air-Gapped Docker (Qdrant SQ8, Neo4j, vLLM CUDA)
Giai đoạn 2 (Day 2-3) : Xây dựng Ingest Pipeline Tự động & ColPali Visual Indexer
Giai đoạn 3 (Day 4)   : Thiết lập Neo4j Knowledge Graph & Cypher Multi-hop Traversal
Giai đoạn 4 (Day 5)   : Thuật toán Retrieval Lai 4 Giai đoạn (ColPali + BM25 + Neo4j + Reranker)
Giai đoạn 5 (Day 6)   : Thuật toán Ánh xạ Visual Bounding Box Heatmap Canvas (32x32 Grid ➔ PDF Pixels)
Giai đoạn 6 (Day 7-8) : Tích hợp Local VLM Client, FastAPI Server & Web UI Viewer
Giai đoạn 7 (Day 9)   : Đánh giá Bộ 30 Câu hỏi Benchmark A3 & RAGAS Metrics
Giai đoạn 8 (Day 10)  : Pitching Slide, Demo Video & Kịch bản Bảo vệ Ban Giám khảo
```

---

> 📄 **Xem chi tiết toàn bộ mã nguồn 100% production python code & 30 câu hỏi benchmark tại:** [KE_HOACH_THUC_HIEN_A3.md](file:///d:/Django_project/DensoFactoryHack2026/PlanA/KE_HOACH_THUC_HIEN_A3.md)
