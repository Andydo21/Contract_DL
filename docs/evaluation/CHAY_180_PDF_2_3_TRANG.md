# Chạy 180 PDF có 2–3 trang

- Tải tài liệu bổ sung từ arXiv và kiểm tra số trang trực tiếp trong PDF; chỉ giữ tài liệu có đúng 2 hoặc 3 trang.
- Khi đủ 180 tài liệu, tự khởi chạy luồng upload và trích xuất chính trong Docker, tuần tự; ColPali được hoãn lại.
- Kiểm tra lại mã SHA-256 và số trang trước khi xử lý từng PDF. Nếu không tìm đủ 180 tài liệu, không bắt đầu trích xuất.
- Danh sách nguồn và số trang: `NGUON_180_TAI_LIEU_2_3_TRANG.md`. Tiến độ tải: `corpus180_short_download.log`; tiến độ trích xuất: `corpus180_short_main_pipeline.json` và `corpus180_short_main_pipeline.log`.
