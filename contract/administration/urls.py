from django.urls import path
from contract.administration.views import administration_views as admin_views

urlpatterns = [
    path('admin-dashboard/', admin_views.admin_dashboard, name='admin_dashboard'),
    path('api/admin/stats/', admin_views.api_admin_stats, name='api_admin_stats'),
    path('api/admin/users/<int:user_id>/delete/', admin_views.api_admin_delete_user, name='api_admin_delete_user'),
    path('api/admin/users/<int:user_id>/retry/', admin_views.api_admin_retry_user, name='api_admin_retry_user'),
    path('api/admin/config/ocr/', admin_views.api_admin_toggle_ocr, name='api_admin_toggle_ocr'),
    path('api/admin/legal/', admin_views.api_admin_legal_documents, name='api_admin_legal_documents'),
    path('api/admin/legal/<int:document_id>/switch/', admin_views.api_admin_switch_legal, name='api_admin_switch_legal'),
]
