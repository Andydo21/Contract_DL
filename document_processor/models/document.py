"""
Output schema chính của module document_processor.

Sử dụng Pydantic để đảm bảo serialisation/deserialisation JSON đúng chuẩn.
Không sinh JSON bằng cách nối chuỗi thủ công.
"""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models (nested trong DocumentOutput)
# ---------------------------------------------------------------------------

class PageModel(BaseModel):
    """Pydantic version của PageData để serialize JSON."""

    page_number: int = Field(..., ge=1, description="Số trang (bắt đầu từ 1)")
    text: str = Field(..., description="Nội dung văn bản của trang")
    source: Literal["docx", "pdf", "ocr", "txt", "native"] = Field(
        ..., description="Nguồn gốc trích xuất"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Độ tin cậy OCR (1.0 nếu native)"
    )

    class Config:
        json_encoders = {}


class ClauseModel(BaseModel):
    """Pydantic version của ClauseData để serialize JSON."""

    id: int = Field(..., ge=1, description="Số thứ tự điều khoản")
    title: str = Field(..., description="Tiêu đề điều khoản")
    content: str = Field(..., description="Nội dung đầy đủ điều khoản")
    start_page: int = Field(..., ge=1, description="Trang bắt đầu")
    end_page: int = Field(..., ge=1, description="Trang kết thúc")


class DocumentInfo(BaseModel):
    """Thông tin meta của tài liệu."""

    file_name: str = Field(..., description="Tên file gốc")
    file_path: str = Field(..., description="Đường dẫn tuyệt đối")
    file_type: str = Field(..., description="Loại file: docx, pdf, image")
    page_count: int = Field(..., ge=0, description="Tổng số trang")
    ocr_used: bool = Field(default=False, description="Có dùng OCR không")
    language: str = Field(default="vi", description="Ngôn ngữ phát hiện được")
    avg_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence trung bình toàn tài liệu (chỉ có nghĩa khi OCR)",
    )


# ---------------------------------------------------------------------------
# Root output object
# ---------------------------------------------------------------------------

class DocumentOutput(BaseModel):
    """Output chính của DocumentService.

    Đây là object duy nhất được trả về và serialize thành JSON.
    """

    document_info: DocumentInfo
    pages: List[PageModel] = Field(default_factory=list)
    clauses: List[ClauseModel] = Field(default_factory=list)
    warnings: List[str] = Field(
        default_factory=list,
        description="Cảnh báo phát sinh khi validate (không dừng chương trình)",
    )

    def to_json(self, indent: int = 2) -> str:
        """Serialize toàn bộ output ra JSON string đúng chuẩn.

        Args:
            indent: Số space indent, mặc định 2.

        Returns:
            JSON string chuẩn UTF-8.
        """
        return self.model_dump_json(indent=indent)

    def to_dict(self) -> dict:
        """Trả về dict Python thuần tuý."""
        return self.model_dump()
