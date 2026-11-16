from django.urls import path, include
from ai.ai_extract.views import layout_views
urlpatterns = [
    path('', include('contract.contracts.urls')),
    path('', include('contract.accounts.urls')),
    path('', include('ai.analysis.urls')),
    path('', include('blockchain.ledger.urls')),
    path('', include('contract.administration.urls')),
    path('', include('contract.approvals.urls')),
    path('', include('ai.legal_ai.urls')),
    path('api/ai/', include('ai.ai_extract.urls')),
    path('ai-extract/contracts/<int:contract_id>/pages/<int:page_number>/', layout_views.page_inspector, name='ai_extract_page'),
]
