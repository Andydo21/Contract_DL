from django.contrib import admin
from .models import ContractSummary


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
