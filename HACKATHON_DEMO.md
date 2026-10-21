# Demo A2/A3 cho web hợp đồng

## Khởi động

Chạy từ `D:\Django_project\Contract_DL\Contract_DL`:

```powershell
.\start-services.ps1
```

Mở http://localhost:8000/contract-intelligence/ và đăng nhập tài khoản web hiện có. Database dùng Neon trong `.env` gốc. Qdrant của Compose lưu trong named volume `contract-a3-qdrant`, truy cập từ web qua `http://qdrant:6333` và từ Windows qua http://localhost:6335. Không xóa volume khi khởi động lại.

Tìm tài liệu A3 từ NewIdea tại http://localhost:8000/newidea/. Từ màn hình pipeline A3, liên kết “Tìm tài liệu này bằng NewIdea” giữ phiên bản đã chọn. NewIdea dùng cùng nguồn/index A3 và session web; không cần tải file lần thứ hai.

## Gateway model

Notebook `ai_extract/a3/kaggle_vllm_qwen_serving.ipynb` giữ Qwen và ColPali, nhúng hàm `register_contract_rag` từ service chung `ai_extract/services/contract_pipeline_service.py` cùng import độc lập. Gọi `register_contract_rag(app)` sau khi tạo FastAPI và trước khi chạy uvicorn; không import cả service Django trong gateway. Model được nạp khi có yêu cầu đầu tiên.

Trong `.env` gốc, `RAG_INFERENCE_URL` là URL gốc của gateway, không có `/v1` hoặc `/colpali`. Các route cần có:

- `POST /rag/embed`: BGE-M3, vector dense 1024 chiều; web chia lô 16 chunk.
- `POST /rag/rerank`: BGE reranker v2 m3, điểm logit dùng để xếp hạng.
- `POST /rag/extract_page`: Surya OCR v2 đọc toàn trang, trả layout, text và bbox theo block thật.
- `POST /colpali/embed_query`, `POST /colpali/embed_page`: ColPali của notebook hiện có.
- `/v1/chat/completions`: Qwen hiện có.

`GET /rag/health` báo dependency và model đã nạp; chỉ endpoint inference thành công mới xác nhận model thực sự chạy. Web không cần cài Torch/Surya nếu dùng gateway. Nếu chạy inference cục bộ, dùng môi trường riêng với `ai_extract/requirements-vision.txt`, rồi bật `RAG_LOCAL_MODELS=True`. Surya 0.22 cần backend vLLM hoặc llama-server; notebook chuẩn bị server Surya riêng trước gateway.

## Kịch bản trình diễn

1. Tải hợp đồng, chọn phiên bản và chạy pipeline A3. Xem trang gốc, layout, bbox và cây Điều → Khoản → Điểm. Kiểm tra trạng thái dense và ColPali sau khi trích xuất.
2. Hỏi một thời hạn hoặc số tiền có trong hợp đồng. A3 kết hợp BM25, BGE-M3 và ColPali bằng RRF, rerank rồi mở rộng điều cha, định nghĩa và dẫn chiếu. Mở citation để đối chiếu trang nguồn.
3. Hỏi điều kiện chấm dứt có dẫn chiếu điều thông báo ở trang khác. Kiểm tra hai phần cùng xuất hiện trong bằng chứng và đường dẫn cấu trúc.
4. Hỏi điều không có trong hợp đồng. Quality gate hoặc kiểm tra câu trả lời phải trả nguồn đối chiếu/thông báo thiếu bằng chứng. ID nguồn, câu có citation và số liệu được kiểm tra; đây chưa phải kiểm chứng ngữ nghĩa hoàn chỉnh.
5. Chọn chế độ rà soát toàn bộ nguồn đã trích xuất và bật Qwen. Theo dõi số lô đã đọc, phần lỗi, phần chưa xử lý trong `context_coverage`. Tối đa 32 lô/request; không coi đây là bảo đảm phát hiện mọi rủi ro pháp lý.
6. A2: nhập ghi chú chuyên gia → tạo đề xuất bằng AI → chuyên gia sửa và xác nhận → lưu nháp → reviewer duyệt → tìm tái sử dụng trên hợp đồng cùng loại. AI không tự lưu hoặc phê duyệt. Case nháp không xuất hiện trong kết quả tái sử dụng; revision giữ lịch sử. Kiểm tra điều kiện áp dụng trước khi dùng case đã duyệt.

