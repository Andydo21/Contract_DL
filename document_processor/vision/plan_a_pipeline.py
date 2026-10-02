"""Page-oriented PlanA vision extraction without PaddleOCR."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class VisionBlock:
    order: int
    layout_type: str
    text: str
    bbox: list[int]
    confidence: float


@dataclass
class VisionPage:
    page_number: int
    width: int
    height: int
    image_path: str
    text: str
    blocks: list[VisionBlock] = field(default_factory=list)


@dataclass
class VisionDocument:
    file_name: str
    pages: list[VisionPage]
    pipeline_name: str = "plan-a-surya-colpali"


class PlanAVisionPipeline:
    """Rasterize pages, detect PlanA/Surya regions and read embedded text.

    Surya locates visual regions only. Text is read from an existing PDF text
    layer; image-only regions intentionally remain visual blocks.
    """

    _layout_predictor: Any = None
    _layout_load_attempted = False

    def __init__(self, output_dir: str | Path, media_root: str | Path):
        self.output_dir = Path(output_dir)
        self.media_root = Path(media_root)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _get_layout_predictor(cls):
        if cls._layout_load_attempted:
            return cls._layout_predictor
        cls._layout_load_attempted = True
        try:
            from surya.fast_layout import FastLayoutPredictor

            cls._layout_predictor = FastLayoutPredictor()
        except Exception as exc:
            logger.warning("Surya layout unavailable; using native PDF blocks: %s", exc)
        return cls._layout_predictor

    def extract(self, file_path: str | Path, document_key: str) -> VisionDocument:
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            pages = self._extract_pdf(path, document_key)
        elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}:
            pages = self._extract_image(path, document_key)
        elif suffix in {".docx", ".doc"}:
            pages = self._extract_docx(path)
        else:
            pages = self._extract_text(path)
        return VisionDocument(file_name=path.name, pages=pages)

    def _extract_pdf(self, path: Path, document_key: str) -> list[VisionPage]:
        import fitz
        from PIL import Image

        pages: list[VisionPage] = []
        predictor = self._get_layout_predictor()
        document = fitz.open(path)
        try:
            for index, page in enumerate(document):
                page_number = index + 1
                pixmap = page.get_pixmap(dpi=150, alpha=False)
                image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                image_path = self.output_dir / f"{document_key}_page_{page_number}.png"
                image.save(image_path, "PNG")

                detected = []
                if predictor is not None:
                    try:
                        prediction = predictor([image])[0]
                        detected = getattr(prediction, "bboxes", getattr(prediction, "boxes", []))
                    except Exception as exc:
                        logger.warning("Surya layout failed on page %s: %s", page_number, exc)

                blocks = self._blocks_from_layout(page, detected, pixmap.width, pixmap.height)
                if not blocks:
                    blocks = self._native_pdf_blocks(page)
                if not blocks:
                    blocks = [VisionBlock(1, "visual", "", [0, 0, 1000, 1000], 1.0)]
                page_text = "\n\n".join(block.text for block in blocks if block.text).strip()
                pages.append(
                    VisionPage(
                        page_number=page_number,
                        width=pixmap.width,
                        height=pixmap.height,
                        image_path=self._relative_media_path(image_path),
                        text=page_text,
                        blocks=blocks,
                    )
                )
        finally:
            document.close()
        return pages

    def _blocks_from_layout(self, page, detected, image_width: int, image_height: int) -> list[VisionBlock]:
        import fitz

        blocks: list[VisionBlock] = []
        scale_x = page.rect.width / image_width if image_width else 1
        scale_y = page.rect.height / image_height if image_height else 1
        for order, item in enumerate(detected, start=1):
            bbox = list(getattr(item, "bbox", item))
            if len(bbox) != 4:
                continue
            label = str(getattr(item, "label", "paragraph")).lower()
            pdf_rect = fitz.Rect(
                bbox[0] * scale_x,
                bbox[1] * scale_y,
                bbox[2] * scale_x,
                bbox[3] * scale_y,
            )
            text = page.get_text("text", clip=pdf_rect).strip()
            blocks.append(
                VisionBlock(
                    order=order,
                    layout_type=self._normalize_layout_type(label, text),
                    text=text,
                    bbox=self._normalize_bbox(bbox, image_width, image_height),
                    confidence=float(getattr(item, "confidence", 0.95) or 0.95),
                )
            )
        return blocks

    def _native_pdf_blocks(self, page) -> list[VisionBlock]:
        result = []
        for order, block in enumerate(page.get_text("blocks") or [], start=1):
            text = block[4].strip()
            if not text:
                continue
            bbox = [
                int(block[0] / page.rect.width * 1000),
                int(block[1] / page.rect.height * 1000),
                int(block[2] / page.rect.width * 1000),
                int(block[3] / page.rect.height * 1000),
            ]
            result.append(VisionBlock(order, self._detect_layout_type(text), text, bbox, 0.90))
        return result

    def _extract_image(self, path: Path, document_key: str) -> list[VisionPage]:
        from PIL import Image

        image = Image.open(path).convert("RGB")
        output_path = self.output_dir / f"{document_key}_page_1.png"
        image.save(output_path, "PNG")
        block = VisionBlock(1, "figure", "", [0, 0, 1000, 1000], 1.0)
        return [VisionPage(1, image.width, image.height, self._relative_media_path(output_path), "", [block])]

    def _extract_docx(self, path: Path) -> list[VisionPage]:
        import docx

        document = docx.Document(path)
        blocks: list[VisionBlock] = []
        order = 1
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                blocks.append(VisionBlock(order, self._detect_layout_type(text), text, [0, 0, 1000, 0], 1.0))
                order += 1
        for table in document.tables:
            for row in table.rows:
                text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if text:
                    blocks.append(VisionBlock(order, "table", text, [0, 0, 1000, 0], 1.0))
                    order += 1
        text = "\n\n".join(block.text for block in blocks)
        return [VisionPage(1, 0, 0, "", text, blocks)]

    def _extract_text(self, path: Path) -> list[VisionPage]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        blocks = [
            VisionBlock(index, self._detect_layout_type(line), line, [0, 0, 1000, 0], 1.0)
            for index, line in enumerate(lines, start=1)
        ]
        return [VisionPage(1, 0, 0, "", "\n".join(lines), blocks)]

    def _relative_media_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.media_root).as_posix()
        except ValueError:
            return path.as_posix()

    @staticmethod
    def _normalize_bbox(bbox, width: int, height: int) -> list[int]:
        if not width or not height:
            return [0, 0, 1000, 1000]
        return [
            max(0, min(1000, int(bbox[0] / width * 1000))),
            max(0, min(1000, int(bbox[1] / height * 1000))),
            max(0, min(1000, int(bbox[2] / width * 1000))),
            max(0, min(1000, int(bbox[3] / height * 1000))),
        ]

    @staticmethod
    def _normalize_layout_type(label: str, text: str) -> str:
        if label in {"title", "section-header", "header"}:
            return "title"
        if label in {"table", "table-row"}:
            return "table"
        if label in {"picture", "figure", "image"}:
            return "figure"
        return PlanAVisionPipeline._detect_layout_type(text)

    @staticmethod
    def _detect_layout_type(text: str) -> str:
        normalized = (text or "").strip().lower()
        if re.match(r"^(bảng|table|stt|danh mục)", normalized):
            return "table"
        if re.match(r"^(điều|chương|mục|phần|section|chapter|article|\d+[.)])", normalized):
            return "title"
        return "paragraph"
