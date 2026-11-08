# Đánh giá Hierarchical Evidence Pods và Hybrid Retrieval

## Trạng thái hiện tại

**Đang chuẩn bị E1–E4.** Theo yêu cầu mới, đã dừng E0; các log E0 trước đó được giữ lại để truy vết, không cần hoàn thiện thêm. Không coi các kết quả chuẩn bị là bằng chứng chứng minh kiến trúc tốt hơn baseline.

### E0 — Đối chiếu lịch sử

- `E0_historical/historical_raw.jsonl` chứa 5 bản ghi gốc, kèm hash file nguồn và JSON pointer. `historical_runs.csv` là bản tóm tắt, không phải lần chạy mới.
- `E0_historical/reconciliation.csv` và `.json` đối chiếu từng ô số trong bản thảo với log. Có 25 trường số khớp, 7 trường sai và 6 trường thiếu giá trị gốc. Không gán các giá trị thiếu cho cấu hình khác.
- `E0_historical/answer_reconciliation.jsonl` giữ nguyên câu trả lời gốc cạnh nhận định tóm tắt trong bản thảo. Ví dụ Q2 cấu hình J trả lời **cả HSR và HS-A1 đều 8 kg**, trong khi M trả lời **HSR 8 kg, HS-A1 5 kg**. Bảng bản thảo tóm tắt “phân định chính xác HSR 8 kg vs HS-A1 5 kg” nhưng không được dùng để khẳng định J đã đưa ra phân định đó. Các trường chưa được đối chiếu nội dung nguồn vẫn để chờ rà soát.
- Số giây trong log là thời gian HTTP submission/polling; không phải riêng thời gian API model. Tổng các stage là tổng số học, không chứng minh các stage không chồng lấp.
- Bản Word được cung cấp có bảng Q1–Q4 với cùng các số trên bản `research_paper.md`; bản đối soát dùng Markdown và log gốc. Các khẳng định về độ chính xác 4/4, loại bỏ triệt để lỗi và tiết kiệm visual token chưa được xác minh bằng nghiên cứu độc lập.
- `E0_exploratory_replay_v2/` đã chạy 25/25 lượt, 5 lần cho từng trường hợp có log gốc. Vì chỉ có J/Q1–Q4 và M/Q2, không thể tái tạo M/Q1, M/Q3, M/Q4 từ log. Replay chỉ chạy sinh từ evidence lưu trong archive, không đo end-to-end qua retrieval và không tái tạo prompt/model/hardware lịch sử; không dùng để tuyên bố so sánh nhân quả. Lượt đầu `E0_exploratory_replay/` bị dừng sau khi output JSON thiếu trường answer; các lỗi được giữ lại, không tính vào thống kê v2.
- Gateway hiện không mở `/tokenize` hoặc `/v1/tokenize`. Replay ghi `tokenizer_preflight=unavailable`, và lấy usage token thực từ phản hồi API nếu có; không ước lượng. Lỗi API và câu trả lời chưa hoàn tất được giữ nguyên trạng thái lỗi.

### Corpus và cấu hình

- `manifest_status.json` ghi Git HEAD, trạng thái dirty và hash các file chính. `source_snapshot.zip` và `source_snapshot_manifest.json` lưu 80 file mã liên quan tại thời điểm chụp; chúng không phải toàn bộ working tree. HEAD không đủ để tái lập các thay đổi chưa commit.
- `corpus_db_inventory_20261030.csv` liệt kê 201 phiên bản có trong DB tại thời điểm ghi, run và trạng thái index; đây là **danh mục**, không phải bản sao bất biến của DB, Neo4j hay Qdrant.
- `corpus_filesystem_20261030.csv` là 75 PDF trong thư mục `documents`, kèm hash và số trang; danh sách này không đồng nhất với 201 phiên bản trong DB. `previous_corpus_snapshot.csv` là snapshot cũ, không nhận là snapshot hiện tại.
- `config_requested.json` là cấu hình evaluator, không chứng minh cấu hình lịch sử. `runtime_observation.json` ghi probe hiện tại: gateway báo model `Qwen/Qwen2.5-VL-7B-Instruct-AWQ`, rerank trả tên `BAAI/bge-reranker-v2-m3`; revision checkpoint và GPU inference chưa xác minh. Code khai báo BM25 và BGE-M3 dense; chưa chứng minh checkpoint/reranker lịch sử đúng như vậy.

### Dataset và E1–E4

