"""
Model đại diện cho một điều khoản trong hợp đồng.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClauseData:
    """Một điều khoản đã được tách ra từ tài liệu.

    Attributes:
        id: Số thứ tự điều khoản trong tài liệu (bắt đầu từ 1).
        title: Tiêu đề điều khoản, ví dụ "Điều 1. Mục đích hợp đồng".
        content: Toàn bộ nội dung điều khoản (đã normalize).
        start_page: Trang bắt đầu của điều khoản.
        end_page: Trang kết thúc (bằng start_page nếu nằm gọn một trang).
    """

    id: int
    title: str
    content: str
    start_page: int
    end_page: int

    @property
    def is_empty(self) -> bool:
        """True nếu điều khoản không có nội dung sau tiêu đề."""
        return not self.content.strip()

    @property
    def spans_multiple_pages(self) -> bool:
        """True nếu điều khoản kéo dài qua nhiều trang."""
        return self.end_page > self.start_page

    @property
    def word_count(self) -> int:
        """Số từ ước tính của điều khoản."""
        return len(self.content.split())
