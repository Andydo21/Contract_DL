from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('contracts/<int:contract_id>/', views.contract_detail, name='contract_detail'),
    path('api/contracts/', views.api_contracts_list, name='api_contracts_list'),
    path('api/contracts/<int:contract_id>/', views.api_contract_detail, name='api_contract_detail'),
    path('api/analyses/<int:analysis_id>/review/', views.api_submit_review, name='api_submit_review'),
    path('api/risks/', views.api_risks_list, name='api_risks_list'),
]
