from django.contrib import admin
from .models import ContractSummary, Clause, ExtractedEntity


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
