from django.urls import path
from core.views import (
    dashboard_view,
    documents_view,
    document_detail_view,
    search_view,
    chat_view,
    experts_view,
    interview_view,
    knowledge_view,
    # APIs
    api_chat,
    api_start_interview,
    api_interview_reply,
    api_generate_knowledge,
    api_approve_knowledge
)

urlpatterns = [
    # Màn hình HTML
    path('', dashboard_view, name='dashboard'),
    path('documents/', documents_view, name='documents'),
    path('documents/<int:pk>/', document_detail_view, name='document_detail'),
    path('search/', search_view, name='search'),
    path('chat/', chat_view, name='chat'),
    path('experts/', experts_view, name='experts'),
    path('interviews/<int:pk>/', interview_view, name='interview_detail'),
    path('knowledge/', knowledge_view, name='knowledge'),

    # APIs
    path('api/chat/', api_chat, name='api_chat'),
    path('api/interviews/', api_start_interview, name='api_start_interview'),
    path('api/interviews/<int:pk>/reply/', api_interview_reply, name='api_interview_reply'),
    path('api/interviews/<int:pk>/generate-knowledge/', api_generate_knowledge, name='api_generate_knowledge'),
    path('api/knowledge/<int:pk>/approve/', api_approve_knowledge, name='api_approve_knowledge'),
]
