from django.urls import path

from ai_extract.views import ai_internal_views

urlpatterns = [
    path('qwen/', ai_internal_views.qwen, name='ai_internal_qwen'),
    path('knowledge-search/', ai_internal_views.knowledge_search, name='ai_internal_knowledge_search'),
]
