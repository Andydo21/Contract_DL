"""
Custom exceptions cho document_processor.

Tất cả exception đều kế thừa DocumentProcessorError để
caller có thể bắt chung một lớp nếu cần.
"""


class DocumentProcessorError(Exception):
    """Base exception cho toàn bộ module document_processor."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail

    def __str__(self) -> str:
        base = super().__str__()
        return f"{base} | Detail: {self.detail}" if self.detail else base


# ---------------------------------------------------------------------------
# File-level exceptions
# ---------------------------------------------------------------------------

class FileNotFoundError(DocumentProcessorError):
    """File đầu vào không tồn tại hoặc không đọc được."""


class UnsupportedFileTypeError(DocumentProcessorError):
    """Định dạng file không được hỗ trợ.

    Ví dụ: .xlsx, .pptx, .zip, v.v.
    """


# ---------------------------------------------------------------------------
# Extraction exceptions
# ---------------------------------------------------------------------------

class ExtractError(DocumentProcessorError):
    """Lỗi khi trích xuất văn bản từ DOCX hoặc PDF.

    Có thể do file bị lỗi, mã hoá, hoặc thư viện không xử lý được.
    """


# ---------------------------------------------------------------------------
# OCR exceptions
# ---------------------------------------------------------------------------

class OCRError(DocumentProcessorError):
    """Lỗi trong quá trình OCR.

    Ví dụ: PaddleOCR không khởi tạo được, ảnh không hợp lệ.
    """


# ---------------------------------------------------------------------------
# Processing exceptions
# ---------------------------------------------------------------------------

class NormalizationError(DocumentProcessorError):
    """Lỗi khi chuẩn hoá văn bản."""


class SplitterError(DocumentProcessorError):
    """Lỗi khi tách điều khoản."""


class ValidationError(DocumentProcessorError):
    """Lỗi khi validate tài liệu (không dừng chương trình, chỉ log)."""
