from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from ai_extract.views import layout_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('contracts.urls')),
    path('', include('contracts.views.knowledge_urls')),
    path('', include('NewIdea.urls')),
    path('', include('contracts.views.ledger_urls')),
    path('api/ai/', include('ai_extract.urls')),
    path('ai-extract/', layout_views.pipeline_dashboard, name='ai_extract_pipeline'),
    path('ai-extract/summary-lab/', layout_views.summary_lab, name='ai_summary_lab'),
    path('ai-extract/contracts/<int:contract_id>/', layout_views.contract_pipeline, name='ai_extract_contract'),
    path(
        'ai-extract/contracts/<int:contract_id>/pages/<int:page_number>/',
        layout_views.page_inspector,
        name='ai_extract_page',
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

