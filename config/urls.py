from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from ai.ai_extract.views import layout_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('contract.contracts.urls')),
    path('', include('contract.accounts.urls')),
    path('', include('ai.analysis.urls')),
    path('', include('ai.legal_ai.urls')),
    path('', include('ai.ai_summary.urls')),
    path('', include('blockchain.ledger.urls')),
    path('', include('contract.administration.urls')),
    # Last: its workflow-service proxy routes catch every other workflows/... path.
    path('', include('contract.approvals.urls')),
    path('api/ai/', include('ai.ai_extract.urls')),
    # Answered only inside the AI service container (AI_SERVICE_ROLE=ai), with the shared token.
    path('internal/ai/', include('ai.ai_extract.internal_urls')),
    # The source page of a citation (page image with its blocks); evidence links open it. No other AI Extract page.
    path(
        'ai-extract/contracts/<int:contract_id>/pages/<int:page_number>/',
        layout_views.page_inspector,
        name='ai_extract_page',
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
