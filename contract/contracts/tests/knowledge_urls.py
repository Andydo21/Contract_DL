"""Test routing for new endpoints; source links are reversed, not fetched."""
from django.http import HttpResponse
from django.urls import path
from blockchain.ledger.urls import urlpatterns as ledger_urls
from ai.legal_ai.urls import urlpatterns as newidea_urls

urlpatterns = ledger_urls + newidea_urls + [
    path('contracts/<int:contract_id>/', lambda request, **kwargs: HttpResponse(), name='contract_detail'),
    path('ai-extract/contracts/<int:contract_id>/pages/<int:page_number>/',
         lambda request, **kwargs: HttpResponse(), name='ai_extract_page'),
]
