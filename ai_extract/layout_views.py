"""Dedicated pages and API for the PlanA extraction pipeline."""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from contracts.models import Contract

from .layout_service import LayoutExtractionService
from .models import LayoutExtractionPage


def _image_url(image_path: str) -> str:
    if not image_path:
        return ""
    return f"/{settings.MEDIA_URL.strip('/')}/{image_path.lstrip('/')}"


@login_required
def pipeline_dashboard(request):
    contracts = Contract.objects.prefetch_related(
        "versions__files", "versions__layout_extraction_runs"
    ).order_by("-updated_at")
    cards = []
    for contract in contracts:
        version = contract.latest_version
        run = version.layout_extraction_runs.first() if version else None
        cards.append({"contract": contract, "version": version, "run": run})
    return render(request, "ai_extract/pipeline_dashboard.html", {"cards": cards})


@login_required
def contract_pipeline(request, contract_id: int):
    contract = get_object_or_404(
        Contract.objects.prefetch_related(
            "versions__files", "versions__layout_extraction_runs__pages__blocks"
        ),
        pk=contract_id,
    )
    version = contract.latest_version
    run = version.layout_extraction_runs.first() if version else None
    pages = list(run.pages.all()) if run else []
    for page in pages:
        page.preview_url = _image_url(page.image_path)
    return render(
        request,
        "ai_extract/contract_pipeline.html",
        {"contract": contract, "version": version, "run": run, "pages": pages},
    )


@login_required
def page_inspector(request, contract_id: int, page_number: int):
    contract = get_object_or_404(Contract, pk=contract_id)
    version = contract.latest_version
    run = version.layout_extraction_runs.filter(status="COMPLETED").first() if version else None
    page = get_object_or_404(
        LayoutExtractionPage.objects.prefetch_related("blocks"),
        run=run,
        page_number=page_number,
    )
    page.preview_url = _image_url(page.image_path)
    for block in page.blocks.all():
        if len(block.bbox) == 4:
            x1, y1, x2, y2 = block.bbox
            block.box_style = (
                f"left:{x1 / 10:.2f}%;top:{y1 / 10:.2f}%;"
                f"width:{max(0, x2 - x1) / 10:.2f}%;height:{max(0, y2 - y1) / 10:.2f}%;"
            )
        else:
            block.box_style = "display:none;"
    page_numbers = list(run.pages.order_by("page_number").values_list("page_number", flat=True))
    index = page_numbers.index(page_number)
    return render(
        request,
        "ai_extract/page_inspector.html",
        {
            "contract": contract,
            "version": version,
            "run": run,
            "page": page,
            "previous_page": page_numbers[index - 1] if index > 0 else None,
            "next_page": page_numbers[index + 1] if index + 1 < len(page_numbers) else None,
        },
    )


@require_POST
@login_required
def api_run_layout_extraction(request, contract_id: int):
    contract = get_object_or_404(Contract, pk=contract_id)
    version = contract.latest_version
    if not version:
        return JsonResponse({"success": False, "error": "Contract has no version."}, status=400)
    try:
        run = LayoutExtractionService().extract_version(version)
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
    return JsonResponse(
        {
            "success": True,
            "run_id": run.id,
            "status": run.status,
            "total_pages": run.total_pages,
            "total_blocks": run.total_blocks,
            "dense_index_status": run.dense_index_status,
            "dense_points_count": run.dense_points_count,
            "colpali_index_status": run.colpali_index_status,
            "colpali_points_count": run.colpali_points_count,
        }
    )
