"""Application service that connects contract files to the PlanA pipeline."""
from __future__ import annotations

from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import tempfile
import urllib.parse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from contracts.crypto_utils import decrypt_pdf
from contracts.models import ContractContext
from document_processor.vision import PlanAVisionPipeline

from .models import LayoutExtractionBlock, LayoutExtractionPage, LayoutExtractionRun
from .vector_indexing import IndexResult, PlanACollectionIndexer


class LayoutExtractionService:
    pipeline_name = "plan-a-surya-colpali"

    def extract_version(self, version) -> LayoutExtractionRun:
        contract_file = version.files.order_by("-uploaded_at").first()
        if not contract_file or not contract_file.file_path:
            raise ValueError("No file is available for this contract version.")

        physical_path = self._physical_path(contract_file.file_path)
        if not physical_path.exists():
            raise ValueError(f"Contract file does not exist on disk: {physical_path}")

        run = LayoutExtractionRun.objects.create(
            version=version,
            pipeline_name=self.pipeline_name,
            status="RUNNING",
        )
        temporary_path = None
        try:
            decrypted_bytes = decrypt_pdf(physical_path.read_bytes())
            suffix = Path(contract_file.file_name or physical_path.name).suffix or ".pdf"
            handle = tempfile.NamedTemporaryFile(
                prefix=f"contract_{version.id}_",
                suffix=suffix,
                delete=False,
            )
            temporary_path = Path(handle.name)
            with handle:
                handle.write(decrypted_bytes)

            output_dir = Path(settings.MEDIA_ROOT) / "ai_extract" / "pages" / f"run_{run.id}"
            pipeline = PlanAVisionPipeline(output_dir=output_dir, media_root=settings.MEDIA_ROOT)
            result = pipeline.extract(temporary_path, document_key=f"contract_{version.id}")
            if not result.pages:
                raise ValueError("PlanA pipeline returned no document pages.")
            self._persist_result(run, result)
            self._index_plan_a_collections(run)
            return run
        except Exception as exc:
            run.status = "FAILED"
            run.error_message = str(exc)
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "error_message", "completed_at"])
            raise
        finally:
            if temporary_path and temporary_path.exists():
                try:
                    os.remove(temporary_path)
                except OSError:
                    pass

    @transaction.atomic
    def _persist_result(self, run: LayoutExtractionRun, result) -> None:
        contexts = []
        total_blocks = 0
        for page_result in result.pages:
            page = LayoutExtractionPage.objects.create(
                run=run,
                page_number=page_result.page_number,
                width=page_result.width,
                height=page_result.height,
                image_path=page_result.image_path,
                extracted_text=page_result.text,
            )
            blocks = [
                LayoutExtractionBlock(
                    page=page,
                    block_order=block.order,
                    layout_type=block.layout_type,
                    text=block.text,
                    bbox=block.bbox,
                    confidence=Decimal(str(round(max(0.0, min(1.0, block.confidence)), 4))),
                )
                for block in page_result.blocks
            ]
            LayoutExtractionBlock.objects.bulk_create(blocks)
            total_blocks += len(blocks)
            contexts.append(
                ContractContext(
                    version=run.version,
                    context_type="raw_text",
                    source=f"plan-a:page:{page_result.page_number}",
                    content=page_result.text,
                    relevance_score=Decimal("1.00") if page_result.text else Decimal("0.00"),
                )
            )

        ContractContext.objects.filter(version=run.version, context_type="raw_text").delete()
        ContractContext.objects.bulk_create(contexts)
        run.status = "COMPLETED"
        run.total_pages = len(result.pages)
        run.total_blocks = total_blocks
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "total_pages", "total_blocks", "completed_at"])

    def _index_plan_a_collections(self, run: LayoutExtractionRun) -> None:
        """Index the Surya text branch and ColPali visual branch concurrently.

        Index failures are recorded independently and never discard the page/layout
        extraction that has already completed successfully.
        """
        run.dense_index_status = "RUNNING"
        run.colpali_index_status = "RUNNING"
        run.dense_index_error = ""
        run.colpali_index_error = ""
        run.save(
            update_fields=[
                "dense_index_status",
                "colpali_index_status",
                "dense_index_error",
                "colpali_index_error",
            ]
        )

        try:
            indexer = PlanACollectionIndexer()
            indexed_run = LayoutExtractionRun.objects.select_related(
                "version__contract"
            ).get(pk=run.pk)
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="plan-a-index") as pool:
                dense_future = pool.submit(indexer.index_dense, indexed_run)
                colpali_future = pool.submit(indexer.index_colpali, indexed_run)
                dense_result = dense_future.result()
                colpali_result = colpali_future.result()
        except Exception as exc:
            failure = IndexResult("FAILED", error=str(exc))
            dense_result = failure
            colpali_result = failure

        run.dense_index_status = dense_result.status
        run.dense_points_count = dense_result.indexed_count
        run.dense_index_error = dense_result.error
        run.colpali_index_status = colpali_result.status
        run.colpali_points_count = colpali_result.indexed_count
        run.colpali_index_error = colpali_result.error
        run.save(
            update_fields=[
                "dense_index_status",
                "dense_points_count",
                "dense_index_error",
                "colpali_index_status",
                "colpali_points_count",
                "colpali_index_error",
            ]
        )

    @staticmethod
    def _physical_path(file_path: str) -> Path:
        relative = urllib.parse.unquote(file_path).lstrip("/\\")
        media_prefix = settings.MEDIA_URL.strip("/\\")
        if media_prefix and relative.startswith(f"{media_prefix}/"):
            relative = relative[len(media_prefix) + 1:]
        return Path(settings.MEDIA_ROOT) / relative
