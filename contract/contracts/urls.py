from django.urls import path
from contract.contracts.views import contract_views, document_download_views

urlpatterns = [
    path('', contract_views.dashboard, name='dashboard'),
    path('contracts/<int:contract_id>/', contract_views.contract_detail, name='contract_detail'),
    path('api/contracts/', contract_views.api_contracts_list, name='api_contracts_list'),
    path('api/contracts/create/', contract_views.api_create_contract, name='api_create_contract'),
    path('api/contracts/<int:contract_id>/', contract_views.api_contract_detail, name='api_contract_detail'),
    path('api/contracts/<int:contract_id>/versions/', contract_views.api_contract_versions, name='api_contract_versions'),
    path('api/contracts/<int:contract_id>/parties/', contract_views.api_contract_parties, name='api_contract_parties'),
    path('api/contracts/<int:contract_id>/tags/', contract_views.api_contract_tags, name='api_contract_tags'),
    path('api/contracts/<int:contract_id>/legal/', contract_views.api_contract_legal, name='api_contract_legal'),
    path('api/contracts/files/<int:file_id>/download/', document_download_views.api_download_file, name='api_download_file'),
    path('api/contracts/<int:contract_id>/download-pdf/', document_download_views.api_download_contract_pdf,
         name='api_download_contract_pdf'),
]
