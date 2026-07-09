"""
main.py — CLI entry point cho document_processor.

Cách dùng:
    python main.py --input contract.pdf
    python main.py --input contract.docx --output results/
    python main.py --input scan.pdf --ocr-lang en

In ra:
    - Thông tin file (tên, loại, kích thước)
    - Số trang
    - Có dùng OCR không
    - Số điều khoản
    - Thời gian xử lý

Lưu kết quả vào:
    output/document.json  (hoặc thư mục chỉ định qua --output)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Thêm thư mục gốc vào sys.path để import khi chạy trực tiếp
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))

from document_processor.exceptions.errors import DocumentProcessorError
from document_processor.services.document_service import DocumentService
from document_processor.utils.logger import get_logger

logger = get_logger("document_processor.main")

# ── Màu ANSI cho terminal (Windows 10+ hỗ trợ) ──────────────────────────────
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

# Kích hoạt màu ANSI trên Windows
if sys.platform == "win32":
    os.system("")  # Kích hoạt Virtual Terminal Processing


def _print_banner() -> None:
    """In banner khi khởi động."""
    print(f"\n{_BOLD}{_CYAN}{'═' * 55}")
    print("  Document Processor — Contract Analysis System")
    print(f"{'═' * 55}{_RESET}\n")


def _print_result_summary(output, elapsed: float) -> None:
    """In kết quả ra terminal theo định dạng dễ đọc.

    Args:
        output: DocumentOutput từ DocumentService.
        elapsed: Thời gian xử lý (giây).
    """
    info = output.document_info

    print(f"\n{_BOLD}{'─' * 55}")
    print("  KẾT QUẢ XỬ LÝ TÀI LIỆU")
    print(f"{'─' * 55}{_RESET}")

    # Thông tin file
    print(f"  {'Tên file':<25}: {_CYAN}{info.file_name}{_RESET}")
    print(f"  {'Loại file':<25}: {info.file_type.upper()}")
    print(f"  {'Số trang':<25}: {_GREEN}{info.page_count}{_RESET}")

    # OCR
    ocr_status = (
        f"{_GREEN}Có{_RESET} (confidence trung bình: {info.avg_confidence:.2%})"
        if info.ocr_used
        else f"{_YELLOW}Không{_RESET}"
    )
    print(f"  {'Dùng OCR':<25}: {ocr_status}")

    # Điều khoản
    clause_count = len(output.clauses)
    print(f"  {'Số điều khoản':<25}: {_GREEN}{clause_count}{_RESET}")

    # Warnings
    warning_count = len(output.warnings)
    if warning_count > 0:
        print(f"  {'Cảnh báo':<25}: {_YELLOW}{warning_count} warnings{_RESET}")
        for w in output.warnings:
            print(f"    ⚠ {w}")
    else:
        print(f"  {'Cảnh báo':<25}: {_GREEN}Không có{_RESET}")

    # Thời gian
    print(f"  {'Thời gian xử lý':<25}: {elapsed:.2f}s")
    print(f"{_BOLD}{'─' * 55}{_RESET}\n")

    # Hiển thị các điều khoản tìm được
    if output.clauses:
        print(f"{_BOLD}  Điều khoản:{_RESET}")
        for clause in output.clauses:
            page_info = (
                f"trang {clause.start_page}"
                if clause.start_page == clause.end_page
                else f"trang {clause.start_page}-{clause.end_page}"
            )
            title_display = clause.title[:60] + "..." if len(clause.title) > 60 else clause.title
            print(f"    [{clause.id:>2}] {title_display} ({page_info})")
        print()


def _save_output(output, output_dir: str, input_file: str) -> str:
    """Lưu DocumentOutput ra file JSON.

    Args:
        output: DocumentOutput từ DocumentService.
        output_dir: Thư mục lưu kết quả.
        input_file: Đường dẫn file đầu vào (để đặt tên output).

    Returns:
        Đường dẫn file JSON đã lưu.
    """
    # Tạo thư mục output nếu chưa có
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Đặt tên file output theo tên file input
    stem = Path(input_file).stem
    output_path = Path(output_dir) / f"{stem}_processed.json"

    json_str = output.to_json(indent=2)
    output_path.write_text(json_str, encoding="utf-8")

    return str(output_path)


def _parse_args() -> argparse.Namespace:
    """Phân tích tham số dòng lệnh."""
    parser = argparse.ArgumentParser(
        description="Document Processor — Chuyển hợp đồng thành dữ liệu có cấu trúc",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python main.py --input contract.pdf
  python main.py --input scan.pdf --ocr-lang vi
  python main.py --input contract.docx --output ./results
  python main.py --input photo.jpg --output ./results --verbose
        """,
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Đường dẫn file đầu vào (DOCX, PDF, PNG, JPG, JPEG)",
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="Thư mục lưu file JSON kết quả (mặc định: output/)",
    )
    parser.add_argument(
        "--ocr-lang",
        default="vi",
        choices=["vi", "en", "ch"],
        help="Ngôn ngữ OCR (mặc định: vi)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Hiển thị log chi tiết",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point chính.

    Returns:
        Exit code: 0 thành công, 1 thất bại.
    """
    import logging

    args = _parse_args()

    # Thiết lập log level
    if args.verbose:
        logging.getLogger("document_processor").setLevel(logging.DEBUG)

    _print_banner()

    # Khởi tạo service
    service = DocumentService(ocr_lang=args.ocr_lang)

    # Xử lý file
    start_time = time.perf_counter()
    try:
        logger.info("Processing: %s", args.input)
        output = service.process(args.input)
        elapsed = time.perf_counter() - start_time

        # In kết quả
        _print_result_summary(output, elapsed)

        # Lưu JSON
        saved_path = _save_output(output, args.output, args.input)
        print(f"  {_GREEN}✔ Đã lưu kết quả:{_RESET} {saved_path}\n")

        return 0

    except DocumentProcessorError as exc:
        elapsed = time.perf_counter() - start_time
        print(f"\n  {_RED}✘ Lỗi xử lý tài liệu:{_RESET} {exc}")
        if hasattr(exc, "detail") and exc.detail:
            print(f"    Chi tiết: {exc.detail}")
        logger.error("Processing failed after %.2fs: %s", elapsed, exc)
        return 1

    except KeyboardInterrupt:
        print(f"\n  {_YELLOW}Đã huỷ bởi người dùng.{_RESET}\n")
        return 130  # Conventional exit code for Ctrl+C


if __name__ == "__main__":
    sys.exit(main())
