"""
BaseExtractor — Abstract base class cho tất cả extractor.

Áp dụng ISP (Interface Segregation) và DIP (Dependency Inversion):
DocumentService phụ thuộc vào BaseExtractor, không phụ thuộc
trực tiếp vào DocxExtractor hay PdfExtractor.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..models.page import PageData


class BaseExtractor(ABC):
    """Interface chung cho tất cả extractor.

    Mỗi extractor implement phương thức extract() và trả về
    danh sách PageData đã chuẩn hoá.
    """

    @abstractmethod
    def extract(self, file_path: str) -> List[PageData]:
        """Trích xuất văn bản từ file.

        Args:
            file_path: Đường dẫn tuyệt đối tới file.

        Returns:
            Danh sách PageData, mỗi phần tử là một trang.

        Raises:
            ExtractError: Nếu không thể đọc hoặc parse file.
        """

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Tên nguồn ("docx", "pdf", "image")."""
