# A3 trong web quản lý hợp đồng

A3 đã được gom vào `ai_extract/services`, cùng ứng dụng AI của web. `a3/` chỉ giữ notebook, dữ liệu và công cụ quản trị schema cũ. Web sử dụng `/contract-intelligence/`, `/contracts/<contract_id>/intelligence/` và API `POST /api/contracts/<contract_id>/intelligence/search/`.

File của phiên bản được giải mã và đưa trực tiếp vào extractor A3 qua service chung `ai_extract/services/contract_pipeline_service.py`. File này chứa adapter, lưu dữ liệu, cây cấu trúc, lập chỉ mục, fusion, kiểm tra bằng chứng, rà soát và Qwen client. Pipeline lưu trang, block, bbox và cây cấu trúc trong các model web. `document_processor` và `clause_tools` đã được bỏ; bản ghi Clause lấy từ cùng cây nguồn.

API ưu tiên block của extraction run hoàn tất, rồi điều khoản hoặc raw text của đúng phiên bản. Không dùng lời khuyên AI làm nguồn hợp đồng. BM25, BGE-M3 và ColPali được kết hợp bằng RRF, neural reranker chọn seed, sau đó mở rộng điều cha, định nghĩa và dẫn chiếu trước khi gọi Qwen.

API kiểm tra tài khoản, công ty, hợp đồng và phiên bản. Vector được lọc thêm company ID và extraction run ID. Payload vector được ánh xạ về leaf nguồn hiện tại. Citation giữ ID hợp đồng/phiên bản, trang, bbox và liên kết đối chiếu. Điểm xếp hạng không phải độ chính xác pháp lý.

Quality gate kiểm tra nguồn trước khi sinh câu trả lời. Kiểm tra sau sinh phát hiện citation sai, câu thiếu citation và số liệu không có trong nguồn; chưa kiểm chứng ngữ nghĩa đầy đủ. Model lỗi hoặc câu trả lời không đạt sẽ trả nguồn đối chiếu. Rà soát toàn bộ nguồn chia các leaf thành lô, báo rõ phần đã xử lý, lỗi và còn thiếu trong `context_coverage`.

## Chạy với Docker Compose

Chạy từ thư mục chứa `manage.py`, dùng Neon SSL trong `.env` gốc:

```powershell
Set-Location 'D:\Django_project\Contract_DL\Contract_DL'
.\start-services.ps1
docker compose exec web python manage.py check
```

Web dùng dependency nhẹ trong `requirements.txt`. Gateway phục vụ Qwen, ColPali và các route BGE/Surya. Hàm `register_contract_rag` nằm trong `ai_extract/views/inference_views.py`; notebook nhúng riêng hàm này cùng import cần thiết để chạy ngoài Django. `RAG_INFERENCE_URL` là URL gốc gateway. Qdrant chạy trong Compose, lưu named volume riêng.

Migration `ai_extract.0005_contract_structure` giữ metadata cấu trúc. Run cũ phân tích lại bằng provider cấu trúc (mặc định Granite) qua `rebuild_contract_structure --version-id <ID>`; lệnh gửi nguồn tới gateway và đặt index PENDING. Khi thay đổi payload index, dùng `reindex_contract_versions --version-id <ID>` với gateway hoạt động. Không cần đổi file hợp đồng hoặc tạo database thay Neon.

Xem [HACKATHON_DEMO.md](../../HACKATHON_DEMO.md) cho cấu hình, luồng trình diễn A2/A3 và bộ 30 câu hỏi có nhãn. Kiểm thử giả lập không xác nhận chất lượng OCR/model trên hợp đồng thật.