- `pilot50_draft.jsonl`, `pilot50_evidence.jsonl`, `pilot50_reference_answers.md` là bộ 50 câu dự thảo trên 20 tài liệu đã dùng phát triển, bao gồm tuple và vị trí nguồn. `pilot50_review_queue.csv` tập hợp từng câu, đáp án, tuple, evidence và trường dành cho người rà soát. Cả 50 đang `pending_independent_review`; chưa được coi là gold, chưa phải test độc lập.
- `pilot50_evidence_trace.csv` kiểm tra tự động đường dẫn PDF và trang: tìm thấy đủ 65/65 vùng nguồn trong PDF/trang tương ứng; text sau chuẩn hóa khớp nguyên chuỗi với text layer của trang ở 38/65 vùng. 27 vùng còn lại không khớp chuỗi có thể do OCR, thứ tự cột/bảng hoặc cách trích xuất khác; chưa được kết luận là sai và cần đối chiếu trực quan.
- `pilot50_current_mapping_candidates.jsonl` và `pilot50_current_rebind.jsonl` ánh xạ 65 vùng cũ sang phiên bản hiện tại có cùng SHA-256 PDF, cùng trang, bbox và text nguyên văn; hai vùng có nhiều hơn một bản trùng PDF trong DB và chọn bản đầu, các ứng viên đều được lưu để kiểm tra. `pilot50_current_graph_contexts.json` đóng băng graph context đã đọc từ 20 snapshot hiện tại; 20/20 trả trạng thái ready. Ánh xạ kỹ thuật này chưa phê duyệt đáp án gold.
- `pilot50_current_questions.jsonl`, `pilot50_current_evidence.jsonl` và `pilot50_current_bound_graph.json` là bộ pilot đã nối lại ID evidence với 20 snapshot hiện tại, giữ nguyên trạng thái chờ duyệt. Metadata production và graph links được giữ theo dữ liệu thật. `pilot50_table_review.csv` liệt kê 16 vùng bảng: 12 vùng có chuỗi ô trùng nội dung nguồn sau chuẩn hóa khoảng trắng, 4 vùng còn cần kiểm tra; phép kiểm tra chuỗi không xác minh đúng hàng/cột.
- `E1_pilot_probe_01` và `E1_pilot_probe_02` là probe trên duy nhất câu P001, mỗi định dạng 3 lượt, cố định evidence. E sử dụng renderer production; A–D sử dụng renderer canonical. `questions.jsonl` lưu prompt, phản hồi và token thực tế; `summary_probe.csv` và `probe_observations.json` chỉ mô tả probe này. Ở probe 02, Qwen nêu đúng tên hai nền tảng ở cả năm định dạng nhưng không trả lời phần công dụng được hỏi. Chênh lệch token lớn nhất/nhỏ nhất là 1,372, vượt ngưỡng 1,25 của config; riêng E/D là 1,225. Không suy rộng probe một câu hoặc tính thành kết quả E1 chính thức. Câu hỏi này không chứa bảng, vì vậy A và C cùng nội dung.
- E1/E2 chưa chạy trên gold được duyệt; E3/E4 chưa chạy. Chưa có bộ test độc lập 200–300 câu được xác nhận tách theo họ tài liệu, text-only LLM thực sự, hoặc baseline đo visual-token/GPU memory. Không có điểm accuracy hay biểu đồ so sánh E1–E4 giả lập.
- `E0_paired_recreated/runner_status.json` ghi lượt đối chứng 4 câu × 2 định dạng × 5 lần chưa bắt đầu được do gateway `/v1/models` trả HTTP 404. Đối chứng này sẽ dùng cùng evidence từ log J cho cả hai định dạng; nó không phải log Markdown lịch sử đã mất.
- `E0_paired_recreated_retry/` chứa các lượt đã ghi trước khi người dùng yêu cầu dừng E0; đây không phải một bộ thí nghiệm hoàn chỉnh và không được tổng hợp thành kết quả chính thức.
- `E0_exploratory_replay_v2/questions.jsonl` ghi prompt, response và token từng lượt; `summary_exploratory.csv` và `generation_latency_exploratory.png` ghi mean và SD của thời gian sinh và token, không phải thời gian end-to-end của hệ thống. Không coi một câu `completed_pending_review` là đúng nếu chưa đối chiếu với evidence.

Các file nguồn và bản thảo gốc không được thay đổi trong bước đối soát này.
