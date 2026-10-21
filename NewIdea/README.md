# NewIdea — tìm kiếm và tri thức hợp đồng

Mở http://localhost:8000/newidea/ bằng tài khoản web hợp đồng.

- **Tìm toàn bộ kho được phép truy cập:** dò phiên bản mới nhất bằng BM25 và chỉ mục BGE-M3; chọn tài liệu liên quan, truy xuất A3 bằng BM25/BGE/ColPali, RRF và reranker. Admin tìm trên tất cả công ty; tài khoản thường giữ quyền đọc hiện có. Kết quả có nguồn và đường dẫn đến đúng phiên bản.
- **Hỏi trên một phiên bản:** giữ cấu trúc điều/khoản, mở rộng cha và dẫn chiếu. Qwen chỉ tổng hợp từ bằng chứng; kiểm tra citation và heuristic chưa chứng minh mọi nhận định đúng.
- **Chuyển chuyên gia:** kết quả tra cứu → gửi yêu cầu → quản lý phân công → chuyên gia tạo case nháp gắn bằng chứng A3 → reviewer khác tác giả phê duyệt → hoàn tất yêu cầu và tái sử dụng case.
- **Nguồn case:** chọn ID `block:…`, `clause:…` hoặc `context:…` tồn tại trong phiên bản. Khi duyệt lưu nội dung và SHA256; nguồn bị thay đổi hoặc mất sẽ loại case khỏi gợi ý. Case cũ chưa có bằng chứng cần tạo revision và duyệt lại.
- **Truy vết:** KnowledgeSearchLog lưu người hỏi, phiên bản, câu hỏi, câu trả lời, nguồn và hash, chính sách retrieval và model cấu hình. Chưa xác minh revision model thực tế của gateway.
- **Tải:** tối đa 30 tra cứu/phút/người dùng, 6 yêu cầu tổng hợp/phút và 3 yêu cầu tổng hợp đang chờ/chạy. UI gửi Qwen vào hàng đợi database; `knowledge-worker` xử lý ngoài request web. Không tự retry job lỗi.

## Phạm vi hackathon

Tìm toàn kho có giới hạn: 100 phiên bản mới nhất theo thời gian tạo, 2.000 block/phiên bản, đọc sâu tối đa 6 hợp đồng, 30 ứng viên trước reranker và 10 kết quả, tối đa 2 đoạn/hợp đồng. API trả phạm vi và cờ `partial`. Đây là baseline cần benchmark với hợp đồng thật; chưa phải chỉ mục lexical phân tán ở quy mô Google. Case đã duyệt dùng BM25 trên các trường nghiệp vụ và cần chuyên gia kiểm tra điều kiện áp dụng. Điểm xếp hạng không phải phần trăm chính xác.

Không tự tìm Internet hoặc gửi hợp đồng ra search engine công khai. A3 dùng gateway inference đã cấu hình. API prototype nhà máy ghi tri thức trực tiếp, trả lời chuyên gia và xóa toàn bộ lịch sử đã ngừng cung cấp trong mọi chế độ. Server NewIdea riêng chuyển đến web chính; prototype case library chỉ bật bằng `NEWIDEA_MODE=prototype`.

## API

- `POST /api/newidea/search/`: tìm toàn bộ kho được phép đọc, JSON `{ "query": "điều kiện chấm dứt" }`.
- `POST /api/newidea/ask/`: tra cứu một hợp đồng, `contract_id`, `version_id`, `query`.
- `POST /api/newidea/jobs/`: xếp hàng tổng hợp Qwen với `scope: "knowledge"`, `query` để hỏi toàn kho; hoặc `version_id`, `query`, `mode` (`structural` hoặc `whole_contract`) để hỏi một phiên bản. Trả 202 và `search_id`.
- `GET /api/newidea/jobs/?id=…`: trạng thái và kết quả, chỉ người hỏi hoặc quản lý được phép xem.
- `GET/POST /api/newidea/inquiries/`: danh sách, tạo từ `search_id`, `assign`, `answer`, `cancel`.
- `GET /api/newidea/inquiries/?id=…`: mở yêu cầu cùng kết quả tra cứu gốc và case đang soạn. Liên kết xử lý tự nạp đúng phiên bản; chỉ chuyên gia được phân công có thể sửa câu trả lời.
- `GET /api/newidea/versions/<id>/sources/`: nguồn có thể gắn vào case, kiểm tra quyền công ty.

