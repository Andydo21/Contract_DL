# Test case chức năng – Contract Guard AI

Lần chạy: 2026-11-14 10:21 trên hệ thống thật (web, AI, GPU runtime, workflow, blockchain, Fabric). Sinh tự động bởi `scratch/system_test_cases.py`.

**Kết quả: 91 đạt, 0 lỗi, 1 chưa chạy được (BLOCKED) trên tổng 92 test case.**

Phân tích rủi ro chưa được chạy trong đợt này. Các case cần Qwen (Kaggle) được ghi BLOCKED khi Qwen tắt.

| Nhóm chức năng | Đạt | Lỗi | BLOCKED |
|---|---|---|---|
| Quản trị | 5 | 0 | 0 |
| Trích xuất AI | 8 | 0 | 0 |
| Danh mục & lịch sử phân tích | 2 | 0 | 1 |
| Phân tích rủi ro | 3 | 0 | 0 |
| Tài khoản | 7 | 0 | 0 |
| Hợp đồng | 17 | 0 | 0 |
| Doanh nghiệp & nhân sự | 11 | 0 | 0 |
| Kho tri thức | 4 | 0 | 0 |
| Ký số & kiểm chứng | 11 | 0 | 0 |
| Giao diện | 8 | 0 | 0 |
| Quy trình phê duyệt | 15 | 0 | 0 |

## Quản trị

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-AD-01 | Xem thống kê và tình trạng dịch vụ | GET /api/admin/stats/ | HTTP 200; Fabric, Blockchain, Workflow, AI đều ONLINE | {'Fabric Gateway': 'ONLINE', 'Blockchain Service (ledger book)': 'ONLINE', 'Workflow Service': 'ONLINE', 'AI Service': 'ONLINE'} | PASS |
| TC-AD-02 | Nhân sự thường không vào được quản trị | Nhân sự LEGAL gọi /api/admin/stats/ | HTTP 403 hoặc chuyển hướng | HTTP 403 | PASS |
| TC-AD-03 | Bật/tắt bỏ qua OCR | Đổi cấu hình SKIP_OCR rồi trả lại như cũ | Cả hai lệnh HTTP 200, giá trị đổi đúng | True -> False -> True | PASS |
| TC-AD-04 | Xem danh sách khoá mã hoá | GET /api/admin/keys/ | HTTP 200 | HTTP 200 {"keys": []} | PASS |
| TC-AD-05 | Xoá tài khoản người dùng | Quản trị viên xoá một tài khoản | HTTP 200, tài khoản không còn | HTTP 200 {"status": "success", "deleted_id": 1000120} | PASS |

## Trích xuất AI

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-AI-01 | Tải lên hợp đồng thật kích hoạt trích xuất | Tải hop_dong_thue_van_phong.pdf | Tạo hợp đồng; trích xuất tự động được xếp hàng | HTTP 200 {"success": true, "contract_id": 1000301, "contract_code": "E2E-AI-58bbce", "status": "DRAFT", "extraction_job_id": "a01742232148406ba1ba368 | PASS |
| TC-AI-02 | Trích xuất bố cục hoàn tất | Theo dõi /api/ai/contracts/{id}/extraction-status/ | Trạng thái COMPLETED | COMPLETED sau 1.2 phút, 1 trang  | PASS |
| TC-AI-03 | Tách điều khoản | GET /api/ai/contracts/{id}/clauses/ | Có ≥ 3 điều khoản | 7 điều khoản | PASS |
| TC-AI-04 | Nhận diện thực thể | GET /api/ai/contracts/{id}/entities/ | HTTP 200, có thực thể (tên bên, số tiền...) | 7 thực thể | PASS |
| TC-AI-05 | Mở trang nguồn của trích dẫn | Mở /ai-extract/contracts/{id}/pages/1/ | HTTP 200, hiển thị ảnh trang và khối bố cục | HTTP 200 | PASS |
| TC-AI-06 | Xem các đoạn nguồn của phiên bản | GET /api/newidea/versions/{version}/sources/ | HTTP 200, có đoạn nguồn | 16 đoạn | PASS |
| TC-AI-07 | Tìm trong nội dung hợp đồng | POST /api/newidea/contracts/{id}/search/ "tiền thuê" | HTTP 200, trả về đoạn có nói về tiền thuê | 6 đoạn khớp | PASS |
| TC-AI-08 | Tóm tắt hợp đồng | POST /api/ai/contracts/{id}/summarize/ | HTTP 200, có tóm tắt | HTTP 200 {"version_id": 1000321, "contract_id": 1000301, "summary": "**T\u00f3m t\u1eaft  | PASS |

## Danh mục & lịch sử phân tích

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-AN-01 | Xem danh mục rủi ro | GET /api/risks/ | HTTP 200, có các luật rủi ro (risk_code) | HTTP 200 [{"id": 1000010, "risk_name": "Kh\u00f4ng \u0111\u00fang h\u00ecnh th\u1ee9c b\u | PASS |
| TC-AN-02 | Xem lịch sử phân tích | GET /api/analyses/ | HTTP 200, danh sách (có thể rỗng) | HTTP 200 [] | PASS |
| TC-AN-03 | Chạy phân tích rủi ro | POST /api/contracts/{id}/analyze/ | Có kết quả rủi ro | chưa chạy theo yêu cầu (để sau khi train) | BLOCKED |

## Phân tích rủi ro

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-AN-03 | Chạy phân tích rủi ro | Bấm "Phân tích rủi ro hợp đồng" (POST /api/contracts/{id}/analyze/), chờ job nền | Job hoàn tất, lưu kết quả phân tích có điểm và mức rủi ro | job complete sau 3.3 phút; điểm 100.00, mức HIGH | PASS |
| TC-AN-04 | Phát hiện rủi ro đã cài (lãi suất vượt trần) | Đọc các rủi ro của hợp đồng vay có lãi 5%/tháng | Có rủi ro về lãi suất, căn cứ Điều 468 Bộ luật Dân sự | 17 rủi ro (10 xung đột luật); Lãi suất vượt mức tối đa: Lãi suất 5%/tháng (tương đương 60%/năm) vượt quá mức lãi suất tối đa 20%/năm được quy định tại Điều 468 khoản 1 của Bộ luật  | PASS |
| TC-AN-05 | Chuyên gia nhận xét kết quả phân tích | Gửi nhận xét và kết luận mức rủi ro HIGH | HTTP 200, lưu nhận xét | HTTP 200 {"success": true, "review_id": 1000001, "status": "ANALYZED"} | PASS |

## Tài khoản

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-AUTH-01 | Đăng nhập API đúng mật khẩu | POST /api/token/ với tài khoản hợp lệ | HTTP 200, trả về access token | token cấp thành công | PASS |
| TC-AUTH-02 | Đăng nhập sai mật khẩu bị từ chối | POST /api/token/ với mật khẩu sai | HTTP 401, không cấp token | HTTP 401 {"error": "Invalid credentials."} | PASS |
| TC-AUTH-03 | Đăng nhập trên giao diện web | Mở /login/, nhập tài khoản và mật khẩu, bấm Đăng nhập | Chuyển hướng (302) sang trang chính, tạo phiên đăng nhập | HTTP 302 -> / | PASS |
| TC-AUTH-04 | Chặn truy cập trang khi chưa đăng nhập | Mở / khi chưa đăng nhập | Chuyển hướng về /login/ | HTTP 302 -> /login/?next=/ | PASS |
| TC-AUTH-05 | Chặn gọi API khi không có token | GET /api/contracts/ không gửi token | HTTP 401 hoặc 403 | HTTP 401 | PASS |
| TC-AUTH-06 | Đăng xuất | Đăng nhập web, mở /logout/, rồi mở lại / | Phiên bị huỷ, / chuyển hướng về /login/ | HTTP 302 -> /login/?next=/ | PASS |
| TC-AUTH-07 | Mở trang đăng ký tài khoản | GET /signup/ | HTTP 200, hiển thị biểu mẫu đăng ký | HTTP 200 | PASS |

## Hợp đồng

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-CT-01 | Tải lên hợp đồng | Quản lý tải tệp PDF kèm mã, tên, loại, giá trị | HTTP 200/201, tạo hợp đồng và phiên bản 1 | HTTP 200 {"success": true, "contract_id": 1000300, "contract_code": "E2E-58bbce", "status": "DRAFT", "extraction_job_id": "4f3f2da0579f4315927159d8f7 | PASS |
| TC-CT-02 | Từ chối tải lên khi thiếu tệp | Gửi biểu mẫu tải lên không kèm tệp | HTTP 400 | HTTP 400 {"error": "C\u1ea7n t\u1ea3i t\u1ec7p h\u1ee3p \u0111\u1ed3ng ho\u1eb7c d\u00e1n n\u1ed9i dung h\u1ee3p \u0111\u1ed3ng."} | PASS |
| TC-CT-03 | Xem danh sách hợp đồng | GET /api/contracts/ | HTTP 200, có hợp đồng vừa tải lên | HTTP 200 [{"id": 1000300, "contract_code": "E2E-58bbce", "title": "H\u1ee3p \u0111\u1ed3n | PASS |
| TC-CT-04 | Xem chi tiết hợp đồng | GET /api/contracts/{id}/ | HTTP 200, đúng mã và tên | HTTP 200 {"id": 1000300, "contract_code": "E2E-58bbce", "title": "H\u1ee3p \u0111\u1ed3ng | PASS |
| TC-CT-05 | Tạo phiên bản mới | Tải tệp mới kèm mô tả thay đổi | HTTP 200/201, tạo phiên bản 2 | HTTP 200 {"success": true, "version_id": 1000320, "version_number": 2, "change_summary": "E2E phi\u00ean b\u1ea3n 2", "extraction_job_id": "c2bc03aa9 | PASS |
| TC-CT-06 | Xem lịch sử phiên bản | GET /api/contracts/{id}/versions/ | Có phiên bản 1 và 2 | [2, 1] | PASS |
| TC-CT-07 | Cập nhật các bên của hợp đồng | Lưu Bên A và Bên B (tên, MST, email, điện thoại) | HTTP 200/201 | HTTP 200 {"success": true, "parties": [{"party_name": "C\u00f4ng ty A", "party_type": "B\u00ean A", "tax_code": "0101", "email": "a@example.test", "p | PASS |
| TC-CT-08 | Đọc lại các bên đã lưu | GET /api/contracts/{id}/parties/ | Có Công ty A và Công ty B | HTTP 200 {"parties": [{"party_name": "C\u00f4ng ty A", "party_type": "B\u00ean A", "tax_c | PASS |
| TC-CT-09 | Gắn tag cho hợp đồng | Chọn một tag và lưu | HTTP 200, tag được đánh dấu chọn | [1000000] | PASS |
| TC-CT-10 | Từ chối dữ liệu tag sai kiểu | Gửi tag_ids không phải danh sách số | HTTP 400 | HTTP 400 {"error": "tag_ids ph\u1ea3i l\u00e0 danh s\u00e1ch s\u1ed1."} | PASS |
| TC-CT-11 | Xem thông tin văn bản pháp luật | GET /api/contracts/{id}/legal/ | HTTP 200, có danh sách tình trạng hiệu lực | HTTP 200 {"legal": null, "statuses": ["C\u00f2n hi\u1ec7u l\u1ef1c", "H\u1ebft hi\u1ec7u  | PASS |
| TC-CT-12 | Từ chối tình trạng hiệu lực không hợp lệ | Đánh dấu văn bản pháp luật với tình trạng sai | HTTP 400 | HTTP 400 {"error": "T\u00ecnh tr\u1ea1ng ph\u1ea3i l\u00e0 m\u1ed9t trong: C\u00f2n hi\u1ec7u l\u1ef1c, H\u1ebft hi\u1ec7u l\u1ef1c m\u1ed9t ph\u1ea7 | PASS |
| TC-CT-13 | Chỉ quản lý được đánh dấu văn bản pháp luật | Nhân sự LEGAL gửi yêu cầu đánh dấu | HTTP 403 | HTTP 403 {"error": "Ch\u1ec9 qu\u1ea3n l\u00fd \u0111\u01b0\u1ee3c \u0111\u00e1nh d\u1ea5u v\u0103n b\u1ea3n ph\u00e1p lu\u1eadt."} | PASS |
| TC-CT-14 | Tải về tệp PDF của hợp đồng | GET /api/contracts/{id}/download-pdf/ | HTTP 200, nội dung là PDF | HTTP 200 application/pdf | PASS |
| TC-CT-15 | Cách ly dữ liệu giữa các doanh nghiệp | Người của doanh nghiệp khác mở hợp đồng | HTTP 403 hoặc 404, không lộ dữ liệu | HTTP 403 {"error": "Permission Denied: You do not have access to this contract."} | PASS |
| TC-CT-16 | Doanh nghiệp khác không xoá được hợp đồng | Người của doanh nghiệp khác gửi lệnh xoá | HTTP 403 hoặc 404, hợp đồng vẫn còn | HTTP 403 {"error": "Permission Denied: You do not have access to this contract."} | PASS |
| TC-CT-17 | Xoá hợp đồng | Quản lý xoá hợp đồng (kèm tệp, chỉ mục, phiên bản) | HTTP 200, hợp đồng không còn trong CSDL | HTTP 200 {"success": true, "contract_id": 1000300, "removed_files": 4, "index": {"graph": | PASS |

## Doanh nghiệp & nhân sự

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-ID-01 | Đăng ký doanh nghiệp mới | POST /api/identity/companies/register/ với tên và MST mới | HTTP 200, doanh nghiệp ở trạng thái hoạt động | HTTP 200 {"status": "success", "company_id": 1000072, "company_name": "E2E New 58bbce", "tax_code": "E2N58bbce", "tx_hash": null, "block_number": nul | PASS |
| TC-ID-02 | Từ chối đăng ký trùng mã số thuế | Đăng ký lại doanh nghiệp với MST đã có | HTTP 400, báo doanh nghiệp đã tồn tại | HTTP 400 {"error": "C\u00f4ng ty \"E2E New 58bbce\" (MST: E2N58bbce) \u0111\u00e3 t\u1ed3n t\u1ea1i trong h\u1ec7 th\u1ed1ng."} | PASS |
| TC-ID-03 | Từ chối đăng ký thiếu thông tin | Đăng ký doanh nghiệp không có tên và MST | HTTP 400 | HTTP 400 {"error": "Thi\u1ebfu t\u00ean c\u00f4ng ty ho\u1eb7c m\u00e3 s\u1ed1 thu\u1ebf"} | PASS |
| TC-ID-04 | Xem danh sách doanh nghiệp | GET /api/identity/companies/ | HTTP 200, có doanh nghiệp vừa đăng ký | HTTP 200 [{"id": 1000072, "company_name": "E2E New 58bbce", "tax_code": "E2N58bbce", "sta | PASS |
| TC-ID-05 | Xem danh sách vai trò | GET /api/identity/roles/ | HTTP 200, có MANAGER, LEGAL, ADMIN | HTTP 200 [{"id": 1, "role_name": "ADMIN"}, {"id": 9, "role_name": "COMPLIANCE"}, {"id": 1 | PASS |
| TC-ID-06 | Đăng ký nhân sự | Quản trị viên tạo tài khoản LEGAL cho doanh nghiệp | HTTP 200/201, tài khoản ACTIVE | HTTP 200 {"status": "success", "user_id": 1000119, "username": "e2e_staff_58bbce", "email": "e2e_staff_58bbce@example.test", "company_name": "E2E Tes | PASS |
| TC-ID-07 | Nhân sự mới đăng nhập được | POST /api/token/ bằng tài khoản vừa tạo | Cấp token | token cấp thành công | PASS |
| TC-ID-08 | Xem danh sách nhân sự | GET /api/identity/users/ | HTTP 200, có nhân sự vừa tạo | HTTP 200 [{"id": 1000119, "username": "e2e_staff_58bbce", "email": "e2e_staff_58bbce@exam | PASS |
| TC-ID-09 | Chặn xem nhân sự và doanh nghiệp khi chưa đăng nhập | GET /api/identity/users/ và /api/identity/companies/ không có token | HTTP 401, không lộ danh sách | [401, 401] | PASS |
| TC-ID-10 | Danh sách nhân sự chỉ gồm doanh nghiệp của mình | Quản lý của doanh nghiệp khác xem danh sách nhân sự | Không thấy nhân sự của doanh nghiệp này | HTTP 200 [{"id": 1000118, "username": "e2e_out_58bbce", "email": "e2e | PASS |
| TC-ID-11 | Chặn tạo tài khoản cho doanh nghiệp khác | Quản lý doanh nghiệp B tạo tài khoản ADMIN cho doanh nghiệp A | HTTP 403, không tạo tài khoản | HTTP 403 {"error": "Ch\u1ec9 \u0111\u01b0\u1ee3c \u0111\u0103ng k\u00fd nh\u00e2n s\u1ef1 cho doanh nghi\u1ec7p c\u1ee7a m\u00ecnh."} | PASS |

## Kho tri thức

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-KB-01 | Tìm điều luật theo câu hỏi | Quản trị viên hệ thống: POST /api/newidea/search/ "lãi suất vay tối đa" (không sinh) | HTTP 200, 3 kết quả đầu có Điều 468 Bộ luật Dân sự | 14 kết quả | PASS |
| TC-KB-02 | Từ chối câu hỏi rỗng | POST /api/newidea/search/ với query rỗng | HTTP 400 | HTTP 400 {"success": false, "error": "C\u00e2u h\u1ecfi c\u1ea7n t\u1eeb 1 \u0111\u1ebfn 2000 k\u00fd t\u1ef1."} | PASS |
| TC-KB-03 | Hỏi đáp có sinh câu trả lời | POST /api/newidea/search/ generate=true | HTTP 200, có câu trả lời kèm trích dẫn | HTTP 200 {"success": true, "results": [{"document_id": "contract-version-1000320", "contract_id": 1000300, "v | PASS |
| TC-KB-04 | Kho luật chia theo doanh nghiệp | Quản lý của một doanh nghiệp chưa có tài liệu nào tìm cùng câu hỏi | HTTP 200, 0 kết quả: không thấy văn bản của doanh nghiệp khác | 0 kết quả | PASS |

## Ký số & kiểm chứng

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-LG-01 | Đăng ký khoá công khai RSA-3072 | Người ký gửi public key PEM | HTTP 200/201, khoá ở trạng thái PENDING | HTTP 201 {"id": 1000017, "status": "PENDING", "fingerprint": "44b15ad622aec1246a46fc23cb8b8cccbcc5c31cd8bda1cc6104ca655c0410ed"} | PASS |
| TC-LG-02 | Chủ khoá không tự duyệt khoá của mình | Người ký tự duyệt khoá | HTTP 403 | HTTP 403 {"error": "Ng\u01b0\u1eddi qu\u1ea3n l\u00fd kh\u00e1c ph\u1ea3i duy\u1ec7t kh\u00f3a."} | PASS |
| TC-LG-03 | Quản lý khác duyệt khoá | Quản trị viên duyệt khoá | HTTP 200, khoá ACTIVE | HTTP 200 {"id": 1000017, "status": "ACTIVE"} | PASS |
| TC-LG-04 | Người ký thấy bước cần ký | GET /api/ledger/workflow-steps/ | Có ít nhất 1 bước ký | [None] | PASS |
| TC-LG-05 | Chuẩn bị yêu cầu ký (manifest) | Tạo thao tác SIGN cho phiên bản và bước ký | HTTP 200/201, trả về manifest cần ký | HTTP 201 {"id": "0cef9277-0e15-4f3c-9051-51d82fd0ec00", "kind": "SIGN", "state": "PENDING", "version_id": 1000320, "actor": "e2e_mgr_58bbce", "manife | PASS |
| TC-LG-06 | Từ chối chữ ký sai | Gửi chữ ký không hợp lệ | HTTP ≥ 400 | HTTP 400 {"error": "Ch\u1eef k\u00fd kh\u00f4ng h\u1ee3p l\u1ec7 ho\u1eb7c kh\u00f4ng thu\u1ed9c phi\u00ean b\u1ea3n n\u00e0y."} | PASS |
| TC-LG-07 | Gửi chữ ký hợp lệ | Ký manifest bằng khoá riêng và gửi | HTTP 200, accepted | HTTP 200 {"id": "0cef9277-0e15-4f3c-9051-51d82fd0ec00", "kind": "SIGN", "state": "PENDING", "version_id": 1000320, "actor": "e2e_mgr_58bbce", "manife | PASS |
| TC-LG-08 | Fabric xác nhận giao dịch ký | Chờ ledger-worker gửi lên Fabric | Trạng thái CONFIRMED, có tx_id và số khối | CONFIRMED block=29 err= | PASS |
| TC-LG-09 | Bước ký đồng bộ về quy trình | Đọc trạng thái quy trình | Bước ký APPROVED | True | PASS |
| TC-LG-10 | Kiểm chứng tệp gốc | Tải lên đúng tệp đã ký để kiểm chứng | Toàn vẹn tệp, khớp bản đã ký, chữ ký hợp lệ, Fabric xác nhận | {'file_integrity': True, 'uploaded_file_matches': True, 'signature_valid': True, 'ledger_verified': True} | PASS |
| TC-LG-11 | Phát hiện tệp bị sửa | Tải lên tệp đã bị sửa để kiểm chứng | uploaded_file_matches = false | False | PASS |

## Giao diện

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-UI-01 | Mở trang Danh sách hợp đồng | Đăng nhập web, mở / | HTTP 200, có thanh điều hướng chung | HTTP 200 | PASS |
| TC-UI-02 | Mở trang Chi tiết hợp đồng | Đăng nhập web, mở /contracts/1000300/ | HTTP 200, có thanh điều hướng chung | HTTP 200 | PASS |
| TC-UI-03 | Mở trang Lịch sử phân tích | Đăng nhập web, mở /analyses/ | HTTP 200, có thanh điều hướng chung | HTTP 200 | PASS |
| TC-UI-04 | Mở trang Quy trình phê duyệt | Đăng nhập web, mở /board/ | HTTP 200, có thanh điều hướng chung | HTTP 200 | PASS |
| TC-UI-05 | Mở trang Ký & kiểm chứng | Đăng nhập web, mở /contract-ledger/ | HTTP 200, có thanh điều hướng chung | HTTP 200 | PASS |
| TC-UI-06 | Mở trang Doanh nghiệp & nhân sự | Đăng nhập web, mở /identity/ | HTTP 200, có thanh điều hướng chung | HTTP 200 | PASS |
| TC-UI-07 | Mở trang Quản trị hệ thống | Đăng nhập web, mở /admin-dashboard/ | HTTP 200, có thanh điều hướng chung | HTTP 200 | PASS |
| TC-UI-08 | Ẩn và chặn trang quản trị với nhân sự thường | Nhân sự LEGAL mở /admin-dashboard/ | Không vào được (403 hoặc chuyển hướng) | HTTP 403 | PASS |

## Quy trình phê duyệt

| Mã | Chức năng | Các bước | Kết quả mong đợi | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|---|
| TC-WF-01 | Đẩy hợp đồng vào quy trình duyệt | POST /api/contracts/{id}/workflow/ với phiên bản 2 | HTTP 200/201, tạo quy trình | HTTP 200 {"success": true, "contract_id": 1000300, "workflow_id": 24, "workflow_name": "Approval Workflow \u2013 H\u1ee3p \u0111\u1ed3ng ki\u1ec3m th | PASS |
| TC-WF-02 | Xem trạng thái quy trình | GET /api/contracts/{id}/workflow/status/ | Có ≥2 bước, step_order liền mạch từ 1 | ['Rà soát & Tiếp nhận Dự thảo Hợp đồng', 'Phê duyệt Chủ trương Cấp Quản lý', 'Thực hiện Ký kết Hợp đồng Chính thức', 'Bàn giao & Lưu trữ Kho Hồ sơ Hợp đồng'] | PASS |
| TC-WF-03 | Thêm bước duyệt vào vị trí 2 | Chèn bước mới ở vị trí 2 | HTTP 200/201 | HTTP 201 {"success": true, "step": {"id": 112, "step_order": 2, "step_name": "E2E Review 58bbce", "role_id": 1000000, "status": "PENDING", "completed | PASS |
| TC-WF-04 | Các bước sau tự dời thứ tự | Đọc lại danh sách bước | Bước mới ở vị trí 2, các bước sau +1 | [1, 2, 3, 4, 5] | PASS |
| TC-WF-05 | Sửa vai trò duyệt của bước | Đổi vai trò của bước vừa thêm sang ADMIN | HTTP 200 | HTTP 200 {"success": true, "step_id": 112, "role_id": 1} | PASS |
| TC-WF-06 | Xoá bước duyệt | Xoá bước vừa thêm | HTTP 200 | HTTP 200 {"success": true} | PASS |
| TC-WF-07 | Sau khi xoá, thứ tự bước liền mạch | Đọc lại danh sách bước | step_order = 1..n | [1, 2, 3, 4] | PASS |
| TC-WF-08 | Không cho xoá bước bắt buộc ký | Xoá bước "Ký kết" | HTTP 400 | HTTP 400 {"error": "Mandatory signing steps cannot be deleted"} | PASS |
| TC-WF-09 | Nối thứ tự bước (A xong trước B) | Thêm phụ thuộc A → B | HTTP 200/201 | HTTP 201 {"success": true, "dependency": {"id": 17, "prerequisite_step_id": 108, "prerequisite_step_name": "Rà soát & Tiếp nhận Dự thảo Hợp đồng", "d | PASS |
| TC-WF-10 | Chặn nối ngược tạo vòng | Thêm phụ thuộc B → A | HTTP 400 | HTTP 400 {"error": "Không thể tạo đường nối vòng lặp phụ thuộc giữa các bước."} | PASS |
| TC-WF-11 | Chặn nối bước với chính nó | Thêm phụ thuộc A → A | HTTP 400 | HTTP 400 {"error": "Một bước không thể nối phụ thuộc tới chính nó."} | PASS |
| TC-WF-12 | Chặn duyệt sai thứ tự | Duyệt B khi A chưa xong | HTTP 400 | HTTP 400 {"error": "Không thể ký/duyệt bước 'Phê duyệt Chủ trương Cấp Quản lý' vì đang bị khóa bởi đường nối phụ thuộc: Bước 'Rà soát & Tiếp nhận Dự  | PASS |
| TC-WF-13 | Bỏ nối thứ tự bước | Xoá phụ thuộc A → B | HTTP 200 | HTTP 200 {"success": true} | PASS |
| TC-WF-14 | Duyệt bước | Duyệt B sau khi bỏ nối | HTTP 200, bước APPROVED | HTTP 200 {"success": true, "step_id": 109, "step_status": "APPROVED", "workflow_status": "IN_PROGRESS", "version_id": 1000320} | PASS |
| TC-WF-15 | Duyệt toàn bộ các bước trước bước ký | Duyệt lần lượt các bước còn lại | Mọi lệnh HTTP 200 | [200, 200] | PASS |
