from django.urls import path
from . import views
from .views import layout_views

urlpatterns = [
    path(
        "contracts/<int:contract_id>/layout-extract/",
        layout_views.api_run_layout_extraction,
        name="layout_extract",
    ),
    # ── Summarize ──────────────────────────────────────────────────────────
    # POST  /api/ai/contracts/<id>/summarize/   → run summarize & save
    path(
        "contracts/<int:contract_id>/summarize/",
        views.api_summarize_contract,
        name="ai_summarize_contract",
    ),
    # GET   /api/ai/contracts/<id>/summary/     → retrieve saved summary
    path(
        "contracts/<int:contract_id>/summary/",
        views.api_get_summary,
        name="ai_get_summary",
    ),

    # ── Summary Lab (test screen at /ai-extract/summary-lab/) ───────────────
    path("summary-lab/health/", views.api_summary_lab_health, name="ai_summary_lab_health"),
    path("summary-lab/text/", views.api_summary_lab_text, name="ai_summary_lab_text"),
    path("summary-lab/compare/", views.api_summary_lab_compare, name="ai_summary_lab_compare"),
    path("summary-lab/contracts/<int:contract_id>/", views.api_summary_lab_contract, name="ai_summary_lab_contract"),

    # ── Extract Entities ────────────────────────────────────────────────────
    # POST  /api/ai/contracts/<id>/extract-entities/  → run per-clause extraction & save
    path(
        "contracts/<int:contract_id>/extract-entities/",
        views.api_extract_entities,
        name="ai_extract_entities",
    ),
    # GET   /api/ai/contracts/<id>/entities/          → list saved entities
    path(
        "contracts/<int:contract_id>/entities/",
        views.api_get_entities,
        name="ai_get_entities",
    ),

    # ── Free-text extraction (no contract binding) ──────────────────────────
    # POST  /api/ai/extract-from-text/
    path(
        "extract-from-text/",
        views.api_extract_from_text,
        name="ai_extract_from_text",
    ),

    # ── Extract Clauses ─────────────────────────────────────────────────────
    # POST  /api/ai/contracts/<id>/extract-clauses/  → AI clause splitting & save
    path(
        "contracts/<int:contract_id>/extract-clauses/",
        views.api_extract_clauses,
        name="ai_extract_clauses",
    ),
    # GET   /api/ai/contracts/<id>/clauses/           → list saved clauses
    path(
        "contracts/<int:contract_id>/clauses/",
        views.api_get_clauses,
        name="ai_get_clauses",
    ),

    # ── Free-text extraction (no contract binding) ──────────────────────────
]
