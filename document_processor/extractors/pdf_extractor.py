"""
PDFExtractor — Trích xuất văn bản từ file PDF.

Sử dụng PyMuPDF (fitz).

Logic xác định trang cần OCR:
  - Nếu số ký tự có ý nghĩa (loại trừ khoảng trắng) < MIN_CHARS_PER_PAGE
    → trang đó được đánh dấu needs_ocr=True.
  - Nếu > 50% số trang cần OCR → toàn file là PDF scan.

Extractor này KHÔNG tự gọi OCR để giữ SRP.
DocumentService sẽ quyết định có gọi OCREngine hay không.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import fitz  # PyMuPDF

from ..exceptions.errors import ExtractError
from ..models.page import PageData
from ..utils.logger import get_logger
from .base import BaseExtractor

logger = get_logger(__name__)

# Ngưỡng: trang có ít hơn ngưỡng này ký tự có nghĩa → cần OCR
_MIN_CHARS_PER_PAGE = 50

# Ngưỡng: nếu tỉ lệ trang cần OCR vượt qua → đây là PDF scan
_SCAN_RATIO_THRESHOLD = 0.5


@dataclass
class PdfExtractionResult:
    """Kết quả extract PDF, phân biệt trang text và trang scan.

    Attributes:
        pages: Danh sách PageData từ trang có text.
        scan_page_numbers: Số thứ tự các trang cần OCR (1-indexed).
        is_scan: True nếu phần lớn tài liệu là scan.
        total_pages: Tổng số trang trong file.
    """

    pages: List[PageData] = field(default_factory=list)
    scan_page_numbers: List[int] = field(default_factory=list)
    is_scan: bool = False
    total_pages: int = 0


class PdfExtractor(BaseExtractor):
    """Extractor cho file .pdf.

    Trả về PdfExtractionResult thay vì List[PageData] để mang thêm
    thông tin về trang scan cho DocumentService.

    Usage:
        extractor = PdfExtractor()
        result = extractor.extract_pdf("contract.pdf")
    """

    @property
    def source_type(self) -> str:
        return "pdf"

    def extract(self, file_path: str) -> List[PageData]:
        """Implement BaseExtractor.extract() — chỉ trả về trang có text.

        Dùng extract_pdf() để lấy đầy đủ thông tin bao gồm scan pages.

        Args:
            file_path: Đường dẫn tuyệt đối tới file .pdf.

        Returns:
            List[PageData] chỉ gồm trang có text native.
        """
        result = self.extract_pdf(file_path)
        return result.pages

    def extract_pdf(self, file_path: str) -> PdfExtractionResult:
        """Trích xuất toàn bộ PDF, phân loại trang text và trang scan.

        Args:
            file_path: Đường dẫn tuyệt đối tới file .pdf.

        Returns:
            PdfExtractionResult với danh sách trang text và scan.

        Raises:
            ExtractError: Nếu không mở được file PDF.
        """
        logger.info("Extract PDF: %s", file_path)
        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            raise ExtractError(
                f"Không thể mở file PDF: {file_path}",
                detail=str(exc),
            ) from exc

        result = PdfExtractionResult(total_pages=len(doc))
        logger.info("PDF has %d pages", result.total_pages)

        try:
            for page_idx in range(len(doc)):
                page_num = page_idx + 1  # 1-indexed
                page = doc[page_idx]

                text = self._extract_page_text(page)
                meaningful_chars = len(text.replace(" ", "").replace("\n", ""))

                if meaningful_chars < _MIN_CHARS_PER_PAGE:
                    # Trang này không có đủ text → cần OCR
                    logger.debug(
                        "Page %d: too few chars (%d) → mark for OCR",
                        page_num,
                        meaningful_chars,
                    )
                    result.scan_page_numbers.append(page_num)
                else:
                    result.pages.append(
                        PageData(
                            page_number=page_num,
                            text=text,
                            source="pdf",
                            confidence=1.0,
                        )
                    )
        finally:
            doc.close()

        # Xác định có phải PDF scan không
        if result.total_pages > 0:
            scan_ratio = len(result.scan_page_numbers) / result.total_pages
            result.is_scan = scan_ratio > _SCAN_RATIO_THRESHOLD

        logger.info(
            "PDF extract done: %d text pages, %d scan pages, is_scan=%s",
            len(result.pages),
            len(result.scan_page_numbers),
            result.is_scan,
        )
        return result

    def render_page_to_image(
        self, file_path: str, page_number: int, dpi: int = 200
    ) -> bytes:
        """Render một trang PDF thành ảnh PNG (bytes) để OCR.

        Dùng thay cho pdf2image để tránh phụ thuộc Poppler trên Windows.
        PyMuPDF tự render nội bộ không cần Poppler.

        Args:
            file_path: Đường dẫn file PDF.
            page_number: Số trang (1-indexed).
            dpi: Độ phân giải ảnh, mặc định 200 DPI.

        Returns:
            PNG image bytes.

        Raises:
            ExtractError: Nếu không render được.
        """
        try:
            doc = fitz.open(file_path)
            page = doc[page_number - 1]

            # Matrix scale để đạt DPI mong muốn (72 DPI mặc định của PDF)
            scale = dpi / 72.0
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image_bytes = pix.tobytes("png")
            doc.close()
            return image_bytes
        except Exception as exc:
            raise ExtractError(
                f"Không render được trang {page_number} từ {file_path}",
                detail=str(exc),
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_page_text(page: fitz.Page) -> str:
        """Lấy text từ một trang PDF với layout blocks.

        Dùng "blocks" thay vì "text" để giữ cấu trúc dòng tốt hơn.

        Args:
            page: fitz.Page object.

        Returns:
            Text string của trang.
        """
        # get_text("text") trả về text có ngắt dòng tự nhiên
        return page.get_text("text").strip()
