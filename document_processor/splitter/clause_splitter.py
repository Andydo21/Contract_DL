"""
ClauseSplitter — Tách điều khoản từ danh sách PageData đã normalize.

Pattern nhận diện tiêu đề điều khoản (hỗ trợ tiếng Việt + tiếng Anh):

  Tiếng Việt:
    - "Điều 1.", "Điều 2:", "ĐIỀU 10", "Điều I", "Điều II"
    - "Điều 1 -", "điều 1."   (không phân biệt hoa/thường)

  Tiếng Anh:
    - "Article 1.", "ARTICLE II:", "Article 10"
    - "Section 1.", "SECTION 2:"
    - "Clause 1.", "CLAUSE II"

Chiến lược ghép trang:
  - Ghép toàn bộ text của tất cả trang thành một chuỗi,
    chèn marker trang để sau này suy ngược start_page/end_page.
  - Tách theo pattern → mỗi đoạn là một điều khoản.
  - Suy ra start_page/end_page từ vị trí ký tự trong chuỗi ghép.

Điều này giải quyết vấn đề điều khoản kéo dài nhiều trang.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..models.clause import ClauseData
from ..models.page import PageData
from ..utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex nhận diện tiêu đề điều khoản
# ---------------------------------------------------------------------------

# Tiếng Việt: Điều <số La Mã hoặc Ả Rập> + dấu phân cách tùy chọn
_VI_CLAUSE_RE = re.compile(
    r"^(?:điều|ĐIỀU|Điều|dieu|DIEU|Dieu)\s+"
    r"(?:[IVXLCDM]+|\d+)"        # Số La Mã hoặc Ả Rập
    r"(?:\.|:|-|\.|\s|$)"        # Dấu phân cách hoặc cuối dòng
    r".*",
    re.IGNORECASE | re.MULTILINE,
)

# Tiếng Anh: Article / Section / Clause
_EN_CLAUSE_RE = re.compile(
    r"^(?:article|section|clause)\s+"
    r"(?:[IVXLCDM]+|\d+)"
    r"(?:\.|:|-|\s|$)"
    r".*",
    re.IGNORECASE | re.MULTILINE,
)

# Kết hợp cả hai
_CLAUSE_HEADER_RE = re.compile(
    r"^((?:điều|ĐIỀU|Điều|dieu|DIEU|Dieu|article|ARTICLE|section|SECTION|clause|CLAUSE)\s+"
    r"(?:[IVXLCDM]+|\d+)"
    r"(?:[\s.:‐\-–—].*)?)"
    r"$",
    re.IGNORECASE | re.MULTILINE,
)

# Marker trang để nhúng vào chuỗi ghép (không xuất hiện trong text thực)
_PAGE_MARKER_TEMPLATE = "\x00PAGE:{page_num}\x00"
_PAGE_MARKER_RE = re.compile(r"\x00PAGE:(\d+)\x00")


@dataclass
class _RawClause:
    """Điều khoản thô — trước khi xác định start/end page."""
    title: str
    body: str
    char_start: int   # vị trí ký tự trong chuỗi ghép


class ClauseSplitter:
    """Tách điều khoản từ danh sách PageData.

    Usage:
        splitter = ClauseSplitter()
        clauses = splitter.split(pages)
    """

    def split(self, pages: List[PageData]) -> List[ClauseData]:
        """Tách điều khoản từ các trang đã normalize.

        Args:
            pages: Danh sách PageData đã được chuẩn hoá.

        Returns:
            Danh sách ClauseData theo thứ tự xuất hiện.
        """
        logger.info("Split clauses from %d pages", len(pages))

        if not pages:
            logger.warning("No pages to split — returning empty clause list")
            return []

        # Bước 1: Ghép text + nhúng marker trang
        merged_text, page_boundaries = self._merge_pages(pages)

        # Bước 2: Tìm tất cả tiêu đề điều khoản
        raw_clauses = self._extract_raw_clauses(merged_text)

        if not raw_clauses:
            logger.warning("No clause headers found in document. Creating a fallback virtual clause.")
            raw_clauses = [
                _RawClause(
                    title="Nội dung hợp đồng",
                    body=_PAGE_MARKER_RE.sub("", merged_text).strip(),
                    char_start=0
                )
            ]

        # Bước 3: Gán start_page / end_page
        clauses = self._assign_pages(raw_clauses, page_boundaries, pages)

        logger.info("Found %d clauses", len(clauses))
        return clauses

    # ------------------------------------------------------------------
    # Private — merge pages
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_pages(
        pages: List[PageData],
    ) -> Tuple[str, List[Tuple[int, int]]]:
        """Ghép tất cả trang thành một chuỗi dài, chèn marker trang.

        Args:
            pages: Danh sách PageData.

        Returns:
            Tuple:
              - merged_text: Chuỗi ghép với marker trang.
              - page_boundaries: List (page_number, char_offset) — vị trí
                ký tự bắt đầu của mỗi trang trong chuỗi ghép.
        """
        parts: List[str] = []
        page_boundaries: List[Tuple[int, int]] = []
        current_offset = 0

        for page in sorted(pages, key=lambda p: p.page_number):
            marker = _PAGE_MARKER_TEMPLATE.format(page_num=page.page_number)
            page_boundaries.append((page.page_number, current_offset))

            segment = f"{marker}\n{page.text}\n"
            parts.append(segment)
            current_offset += len(segment)

        return "".join(parts), page_boundaries

    # ------------------------------------------------------------------
    # Private — raw clause extraction
    # ------------------------------------------------------------------

    def _extract_raw_clauses(self, merged_text: str) -> List[_RawClause]:
        """Tìm tất cả tiêu đề điều khoản trong chuỗi ghép.

        Args:
            merged_text: Chuỗi văn bản ghép đầy đủ.

        Returns:
            Danh sách _RawClause theo thứ tự xuất hiện.
        """
        matches = list(_CLAUSE_HEADER_RE.finditer(merged_text))
        
        raw_clauses: List[_RawClause] = []
        
        # Thêm phần mở đầu (preamble) trước điều khoản đầu tiên nếu có
        if matches:
            preamble_text = merged_text[0:matches[0].start()].strip()
            clean_preamble = _PAGE_MARKER_RE.sub("", preamble_text).strip()
            if len(clean_preamble) > 10:
                raw_clauses.append(
                    _RawClause(
                        title="Phần mở đầu",
                        body=clean_preamble,
                        char_start=0
                    )
                )

        for i, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.start()

            # Body = từ cuối dòng tiêu đề đến đầu tiêu đề kế tiếp
            body_start = match.end()
            body_end = matches[i + 1].start() if i + 1 < len(matches) else len(merged_text)
            body = merged_text[body_start:body_end]

            # Xoá marker trang khỏi body
            body = _PAGE_MARKER_RE.sub("", body).strip()

            raw_clauses.append(_RawClause(title=title, body=body, char_start=start))

        return raw_clauses

    # ------------------------------------------------------------------
    # Private — page assignment
    # ------------------------------------------------------------------

    @staticmethod
    def _assign_pages(
        raw_clauses: List[_RawClause],
        page_boundaries: List[Tuple[int, int]],
        pages: List[PageData],
    ) -> List[ClauseData]:
        """Gán start_page và end_page cho từng điều khoản.

        Dùng page_boundaries để ánh xạ vị trí ký tự → số trang.

        Args:
            raw_clauses: Danh sách điều khoản thô.
            page_boundaries: List (page_number, char_offset).
            pages: Danh sách trang gốc (để lấy max page).

        Returns:
            Danh sách ClauseData hoàn chỉnh.
        """
        max_page = max(p.page_number for p in pages)

        def char_to_page(char_pos: int) -> int:
            """Ánh xạ vị trí ký tự → số trang."""
            page_num = page_boundaries[0][0]
            for p_num, offset in page_boundaries:
                if offset <= char_pos:
                    page_num = p_num
                else:
                    break
            return page_num

        clauses: List[ClauseData] = []
        for idx, raw in enumerate(raw_clauses):
            start_page = char_to_page(raw.char_start)

            # end_page = start_page của điều khoản kế tiếp (hoặc trang cuối)
            if idx + 1 < len(raw_clauses):
                end_page = char_to_page(raw_clauses[idx + 1].char_start)
                # Điều khoản kết thúc trước khi điều tiếp bắt đầu
                # → end_page = trang của điều tiếp hoặc trang trước đó
                # Đơn giản: nếu start của điều tiếp trùng trang → cùng trang
            else:
                end_page = max_page

            clauses.append(
                ClauseData(
                    id=idx + 1,
                    title=raw.title,
                    content=raw.body,
                    start_page=start_page,
                    end_page=end_page,
                )
            )

        return clauses
