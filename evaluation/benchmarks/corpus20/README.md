# Corpus 20 tài liệu — A3 trước, câu hỏi sau

20 PDF thật được chọn từ `documents/`, không gồm hai tài liệu regression
Dual-arm Control và EVP2. Danh sách nằm ở `../corpus20_selection.json`.

Luồng đang chạy là production:

`ContractService` lưu PDF mã hóa → `LayoutExtractionService.extract_version`
→ Surya OCR → cấu trúc nguồn/GLiNER → Neo4j → BGE/Qdrant và ColPali/Qdrant.

- `a3_ingestion.json`: SHA-256, contract ID, version ID, run ID và trạng thái thực.
- `a3_ingestion.log`: tiến trình production từng trang, lỗi và thời gian thực.
- `a3-runtime.out.log` / `a3-runtime.err.log`: log inference host.
- `a3_worker_location.json`: vị trí worker và volume trạng thái của lượt chạy tiếp.
- `a3_resume.log`: bản sao log của lượt chạy tiếp, được watcher Windows cập nhật.
- `pdfs/`: bản sao nguyên byte của 20 PDF đã chọn.
- `source_pages.json`: lớp chữ PDF đọc trong bước kiểm kê ban đầu;
  **không phải output A3, không dùng thay OCR/evidence chuẩn cho bộ câu hỏi**.

Không có câu hỏi hoặc đáp án mới được sinh trong bước nạp này. Sau khi kiểm tra
output A3, soạn 50 câu pilot rồi thêm 200 câu, đối chiếu với ảnh PDF và giữ
cảnh báo OCR/điều kiện áp dụng. Đây là mở rộng câu hỏi trên corpus đang chọn;
không tự nhận là test độc lập trên tài liệu chưa từng dùng phát triển.

Sau sự cố `errno=12`, trạng thái và log của lượt chạy tiếp được ghi chính vào
`/evaluation-state/` trong named volume Linux (xem `a3_worker_location.json`).
Watcher đọc trạng thái từ đó, đồng bộ `a3_ingestion.json` và `a3_resume.log` bằng
Windows host, đồng thời báo nếu container thoát bất ngờ. Log cũ không bị xóa;
container trước được giữ lại với tên `contract_evaluation_batch_previous_*`.
Các run đã có trạng thái COMPLETED không chạy lại, kể cả khi còn cảnh báo index;
những cảnh báo đó vẫn được liệt kê riêng trong báo cáo cuối.

Kiểm tra trạng thái live trong DB:

```powershell
docker exec riskdl_web python manage.py ingest_evaluation_corpus --username admin --status
```

Batch được chạy trong container, tiếp tục khi đóng terminal/chat. Không chạy lại
lệnh ingest khi batch đang hoạt động. Run COMPLETED không tự bảo đảm mọi vùng
OCR đã đọc được hoặc tất cả index đã thành công; kiểm tra processing warnings,
graph, dense và colpali riêng trước khi chọn evidence.


Active short-document corpus: 20 unique PDFs, at most 5 pages each, 66 pages total. Selection: `evaluation/benchmarks/corpus20_short_selection.json`. 11 prior completed extractions are reused; 9 additions registered with version IDs 175-183. Container: `contract_evaluation_short20`; native state volume: `contract_evaluation_short20_state_20261025`. ColPali is explicitly deferred because the remote ngrok endpoint is offline; this is not full visual-index completion. ROB was removed at user request; see `rob84_removal.json`. Original extraction logs remain in previous containers/volumes.
