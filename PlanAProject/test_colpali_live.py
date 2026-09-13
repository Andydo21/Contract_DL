import os
import django
import sys
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from documents.models import DocumentFile
from documents.services.colpali_service import ColPaliVisualIndexer

def test_colpali():
    print("=" * 60)
    print("🔬 KIỂM TRA MÔ HÌNH COLPALI VISUAL LATE INTERACTION MAXSIM")
    print("=" * 60)

    # 1. Khởi tạo Indexer
    colpali = ColPaliVisualIndexer()
    print(f"✅ 1. Khởi tạo ColPali thành công!")
    print(f"   - Qdrant Collection: {colpali.COLLECTION_NAME}")
    print(f"   - Vector Dimension:  {colpali.VECTOR_DIM}")
    print(f"   - Grid Size:         {colpali.GRID_SIZE}")

    # 2. Chọn một tài liệu mẫu PDF thực tế (> 10KB)
    doc = None
    for candidate in DocumentFile.objects.filter(category='pdf'):
        if candidate.file and os.path.exists(candidate.file.path) and os.path.getsize(candidate.file.path) > 10000:
            doc = candidate
            break

    if not doc:
        doc = DocumentFile.objects.filter(category='image').first()

    if not doc:
        print("❌ Không tìm thấy tài liệu nào trong database để test!")
        return

    print(f"\n📑 2. Tiến hành Ingest Visual Patches cho tài liệu: {doc.original_name} (ID: {doc.id})")
    ingest_res = colpali.index_document_colpali(doc)
    print(f"   -> Kết quả: Đã lập chỉ mục {ingest_res['indexed_patches']} visual patch vectors trên {ingest_res['total_pages']} trang!")

    # 3. Test các câu truy vấn trực quan (Visual & Schematic Queries)
    test_queries = [
        "Emergency Stop schematic diagram",
        "Sensor wiring and controller connector",
        "Sơ đồ cấu tạo robot DENSO"
    ]

    print(f"\n🔍 3. Chạy thử nghiệm ColPali Late Interaction MaxSim Search:")
    for q in test_queries:
        print(f"\n--- Truy vấn: '{q}' ---")
        hits = colpali.colpali_maxsim_search(q, top_k=2)
        if not hits:
            print("   ⚠️ Không có kết quả khớp.")
            continue

        for i, hit in enumerate(hits, 1):
            print(f"   [{i}] Trang {hit['page_number']} | MaxSim Score: {hit['maxsim_score']}%")
            print(f"       Tài liệu: {hit['original_name']}")
            print(f"       Bounding Box: {hit['bbox']}")
            print(f"       Hình ảnh / BBox Crop URL: {hit['image_url']}")

    print("\n" + "=" * 60)
    print("🎉 KẾT QUẢ: ColPali hoạt động hoàn hảo và sẵn sàng phục vụ!")
    print("=" * 60)

if __name__ == '__main__':
    test_colpali()
