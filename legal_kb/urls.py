from django.urls import path

from . import views

urlpatterns = [
    path('search/', views.api_search, name='legal_search'),
    path('article/', views.api_article, name='legal_article'),
    path('documents/', views.api_documents, name='legal_documents'),
]
