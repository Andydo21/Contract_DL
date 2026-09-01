from rest_framework import serializers
from .models import DocumentFile

class DocumentFileSerializer(serializers.ModelSerializer):
    formatted_size = serializers.ReadOnlyField()
    badge_color = serializers.ReadOnlyField()
    file_url = serializers.SerializerMethodField()
    extracted_chunks = serializers.SerializerMethodField()

    class Meta:
        model = DocumentFile
        fields = [
            'id', 'file', 'original_name', 'extension', 
            'category', 'file_size', 'formatted_size', 
            'mime_type', 'description', 'uploaded_at', 
            'badge_color', 'file_url',
            'is_extracted', 'is_vector_indexed',
            'extracted_chunks_count', 'vector_points_count',
            'extracted_chunks'
        ]
        read_only_fields = ['original_name', 'extension', 'category', 'file_size', 'mime_type', 'uploaded_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and hasattr(obj.file, 'url'):
            if request is not None:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

    def get_extracted_chunks(self, obj):
        return obj.get_extracted_chunks()
