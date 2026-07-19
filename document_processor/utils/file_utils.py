"""
Các hàm tiện ích thao tác với file.

Tách ra để Loader và Extractor không cần biết cách đọc file,
chỉ cần gọi hàm từ đây (SRP).
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Generator


# Map extension → file type chuẩn nội bộ
_EXTENSION_MAP: dict[str, str] = {
    ".docx": "docx",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".txt": "txt",
}

# MIME types được chấp nhận
_SUPPORTED_MIMES: set[str] = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "text/plain",
}


def file_exists(path: str | Path) -> bool:
    """Kiểm tra file có tồn tại và có thể đọc không.

    Args:
        path: Đường dẫn tới file.

    Returns:
        True nếu file tồn tại và là file thường (không phải thư mục).
    """
    p = Path(path)
    return p.exists() and p.is_file()


def get_file_extension(path: str | Path) -> str:
    """Trả về extension thường (ví dụ ".pdf", ".docx").

    Args:
        path: Đường dẫn file.

    Returns:
        Extension dạng chữ thường, bao gồm dấu chấm.
    """
    return Path(path).suffix.lower()


def get_file_type(path: str | Path) -> str | None:
    """Xác định loại file nội bộ dựa trên extension.

    Args:
        path: Đường dẫn file.

    Returns:
        "docx", "pdf", "image" hoặc None nếu không hỗ trợ.
    """
    ext = get_file_extension(path)
    return _EXTENSION_MAP.get(ext)


def get_mime_type(path: str | Path) -> str:
    """Đoán MIME type từ tên file (không đọc nội dung).

    Args:
        path: Đường dẫn file.

    Returns:
        MIME type string hoặc "application/octet-stream" nếu không xác định được.
    """
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def is_supported_file(path: str | Path) -> bool:
    """Kiểm tra file có thuộc định dạng được hỗ trợ không.

    Args:
        path: Đường dẫn file.

    Returns:
        True nếu extension nằm trong danh sách hỗ trợ.
    """
    return get_file_type(path) is not None


def get_file_size_mb(path: str | Path) -> float:
    """Trả về kích thước file tính theo MB.

    Args:
        path: Đường dẫn file.

    Returns:
        Kích thước file (MB), làm tròn 2 chữ số.
    """
    size_bytes = os.path.getsize(str(path))
    return round(size_bytes / (1024 * 1024), 2)


def read_bytes_chunk(
    path: str | Path,
    chunk_size: int = 4096,
) -> Generator[bytes, None, None]:
    """Đọc file theo từng chunk để tiết kiệm RAM.

    Args:
        path: Đường dẫn file.
        chunk_size: Kích thước mỗi chunk (bytes), mặc định 4KB.

    Yields:
        bytes chunk.
    """
    with open(str(path), "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk
