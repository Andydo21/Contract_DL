"""
Model đại diện cho một trang tài liệu sau khi extract / OCR.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# Nguồn gốc của text trên trang
SourceType = Literal["docx", "pdf", "ocr"]


@dataclass
class PageData:
    """Dữ liệu một trang tài liệu sau khi trích xuất.

    Attributes:
        page_number: Số thứ tự trang (bắt đầu từ 1).
        text: Nội dung văn bản đã trích xuất.
        source: Nguồn gốc — "docx", "pdf", hay "ocr".
        confidence: Độ tin cậy từ 0.0 đến 1.0.
            - PDF/DOCX native text: luôn là 1.0.
            - OCR: confidence trung bình từ PaddleOCR.
    """

    page_number: int
    text: str
    source: SourceType
    confidence: float = field(default=1.0)

    def __post_init__(self) -> None:
        # Clamp confidence về khoảng [0.0, 1.0]
        self.confidence = max(0.0, min(1.0, self.confidence))

    @property
    def is_empty(self) -> bool:
        """Trả về True nếu trang không có nội dung thực sự."""
        return not self.text.strip()

    @property
    def word_count(self) -> int:
        """Số từ ước tính của trang."""
        return len(self.text.split())
