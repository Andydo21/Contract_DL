"""
Logging utility cho document_processor.

Cấu hình một logger duy nhất với format chuẩn.
Mọi module trong package đều gọi get_logger(__name__).
"""
from __future__ import annotations

import logging
import sys
from typing import Optional


# Format: [thời gian] [cấp độ] [tên module] — nội dung
_FORMAT = "%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Flag để tránh thêm handler trùng lặp
_configured = False


def _configure_root_logger(level: int) -> None:
    """Cấu hình root logger một lần duy nhất."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger("document_processor")
    root.setLevel(level)
    root.addHandler(handler)
    # Không propagate lên root logger của Python để tránh log đôi
    root.propagate = False

    _configured = True


def get_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """Trả về logger đã được cấu hình cho module.

    Args:
        name: Tên module, thường truyền __name__.
        level: Mức log mặc định (logging.INFO).
        log_file: Nếu truyền vào, sẽ ghi log ra file thêm vào stdout.

    Returns:
        logging.Logger đã sẵn sàng sử dụng.
    """
    _configure_root_logger(level)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Thêm file handler nếu được yêu cầu
    if log_file and not any(
        isinstance(h, logging.FileHandler) for h in logger.handlers
    ):
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
        logger.addHandler(file_handler)

    return logger
