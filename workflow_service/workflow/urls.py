from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),

    # Workflow
    path('workflows/', views.create_workflow, name='create_workflow'),
    path('workflows/all/', views.list_all_workflows, name='list_all_workflows'),
    path('workflows/<int:version_id>/', views.get_workflow, name='get_workflow'),
    path('workflows/detail/<int:workflow_id>/', views.get_workflow_by_id_view, name='get_workflow_by_id_view'),
    path('workflows/steps/<int:step_id>/approve/', views.approve_step, name='approve_step'),

    # Key Management
    path('keys/', views.key_list_create, name='key_list_create'),
    path('keys/<int:key_id>/rotate/', views.key_rotate, name='key_rotate'),
    path('keys/<int:key_id>/revoke/', views.key_revoke, name='key_revoke'),
    path('keys/active/<int:company_id>/', views.key_active, name='key_active'),

    # Digital Signatures
    path('signatures/', views.signature_list, name='signature_list'),
]
