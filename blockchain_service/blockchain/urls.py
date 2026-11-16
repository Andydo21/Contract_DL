from django.urls import path
from . import views, book_views

urlpatterns = [
    # The ledger book: the contract web files here what Fabric confirmed (service token, see book_views).
    path('book/operations/', book_views.record_operation, name='book_operation'),
    path('book/verifications/', book_views.record_verification, name='book_verification'),
    path('book/credentials/', book_views.record_credential, name='book_credential'),
    path('book/users/', book_views.register_user, name='book_user'),
    path('health/', views.health_check, name='health_check'),
]
