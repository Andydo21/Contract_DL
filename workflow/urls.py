from django.urls import path
from . import views

urlpatterns = [
    # ── Page routes ──────────────────────────────────────────────────────
    path('', views.workflow_dashboard, name='workflow_dashboard'),
    path('recommend/', views.workflow_recommendation, name='workflow_recommendation'),
    path('builder/', views.workflow_builder, name='workflow_builder'),
    path('templates/', views.workflow_templates, name='workflow_templates'),

    # ── Existing API routes ───────────────────────────────────────────────
    path('api/recommend/', views.api_workflow_recommend, name='api_workflow_recommend'),
    path('api/build/', views.api_workflow_build, name='api_workflow_build'),

    # ── Template API routes ───────────────────────────────────────────────
    path('api/templates/', views.api_templates_list, name='api_templates_list'),
    path('api/templates/import/', views.api_template_import, name='api_template_import'),
    path('api/templates/<str:template_id>/', views.api_template_detail, name='api_template_detail'),
    path('api/templates/<str:template_id>/duplicate/', views.api_template_duplicate, name='api_template_duplicate'),
    path('api/templates/<str:template_id>/delete/', views.api_template_delete, name='api_template_delete'),
]
