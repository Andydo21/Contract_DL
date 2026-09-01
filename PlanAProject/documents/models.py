import os
import mimetypes
import json
from django.db import models

class DocumentFile(models.Model):
    """
    Bảng dữ liệu 'documents_file' lưu trữ tài liệu + trạng thái Extraction LayoutLM & Vector DB (Qdrant).
    Hỗ trợ đầy đủ các định dạng: PDF, DOCX, XLSX, PPTX, TXT, LOG, PNG, JPG, ...
    """
    CATEGORY_CHOICES = (
        ('pdf', 'PDF Document'),
        ('docx', 'Word Document (.docx / .doc)'),
        ('xlsx', 'Excel / CSV (.xlsx / .csv)'),
        ('pptx', 'PowerPoint (.pptx / .ppt)'),
        ('text', 'Text / Code / Log (.txt / .md / .json)'),
        ('image', 'Hình ảnh / Sơ đồ (.png / .jpg / .webp)'),
        ('other', 'Định dạng khác'),
    )

    file = models.FileField(upload_to='uploaded_documents/%Y/%m/%d/', verbose_name="File lưu trữ")
    original_name = models.CharField(max_length=255, verbose_name="Tên file gốc")
    extension = models.CharField(max_length=20, verbose_name="Đuôi file")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', verbose_name="Phân loại")
    file_size = models.BigIntegerField(verbose_name="Kích thước (Bytes)")
    mime_type = models.CharField(max_length=100, blank=True, null=True, verbose_name="MIME Type")
    description = models.TextField(blank=True, null=True, verbose_name="Mô tả tài liệu")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tải lên")

    # LayoutLM Extraction & Vector DB Fields
    is_extracted = models.BooleanField(default=False, verbose_name="Đã trích xuất LayoutLM (Text + Ảnh)")
    is_vector_indexed = models.BooleanField(default=False, verbose_name="Đã lưu vào Vector DB (Qdrant)")
    extracted_chunks_count = models.IntegerField(default=0, verbose_name="Số lượng Chunks")
    vector_points_count = models.IntegerField(default=0, verbose_name="Số lượng Vector Points")
    extracted_json = models.TextField(blank=True, null=True, verbose_name="Dữ liệu Layout JSON")

    class Meta:
        ordering = ['-uploaded_at']
        db_table = 'documents_file'
        verbose_name = 'Tài liệu File'
        verbose_name_plural = 'Danh sách Tài liệu File'

    def __str__(self):
        return f"{self.original_name} ({self.formatted_size})"

    @property
    def formatted_size(self):
        size = self.file_size or 0
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"

    @property
    def badge_color(self):
        mapping = {
            'pdf': 'pdf-badge',
            'docx': 'docx-badge',
            'xlsx': 'xlsx-badge',
            'pptx': 'pptx-badge',
            'text': 'text-badge',
            'image': 'image-badge',
            'other': 'other-badge',
        }
        return mapping.get(self.category, mapping['other'])

    def get_extracted_chunks(self):
        if self.extracted_json:
            try:
                return json.loads(self.extracted_json)
            except Exception:
                return []
        return []

    @staticmethod
    def detect_category(extension):
        ext = extension.lower().strip('.')
        if ext in ['pdf']:
            return 'pdf'
        elif ext in ['docx', 'doc', 'odt']:
            return 'docx'
        elif ext in ['xlsx', 'xls', 'csv', 'tsv']:
            return 'xlsx'
        elif ext in ['pptx', 'ppt']:
            return 'pptx'
        elif ext in ['txt', 'md', 'json', 'log', 'xml', 'py', 'js', 'html', 'css']:
            return 'text'
        elif ext in ['png', 'jpg', 'jpeg', 'webp', 'svg', 'bmp', 'gif', 'tiff']:
            return 'image'
        return 'other'
