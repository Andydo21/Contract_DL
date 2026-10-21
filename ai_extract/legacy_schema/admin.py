from django.contrib import admin
from .models import DocumentFile

@admin.register(DocumentFile)
class DocumentFileAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_name', 'extension', 'category', 'formatted_size', 'uploaded_at')
    list_filter = ('category', 'extension', 'uploaded_at')
    search_fields = ('original_name', 'description')
    ordering = ('-uploaded_at',)
