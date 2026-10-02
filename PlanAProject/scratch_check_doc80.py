import os, django, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from documents.models import DocumentFile
doc = DocumentFile.objects.get(id=80)
chunks = json.loads(doc.extracted_json)

for i in range(10, 20):
    if i < len(chunks):
        c = chunks[i]
        print(f"--- Chunk {i} | Page {c.get('page_number')} | Type {c.get('layout_type')} | Image {c.get('image_url')} ---")
        print(repr(c.get('text')))
