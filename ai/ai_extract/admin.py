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


def start_background_job(modeladmin, request, contract_ids, mode):
    """Queue the selected documents for one background job (extract: read the files again; rerun: rebuild tree,
    links and vectors from the stored reading). Other work on the site goes on while it runs."""
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied
    from ai.ai_extract.services import bulk_service
    try:
        job = bulk_service.start(request.user, list(contract_ids), mode)
    except (ValueError, PermissionDenied) as error:
        modeladmin.message_user(request, str(error), messages.ERROR)
        return None
    label = 'trích xuất lại' if mode == 'extract' else 'chạy lại'
    modeladmin.message_user(request, f"Đã xếp hàng {label} {len(job['items'])} văn bản (job {job['id']}), chạy ngầm "
                            "lần lượt từng văn bản; cột Trích xuất cho biết kết quả khi xong.", messages.SUCCESS)
    return job


def extraction_label(contract):
    from ai.ai_extract.repositories import layout_repository
    version = contract.latest_version if contract else None
    run = layout_repository.latest_run(version) if version else None
    return f"{run.status} · {run.started_at:%d/%m %H:%M}" if run else "chưa trích xuất"


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
    list_display = ("number_label", "short_title", "type_label", "status_label", "applied", "toggle", "effective_label",
                    "extraction", "graph")
    list_display_links = ("number_label",)
    list_filter = ("status", "doc_type", "public")
    search_fields = ("number", "title")
    readonly_fields = ("status_before_off",)
    ordering = ("pk",)
    actions = ("turn_off", "turn_on", "bulk_extract", "bulk_rerun")

    @admin.display(description="Số hiệu", ordering="number")
    def number_label(self, document):
        return document.number or "—"

    @admin.display(description="Tên văn bản", ordering="title")
    def short_title(self, document):
        title = document.title or ""
        return title if len(title) <= 90 else title[:89].rstrip() + "…"

    @admin.display(description="Loại", ordering="doc_type")
    def type_label(self, document):
        return document.doc_type

    @admin.display(description="Tình trạng", ordering="status")
    def status_label(self, document):
        return document.status

    @admin.display(description="Ngày hiệu lực", ordering="effective_on")
    def effective_label(self, document):
        return f"{document.effective_on:%d/%m/%Y}" if document.effective_on else "—"

    @admin.display(description="Bật / tắt")
    def toggle(self, document):
        """One-click switch for this row: it runs the same turn_off / turn_on action on this text alone."""
        from django.utils.html import format_html
        off = document.status != LegalDocument.REPEALED
        script = ("var f=this.form;f.querySelectorAll('input.action-select').forEach(function(c){c.checked=false});"
                  "this.closest('tr').querySelector('input.action-select').checked=true;"
                  "f.elements['action'].value='%s';f.submit();" % ("turn_off" if off else "turn_on"))
        return format_html('<button type="button" class="button" style="padding:4px 10px;white-space:nowrap" onclick="{}">{}</button>',
                           script, "Tắt" if off else "Bật")

    @admin.display(description="Dùng làm căn cứ", boolean=True)
    def applied(self, document):
        """Whether search and risk analysis read this text now (the same rule as legal_contracts)."""
        from ai.legal_ai.repositories import knowledge_repository
        return knowledge_repository.legal_applied(document)

    def set_status(self, request, queryset, status, label):
        from django.contrib import messages
        from ai.legal_ai.repositories import knowledge_repository
        changed = 0
        for document in queryset:
            # Off keeps the status the text had; on gives it back (a partly repealed or not-yet-in-force text stays so).
            if knowledge_repository.switch_legal(document, on=status != LegalDocument.REPEALED):
                self.log_change(request, document, f'{label}: tình trạng → {document.status}')
                changed += 1
        self.message_user(request, f'{label} {changed} văn bản. Có tác dụng ngay với các lần tìm kiếm '
                                   'và phân tích rủi ro sau; kết quả đã phân tích trước đó giữ nguyên.', messages.SUCCESS)

    @admin.action(description="Tắt các văn bản đã chọn (Hết hiệu lực: giữ trong kho, không dùng làm căn cứ)")
    def turn_off(self, request, queryset):
        self.set_status(request, queryset, LegalDocument.REPEALED, 'Đã tắt')

    @admin.action(description="Bật lại các văn bản đã tắt (trả về tình trạng trước khi tắt)")
    def turn_on(self, request, queryset):
        self.set_status(request, queryset, LegalDocument.FULLY_IN_FORCE, 'Đã bật')

    def latest_run(self, document):
        from ai.ai_extract.repositories import layout_repository
        return layout_repository.latest_run(document.contract.latest_version, completed=True)

    @admin.display(description="Trích xuất")
    def extraction(self, document):
        return extraction_label(document.contract)

    @admin.action(description="Trích xuất lại các văn bản đã chọn (đọc lại tệp, chạy ngầm)")
    def bulk_extract(self, request, queryset):
        start_background_job(self, request, queryset.order_by("pk").values_list("contract_id", flat=True), "extract")

    @admin.display(description="Đồ thị")
    def graph(self, document):
        run = self.latest_run(document)
        return ((run.structure or {}).get("graph_index") or {}).get("status", "—") if run else "—"

    @admin.action(description="Chạy lại hàng loạt các văn bản đã chọn (cây mục, quan hệ, vector; không OCR lại)")
    def bulk_rerun(self, request, queryset):
        # Each document links only to those already done in the job; the later ones link back on their turn.
        start_background_job(self, request, queryset.order_by("pk").values_list("contract_id", flat=True), "rerun")
