from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('api/documents/', views.DocumentListCreateAPIView.as_view(), name='api-document-list-create'),
    path('api/documents/<int:pk>/', views.DocumentDetailAPIView.as_view(), name='api-document-detail'),
    path('api/documents/<int:pk>/extract/', views.ExtractLayoutAPIView.as_view(), name='api-document-extract'),
    path('api/documents/<int:pk>/vectorize/', views.VectorizeDocumentAPIView.as_view(), name='api-document-vectorize'),
    path('api/documents/vector-search/', views.VectorSearchAPIView.as_view(), name='api-vector-search'),
    path('api/documents/<int:pk>/colpali-index/', views.ColPaliIndexAPIView.as_view(), name='api-colpali-index'),
    path('api/documents/colpali-search/', views.ColPaliSearchAPIView.as_view(), name='api-colpali-search'),
    path('api/documents/rag-chat/', views.RAGChatbotAPIView.as_view(), name='api-rag-chat'),
    path('api/documents/<int:pk>/preview/', views.DocumentPreviewView.as_view(), name='api-document-preview'),
    path('documents/<int:pk>/download/', views.DocumentDownloadView.as_view(), name='document-download'),
    path('documents/<int:pk>/preview/', views.DocumentPreviewView.as_view(), name='document-preview'),
]

