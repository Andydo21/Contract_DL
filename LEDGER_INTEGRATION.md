# Ký theo phiên bản và đối chiếu Fabric

Mở `/contract-ledger/` hoặc mục Blockchain trên web. Giao dịch mới dùng outbox trong database hợp đồng; các bảng blockchain cũ được giữ nguyên để bảo toàn lịch sử, nhưng API ký/ghi cũ đã ngừng nhận yêu cầu.

## Sử dụng

1. Tài khoản ký cần thuộc công ty của hợp đồng. MANAGER/ADMIN, SIGNER hoặc role có permission `ledger.sign` được ký; `ledger.anchor` cấp quyền ghi hash. Quản trị viên gán permission trên role qua Django admin. Superuser vẫn cần thuộc công ty khi tự ký; quyền đọc toàn hệ thống không thay thế danh tính người ký.
2. Người ký tạo RSA 3072 trong trình duyệt, tải khóa riêng PKCS#8 và đăng ký public key. Khóa riêng không được gửi lên server. Bảo quản file khóa riêng; ứng dụng không có bản sao để khôi phục.
3. Một MANAGER/ADMIN khác duyệt public key. Không tự duyệt khóa. Có thể thu hồi khóa hoặc đăng ký khóa mới để thay thế.
4. Chọn chính xác phiên bản và, nếu cần, bước ký workflow. Trình duyệt ký nguyên văn manifest do server chuẩn bị. Server và chaincode đều xác minh chữ ký RSA-SHA256; manifest chứa company/contract/version/signer/step, hash từng file và fingerprint khóa.
5. Yêu cầu được lưu trước trong outbox. `PENDING` chờ xử lý; `SUBMITTED` đang xử lý bằng lease; `FAILED` có lỗi và được thử lại theo backoff; `CONFIRMED` chỉ sau khi đọc được transaction/block của commit thực tế. Tối đa 12 lần tự thử; người ký hoặc quản lý có thể retry yêu cầu thất bại.
6. Trang kiểm chứng hiển thị riêng: hash file đang lưu, hash file tải lên, chữ ký RSA, bằng chứng ledger và trạng thái khóa hiện tại. Khóa bị thu hồi không xóa chữ ký lịch sử; cột trạng thái khóa cho biết tình trạng hiện tại.

## Chống gửi trùng và phục hồi

Mã idempotency là duy nhất theo loại thao tác, phiên bản, người thực hiện, credential và bước workflow. Worker claim bằng row lock/skip-locked, dùng lease token để ngăn worker cũ ghi đè kết quả của worker mới. Gateway và chaincode giữ operation ID và payload hash. Khi mất phản hồi hoặc worker chết sau commit, lần xử lý tiếp theo đọc lại record và transaction cũ trước khi quyết định gửi.

Sau commit chữ ký, worker đồng bộ bước workflow tương ứng. Nếu database workflow tạm lỗi, trạng thái ledger vẫn CONFIRMED, cờ `workflow_synced` còn false và worker tiếp tục đồng bộ. Không tạo chữ ký ngẫu nhiên hoặc cấp chứng chỉ tự động khi duyệt bước thường. Bước `requires_signature` không được duyệt/force-complete qua endpoint cũ và không được xóa.

## Triển khai trên máy này

Các migration đã áp dụng: contracts 0011/0012 (credential, outbox, permission), workflow 0009 (đánh dấu bước ký). Fabric đã nâng chaincode lên version 2.0, sequence 2; ledger/chứng chỉ được giữ nguyên.

```powershell
.\start-services.ps1
docker compose -f docker-compose.yml -f docker-compose.web-local.yml logs --tail 30 ledger-worker
```

`FABRIC_GATEWAY_TOKEN` và `WORKFLOW_SERVICE_TOKEN` nằm trong `.env` gốc, không commit vào git. Gateway kiểm tra service token; chaincode chỉ nhận thao tác enterprise từ chứng chỉ gateway được pin. Workflow đối chiếu tài khoản/công ty/role từ database hợp đồng, không tin các trường user/company/is_manager trong body.

`ENCRYPTION_KEY` được tách khỏi `SECRET_KEY` để đổi khóa phiên/JWT không làm mất khả năng giải mã file cũ. Khóa phiên/JWT đã được thay bằng giá trị ngẫu nhiên; người dùng cần đăng nhập lại. Khóa mã hóa file cũ được giữ để bảo toàn dữ liệu; cần quy trình re-encryption riêng khi muốn luân chuyển nó.

## Phạm vi tin cậy

Đây là chữ ký RSA bằng public key được người quản lý duyệt trong ứng dụng. Chưa có chứng thư CA độc lập, kiểm tra chuỗi chứng thư/OCSP/CRL hoặc HSM; không tuyên bố chữ ký đạt điều kiện pháp lý của một nhà cung cấp chứng thực chữ ký số. Các tenant chia sẻ danh tính gateway Fabric; quyền công ty do ứng dụng kiểm soát, còn chaincode kiểm tra binding công ty/người ký/khóa và chữ ký. Chưa có MSP riêng cho từng tổ chức hoặc hạ tầng nhiều orderer chịu lỗi.

File hash được tính trên bytes gốc sau giải mã AES-GCM, không decode PDF thành chuỗi. Ledger chỉ nhận manifest/hash/public key/chữ ký, không nhận nội dung tài liệu. Khi mất file gốc hoặc khóa giải mã, hash trên ledger không thể khôi phục nội dung file.

Các giao dịch giả đã lưu trong hệ thống cũ không được tự động chuyển thành bằng chứng hợp lệ. Trang mới chỉ xác nhận bằng chứng đọc được từ namespace enterprise của chaincode.

## Kiểm thử

Tests mặc định dùng SQLite cô lập, không thay đổi Neon:

```powershell
docker compose -f docker-compose.yml -f docker-compose.web-local.yml exec -T web python manage.py test contracts.tests.test_ledger contracts.tests.test_intelligence --settings=config.intelligence_test_settings --noinput
docker compose -f docker-compose.yml -f docker-compose.web-local.yml exec -T workflow-service python manage.py test workflow.test_signing_policy workflow.test_tenant_guard --settings=config.test_settings --noinput
docker compose -f docker-compose.yml -f docker-compose.web-local.yml exec -T fabric-chaincode go test ./...
```

Smoke test live là opt-in: tạo dữ liệu người/công ty/file giả trong SQLite và ghi một record mẫu vào Fabric, không tạo hoặc sửa hợp đồng/tài khoản trong Neon. Lần kiểm tra mới nhất đã xác nhận mất phản hồi sau commit và phục hồi đúng transaction cũ tại block 7.

```powershell
docker compose -f docker-compose.yml -f docker-compose.web-local.yml exec -T -e LEDGER_LIVE_SMOKE=1 web python manage.py test contracts.tests.test_ledger.LedgerTests.test_live_commit_and_lost_response_recovery --settings=config.intelligence_test_settings --noinput
```
