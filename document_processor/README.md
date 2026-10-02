# Document Processor

Module xử lý tài liệu hợp đồng lao động → dữ liệu có cấu trúc cho AI.

Pipeline hiện tại dùng kiến trúc PlanA kép: Rasterize → Surya Layout/Text và ColPali Visual → hai collection Qdrant → Split Clause/JSON. Không còn phụ thuộc PaddleOCR.

Hai collection giữ nguyên schema của PlanA:

- `denso_document_vectors`: BGE-M3 dense vector 1024 chiều cho layout/text blocks.
- `denso_colpali_visual_patches`: ColPali multi-vector 128 chiều, MaxSim, một point cho mỗi trang.

Sau khi Surya lưu dữ liệu trang, hai nhánh dense và ColPali được index song song. Với gateway trong `PlanAProject/kaggle_vllm_qwen_serving.ipynb`, cấu hình `VLLM_BASE_URL=<ngrok>/v1` và `COLPALI_BASE_URL=<ngrok>/colpali`. ColPali gọi `POST /embed_page` với header bypass ngrok; nếu endpoint không được cấu hình thì nhánh này được đánh dấu `SKIPPED` mà không làm mất kết quả Surya.

## Hỗ trợ định dạng

| Định dạng | Phương thức |
|---|---|
| `.docx` | python-docx (paragraph + table) |
| `.pdf` (có text) | PyMuPDF native text |
| `.pdf` | PyMuPDF render → PlanA/Surya layout theo từng trang |
| `.png` / `.jpg` / `.jpeg` | PlanA visual layout (không OCR text) |

## Cài đặt

```bash
cd document_processor
pip install -r requirements.txt
```

> Module **không cần Poppler** vì dùng PyMuPDF để rasterize PDF.
> Tài liệu scan/anh được giữ dưới dạng visual blocks; pipeline không tự nhận dạng ký tự bằng PaddleOCR.

## Sử dụng

### CLI

```bash
# Xử lý PDF
python main.py --input contract.pdf

# Xử lý PDF scan theo visual layout (không OCR)
python main.py --input scan.pdf

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

service = DocumentService()
output = service.process("contract.pdf")

print(f"Số trang: {output.document_info.page_count}")
print(f"Số điều khoản: {len(output.clauses)}")
print(f"Số trang: {output.document_info.page_count}")

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
├── vision/          # PlanA/Surya page-layout pipeline
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

- Hợp đồng 30–50 trang: phụ thuộc CPU/GPU và số layout blocks
- Tiết kiệm RAM: PDF scan render từng trang, không load toàn bộ ảnh
- Surya FastLayoutPredictor chỉ khởi tạo một lần (singleton)
