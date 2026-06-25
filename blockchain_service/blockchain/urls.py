from django.urls import path
from . import views

urlpatterns = [
    path('health/', views.health_check, name='health_check'),
    path('certificates/create/', views.create_certificate, name='create_certificate'),
    path('proofs/generate/', views.generate_proof, name='generate_proof'),
    path('proofs/anchor/', views.anchor_proof, name='anchor_proof'),
    path('proofs/verify/', views.verify_proof, name='verify_proof'),
    path('signatures/create/', views.sign_step, name='sign_step'),
]
