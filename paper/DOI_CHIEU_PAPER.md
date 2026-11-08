# Đối chiếu `research_paper.md` với hệ thống hiện tại (2026-10-30)

Bản LaTeX trong `paper/main.tex` đã sửa toàn bộ các điểm dưới đây. File `research_paper.md`/`.docx` cũ **giữ nguyên**, không bị ghi đè.

## Mô tả kỹ thuật sai so với code

| # | Bài báo cũ ghi | Code hiện tại làm | Nguồn |
|---|---|---|---|
| 1 | Reranker là BGE-Reranker-**Large** | `BAAI/bge-reranker-v2-m3` (đa ngôn ngữ) | runtime `/rag/health`, `search_job_service.py` |
| 2 | BM25 là "nhánh sparse của BGE-M3", lưu trong Qdrant | BM25 tính trên token postings lưu trong **PostgreSQL** (`RetrievalPassage.token_counts`). Không dùng sparse BGE-M3 | `contract_repository.keyword_search`, `shared/retrieval.py` |
| 3 | Bảng do "Surya Table" nhận diện bằng "anchor-free grid regression" | **TATR (Table Transformer)** tách hàng/cột, rồi Surya OCR đọc từng ô. Bảng chỉ được coi là có cấu trúc khi chuỗi ô ghép lại khớp đúng text OCR | `surya_inference_service.py:172` |
| 4 | Ô gộp được **sao chép lặp lại** vào các ô (Hình 3 cũng vẽ như vậy) | Ô gộp **để trống**, kèm metadata `merged_cells` (row/column/rowspan/colspan) và `table_header_rows`. Không nhân bản giá trị | `knowledge_answer_service.answer_source_pods` |
| 5 | Image-to-Text: "tổng hợp văn bản đặc tả sơ đồ" | Không có bước sinh mô tả ảnh. Chỉ OCR chữ trong hình một lần; caption/đoạn lân cận nối bằng hình học và đánh dấu là **candidate chưa xác minh** | `ai_extract/README.md`, `document_graph_service.py` |
| 6 | Cạnh `CAPTION_FOR`, `NEAR` | Thực tế là `FIGURE_CAPTION_CANDIDATE`, `FIGURE_NEAR_TEXT_CANDIDATE`, `ABOVE`, `LEFT_OF`, `HAS_FIGURE_TEXT`. Không có `CAPTION_FOR` | export Neo4j 2026-10-30 |
| 7 | Node DocNode/PageNode/HeadingNode/TableNode/FigureNode; Tài liệu → Trang → Đề mục | Các category: `structure`, `layout_block`, `evidence`, `table`/`table_row`/`table_cell`, `source_image`, `visual_object`, `visual_embedding`, `entity`. `CONTAINS` theo cây heading, không có tầng Trang | `document_graph_service.projection` |
| 8 | GLiNER "thiết lập quan hệ ngữ nghĩa hai chiều trực tiếp trên đồ thị" | Quan hệ chỉ là đề xuất, phải qua code kiểm tra và vẫn ở trạng thái unreviewed. Audit 20 tài liệu ngày 28/10: **0 cạnh ngữ nghĩa trực tiếp** giữa các entity, chỉ có `MENTIONS` | `RELATION_NEWIDEA_AUDIT_20261028.md` |
| 9 | Top-20 sau RRF → reranker chọn **8** khối | Reranker chấm **toàn bộ** ứng viên đã fuse. Seed chọn tham lam theo độ phủ ý hỏi, relevance − 0,35·Jaccard + 0,05 nếu là tài liệu mới; tối đa min(24, max(số ý, 3·số nhóm)) | `search_evidence_service.select_retrieval_seeds` |
| 10 | Mở rộng graph = heading cha + đoạn trước/sau | Lấy các quan hệ cấu trúc trực tiếp, entity dùng chung, liên kết hình, `RELATED_PASSAGE` (phải qua rerank) trong cùng snapshot. Breadcrumb lấy từ `heading_path` lưu sẵn lúc extract, không duyệt graph lúc hỏi | `document_graph_repository.neighbors` |
| 11 | Mã trích dẫn `[E_i]` | ID nguồn ổn định `a3:v{version}:r{run}:{chunk}`. Output là cited claims; code kiểm tra ID/định dạng, sửa lỗi định dạng tối đa 1 lần | `knowledge_answer_service.py` |
| 12 | Qdrant 1.9 | `qdrant/qdrant:v1.13.6`; Neo4j `5-community` | `docker ps` |
| 13 | ColPali không ghi checkpoint; "cho các vùng hình ảnh" | `vidore/colpali-v1.2`, **chỉ** nhúng crop figure; text/bảng không bao giờ dùng embedding cả trang | `document_graph_service.py:421` |
| 14 | Mô hình sinh "VLM-7B" | `Qwen/Qwen2.5-VL-7B-Instruct-AWQ` trên vLLM, `max_model_len` 16.384 | `/v1/models` |

## Khẳng định chưa có bằng chứng (đã gỡ khỏi bản LaTeX)

- "Loại bỏ triệt để rò rỉ thuộc tính", "chính xác 100%", "tiết kiệm hơn 90% visual tokens", "giảm 18 lần Attention" (con số 15.000 → 3.500 token không có trong log).
- Bảng 2 (Q1–Q4). Đối soát E0 với log gốc: 25 trường khớp, **7 trường sai**, 6 trường không có giá trị gốc. Riêng Q2 cấu hình J, log gốc trả lời "cả HSR và HS-A1 đều 8 kg", trái với nhận định "phân định chính xác" trong bài.
- "Mô hình thuần văn bản vẫn phân định đúng 4/4": không có log nào chạy một LLM text-only thật.
- "572 test, 571 pass": không tìm thấy log tương ứng.
- Mục 4.3 so sánh với ">200 giây khi nạp ảnh VLM nguyên trang": không có log.

## Tài liệu tham khảo

- Bài viện dẫn đến [13]–[17] nhưng danh sách chỉ có [1]–[12]. RRF được trích là [11] trong khi mục RRF là [10].
- [2] là một "chuẩn IEEE/ISO" có tên không tồn tại.
- [4] ColPali ghi sai tác giả: tác giả đúng là Faysse, Sibille, Wu, Omrani, Viaud, Hudelot, Colombo, công bố tại ICLR 2025.
- [8] Surya ghi sai tác giả: tác giả đúng là Vik Paruchuri; Blecher là tác giả của Nougat.
- Bản LaTeX dùng `refs.bib` mới, gồm 17 mục mà mỗi mục đều được trích trong bài.
