"""
TextNormalizer — Chuẩn hoá văn bản sau khi extract / OCR.

Thứ tự áp dụng (quan trọng — đừng đổi thứ tự):
  1. Chuẩn hoá Unicode (NFC).
  2. Chuẩn hoá dấu câu / ký tự đặc biệt.
  3. Ghép dòng bị ngắt sai (soft hyphen / OCR line break).
  4. Loại bỏ header / footer lặp lại.
  5. Xoá số trang độc lập.
  6. Loại bỏ khoảng trắng thừa.

Nguyên tắc:
  - KHÔNG xoá nội dung điều khoản.
  - KHÔNG thay đổi nghĩa văn bản.
  - Mỗi bước là một hàm private nhỏ (SRP, dễ test).
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import List

from ..models.page import PageData
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Số lần xuất hiện tối thiểu của một dòng để coi là header/footer
_HEADER_FOOTER_MIN_REPEAT = 3

# Regex: dòng chỉ chứa số trang (ví dụ: "1", "- 2 -", "Page 3", "Trang 4")
_PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:[-–—]?\s*)?(?:Page|Trang)?\s*\d{1,4}\s*(?:[-–—]?\s*)?$",
    re.IGNORECASE,
)

# Regex: ghép dòng bị ngắt giữa chừng (không kết thúc bằng dấu câu)
# Dòng không kết thúc bằng . ! ? : ; ) " » → có thể là bị ngắt
_SOFT_BREAK_RE = re.compile(
    r"(?<![.!?:;)\"»\d])\n(?=[a-záàảãạăắặẳẵặâấầẩẫậđéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵa-z])",
    re.UNICODE,
)

# Regex: nhiều khoảng trắng liên tiếp → một khoảng trắng
_MULTI_SPACE_RE = re.compile(r"[ \t]+")

# Regex: nhiều dòng trống liên tiếp → tối đa 2 dòng trống
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")

# Ký tự control không in được (trừ \n, \t)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TextNormalizer:
    """Chuẩn hoá văn bản trên toàn bộ danh sách PageData.

    Usage:
        normalizer = TextNormalizer()
        clean_pages = normalizer.normalize(pages)
    """

    def normalize(self, pages: List[PageData]) -> List[PageData]:
        """Chuẩn hoá toàn bộ danh sách trang.

        Phát hiện header/footer lặp lại trước (cần nhìn toàn bộ pages),
        sau đó xử lý từng trang độc lập.

        Args:
            pages: Danh sách PageData chưa chuẩn hoá.

        Returns:
            Danh sách PageData mới với text đã chuẩn hoá.
        """
        logger.info("Normalize %d pages", len(pages))

        # Bước 1: Xác định header/footer lặp lại trên toàn tài liệu
        repeated_lines = self._detect_repeated_lines(pages)
        if repeated_lines:
            logger.debug(
                "Detected %d repeated header/footer patterns", len(repeated_lines)
            )

        # Bước 2: Xử lý từng trang
        normalized: List[PageData] = []
        for page in pages:
            clean_text = self._normalize_text(page.text, repeated_lines)
            # Tạo PageData mới (immutable approach — không mutate)
            normalized.append(
                PageData(
                    page_number=page.page_number,
                    text=clean_text,
                    source=page.source,
                    confidence=page.confidence,
                )
            )

        logger.info("Normalization complete")
        return normalized

    # ------------------------------------------------------------------
    # Private — pipeline
    # ------------------------------------------------------------------

    def _normalize_text(self, text: str, repeated_lines: set[str]) -> str:
        """Áp dụng pipeline chuẩn hoá cho một đoạn text.

        Args:
            text: Text thô.
            repeated_lines: Tập hợp dòng header/footer cần xoá.

        Returns:
            Text đã chuẩn hoá.
        """
        text = self._remove_control_chars(text)
        text = self._normalize_unicode(text)
        text = self._normalize_punctuation(text)
        text = self._join_soft_line_breaks(text)
        text = self._remove_page_numbers(text)
        text = self._remove_repeated_lines(text, repeated_lines)
        text = self._collapse_whitespace(text)
        return text.strip()

    # ------------------------------------------------------------------
    # Private — individual steps
    # ------------------------------------------------------------------

    @staticmethod
    def _remove_control_chars(text: str) -> str:
        """Xoá ký tự điều khiển không in được."""
        return _CONTROL_CHARS_RE.sub("", text)

    @staticmethod
    def _normalize_unicode(text: str) -> str:
        """Chuẩn hoá Unicode về dạng NFC (composed form).

        NFC đảm bảo ký tự tiếng Việt được biểu diễn nhất quán,
        tránh trường hợp cùng một chữ nhưng encode khác nhau.
        """
        return unicodedata.normalize("NFC", text)

    @staticmethod
    def _normalize_punctuation(text: str) -> str:
        """Chuẩn hoá dấu câu và ký tự đặc biệt phổ biến.

        Thay thế:
          - Dấu ngoặc kép kiểu typographic → ASCII
          - Dấu gạch ngang dài → dấu gạch ngang thường
          - Dấu chấm lửng → "..."
          - Khoảng trắng không co giãn → khoảng trắng thường
        """
        replacements = [
            ("\u201c", '"'),   # " → "
            ("\u201d", '"'),   # " → "
            ("\u2018", "'"),   # ' → '
            ("\u2019", "'"),   # ' → '
            ("\u2013", "-"),   # – → -
            ("\u2014", "-"),   # — → -
            ("\u2026", "..."), # … → ...
            ("\u00a0", " "),   # non-breaking space → space
            ("\u200b", ""),    # zero-width space → xoá
            ("\ufeff", ""),    # BOM → xoá
        ]
        for old, new in replacements:
            text = text.replace(old, new)
        return text

    @staticmethod
    def _join_soft_line_breaks(text: str) -> str:
        """Ghép các dòng bị ngắt giữa chừng do OCR hoặc PDF reflow.

        Chỉ ghép khi dòng KHÔNG kết thúc bằng dấu câu kết thúc câu.
        """
        return _SOFT_BREAK_RE.sub(" ", text)

    @staticmethod
    def _remove_page_numbers(text: str) -> str:
        """Xoá các dòng chỉ chứa số trang đứng độc lập."""
        lines = text.split("\n")
        clean_lines = [
            line for line in lines if not _PAGE_NUMBER_RE.match(line)
        ]
        return "\n".join(clean_lines)

    @staticmethod
    def _remove_repeated_lines(text: str, repeated_lines: set[str]) -> str:
        """Xoá các dòng được xác định là header/footer lặp lại.

        Args:
            text: Text của trang.
            repeated_lines: Tập dòng cần xoá.

        Returns:
            Text đã lọc.
        """
        if not repeated_lines:
            return text
        lines = text.split("\n")
        clean_lines = [
            line for line in lines if line.strip() not in repeated_lines
        ]
        return "\n".join(clean_lines)

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        """Thu gọn khoảng trắng thừa trong từng dòng và nhiều dòng trống."""
        # Thu gọn space/tab trong mỗi dòng
        lines = [_MULTI_SPACE_RE.sub(" ", line) for line in text.split("\n")]
        text = "\n".join(lines)
        # Tối đa 2 dòng trống liên tiếp
        text = _MULTI_NEWLINE_RE.sub("\n\n", text)
        return text

    # ------------------------------------------------------------------
    # Private — header/footer detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_repeated_lines(pages: List[PageData]) -> set[str]:
        """Tìm các dòng lặp lại qua nhiều trang (header/footer).

        Logic:
          - Lấy 3 dòng đầu và 3 dòng cuối mỗi trang.
          - Đếm tần suất xuất hiện.
          - Dòng nào xuất hiện >= MIN_REPEAT lần → header/footer.

        Args:
            pages: Danh sách trang.

        Returns:
            Set các dòng được coi là header/footer.
        """
        counter: Counter = Counter()
        for page in pages:
            lines = [ln.strip() for ln in page.text.split("\n") if ln.strip()]
            # Lấy 3 đầu + 3 cuối (có thể trùng nếu trang ngắn)
            candidates = lines[:3] + lines[-3:]
            for line in set(candidates):  # set để tránh đếm trùng trong cùng trang
                if len(line) > 5:  # bỏ qua dòng quá ngắn
                    counter[line] += 1

        return {
            line
            for line, count in counter.items()
            if count >= _HEADER_FOOTER_MIN_REPEAT
        }
