"""
DOCXExtractor — Trích xuất văn bản từ file DOCX.

Sử dụng python-docx.
Đọc:
  - Paragraph: text thường.
  - Table: ghép tất cả cell theo hàng, ngăn cách bằng tab.

Vì DOCX không có khái niệm "trang" rõ ràng, toàn bộ nội dung
được nhóm thành một "trang" duy nhất (page_number=1).
Nếu cần phân trang thực sự thì phải dùng LibreOffice CLI để
render sang PDF trước.
"""
from __future__ import annotations

from typing import List

import docx  # python-docx

from ..exceptions.errors import ExtractError
from ..models.page import PageData
from ..utils.logger import get_logger
from .base import BaseExtractor

logger = get_logger(__name__)


class DocxExtractor(BaseExtractor):
    """Extractor cho file .docx.

    Usage:
        extractor = DocxExtractor()
        pages = extractor.extract("contract.docx")
    """

    @property
    def source_type(self) -> str:
        return "docx"

    def extract(self, file_path: str) -> List[PageData]:
        """Trích xuất toàn bộ text từ DOCX.

        Args:
            file_path: Đường dẫn tuyệt đối tới file .docx.

        Returns:
            List gồm một PageData (vì DOCX không có khái niệm trang).

        Raises:
            ExtractError: Nếu không đọc được file.
        """
        logger.info("Extract DOCX: %s", file_path)
        try:
            document = docx.Document(file_path)
        except Exception as exc:
            raise ExtractError(
                f"Không thể mở file DOCX: {file_path}",
                detail=str(exc),
            ) from exc

        parts: List[str] = []

        # Đọc paragraph và table theo thứ tự xuất hiện trong XML
        for element in document.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                # Paragraph thông thường
                para = docx.text.paragraph.Paragraph(element, document)
                text = para.text.strip()
                if text:
                    parts.append(text)

            elif tag == "tbl":
                # Table — ghép nội dung cell
                table_text = self._extract_table(element, document)
                if table_text:
                    parts.append(table_text)

        full_text = "\n".join(parts)
        logger.info("Extracted %d characters from DOCX", len(full_text))

        return [
            PageData(
                page_number=1,
                text=full_text,
                source="docx",
                confidence=1.0,
            )
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_table(tbl_element, document) -> str:
        """Chuyển một bảng DOCX thành text dạng phẳng.

        Mỗi hàng là một dòng, các cell cách nhau bằng ký tự tab.

        Args:
            tbl_element: XML element <w:tbl>.
            document: docx.Document object.

        Returns:
            Text đã được làm phẳng.
        """
        table = docx.table.Table(tbl_element, document)
        rows: List[str] = []
        for row in table.rows:
            cell_texts = [cell.text.strip() for cell in row.cells]
            # Bỏ cell trống ở đầu/cuối hàng
            row_text = "\t".join(t for t in cell_texts if t)
            if row_text:
                rows.append(row_text)
        return "\n".join(rows)