Mọi API web dùng đăng nhập hiện có và CSRF. Phạm vi quyền hiện là công ty; cần bổ sung quyền riêng từng hợp đồng nếu doanh nghiệp yêu cầu.

## Chạy

```powershell
docker compose -f docker-compose.yml -f docker-compose.web-local.yml exec web python manage.py migrate contracts
docker compose -f docker-compose.yml -f docker-compose.web-local.yml up -d --no-deps knowledge-worker
```

Tham khảo: [Google — How Search works](https://www.google.com/intl/en_us/search/howsearchworks/how-search-works/) và [Qdrant — hybrid queries](https://qdrant.tech/documentation/search/hybrid-queries/). Pipeline áp dụng truy xuất nhiều nhánh và xếp hạng, không cam kết tìm được mọi câu trả lời.

## Cấu trúc code

- `views/contract_views.py`: trang NewIdea và API tra cứu một hợp đồng.
- `views/knowledge_views.py`: HTTP/JSON, đăng nhập, lỗi và các API kho tri thức, chuyên gia, job.
- `services/contract_search_service.py`: truy xuất A3 theo phiên bản và chuẩn bị dữ liệu trang.
- `services/knowledge_search_service.py`: tìm toàn bộ kho được phép đọc, fusion và reranking.
- `services/search_evidence_service.py`: tìm case chuyên gia còn đúng nguồn, tạo citation và ánh xạ node.
- `services/knowledge_answer_service.py`: kiểm tra bằng chứng, gọi Qwen, sửa citation tối đa một lần và xác minh câu trả lời. Cả hỏi toàn kho và hỏi một phiên bản dùng chung `generate_checked_answer()`.
- `services/expert_workflow_service.py`: phân công, trả lời và chuyển trạng thái yêu cầu.
- `services/search_job_service.py`: quota, lịch sử bằng chứng và xếp hàng tổng hợp.
- `services/evidence_service.py`, `services/case_rules.py`: kiểm tra nguồn và quy tắc case.
- `repositories/contract_repository.py`: đọc hợp đồng, phiên bản, nguồn A3 theo quyền.
- `repositories/knowledge_repository.py`: đọc/ghi case, inquiry, receipt và audit.

Luồng phụ thuộc: URL → view → service → repository → model/database.
View không truy vấn ORM; service không nhận HttpRequest hoặc trả JsonResponse.
Các chức năng liên quan được nhóm theo nghiệp vụ, không tạo một file cho từng hàm.
Các script seed dữ liệu nhà máy và pipeline demo cũ đã được bỏ. Models/migrations của prototype được giữ để bảo toàn lịch sử dữ liệu.

Kiểm thử web hợp đồng từ thư mục gốc: `python manage.py test NewIdea.tests.test_enterprise NewIdea.tests.test_contract_search --settings=config.intelligence_test_settings --noinput`.
Kiểm thử prototype độc lập từ thư mục `NewIdea`: `python manage.py test core --noinput`.

## Tối ưu tra cứu A2 — 2026-10-13

Một `SearchBackend` chỉ tồn tại trong một lượt hỏi: dùng lại embedding BGE và
ColPali của câu hỏi, kể cả ghi nhớ lỗi để tránh gọi lại endpoint đang lỗi cho
từng tài liệu. Mỗi truy vấn Qdrant vẫn có bộ lọc công ty/hợp đồng/phiên bản/run
riêng; cache không chia sẻ kết quả giữa người dùng.

A3 trả ứng viên BM25 + dense + ColPali đã fusion. A2 gom ứng viên của tối đa
6 tài liệu, giữ cơ hội cho từng tài liệu trong pool 30 đoạn, rerank chung một
lượt rồi mở rộng ngữ cảnh đề mục/dẫn chiếu/Neo4j. Hỏi riêng một tài liệu rerank
ứng viên trước, rồi chấm lại phần mở rộng bằng cùng reranker: giữ các nguồn chính
và phần mở rộng có relevance ít nhất bằng nguồn chính thấp nhất. Phần lược bỏ
được ghi trong coverage; không cắt text bên trong chunk.

Job lưu tiến trình `discovering → retrieving → reranking → reading_graph →
generating → verifying`; `repairing_citations` chỉ xuất hiện khi cần sửa trích
dẫn. Web hiển thị giai đoạn thực tế và thời gian chờ ngay dưới câu hỏi, không
hiển thị câu trả lời chưa kiểm chứng. Số lượt Qwen phụ thuộc số nhận định:
sinh câu trả lời, kiểm chứng riêng từng nhận định và kiểm tra trả lời đủ câu hỏi;
có một lượt sửa nếu nội dung hoặc trích dẫn chưa đạt.

## Nguồn và cấu trúc trong câu trả lời A2

A2 giữ nguyên chunk, text, trang và bbox đã lưu. Neo4j cung cấp cấu trúc và
liên kết tới đúng các nguồn được truy xuất, với ngân sách cân bằng giữa các loại
cạnh. `NEXT` chỉ sắp thứ tự trình bày nguồn khi liên kết rõ ràng, không gộp đoạn.
Qwen nhận các nguồn dưới dạng danh sách có ID cùng graph; không ghép riêng toàn
trang để vượt qua kiểm thử. Case DEMO không đi vào luồng hỏi một hợp đồng.

A2 sends the original question, native source passages, and source-bound Neo4j
nodes/edges with a legend for each delivered relationship type. Spatial edges are
supplementary; NEXT is reading order only. Every retrieved type is eligible, subject
to source access and explicit context budgets (partial/omitted_edges).
No subject-name decoder constraints, fixed translation glossary or question
translation stage is used. Qwen selects the source IDs and interprets meaning.
Code validates IDs and formatting; model calls check support and completeness.
Raw provider responses are retained. Self-verification is not proof of accuracy.

Connected context retrieval keeps per-seed neighbor mappings from Neo4j rather
than assigning one combined neighbor list to every seed. Direct structural
links, including NEXT and spatial links, can retrieve their opposite source.
Graph reads have no implicit 16-source/80-edge cutoff. Source expansion has no implicit character/source-count cutoff. If a caller
sets an explicit budget, omitted source IDs and reasons are reported.
Expanded context is reranked for ordering only. Model graph delivery groups
edges by type with columns, rows and shared constants; source text is not
summarized. Audit receipts retain the original graph. The normal model graph
has no separate character cutoff: provider context overflow fails explicitly.

Indexed retrieval follows explicit neighbors of the seed's lowest source owner.
It does not load every sibling solely because they share a heading. Upward
CONTAINS traversal supplies the heading path, not every descendant's text.
Model graph nodes and edges use tables with named columns and shared constants;
all original values remain in the audit snapshot. Stable verification context
precedes the changing claim to permit provider prefix-cache reuse.

The graph prompt is scoped to primary retrieval seeds and their direct relations
plus source/hierarchy paths. Expanded passages do not recursively seed another
round of graph relations. Shared page membership does not fetch all page objects.
Generation, claim verification and completeness receive the same source/graph
context; supplied images are retained during both verification stages.
The server must accommodate input plus the configured output reservation;
context overflow is reported rather than handled by silently dropping evidence.

Normal A2 answers default to concise style with at most 2048 reserved output
tokens (or a lower configured budget). This changes answer length, not evidence
or graph retrieval. Explicit explanatory requests retain the larger configured
budget. Graph details remain model context and are not enumerated in the answer.
