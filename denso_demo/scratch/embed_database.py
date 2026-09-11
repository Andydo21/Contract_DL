import os
import sys
import json
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from sentence_transformers import SentenceTransformer
from core.models import Chunk, Case, Knowledge

print("Loading local paraphrase-multilingual-MiniLM-L12-v2 model...")
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

print("\n1. Embedding Chunks...")
chunks = Chunk.objects.all()
for c in chunks:
    text = f"{c.chunk_type} {c.content}"
    vec = model.encode(text).tolist()
    c.embedding_json = json.dumps(vec)
    c.save(update_fields=['embedding_json'])
print(f"-> Successfully embedded {chunks.count()} chunks.")

print("\n2. Embedding Cases...")
cases = Case.objects.all()
for cs in cases:
    text = f"{cs.title} {cs.machine} {cs.symptom} {cs.root_cause} {cs.solution}"
    vec = model.encode(text).tolist()
    cs.embedding_json = json.dumps(vec)
    cs.save(update_fields=['embedding_json'])
print(f"-> Successfully embedded {cases.count()} cases.")

print("\n3. Embedding Knowledge Rules...")
rules = Knowledge.objects.all()
for k in rules:
    text = f"{k.title} {k.content}"
    vec = model.encode(text).tolist()
    k.embedding_json = json.dumps(vec)
    k.save(update_fields=['embedding_json'])
print(f"-> Successfully embedded {rules.count()} knowledge rules.")

print("\n=== All Database Entities Embedded Successfully! ===")
