"""
OCREngine — Wrapper PaddleOCR cho document_processor.

Chiến lược:
  - Lazy import PaddleOCR để không bắt buộc cài khi không dùng OCR.
  - Singleton pattern: khởi tạo PaddleOCR một lần duy nhất (nặng ~2-3s).
  - Chấp nhận đầu vào là bytes (PNG) hoặc numpy array để linh hoạt.

Hỗ trợ:
  - PDF scan: nhận bytes ảnh từ PdfExtractor.render_page_to_image()
  - Ảnh (PNG/JPG): đọc trực tiếp bằng Pillow rồi convert numpy.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from PIL import Image

from ..exceptions.errors import OCRError
from ..models.page import PageData
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OCRPageResult:
    """Kết quả OCR một trang / ảnh.

    Attributes:
        page_number: Số trang (1-indexed).
        text: Văn bản đã ghép từ các dòng OCR.
        confidence: Confidence trung bình của trang.
        line_count: Số dòng text được nhận dạng.
    """

    page_number: int
    text: str
    confidence: float
    line_count: int


class OCREngine:
    """Wrapper PaddleOCR với lazy initialization và singleton model.

    Usage:
        engine = OCREngine(lang="vi")
        page_data = engine.ocr_image_bytes(image_bytes, page_number=1)
    """

    # Class-level cache để tái sử dụng model giữa các lần gọi
    _instance: Optional["OCREngine"] = None
    _ocr_model = None

    def __init__(self, lang: str = "vi") -> None:
        """Khởi tạo OCR engine.

        Args:
            lang: Ngôn ngữ OCR ("vi" cho tiếng Việt, "en" cho tiếng Anh).
                  PaddleOCR hỗ trợ đa ngôn ngữ, tiếng Việt dùng model "vi".
        """
        self.lang = lang
        self._paddle = None  # Lazy — chỉ load khi dùng lần đầu

    def _get_paddle(self):
        """Lazy load PaddleOCR model (singleton per lang).

        Raises:
            OCRError: Nếu không import được paddleocr.
        """
        if self._paddle is not None:
            return self._paddle

        logger.info("Initializing PaddleOCR (lang=%s) — first call only...", self.lang)
        try:
            from paddleocr import PaddleOCR  # type: ignore[import]

            # use_angle_cls=True: phát hiện và xoay ảnh nếu bị nghiêng
            # use_gpu=False: CPU mode để chạy trên Windows không cần GPU
            self._paddle = PaddleOCR(
                use_textline_orientation=True,
                lang=self.lang,
                device="cpu",
                enable_mkldnn=False,
            )
            logger.info("PaddleOCR initialized successfully")
        except ImportError as exc:
            raise OCRError(
                "Không thể import paddleocr. Hãy cài: pip install paddleocr",
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise OCRError(
                "Không thể khởi tạo PaddleOCR",
                detail=str(exc),
            ) from exc

        return self._paddle

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ocr_image_bytes(self, image_bytes: bytes, page_number: int) -> PageData:
        """OCR một ảnh từ dạng bytes.

        Dùng cho PDF scan (bytes từ PdfExtractor) hoặc ảnh PNG/JPG đọc từ disk.

        Args:
            image_bytes: Nội dung ảnh dạng bytes (PNG hoặc JPEG).
            page_number: Số trang để ghi vào PageData.

        Returns:
            PageData với source="ocr".

        Raises:
            OCRError: Nếu OCR thất bại.
        """
        logger.debug("OCR page %d (%d bytes)", page_number, len(image_bytes))
        try:
            image_array = self._bytes_to_numpy(image_bytes)
            result = self._run_ocr(image_array)
            ocr_result = self._parse_result(result, page_number)
        except OCRError:
            raise
        except Exception as exc:
            raise OCRError(
                f"OCR thất bại trang {page_number}",
                detail=str(exc),
            ) from exc

        logger.debug(
            "Page %d OCR: %d lines, confidence=%.3f",
            page_number,
            ocr_result.line_count,
            ocr_result.confidence,
        )

        return PageData(
            page_number=page_number,
            text=ocr_result.text,
            source="ocr",
            confidence=ocr_result.confidence,
        )

    def ocr_image_file(self, file_path: str, page_number: int) -> PageData:
        """OCR trực tiếp từ file ảnh (PNG/JPG/JPEG).

        Args:
            file_path: Đường dẫn file ảnh.
            page_number: Số trang để ghi vào PageData.

        Returns:
            PageData với source="ocr".

        Raises:
            OCRError: Nếu không đọc được ảnh hoặc OCR thất bại.
        """
        logger.info("OCR image file: %s", file_path)
        try:
            with open(file_path, "rb") as f:
                image_bytes = f.read()
        except OSError as exc:
            raise OCRError(
                f"Không đọc được file ảnh: {file_path}",
                detail=str(exc),
            ) from exc

        return self.ocr_image_bytes(image_bytes, page_number)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bytes_to_numpy(image_bytes: bytes) -> np.ndarray:
        """Chuyển bytes → numpy array RGB.

        Args:
            image_bytes: Raw bytes của ảnh (PNG / JPEG).

        Returns:
            numpy array shape (H, W, 3) kiểu uint8.
        """
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return np.array(image)

    def _run_ocr(self, image_array: np.ndarray) -> list:
        """Chạy PaddleOCR trên numpy array.

        Args:
            image_array: numpy array RGB.

        Returns:
            Raw result từ PaddleOCR (nested list).
        """
        paddle = self._get_paddle()
        result = paddle.ocr(image_array)
        # PaddleOCR trả về [[page_results]] hoặc [page_results] tuỳ version
        if result and isinstance(result[0], list) and result[0] and isinstance(result[0][0], list):
            return result[0]  # unwrap page wrapper
        return result or []

    @staticmethod
    def _parse_result(raw_result: list, page_number: int) -> OCRPageResult:
        """Parse kết quả PaddleOCR thành OCRPageResult.

        Mỗi entry trong raw_result có dạng:
          [[box_coords], (text, confidence)]

        Args:
            raw_result: Danh sách detection từ PaddleOCR.
            page_number: Số trang.

        Returns:
            OCRPageResult đã tổng hợp.
        """
        lines: List[str] = []
        confidences: List[float] = []

        for entry in raw_result:
            if not entry:
                continue

            # Case 1: Newer Dict-based output format
            if isinstance(entry, dict):
                texts = entry.get("rec_texts", [])
                scores = entry.get("rec_scores", [])
                for t, s in zip(texts, scores):
                    t = str(t).strip()
                    if t:
                        lines.append(t)
                        confidences.append(float(s))

            # Case 2: Legacy List-based format: [[box], (text, confidence)]
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                text_conf = entry[1]
                if isinstance(text_conf, (list, tuple)) and len(text_conf) == 2:
                    text, conf = text_conf
                    text = str(text).strip()
                    conf = float(conf)
                    if text:
                        lines.append(text)
                        confidences.append(conf)

        full_text = "\n".join(lines)
        avg_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        return OCRPageResult(
            page_number=page_number,
            text=full_text,
            confidence=avg_confidence,
            line_count=len(lines),
        )
