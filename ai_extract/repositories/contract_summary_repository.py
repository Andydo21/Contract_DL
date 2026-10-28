from decimal import Decimal
from contracts.models import ContractVersion
from ai_extract.models import ContractSummary, Clause, ExtractedEntity, LayoutExtractionBlock


class ContractSummaryRepository:
    @staticmethod
    def get_by_version(version: ContractVersion) -> ContractSummary:
        try:
            return ContractSummary.objects.get(version=version)
        except ContractSummary.DoesNotExist:
            return None

    @staticmethod
    def create_or_update(version: ContractVersion, summary: str, model_id: str = "") -> ContractSummary:
        obj, _ = ContractSummary.objects.update_or_create(
            version=version,
            defaults={
                "summary": summary,
                **({"model_id": model_id} if model_id else {}),
            },
        )
        return obj

    @staticmethod
    def source(version: ContractVersion) -> dict:
        """OCR text from the latest completed extraction run, else the stored raw text, with its origin."""
        run = version.layout_extraction_runs.filter(status="COMPLETED").first()
        if run:
            blocks = LayoutExtractionBlock.objects.filter(page__run=run).order_by(
                "page__page_number", "block_order"
            ).values_list("text", flat=True)
            text = "\n\n".join(t.strip() for t in blocks if t and t.strip())
            if text:
                return {"text": text, "origin": "ocr_blocks", "run_id": run.id}
            text = "\n\n".join(p.extracted_text for p in run.pages.all() if p.extracted_text.strip())
            if text:
                return {"text": text, "origin": "ocr_pages", "run_id": run.id}
        text = "\n\n".join(
            version.contexts.filter(context_type="raw_text").order_by("id").values_list("content", flat=True)
        )
        return {"text": text, "origin": "raw_text" if text else "none", "run_id": None}

    @staticmethod
    def get_all():
        return (
            ContractSummary.objects.select_related(
                "version__contract"
            ).order_by("-created_at")
        )
