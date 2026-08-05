from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.health_check, name='health_check'),
    path('stats/', views.get_stats, name='get_stats'),
    path('certificates/create/', views.create_certificate, name='create_certificate'),
    path('proofs/generate/', views.generate_proof, name='generate_proof'),
    path('proofs/anchor/', views.anchor_proof, name='anchor_proof'),
    path('proofs/verify/', views.verify_proof, name='verify_proof'),
    path('signatures/create/', views.sign_step, name='sign_step'),
    
    # New patterns
    path('hash/', views.generate_proof, name='hash'),
    path('sign/', views.sign_step, name='sign'),
    path('verify/', views.verify_proof, name='verify'),
    path('anchor/', views.anchor_proof, name='anchor'),
    path('history/<int:version_id>/', views.get_history, name='get_history'),
    path('transaction/<str:tx_hash>/', views.get_transaction, name='get_transaction'),
    path('proof/<int:version_id>/', views.get_proof, name='get_proof'),
    path('certificate/<int:user_id>/', views.get_certificate, name='get_certificate'),
    path('company/register/', views.register_company, name='register_company'),
    path('user/register/', views.register_user, name='register_user'),
]
