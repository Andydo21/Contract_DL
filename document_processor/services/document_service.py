"""
DocumentService — Orchestrator kết nối toàn bộ pipeline.

Thứ tự thực hiện:
  1. FileLoader.load()          → kiểm tra file, xác định loại
  2. Extractor.extract()        → trích xuất text
  3. OCREngine (nếu cần)        → OCR trang scan / ảnh
  4. TextNormalizer.normalize() → chuẩn hoá text
  5. ClauseSplitter.split()     → tách điều khoản
  6. Validator.validate()       → kiểm tra, sinh warnings
  7. Build DocumentOutput       → đóng gói kết quả

DocumentService KHÔNG biết chi tiết từng bước — chỉ điều phối.
Mỗi bước được inject từ ngoài (DIP) để dễ test / thay thế.
"""
from __future__ import annotations

import statistics
from typing import List, Optional

from ..exceptions.errors import DocumentProcessorError, OCRError
from ..extractors.docx_extractor import DocxExtractor
from ..extractors.pdf_extractor import PdfExtractor
from ..loaders.file_loader import FileLoader, LoadResult
from ..models.clause import ClauseData
from ..models.document import (
    ClauseModel,
    DocumentInfo,
    DocumentOutput,
    PageModel,
)
from ..models.page import PageData
from ..ocr.paddle_ocr import OCREngine
from ..preprocess.text_normalizer import TextNormalizer
from ..splitter.clause_splitter import ClauseSplitter
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Ngưỡng confidence OCR thấp → sinh warning
_LOW_CONFIDENCE_THRESHOLD = 0.6

# Ngưỡng trang rỗng sau normalize → sinh warning
_EMPTY_PAGE_WARNING_THRESHOLD = 0