Vector được lọc theo công ty, hợp đồng, phiên bản và lần trích xuất hoàn tất. Nội dung bằng chứng lấy lại từ nguồn hiện tại thay vì tin text trong payload vector. Giao diện báo trạng thái từng nhánh và reranker; khi model lỗi, kết quả còn lại được ghi rõ là truy xuất lexical/cấu trúc.

Fusion dùng baseline trọng số BM25:dense:ColPali = 1:1:1 (`equal-baseline-v2`). Nhận diện loại câu hỏi chỉ dùng để mô tả, không tự đổi trọng số. ColPali trả tối đa 8 trang; trong mỗi trang, BM25 chọn tối đa 3 chunk nguyên văn, bổ sung theo thứ tự nguồn nếu chưa đủ chunk khớp. Mọi chunk được chọn kế thừa thứ hạng trang gốc để tính phần đóng góp ColPali trong RRF; số chunk của trang trước không làm tụt hạng trang sau. Payload kết quả giữ `colpali_page_rank`, `colpali_page_score`, `colpali_chunk_rank`. API báo `fusion_weights`, `fusion_policy` và số trang/chunk đã chọn.

Trọng số này chưa được tối ưu trên hợp đồng thật. Khi đánh giá, chia tập theo hợp đồng và dùng câu hỏi có nhãn nguồn do người đọc xác nhận; so sánh cấu hình trên cùng tập ứng viên, đo source recall, nDCG và latency. Không chọn trọng số theo kết quả của bộ 30 câu tổng hợp rồi báo đó là chất lượng held-out. Giới hạn 30 ứng viên trước reranker hiện vẫn áp dụng.

Nếu dữ liệu đã được lập chỉ mục trước khi thêm scope công ty và leaf ID:

```powershell
docker compose exec web python manage.py reindex_contract_versions --version-id <ID>
```

Lệnh chỉ lập lại index của run hoàn tất, không sửa file gốc. Cần gateway inference hoạt động. Phân tích lại cây của run cũ bằng provider cấu trúc (mặc định Granite) qua `rebuild_contract_structure --version-id <ID>` trước đó; lệnh này gửi text/ảnh tới gateway và đặt index PENDING.

## Benchmark có nhãn

```powershell
docker compose exec web python manage.py evaluate_contract_demo
docker compose exec web python manage.py evaluate_contract_demo --generate
```

Mặc định dùng `ai_extract/demo/contracts_qa.json`: 30 câu tổng hợp trên 6 hợp đồng mẫu, gồm 24 câu có đáp án và 6 câu không có đáp án. Lệnh đầu không gọi model và không ghi dữ liệu hợp đồng vào Neon. Lệnh thứ hai gọi Qwen với nguồn mẫu; kiểm tra citation/số liệu và đáp án được gán nhãn. Kết quả ghi vào `scratch/contracts_demo_results.json`.

Kết quả phát triển hiện tại: mean required source recall của BM25 trên page block là 0.75, của truy xuất mở rộng cấu trúc là 1.00; quyết định có/không đủ nguồn đúng 30/30 câu mẫu. Gate đã được chỉnh theo bộ mẫu này. Đây là kiểm tra hồi quy trên dữ liệu tổng hợp, không phải held-out benchmark, độ chính xác pháp lý, chất lượng OCR hay đánh giá hybrid/model thực tế. Khi thuyết trình cần ghi rõ phạm vi này. Thay bộ mẫu bằng hợp đồng đã ẩn danh và nhãn do người đọc xác nhận để đánh giá chất lượng thực.

## Kiểm thử code

```powershell
docker compose exec web python manage.py test NewIdea.tests.test_contract_search ai_extract.tests.test_hybrid_retrieval ai_extract.tests.test_contract_structure ai_extract.tests.test_a3_bridge contracts.tests.test_intelligence contracts.tests.test_ledger --settings=config.intelligence_test_settings --noinput
```

Các test dùng database SQLite riêng, model giả lập có nhãn rõ và kiểm tra phân quyền, dẫn chiếu, batching, nguồn thiếu, số liệu sai, draft và phê duyệt. Không coi test giả lập là xác nhận gateway Qwen/ColPali đang chạy.
