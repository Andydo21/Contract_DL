import os
import sys
import django
from pathlib import Path

# Setup Django Environment
project_dir = r"d:\Django_project\DensoFactoryHack2026\PlanAProject"
os.chdir(project_dir)
sys.path.insert(0, project_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from documents.models import DocumentFile
from documents.services.colpali_service import ColPaliVisualIndexer
from documents.services.layout_extractor import LayoutLMExtractor
from documents.services.vector_db_service import QdrantVectorDBService
from django.core.files import File

def ingest_documents_from_folder(folder_path):
    folder = Path(folder_path)
    if not folder.exists():
        print(f"Error: Folder path {folder_path} does not exist!")
        return

    supported_extensions = ['.pdf', '.png', '.jpg', '.jpeg', '.docx', '.xlsx']
    files_to_process = [f for f in folder.rglob('*') if f.suffix.lower() in supported_extensions and f.is_file()]

    print(f"=== Found {len(files_to_process)} document/image files to ingest ===")
    
    colpali_indexer = None
    try:
        colpali_indexer = ColPaliVisualIndexer()
        print("[INFO] Initialized ColPali Visual Indexer")
    except Exception as e:
        print("[WARN] ColPali Visual Indexer initialization error:", str(e))

    layout_extractor = None
    try:
        layout_extractor = LayoutLMExtractor()
        print("[INFO] Initialized LayoutLM Extractor")
    except Exception as e:
        print("[WARN] LayoutLM Extractor initialization error:", str(e))

    vector_db_service = None
    try:
        vector_db_service = QdrantVectorDBService()
        print("[INFO] Initialized Qdrant Vector DB Service")
    except Exception as e:
        print("[WARN] Qdrant Vector DB Service initialization error:", str(e))

    successful = 0
    failed = 0

    for idx, file_path in enumerate(files_to_process, 1):
        print(f"\n[{idx}/{len(files_to_process)}] Processing: {file_path.name}...")
        try:
            # Check if file already exists in DB
            existing_doc = DocumentFile.objects.filter(original_name=file_path.name).first()
            if existing_doc:
                doc = existing_doc
                print(f"  -> File '{file_path.name}' already exists in DB (ID: {doc.id})")
            else:
                with open(file_path, 'rb') as f:
                    django_file = File(f, name=file_path.name)
                    extension = file_path.suffix.lower()
                    category = DocumentFile.detect_category(extension)
                    file_size = file_path.stat().st_size
                    mime_type = 'application/pdf' if extension == '.pdf' else ('image/png' if extension == '.png' else 'application/octet-stream')
                    
                    doc = DocumentFile.objects.create(
                        file=django_file,
                        original_name=file_path.name,
                        extension=extension,
                        category=category,
                        file_size=file_size,
                        mime_type=mime_type,
                        description=f"Auto-ingested from {file_path.parent.name}"
                    )
                print(f"  -> Created DB Record ID: {doc.id}")

            # 1. Run ColPali Indexer
            if colpali_indexer:
                try:
                    res = colpali_indexer.index_document_colpali(doc)
                    print(f"  [ColPali] Indexed {res.get('indexed_patches', 0)} visual patches")
                except Exception as col_err:
                    print(f"  [ColPali Error] {col_err}")

            # 2. Run LayoutLM / Surya Layout Extraction & Qdrant Text Vector DB Indexing
            if layout_extractor and vector_db_service:
                try:
                    ext_res = layout_extractor.extract_document(doc)
                    chunks = ext_res if isinstance(ext_res, list) else (ext_res.get('chunks', []) if isinstance(ext_res, dict) else [])
                    if chunks:
                        v_res = vector_db_service.index_document_chunks(doc, chunks)
                        indexed_cnt = v_res if isinstance(v_res, int) else (v_res.get('indexed_chunks', 0) if isinstance(v_res, dict) else 0)
                        
                        doc.is_extracted = True
                        doc.extracted_chunks_count = len(chunks)
                        doc.is_vector_indexed = True
                        doc.vector_points_count = indexed_cnt
                        doc.save()
                        
                        print(f"  [LayoutLM & Qdrant] Extracted {len(chunks)} chunks, indexed {indexed_cnt} vectors (DB Status Updated!)")
                except Exception as ext_err:
                    print(f"  [LayoutLM Error] {ext_err}")

            successful += 1

        except Exception as file_err:
            print(f"  [FAILED] Could not process {file_path.name}: {file_err}")
            failed += 1

    print(f"\n==========================================")
    print(f"INGESTION COMPLETE: Successful = {successful}, Failed = {failed}")
    print(f"==========================================")

if __name__ == '__main__':
    target_dir = r"d:\Django_project\DensoFactoryHack2026\data\documents"
    ingest_documents_from_folder(target_dir)
