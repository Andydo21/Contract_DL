# Document Processor

Module xử lý tài liệu hợp đồng lao động → dữ liệu có cấu trúc cho AI.

**Không dùng AI/LLM.** Chỉ: Extract → OCR → Normalize → Split Clause → JSON.

## Hỗ trợ định dạng

| Định dạng | Phương thức |
|---|---|
| `.docx` | python-docx (paragraph + table) |
| `.pdf` (có text) | PyMuPDF native text |
| `.pdf` (scan) | PyMuPDF render → PaddleOCR |
| `.png` / `.jpg` / `.jpeg` | PaddleOCR trực tiếp |

## Cài đặt

```bash
cd document_processor
pip install -r requirements.txt
```

> **Lưu ý PaddleOCR trên Windows:**
> PaddleOCR cần `paddlepaddle` CPU. Nếu cài thất bại, thử:
> ```bash
> pip install paddlepaddle -i https://pypi.tuna.tsinghua.edu.cn/simple
> pip install paddleocr
> ```
> Module **không cần Poppler** vì dùng PyMuPDF để render PDF scan → ảnh.

## Sử dụng

### CLI

```bash
# Xử lý PDF
python main.py --input contract.pdf

# Xử lý PDF scan với OCR tiếng Việt
python main.py --input scan.pdf --ocr-lang vi

# Xử lý DOCX, lưu vào thư mục tùy chỉnh
python main.py --input contract.docx --output ./results

# Xử lý ảnh
python main.py --input photo.jpg

# Bật log chi tiết
python main.py --input contract.pdf --verbose
```

Kết quả được lưu vào: `output/<tên_file>_processed.json`

### Python API

```python
from document_processor.services import DocumentService

service = DocumentService(ocr_lang="vi")
output = service.process("contract.pdf")

print(f"Số trang: {output.document_info.page_count}")
print(f"Số điều khoản: {len(output.clauses)}")
print(f"Dùng OCR: {output.document_info.ocr_used}")

# Lưu JSON
with open("result.json", "w", encoding="utf-8") as f:
    f.write(output.to_json())
```

## Cấu trúc output JSON

```json
{
  "document_info": {
    "file_name": "contract.pdf",
    "file_path": "C:/path/to/contract.pdf",
    "file_type": "pdf",
    "page_count": 12,
    "ocr_used": false,
    "language": "vi",
    "avg_confidence": 1.0
  },
  "pages": [
    {
      "page_number": 1,
      "text": "CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM...",
      "source": "pdf",
      "confidence": 1.0
    }
  ],
  "clauses": [
    {
      "id": 1,
      "title": "Điều 1. Thông tin các bên",
      "content": "Bên A: Công ty ABC...",
      "start_page": 1,
      "end_page": 2
    }
  ],
  "warnings": []
}
```

## Kiến trúc (Clean Architecture)

```
document_processor/
├── models/          # Data models (PageData, ClauseData, DocumentOutput)
├── exceptions/      # Custom exceptions phân cấp
├── utils/           # Logger, file utilities
├── loaders/         # FileLoader — validate & nhận diện file
├── extractors/      # DOCXExtractor, PDFExtractor (BaseExtractor ABC)
├── ocr/             # OCREngine (PaddleOCR, lazy load)
├── preprocess/      # TextNormalizer — pipeline chuẩn hoá
├── splitter/        # ClauseSplitter — tách điều khoản đa trang
├── services/        # DocumentService — orchestrator
└── main.py          # CLI entry point
```

## Nhận diện điều khoản

Hỗ trợ các pattern:

| Tiếng Việt | Tiếng Anh |
|---|---|
| Điều 1, Điều 2... | Article 1, Article II... |
| ĐIỀU 1, Điều I | Section 1, SECTION 2 |
| điều 10. | Clause 1, CLAUSE II |

## Performance

- Hợp đồng 30–50 trang: < 30s (PDF text) / 2–5 phút (PDF scan có OCR)
- Tiết kiệm RAM: PDF scan render từng trang, không load toàn bộ ảnh
- PaddleOCR chỉ khởi tạo một lần (singleton)
