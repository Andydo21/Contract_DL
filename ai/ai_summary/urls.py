from django.urls import path

from ai.ai_summary.views import summary_views

urlpatterns = [
    path('api/ai/summary/summarize/', summary_views.summarize_contract, name='ai_summary_summarize'),
    path('api/ai/summary/compare/', summary_views.compare_versions, name='ai_summary_compare'),
    path('api/ai/summary/prepare/', summary_views.prepare_contract, name='ai_summary_prepare'),
    path('api/ai/summary/read/', summary_views.read_file, name='ai_summary_read'),
    path('api/ai/summary/sections/', summary_views.file_sections, name='ai_summary_sections'),
    path('api/ai/summary/summarize-file/', summary_views.summarize_file, name='ai_summary_summarize_file'),
    path('api/ai/summary/compare-files/', summary_views.compare_files, name='ai_summary_compare_files'),
    path('api/ai/summary/health/', summary_views.health_check, name='ai_summary_health'),
]
