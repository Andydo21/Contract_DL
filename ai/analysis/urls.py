from django.urls import path
from ai.analysis.views import analysis_views, risk_views

urlpatterns = [
    path('analyses/', analysis_views.analysis_history, name='analysis_history'),
    path('api/contracts/<int:contract_id>/analyze/', analysis_views.api_analyze_contract, name='api_analyze_contract'),
    path('api/analyses/', analysis_views.api_analyses_list, name='api_analyses_list'),
    path('api/analyses/<int:analysis_id>/review/', analysis_views.api_submit_review, name='api_submit_review'),
    path('api/risks/', risk_views.api_risks_list, name='api_risks_list'),
]