class DocumentService:
    """Orchestrator chính của document_processor.

    Args:
        loader: FileLoader instance (injectable).
        normalizer: TextNormalizer instance (injectable).
        splitter: ClauseSplitter instance (injectable).
        ocr_lang: Ngôn ngữ OCR ("vi" hoặc "en").

    Usage:
        service = DocumentService()
        output = service.process("contract.pdf")
    """

    def __init__(
        self,
        loader: Optional[FileLoader] = None,
        normalizer: Optional[TextNormalizer] = None,
        splitter: Optional[ClauseSplitter] = None,
        ocr_lang: str = "vi",
    ) -> None:
        self._loader = loader or FileLoader()
        self._normalizer = normalizer or TextNormalizer()
        self._splitter = splitter or ClauseSplitter()
        self._ocr_lang = ocr_lang
        # OCREngine khởi tạo lazy — chỉ khi cần OCR
        self._ocr_engine: Optional[OCREngine] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, file_path: str, split_clauses: bool = False) -> DocumentOutput:
        """Xử lý tài liệu và trả về DocumentOutput.

        Args:
            file_path: Đường dẫn tới file (DOCX, PDF, PNG, JPG, JPEG).
            split_clauses: Có thực hiện tách điều khoản hay không (mặc định False).

        Returns:
            DocumentOutput chuẩn hoá.

        Raises:
            DocumentProcessorError: Nếu gặp lỗi nghiêm trọng.
        """
        # ── Bước 1: Load & validate file ──────────────────────────────
        logger.info("═══ Start processing: %s ═══", file_path)
        load_result = self._loader.load(file_path)

        # ── Bước 2: Extract text theo loại file ───────────────────────
        pages, ocr_used = self._extract(load_result)

        # ── Bước 3: Normalize ─────────────────────────────────────────
        logger.info("Normalizing text...")
        pages = self._normalizer.normalize(pages)

        # ── Bước 4: Split clauses (chỉ khi được yêu cầu) ──────────────
        clauses = []
        if split_clauses:
            logger.info("Splitting clauses...")
            clauses = self._splitter.split(pages)

        # ── Bước 5: Validate → sinh warnings ──────────────────────────
        logger.info("Validating document...")
        warnings = self._validate(pages, clauses, load_result, split_clauses=split_clauses)

        # ── Bước 6: Build output ───────────────────────────────────────
        output = self._build_output(load_result, pages, clauses, ocr_used, warnings)

        logger.info(
            "═══ Done: %d pages | %d clauses | %d warnings | OCR=%s ═══",
            len(pages),
            len(clauses),
            len(warnings),
            ocr_used,
        )
        return output

    # ------------------------------------------------------------------
    # Private — extraction
    # ------------------------------------------------------------------

    def _extract(self, load_result: LoadResult):
        """Phân nhánh extract theo file_type.

        Args:
            load_result: Kết quả từ FileLoader.

        Returns:
            Tuple (pages: List[PageData], ocr_used: bool)
        """
        file_type = load_result.file_type
        file_path = load_result.file_path

        if file_type == "docx":
            return self._extract_docx(file_path)
        elif file_type == "pdf":
            try:
                return self._extract_pdf(file_path)
            except Exception as exc:
                logger.warning("Failed to extract as PDF, falling back to TXT: %s", exc)
                return self._extract_txt(file_path)
        elif file_type == "image":
            return self._extract_image(file_path)
        elif file_type == "txt":
            return self._extract_txt(file_path)
        else:
            raise DocumentProcessorError(f"Loại file không xử lý được: {file_type}")

    def _extract_txt(self, file_path: str):
        """Extract TXT."""
        logger.info("Extract text from TXT")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return [PageData(page_number=1, text=text, source="txt", confidence=1.0)], False

    def _extract_docx(self, file_path: str):
        """Extract DOCX."""
        logger.info("Extract text from DOCX")
        extractor = DocxExtractor()
        pages = extractor.extract(file_path)
        return pages, False  # DOCX không cần OCR

    def _extract_pdf(self, file_path: str):
        """Extract PDF — tự động OCR trang scan."""
        logger.info("Extract text from PDF")
        extractor = PdfExtractor()
        result = extractor.extract_pdf(file_path)

        all_pages: List[PageData] = list(result.pages)  # trang có text native
        ocr_used = False

        if result.scan_page_numbers:
            logger.info(
                "PDF has %d scan pages — running OCR: %s",
                len(result.scan_page_numbers),
                result.scan_page_numbers,
            )
            ocr_pages = self._ocr_pdf_pages(
                extractor, file_path, result.scan_page_numbers
            )
            all_pages.extend(ocr_pages)
            ocr_used = True

        # Sắp xếp lại theo page_number sau khi merge
        all_pages.sort(key=lambda p: p.page_number)

        # Nếu không có trang nào (PDF scan hoàn toàn mà OCR thất bại)
        if not all_pages:
            logger.warning("No pages extracted from PDF — returning empty")

        return all_pages, ocr_used

    def _extract_image(self, file_path: str):
        """OCR trực tiếp file ảnh."""
        logger.info("Extract text from image file via OCR")
        engine = self._get_ocr_engine()
        page = engine.ocr_image_file(file_path, page_number=1)
        return [page], True

    def _ocr_pdf_pages(
        self,
        extractor: PdfExtractor,
        file_path: str,
        page_numbers: List[int],
    ) -> List[PageData]:
        """OCR từng trang scan của PDF.

        Dùng PdfExtractor.render_page_to_image() (PyMuPDF, không cần Poppler)
        rồi truyền bytes vào OCREngine.

        Args:
            extractor: PdfExtractor đã khởi tạo.
            file_path: Đường dẫn PDF.
            page_numbers: Danh sách trang cần OCR (1-indexed).

        Returns:
            Danh sách PageData với source="ocr".
        """
        engine = self._get_ocr_engine()
        ocr_pages: List[PageData] = []

        for page_num in page_numbers:
            try:
                logger.info("OCR PDF scan page %d", page_num)
                image_bytes = extractor.render_page_to_image(file_path, page_num)
                page_data = engine.ocr_image_bytes(image_bytes, page_num)
                ocr_pages.append(page_data)
            except OCRError as exc:
                # Log và bỏ qua trang lỗi — không dừng toàn bộ pipeline
                logger.warning("OCR failed for page %d: %s", page_num, exc)

        return ocr_pages

    def _get_ocr_engine(self) -> OCREngine:
        """Lazy load OCREngine (singleton)."""
        if self._ocr_engine is None:
            self._ocr_engine = OCREngine(lang=self._ocr_lang)
        return self._ocr_engine

    # ------------------------------------------------------------------
    # Private — validation
    # ------------------------------------------------------------------

    def _validate(
        self,
        pages: List[PageData],
        clauses: List[ClauseData],
        load_result: LoadResult,
        split_clauses: bool = False,
    ) -> List[str]:
        """Kiểm tra tài liệu và trả về danh sách warnings.

        Không raise exception — chỉ log và tích lũy warnings.

        Args:
            pages: Danh sách trang đã normalize.
            clauses: Danh sách điều khoản.
            load_result: Thông tin file gốc.
            split_clauses: Có thực hiện tách điều khoản hay không.

        Returns:
            Danh sách chuỗi warning.
        """
        warnings: List[str] = []

        # Kiểm tra tài liệu rỗng
        if not pages:
            warnings.append("Tài liệu không có trang nào được trích xuất")

        # Kiểm tra trang rỗng
        empty_pages = [p.page_number for p in pages if p.is_empty]
        if empty_pages:
            warnings.append(f"Trang rỗng sau normalize: {empty_pages}")

        # Kiểm tra confidence OCR thấp
        low_conf_pages = [
            p.page_number
            for p in pages
            if p.source == "ocr" and p.confidence < _LOW_CONFIDENCE_THRESHOLD
        ]
        if low_conf_pages:
            warnings.append(
                f"OCR confidence thấp (<{_LOW_CONFIDENCE_THRESHOLD}) tại trang: {low_conf_pages}"
            )

        if split_clauses:
            # Kiểm tra điều khoản rỗng
            empty_clauses = [c.id for c in clauses if c.is_empty]
            if empty_clauses:
                warnings.append(f"Điều khoản rỗng (không có nội dung): {empty_clauses}")

            # Kiểm tra điều khoản không có tiêu đề
            no_title_clauses = [c.id for c in clauses if not c.title.strip()]
            if no_title_clauses:
                warnings.append(f"Điều khoản thiếu tiêu đề: {no_title_clauses}")

            # Kiểm tra không tìm thấy điều khoản nào
            if not clauses:
                warnings.append(
                    "Không tìm thấy điều khoản nào — hãy kiểm tra format tài liệu"
                )

        # Log tất cả warnings
        for w in warnings:
            logger.warning("[VALIDATOR] %s", w)

        return warnings

    # ------------------------------------------------------------------
    # Private — build output
    # ------------------------------------------------------------------

    @staticmethod
    def _build_output(
        load_result: LoadResult,
        pages: List[PageData],
        clauses: List[ClauseData],
        ocr_used: bool,
        warnings: List[str],
    ) -> DocumentOutput:
        """Đóng gói kết quả thành DocumentOutput (Pydantic).

        Args:
            load_result: Thông tin file gốc.
            pages: Danh sách trang đã xử lý.
            clauses: Danh sách điều khoản.
            ocr_used: Có dùng OCR không.
            warnings: Danh sách cảnh báo.

        Returns:
            DocumentOutput hoàn chỉnh.
        """
        logger.info("Building output...")

        # Confidence trung bình (chỉ tính trang OCR)
        ocr_pages = [p for p in pages if p.source == "ocr"]
        avg_confidence = (
            statistics.mean(p.confidence for p in ocr_pages)
            if ocr_pages
            else 1.0
        )

        doc_info = DocumentInfo(
            file_name=load_result.file_name,
            file_path=load_result.file_path,
            file_type=load_result.file_type,
            page_count=len(pages),
            ocr_used=ocr_used,
            language="vi",  # TODO: tích hợp langdetect nếu cần
            avg_confidence=round(avg_confidence, 4),
        )

        page_models = [
            PageModel(
                page_number=p.page_number,
                text=p.text,
                source=p.source,
                confidence=p.confidence,
            )
            for p in pages
        ]

        clause_models = [
            ClauseModel(
                id=c.id,
                title=c.title,
                content=c.content,
                start_page=c.start_page,
                end_page=c.end_page,
            )
            for c in clauses
        ]

        return DocumentOutput(
            document_info=doc_info,
            pages=page_models,
            clauses=clause_models,
            warnings=warnings,
        )
