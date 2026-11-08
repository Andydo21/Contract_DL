from django.contrib import admin
from .models import (
    ContractSummary,
    Clause,
    ExtractedEntity,
    LayoutExtractionRun,
    LayoutExtractionPage,
    LayoutExtractionBlock,
    LegalDocument,
)


@admin.register(ContractSummary)
class ContractSummaryAdmin(admin.ModelAdmin):
    list_display = ("__str__", "model_id", "created_at", "updated_at")
    list_filter = ("model_id",)
    search_fields = (
        "version__contract__contract_code",
        "version__contract__title",
        "summary",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(Clause)
class ClauseAdmin(admin.ModelAdmin):
    list_display = ("clause_title", "version", "clause_type")
    list_filter = ("clause_type", "version__contract")
    search_fields = ("clause_title", "clause_content")


@admin.register(ExtractedEntity)
class ExtractedEntityAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "entity_value", "clause", "confidence_score")
    list_filter = ("entity_type",)
    search_fields = ("entity_value", "clause__clause_title")


@admin.register(LayoutExtractionRun)
class LayoutExtractionRunAdmin(admin.ModelAdmin):
    list_display = (
        "version", "pipeline_name", "status", "total_pages", "total_blocks",
        "dense_index_status", "dense_points_count", "colpali_index_status",
        "colpali_points_count", "started_at",
    )
    list_filter = ("status", "dense_index_status", "colpali_index_status", "pipeline_name")
    readonly_fields = ("started_at", "completed_at")


@admin.register(LayoutExtractionPage)
class LayoutExtractionPageAdmin(admin.ModelAdmin):
    list_display = ("run", "page_number", "width", "height")
    list_filter = ("run__status",)


@admin.register(LayoutExtractionBlock)
class LayoutExtractionBlockAdmin(admin.ModelAdmin):
    list_display = ("page", "block_order", "layout_type", "confidence")
    list_filter = ("layout_type",)


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    """The legal texts of the knowledge base, with a bulk rerun of their graph, links and vectors."""
    list_display = ("number", "title", "doc_type", "status", "effective_on", "extraction", "graph")
    list_filter = ("status", "doc_type", "public")
    search_fields = ("number", "title")
    ordering = ("pk",)
    actions = ("bulk_rerun",)

    def latest_run(self, document):
        from ai_extract.repositories import layout_repository
        return layout_repository.latest_run(document.contract.latest_version, completed=True)

    @admin.display(description="Trích xuất")
    def extraction(self, document):
        run = self.latest_run(document)
        return f"run {run.pk} · {run.status}" if run else "chưa trích xuất"

    @admin.display(description="Đồ thị")
    def graph(self, document):
        run = self.latest_run(document)
        return ((run.structure or {}).get("graph_index") or {}).get("status", "—") if run else "—"

    @admin.action(description="Chạy lại hàng loạt các văn bản đã chọn (cây mục, quan hệ, vector; không OCR lại)")
    def bulk_rerun(self, request, queryset):
        from django.contrib import messages
        from django.core.exceptions import PermissionDenied
        from ai_extract.services import bulk_service
        ids = list(queryset.order_by("pk").values_list("contract_id", flat=True))
        try:
            job = bulk_service.start(request.user, ids, "rerun")
        except (ValueError, PermissionDenied) as error:
            self.message_user(request, str(error), messages.ERROR)
            return
        self.message_user(request, f"Đã bắt đầu chạy lại {len(job['items'])} văn bản (job {job['id']}). "
                          "Mỗi văn bản chỉ nối với các văn bản đã xong trong lượt; tiến độ xem ở /ai-extract/ "
                          f"hoặc /api/ai/bulk/{job['id']}/.", messages.SUCCESS)
