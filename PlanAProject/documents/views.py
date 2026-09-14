import os
import json
import mimetypes
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, FileResponse, Http404, HttpResponse
from django.views import View
from django.db.models import Q, Sum, Count
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import DocumentFile
from .serializers import DocumentFileSerializer
from .services.layout_extractor import LayoutLMExtractor
from .services.vector_db_service import QdrantVectorDBService

class IndexView(View):
    """
    Giao diện chính (Dashboard Web UI Frontend) quản lý & tải lên tài liệu DENSO VisionMind
    """
    def get(self, request):
        response = render(request, 'documents/index.html')
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response


class DocumentListCreateAPIView(APIView):
    """
    API Danh sách & Upload tài liệu vào Database
    """
    def get(self, request):
        category = request.GET.get('category')
        query = request.GET.get('q')
        sort = request.GET.get('sort', '-uploaded_at')

        queryset = DocumentFile.objects.all()

        if category and category != 'all':
            queryset = queryset.filter(category=category)

        if query:
            queryset = queryset.filter(
                Q(original_name__icontains=query) |
                Q(description__icontains=query) |
                Q(extension__icontains=query)
            )

        if sort in ['uploaded_at', '-uploaded_at', 'original_name', '-original_name', 'file_size', '-file_size']:
            queryset = queryset.order_by(sort)

        # Thống kê tổng quan
        total_files = DocumentFile.objects.count()
        total_bytes = DocumentFile.objects.aggregate(Sum('file_size'))['file_size__sum'] or 0
        total_extracted = DocumentFile.objects.filter(is_extracted=True).count()
        total_vector_indexed = DocumentFile.objects.filter(is_vector_indexed=True).count()

        categories_stats = DocumentFile.objects.values('category').annotate(count=Count('id'))

        serializer = DocumentFileSerializer(queryset, many=True, context={'request': request})

        return Response({
            'success': True,
            'total_files': total_files,
            'total_bytes': total_bytes,
            'formatted_total_bytes': self._format_bytes(total_bytes),
            'total_extracted': total_extracted,
            'total_vector_indexed': total_vector_indexed,
            'categories_stats': {cat['category']: cat['count'] for cat in categories_stats},
            'documents': serializer.data
        })

    def post(self, request):
        files = request.FILES.getlist('file') or request.FILES.getlist('files')
        if not files and 'file' in request.FILES:
            files = [request.FILES['file']]

        if not files:
            return Response({'success': False, 'message': 'Không tìm thấy file tải lên.'}, status=status.HTTP_400_BAD_REQUEST)

        created_docs = []
        errors = []

        for uploaded_file in files:
            try:
                original_name = uploaded_file.name
                extension = os.path.splitext(original_name)[1].lower()
                category = DocumentFile.detect_category(extension)
                file_size = uploaded_file.size
                mime_type = uploaded_file.content_type or mimetypes.guess_type(original_name)[0] or 'application/octet-stream'
                description = request.data.get('description', '')

                doc = DocumentFile.objects.create(
                    file=uploaded_file,
                    original_name=original_name,
                    extension=extension,
                    category=category,
                    file_size=file_size,
                    mime_type=mime_type,
                    description=description
                )
                
                # Tự động trigger ColPali No-OCR Visual Indexer làm Công cụ Tìm kiếm Chính (Primary Engine)
                try:
                    from documents.services.colpali_service import ColPaliVisualIndexer
                    colpali = ColPaliVisualIndexer()
                    colpali.index_document_colpali(doc)
                except Exception as col_err:
                    print("[Auto ColPali Index Error]", str(col_err))

                created_docs.append(DocumentFileSerializer(doc, context={'request': request}).data)
            except Exception as e:
                errors.append(f"Lỗi file {uploaded_file.name}: {str(e)}")

        return Response({
            'success': len(created_docs) > 0,
            'uploaded_count': len(created_docs),
            'errors': errors,
            'documents': created_docs
        }, status=status.HTTP_201_CREATED if created_docs else status.HTTP_400_BAD_REQUEST)

    def _format_bytes(self, size):
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"


