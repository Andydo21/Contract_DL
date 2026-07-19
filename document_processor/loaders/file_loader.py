"""
FileLoader — cổng vào duy nhất của pipeline.

Trách nhiệm:
  1. Kiểm tra file tồn tại.
  2. Kiểm tra định dạng được hỗ trợ.
  3. Xác định loại file (docx / pdf / image).
  4. Trả về LoadResult chứa thông tin cần thiết cho các bước sau.

Không đọc nội dung file ở đây (SRP).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..exceptions.errors import (
    FileNotFoundError as DocFileNotFoundError,
    UnsupportedFileTypeError,
)
from ..utils.file_utils import (
    file_exists,
    get_file_extension,
    get_file_size_mb,
    get_file_type,
    get_mime_type,
    is_supported_file,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Các loại file được hỗ trợ
FileType = Literal["docx", "pdf", "image", "txt"]


@dataclass(frozen=True)
class LoadResult:
    """Kết quả của FileLoader.load().

    Immutable — không thay đổi sau khi tạo.

    Attributes:
        file_path: Đường dẫn tuyệt đối tới file.
        file_name: Tên file (không bao gồm thư mục).
        file_type: Loại file nội bộ.
        extension: Extension chữ thường, ví dụ ".pdf".
        mime_type: MIME type đoán từ extension.
        size_mb: Kích thước file (MB).
    """

    file_path: str
    file_name: str
    file_type: FileType
    extension: str
    mime_type: str
    size_mb: float


class FileLoader:
    """Kiểm tra và nhận diện file đầu vào.

    Usage:
        loader = FileLoader()
        result = loader.load("path/to/contract.pdf")
    """

    def load(self, path: str | Path) -> LoadResult:
        """Validate file và trả về LoadResult.

        Args:
            path: Đường dẫn tới file cần xử lý.

        Returns:
            LoadResult chứa thông tin về file.

        Raises:
            DocFileNotFoundError: Nếu file không tồn tại.
            UnsupportedFileTypeError: Nếu định dạng không được hỗ trợ.
        """
        path = Path(path).resolve()
        logger.info("Load file: %s", path)

        # 1. Kiểm tra file tồn tại
        self._check_exists(path)

        # 2. Kiểm tra định dạng
        self._check_supported(path)

        # 3. Thu thập thông tin
        file_type = get_file_type(path)  # type: ignore[assignment]
        result = LoadResult(
            file_path=str(path),
            file_name=path.name,
            file_type=file_type,
            extension=get_file_extension(path),
            mime_type=get_mime_type(path),
            size_mb=get_file_size_mb(path),
        )

        logger.info(
            "Detected: type=%s | size=%.2f MB | mime=%s",
            result.file_type,
            result.size_mb,
            result.mime_type,
        )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_exists(path: Path) -> None:
        """Raise nếu file không tồn tại."""
        if not file_exists(path):
            raise DocFileNotFoundError(
                f"File không tồn tại: {path}",
                detail=f"Absolute path: {path.resolve()}",
            )

    @staticmethod
    def _check_supported(path: Path) -> None:
        """Raise nếu định dạng file không được hỗ trợ."""
        if not is_supported_file(path):
            ext = get_file_extension(path)
            raise UnsupportedFileTypeError(
                f"Định dạng không được hỗ trợ: '{ext}'",
                detail="Hỗ trợ: .docx, .pdf, .png, .jpg, .jpeg",
            )
