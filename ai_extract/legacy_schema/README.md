# Schema tương thích của database A3 cũ

Không chứa pipeline hoặc API xử lý AI. Web chính chỉ dùng app `ai_extract` và dữ liệu theo `ContractVersion`.

Model và toàn bộ migration giữ nguyên nội dung. AppConfig dùng namespace `ai_extract.legacy_schema`, app label vẫn là `documents`; bảng vẫn là `documents_file`. SQLite, media và Qdrant cũ không bị đổi hoặc xóa.

Entry point `ai_extract/a3/manage.py` được giữ cho quản trị database lịch sử. Root URL chuyển người dùng sang web hợp đồng; các API tài liệu độc lập đã bỏ.

Từ thư mục `ai_extract/a3`, kiểm tra schema mà không áp dụng migration:

```powershell
..\..\.venv\Scripts\python.exe manage.py makemigrations documents --check --dry-run
..\..\.venv\Scripts\python.exe manage.py test ai_extract.legacy_schema.tests --noinput
```