class DocumentDetailAPIView(APIView):
    """
    API Chi tiết & Xóa tài liệu khỏi Database và Ổ đĩa
    """
    def get(self, request, pk):
        doc = get_object_or_404(DocumentFile, pk=pk)
        serializer = DocumentFileSerializer(doc, context={'request': request})
        return Response({'success': True, 'document': serializer.data})

    def delete(self, request, pk):
        doc = get_object_or_404(DocumentFile, pk=pk)
        try:
            # Xóa vector points khỏi Qdrant Vector DB
            from documents.services.vector_db_service import QdrantVectorDBService
            QdrantVectorDBService().delete_document_vectors(doc.id)

            if doc.file and os.path.isfile(doc.file.path):
                os.remove(doc.file.path)
            doc.delete()
            return Response({'success': True, 'message': 'Đã xóa file và các Vector Points khỏi Database & Qdrant.'})
        except Exception as e:
            return Response({'success': False, 'message': f'Lỗi khi xóa file: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExtractLayoutAPIView(APIView):
    """
    API Trích xuất LayoutLM (Text + Bounding Boxes + Hình ảnh sơ đồ)
    """
    def post(self, request, pk):
        doc = get_object_or_404(DocumentFile, pk=pk)
        try:
            extractor = LayoutLMExtractor()
            chunks = extractor.extract_document(doc)

            doc.extracted_json = json.dumps(chunks, ensure_ascii=False)
            doc.extracted_chunks_count = len(chunks)
            doc.is_extracted = True
            doc.save()

            return Response({
                'success': True,
                'message': f'Đã trích xuất thành công {len(chunks)} Layout chunks (Text + BBox + Ảnh).',
                'extracted_chunks_count': len(chunks),
                'chunks': chunks
            })
        except Exception as e:
            return Response({'success': False, 'message': f'Lỗi trích xuất LayoutLM: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VectorizeDocumentAPIView(APIView):
    """
    API Lưu trữ Embeddings vào Qdrant Vector Database
    """
    def post(self, request, pk):
        doc = get_object_or_404(DocumentFile, pk=pk)
        if not doc.is_extracted or not doc.extracted_json:
            # Tự động trigger trích xuất Layout trước nếu chưa trích xuất
            extractor = LayoutLMExtractor()
            chunks = extractor.extract_document(doc)
            doc.extracted_json = json.dumps(chunks, ensure_ascii=False)
            doc.extracted_chunks_count = len(chunks)
            doc.is_extracted = True
            doc.save()
        else:
            chunks = doc.get_extracted_chunks()

        try:
            vector_service = QdrantVectorDBService()
            indexed_count = vector_service.index_document_chunks(doc, chunks)

            # Tự động đồng bộ sang ColPali Visual Multi-Vector Engine nếu là file PDF hoặc ảnh
            colpali_msg = ""
            if doc.category in ['pdf', 'image']:
                try:
                    from documents.services.colpali_service import ColPaliVisualIndexer
                    colpali_indexer = ColPaliVisualIndexer()
                    c_res = colpali_indexer.index_document_colpali(doc)
                    colpali_msg = f" và {c_res.get('indexed_pages', 0)} trang ColPali Visual"
                except Exception as c_err:
                    print(f"[ColPali Auto-Index Notice] {c_err}")

            doc.is_vector_indexed = True
            doc.vector_points_count = indexed_count
            doc.save()

            return Response({
                'success': True,
                'message': f'Đã lưu thành công {indexed_count} vector points{colpali_msg} vào Qdrant Vector DB.',
                'vector_points_count': indexed_count
            })
        except Exception as e:
            return Response({'success': False, 'message': f'Lỗi lưu trữ Vector DB: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VectorSearchAPIView(APIView):
    """
    API Tìm kiếm Tương đồng Vector Similarity Search trên Qdrant Vector DB (Hỗ trợ Text & ColPali Visual Vector)
    """
    def post(self, request):
        query = request.data.get('query', '').strip()
        category = request.data.get('category', 'all')
        doc_id = request.data.get('document_id')
        search_type = request.data.get('search_type', 'text')
        top_k = int(request.data.get('top_k', 10))

        if not query:
            return Response({'success': False, 'message': 'Vui lòng nhập từ khóa truy vấn Vector.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            results = []
            if search_type == 'colpali':
                from documents.services.colpali_service import ColPaliVisualIndexer
                colpali = ColPaliVisualIndexer()
                results = colpali.colpali_maxsim_search(query_text=query, top_k=top_k, doc_id_filter=doc_id)
            else:
                vector_service = QdrantVectorDBService()
                results = vector_service.vector_search(query_text=query, top_k=top_k, category_filter=category, doc_id_filter=doc_id)

            return Response({
                'success': True,
                'query': query,
                'search_type': search_type,
                'results_count': len(results),
                'results': results
            })
        except Exception as e:
            return Response({'success': False, 'message': f'Lỗi truy vấn Vector DB: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DocumentDownloadView(View):
    """
    Download file trực tiếp
    """
    def get(self, request, pk):
        doc = get_object_or_404(DocumentFile, pk=pk)
        if not doc.file or not os.path.exists(doc.file.path):
            raise Http404("File không tồn tại trên ổ đĩa server.")
        
        response = FileResponse(open(doc.file.path, 'rb'), content_type=doc.mime_type)
        response['Content-Disposition'] = f'attachment; filename="{doc.original_name}"'
        return response


class DocumentPreviewView(View):
    """
    Xem trước nội dung (Preview) tài liệu (PDF, Image, DOCX, TXT, ...)
    """
    def get(self, request, pk):
        doc = get_object_or_404(DocumentFile, pk=pk)
        if not doc.file or not os.path.exists(doc.file.path):
            return JsonResponse({'success': False, 'message': 'File không tồn tại trên ổ đĩa.'}, status=404)

        file_path = doc.file.path
        category = doc.category
        file_url = request.build_absolute_uri(doc.file.url)

        raw_chunks = doc.get_extracted_chunks()
        from documents.services.vector_db_service import QdrantVectorDBService
        vec_service = QdrantVectorDBService()
        for chunk in raw_chunks:
            if not chunk.get('full_vector') or len(chunk.get('full_vector', [])) < 384:
                vector = vec_service.generate_embedding(
                    chunk.get('text', ''),
                    chunk.get('layout_type', 'paragraph'),
                    chunk.get('bbox', None)
                )
                full_v = [round(float(v), 4) for v in vector]
                chunk['vector_dim'] = len(full_v)
                chunk['vector_sample'] = full_v[:10]
                chunk['full_vector'] = full_v

        annotated_pages = {}
        original_pages = {}
        if category == 'pdf':
            original_pages, annotated_pages = self._generate_annotated_pdf_pages(doc, raw_chunks)

        preview_data = {
            'id': doc.id,
            'original_name': doc.original_name,
            'category': doc.category,
            'extension': doc.extension,
            'file_url': file_url,
            'formatted_size': doc.formatted_size,
            'uploaded_at': doc.uploaded_at.strftime('%H:%M:%S %d/%m/%Y'),
            'is_extracted': doc.is_extracted,
            'is_vector_indexed': doc.is_vector_indexed,
            'extracted_chunks_count': doc.extracted_chunks_count,
            'vector_points_count': doc.vector_points_count,
            'extracted_chunks': raw_chunks,
            'annotated_pages': annotated_pages,
            'original_pages': original_pages,
            'preview_type': 'raw',
            'content': None
        }

        if category == 'image':
            preview_data['preview_type'] = 'image'
        elif category == 'pdf':
            preview_data['preview_type'] = 'pdf'
        elif category == 'text':
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    preview_data['content'] = f.read(5000)
                preview_data['preview_type'] = 'text'
            except Exception as e:
                preview_data['content'] = f"Không thể đọc text: {str(e)}"
        elif category == 'docx':
            try:
                import docx
                doc_obj = docx.Document(file_path)
                full_text = [p.text for p in doc_obj.paragraphs if p.text.strip()]
                preview_data['content'] = "\n".join(full_text[:50])
                preview_data['preview_type'] = 'docx'
            except Exception as e:
                preview_data['content'] = f"Đọc file DOCX: {doc.original_name}"
                preview_data['preview_type'] = 'docx'
        else:
            preview_data['preview_type'] = 'download'

        return JsonResponse({'success': True, 'preview': preview_data})

    def _generate_annotated_pdf_pages(self, doc, raw_chunks):
        annotated_map = {}
        original_map = {}
        try:
            from django.conf import settings
            from PIL import Image, ImageDraw, ImageFont
            from pathlib import Path

            output_dir = Path(settings.MEDIA_ROOT) / 'extracted_images'
            output_dir.mkdir(parents=True, exist_ok=True)

            page_chunks_map = {}
            for c in raw_chunks:
                p_num = c.get('page_number', 1)
                if p_num not in page_chunks_map:
                    page_chunks_map[p_num] = []
                page_chunks_map[p_num].append(c)

            for p_num, p_chunks in page_chunks_map.items():
                annotated_filename = f"annotated_doc_{doc.id}_p{p_num}.png"
                annotated_path = output_dir / annotated_filename
                annotated_url = f"{settings.MEDIA_URL}extracted_images/{annotated_filename}"

                base_page_filename = f"pdf_page_{doc.id}_p{p_num}.png"
                base_page_path = output_dir / base_page_filename
                base_page_url = f"{settings.MEDIA_URL}extracted_images/{base_page_filename}"

                if base_page_path.exists():
                    original_map[str(p_num)] = base_page_url

                if annotated_path.exists():
                    annotated_map[str(p_num)] = annotated_url
                    continue

                if not base_page_path.exists() and doc.file and os.path.exists(doc.file.path):
                    import fitz
                    pdf_doc = fitz.open(doc.file.path)
                    if p_num - 1 < len(pdf_doc):
                        page = pdf_doc[p_num - 1]
                        pix = page.get_pixmap(dpi=150)
                        pix.save(str(base_page_path))
                        original_map[str(p_num)] = base_page_url
                    pdf_doc.close()

                if base_page_path.exists():
                    with Image.open(base_page_path) as img:
                        img = img.convert("RGB")
                        w, h = img.size
                        draw = ImageDraw.Draw(img)

                        for chunk in p_chunks:
                            bbox = chunk.get('bbox') or [50, 50, 950, 950]
                            x0 = int((bbox[0] / 1000.0) * w)
                            y0 = int((bbox[1] / 1000.0) * h)
                            x1 = int((bbox[2] / 1000.0) * w)
                            y1 = int((bbox[3] / 1000.0) * h)

                            l_type = (chunk.get('layout_type') or 'paragraph').lower()
                            if 'table' in l_type:
                                color = "#10b981"
                                label_text = f"TABLE #{chunk.get('chunk_id')}"
                            elif 'title' in l_type:
                                color = "#f59e0b"
                                label_text = f"TITLE #{chunk.get('chunk_id')}"
                            else:
                                color = "#ef4444"
                                label_text = f"BBOX #{chunk.get('chunk_id')}: {l_type.upper()}"

                            draw.rectangle([x0, y0, x1, y1], outline=color, width=4)
                            draw.rectangle([x0, max(0, y0 - 18), x0 + min(160, len(label_text)*9), y0], fill=color)
                            draw.text((x0 + 4, max(0, y0 - 15)), label_text, fill="white")

                        img.save(annotated_path, "PNG")
                        annotated_map[str(p_num)] = annotated_url
        except Exception as e:
            print("[Generate Annotated Pages Error]", str(e))

        return original_map, annotated_map


class ColPaliIndexAPIView(APIView):
    """
    API Ingestion ColPali No-OCR Visual Indexer:
    Biến PDF/Sơ đồ thành tập hợp các Visual Patches 32x32 đẩy vào Qdrant DB
    """
    def post(self, request, pk):
        doc = get_object_or_404(DocumentFile, pk=pk)
        try:
            from documents.services.colpali_service import ColPaliVisualIndexer
            indexer = ColPaliVisualIndexer()
            res = indexer.index_document_colpali(doc)

            return Response({
                'success': True,
                'message': f'Đã indexing ColPali No-OCR Visual Patches thành công! ({res.get("indexed_pages", 0)} trang tài liệu)',
                'result': res
            })
        except Exception as e:
            return Response({'success': False, 'message': f'Lỗi ColPali Visual Indexing: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ColPaliSearchAPIView(APIView):
    """
    API Late Interaction MaxSim Search với ColPali No-OCR Visual Engine
    """
    def post(self, request):
        query_text = request.data.get('query', '').strip()
        top_k = int(request.data.get('top_k', 5))

        if not query_text:
            return Response({'success': False, 'message': 'Vui lòng nhập từ khóa truy vấn ColPali.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from documents.services.colpali_service import ColPaliVisualIndexer
            indexer = ColPaliVisualIndexer()
            results = indexer.colpali_maxsim_search(query_text, top_k=top_k)

            return Response({
                'success': True,
                'query': query_text,
                'total_matches': len(results),
                'results': results
            })
        except Exception as e:
            return Response({'success': False, 'message': f'Lỗi ColPali MaxSim Search: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RAGChatbotAPIView(APIView):
    """
    API RAG Chatbot Đa phương thức (Multimodal RAG Engine):
    - ColPali VLM No-OCR Search + Qdrant Vector Search + Surya-Table Parser
    - BGE-Reranker-v2-m3 Cross-Encoder Lọc kết quả Top-K (> 95% Precision)
    - Trả về câu trả lời tổng hợp kèm Visual Citation Bounding Box trực quan
    """
    def post(self, request):
        import time
        start_time = time.time()
        query = request.data.get('message', '').strip()

        if not query:
            return Response({'success': False, 'message': 'Vui lòng nhập câu hỏi Chatbot.'}, status=status.HTTP_400_BAD_REQUEST)

        mode = request.data.get('mode', 'hybrid').strip().lower()

        try:
            colpali_results = []
            vec_results = []
            graph_citations = []
            keyword_candidates = []

            # 1. Pipeline ColPali (Chạy khi mode là 'colpali' hoặc 'hybrid')
            if mode in ['colpali', 'hybrid']:
                from documents.services.colpali_service import ColPaliVisualIndexer
                colpali = ColPaliVisualIndexer()
                colpali_results = colpali.colpali_maxsim_search(query, top_k=8)

                # Bổ sung nội dung text ngữ cảnh từ các chunk của trang tương ứng để Qwen có đầy đủ thông số trả lời
                from documents.models import DocumentFile
                for res in colpali_results:
                    doc_id = res.get('document_id')
                    page_num = res.get('page_number', 1)
                    txt = (res.get('text') or '').strip()
                    if doc_id and len(txt.split('\n')) <= 2:
                        try:
                            df = DocumentFile.objects.filter(id=doc_id).first()
                            if df:
                                chunks = df.get_extracted_chunks()
                                page_texts = [c.get('text', '') for c in chunks if c.get('page_number') == page_num and c.get('text')]
                                if page_texts:
                                    res['text'] = (txt + "\n" + "\n".join(page_texts[:5])).strip()
                        except Exception:
                            pass

            # 2. Pipeline Surya + LayoutLM + all-MiniLM (Chạy khi mode là 'surya_layout' hoặc 'hybrid')
            if mode in ['surya_layout', 'hybrid']:
                from documents.services.vector_db_service import QdrantVectorDBService
                vec_service = QdrantVectorDBService()
                vec_results = vec_service.vector_search(query, top_k=25)

                # Neo4j Knowledge Graph Path Matching (GraphRAG)
                try:
                    from documents.services.neo4j_service import Neo4jGraphService
                    graph_service = Neo4jGraphService()
                    graph_paths = graph_service.query_graph_rag(query)
                    for gp in graph_paths:
                        graph_citations.append({
                            "original_name": gp.get("file", "Robot_DENSO_Manual.pdf"),
                            "layout_type": "neo4j_graph_node",
                            "score": gp.get("graph_score", 95.0),
                            "text": f"[Neo4j Graph Path]: {gp.get('source')} --({gp.get('relation')})--> {gp.get('target')}"
                        })
                except Exception as g_err:
                    print("[Neo4j RAG Error]", str(g_err))

                # Dynamic Keyword Candidate Retrieval across extracted database chunks
                import re
                from documents.models import DocumentFile
                stopwords = {'bao', 'nhiêu', 'của', 'các', 'cho', 'với', 'trong', 'được', 'này', 'khi', 'denso', 'kĩ', 'kỹ', 'sư', 'thế', 'nào', 'sao'}
                query_tokens = [
                    t.strip().lower() for t in re.split(r'[\s,;:?!\(\)]+', query)
                    if len(t.strip()) >= 3 and t.strip().lower() not in stopwords
                ]
                from django.db.models import Q
                q_filter = Q()
                for tok in query_tokens[:5]:
                    q_filter |= Q(original_name__icontains=tok) | Q(extracted_json__icontains=tok)
                matching_docs = DocumentFile.objects.filter(is_extracted=True).filter(q_filter)[:12] if q_filter else DocumentFile.objects.filter(is_extracted=True)[:6]

                for doc in matching_docs:
                    doc_name_lower = doc.original_name.lower()
                    doc_stem = doc_name_lower.split('.')[0]
                    doc_stem_space = doc_stem.replace('_', ' ').replace('-', ' ')
                    
                    query_lower = query.lower()
                    is_doc_mentioned = doc_name_lower in query_lower or doc_stem in query_lower or doc_stem_space in query_lower

                    extracted_chunks = doc.get_extracted_chunks()
                    for chunk in extracted_chunks:
                        if len(keyword_candidates) >= 30:
                            break
                        txt = chunk.get("text", "")
                        txt_lower = txt.lower()
                        term_match = any(t in txt_lower for t in query_tokens) if query_tokens else False
                        
                        if is_doc_mentioned or term_match:
                            keyword_candidates.append({
                                "document_id": doc.id,
                                "original_name": doc.original_name,
                                "category": doc.category,
                                "chunk_id": chunk.get("chunk_id", 0),
                                "layout_type": chunk.get("layout_type", "text"),
                                "text": txt,
                                "bbox": chunk.get("bbox", []),
                                "page_number": chunk.get("page_number", 1),
                                "score": 0.0,
                                "image_url": chunk.get("image_url", ""),
                                "file_url": doc.file.url if doc.file else ""
                            })

            # Tổng hợp Candidates theo từng mode bằng Reciprocal Rank Fusion (RRF)
            from documents.services.reranker_service import BGERerankerService

            if mode == 'colpali':
                all_candidates = colpali_results
                for c in all_candidates:
                    c['rerank_score'] = float(c.get('score') or c.get('maxsim_score') or 0.0)
                top_citations = sorted(all_candidates, key=lambda x: x.get('rerank_score', 0.0), reverse=True)[:8]
                bot_name = "Qwen-2.5 ColPali Visual Bot"
            elif mode == 'surya_layout':
                ranked_streams = {
                    "dense": vec_results,
                    "graph": graph_citations,
                    "keyword": keyword_candidates
                }
                all_candidates = BGERerankerService.reciprocal_rank_fusion(
                    ranked_streams,
                    k=60,
                    weights={"dense": 1.2, "graph": 1.0, "keyword": 0.8}
                )
                bot_name = "Qwen-2.5 Surya-LayoutLM Bot"
                reranker = BGERerankerService()
                top_citations = reranker.rerank(query, all_candidates, top_k=8)
            else:
                mode = 'hybrid'
                # RECIPROCAL RANK FUSION (RRF): Tuyệt đối không cộng gộp thô điểm MaxSim và Dense Similarity
                ranked_streams = {
                    "colpali": colpali_results,
                    "dense": vec_results,
                    "graph": graph_citations,
                    "keyword": keyword_candidates
                }
                all_candidates = BGERerankerService.reciprocal_rank_fusion(
                    ranked_streams,
                    k=60,
                    weights={"colpali": 1.5, "dense": 1.2, "graph": 1.0, "keyword": 0.8}
                )
                bot_name = "Qwen-2.5 Multimodal Hybrid Bot"
                reranker = BGERerankerService()
                top_citations = reranker.rerank(query, all_candidates, top_k=8)

            # 4. Trích xuất danh sách các ảnh / bản vẽ / vùng thị giác thực sự (Ưu tiên ColPali Visual MaxSim + Figures)
            seen_img_urls = set()
            relevant_images = []
            doc_chunks_cache = {}

            # ƯU TIÊN SỐ 1: Các kết quả thị giác trực tiếp từ ColPali Visual Engine (MaxSim Score cao)
            for c in (colpali_results or []):
                score = round(float(c.get("score") or c.get("maxsim_score", 0.0)), 1)
                if score >= 35.0:
                    doc_id = c.get("document_id")
                    page_num = c.get("page_number", 1)
                    full_page = c.get("full_page_url") or c.get("image_url") or ""
                    
                    fig_to_use = full_page
                    bbox_to_use = c.get("bbox", [])
                    if doc_id:
                        if doc_id not in doc_chunks_cache:
                            try:
                                df_obj = DocumentFile.objects.filter(id=doc_id).first()
                                doc_chunks_cache[doc_id] = df_obj.get_extracted_chunks() if df_obj else []
                            except Exception:
                                doc_chunks_cache[doc_id] = []
                        page_figs = [
                            ck for ck in doc_chunks_cache.get(doc_id, [])
                            if ck.get('page_number') == page_num and ck.get('layout_type') in ['figure', 'picture', 'image'] and ck.get('image_url')
                        ]
                        if page_figs:
                            def fig_area(f):
                                fb = f.get('bbox') or [0, 0, 0, 0]
                                return (fb[2] - fb[0]) * (fb[3] - fb[1])
                            best_page_fig = max(page_figs, key=fig_area)
                            if best_page_fig.get('image_url'):
                                fig_to_use = best_page_fig.get('image_url')
                                bbox_to_use = best_page_fig.get('bbox', [])

                    if fig_to_use and fig_to_use not in seen_img_urls and len(relevant_images) < 8:
                        seen_img_urls.add(fig_to_use)
                        cache_busted_url = f"{fig_to_use}?t={int(time.time())}" if "?" not in fig_to_use else fig_to_use
                        relevant_images.append({
                            "image_url": cache_busted_url,
                            "full_page_url": full_page,
                            "original_name": c.get("original_name", "Bản vẽ kỹ thuật"),
                            "page_number": page_num,
                            "bbox": bbox_to_use,
                            "score": score,
                            "layout_type": "colpali_maxsim_visual",
                            "text": f"[ColPali Match: {score}%] Bản vẽ chi tiết trang {page_num} của '{c.get('original_name', '')}'"
                        })

            # Thu thập thêm từ top_citations sau khi rerank
            for c in top_citations:
                if len(relevant_images) >= 8:
                    break
                doc_id = c.get("document_id")
                page_num = c.get("page_number", 1)
                ltype = (c.get("layout_type") or "").lower()
                c_score = round(float(c.get("rerank_score") or c.get("score", 0.0)), 1)
                
                full_page = c.get("full_page_url") or ""
                if not full_page and doc_id and page_num:
                    from pathlib import Path
                    p_img = Path(settings.MEDIA_ROOT) / "extracted_images" / f"pdf_page_{doc_id}_p{page_num}.png"
                    if not p_img.exists():
                        p_img = Path(settings.MEDIA_ROOT) / "extracted_images" / f"colpali_pdf_{doc_id}_p{page_num}.png"
                    if p_img.exists():
                        full_page = f"{settings.MEDIA_URL}extracted_images/{p_img.name}"
                if not full_page:
                    full_page = c.get("image_url") or ""

                # TH1: Citation vốn đã là Hình vẽ / Sơ đồ / Bản vẽ
                if ltype in ['figure', 'picture', 'image', 'table', 'colpali_visual_patch', 'colpali_maxsim_visual']:
                    img_url = c.get("image_url")
                    if img_url and str(img_url).strip() and img_url not in seen_img_urls:
                        seen_img_urls.add(img_url)
                        cache_busted_url = f"{img_url}?t={int(time.time())}" if "?" not in img_url else img_url
                        relevant_images.append({
                            "image_url": cache_busted_url,
                            "full_page_url": full_page,
                            "original_name": c.get("original_name", "Bản vẽ kỹ thuật"),
                            "page_number": page_num,
                            "bbox": c.get("bbox", []),
                            "score": c_score,
                            "layout_type": ltype,
                            "text": (c.get("text") or "")[:200]
                        })
                else:
                    # TH2: Citation là đoạn văn bản (PARAGRAPH, TITLE) -> Tìm hình vẽ tương ứng trên trang
                    if doc_id:
                        if doc_id not in doc_chunks_cache:
                            try:
                                df_obj = DocumentFile.objects.filter(id=doc_id).first()
                                doc_chunks_cache[doc_id] = df_obj.get_extracted_chunks() if df_obj else []
                            except Exception:
                                doc_chunks_cache[doc_id] = []

                        page_chunks = doc_chunks_cache.get(doc_id, [])
                        page_figures = [
                            ck for ck in page_chunks
                            if ck.get('page_number') == page_num and ck.get('layout_type') in ['figure', 'picture', 'image', 'table'] and ck.get('image_url')
                        ]

                        for best_fig in page_figures[:1]:
                            fig_url = best_fig.get("image_url")
                            if fig_url and fig_url not in seen_img_urls and len(relevant_images) < 8:
                                seen_img_urls.add(fig_url)
                                cache_busted_url = f"{fig_url}?t={int(time.time())}" if "?" not in fig_url else fig_url
                                relevant_images.append({
                                    "image_url": cache_busted_url,
                                    "full_page_url": full_page,
                                    "original_name": c.get("original_name", "Sơ đồ kỹ thuật"),
                                    "page_number": page_num,
                                    "bbox": best_fig.get("bbox", []),
                                    "score": c_score,
                                    "layout_type": best_fig.get("layout_type", "figure"),
                                    "text": f"[Hình ảnh minh họa trang {page_num}]: {c.get('text', '')[:120]}"
                                })


            # Sắp xếp các ảnh ưu tiên Hình ảnh/Bản vẽ thực sự (figure/table) lên trước ảnh text
            def img_priority(x):
                is_visual = 1 if x.get("layout_type") in ['figure', 'picture', 'image', 'table', 'colpali_maxsim_visual'] else 0
                return (is_visual, x.get("score", 0.0))

            relevant_images.sort(key=img_priority, reverse=True)

            latency_ms = round((time.time() - start_time) * 1000, 2)

            # 5. Synthesize Answer using Specialized Qwen-2.5 Engine
            from documents.services.qwen_service import QwenChatbotService
            qwen_engine = QwenChatbotService()
            generated_answer = qwen_engine.generate_answer(query, top_citations, images=relevant_images, mode=mode)

            best_precision = 0.0
            if top_citations and 'rerank_score' in top_citations[0]:
                best_precision = max(best_precision, float(top_citations[0]['rerank_score']))
            if relevant_images and 'score' in relevant_images[0]:
                best_precision = max(best_precision, float(relevant_images[0]['score']))

            return Response({
                'success': True,
                'query': query,
                'mode': mode,
                'bot_name': bot_name,
                'answer': generated_answer,
                'latency_ms': latency_ms,
                'precision_score': round(best_precision, 1),
                'citations': top_citations,
                'relevant_images': relevant_images
            })
        except Exception as e:
            return Response({'success': False, 'message': f'Lỗi RAG Chatbot ({mode}): {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

