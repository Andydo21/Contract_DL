import json
from typing import List, Optional, Dict, Any
from core.models import (
    Document, DocumentPage, Chunk,
    Expert, ExpertSkill,
    Case, Knowledge,
    Interview, InterviewMessage, KnowledgeGap,
    Feedback
)

# ==============================================================================
# REPOSITORIES CHO TẤT CẢ CÁC BẢNG (TẬP TRUNG TẠI 1 FILE DUY NHẤT)
# ==============================================================================

class DocumentRepository:
    """Repository quản lý Tài liệu, Trang và Chunks (A3)"""
    @staticmethod
    def get_all_documents(limit: int = 50) -> List[Document]:
        return list(Document.objects.prefetch_related('pages').all()[:limit])

    @staticmethod
    def get_document_by_id(doc_id: int) -> Optional[Document]:
        return Document.objects.filter(id=doc_id).first()

    @staticmethod
    def get_document_by_code(doc_code: str) -> Optional[Document]:
        return Document.objects.filter(doc_code=doc_code).first()

    @staticmethod
    def get_page(document_id: int, page_number: int) -> Optional[DocumentPage]:
        return DocumentPage.objects.filter(document_id=document_id, page_number=page_number).first()

    @staticmethod
    def get_chunks_by_page(page_id: int) -> List[Chunk]:
        return list(Chunk.objects.filter(page_id=page_id).all())

    @staticmethod
    def search_chunks(query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Tìm kiếm các chunk văn bản, bản vẽ CAD bằng Qdrant HNSW Vector Search"""
        from core.services import EmbeddingService, QdrantVectorService
        query_vec = EmbeddingService.embed_text(query)
        if not query_vec:
            return []

        # 1. Ưu tiên truy vấn qua Qdrant HNSW Index
        try:
            qdrant_svc = QdrantVectorService()
            results = qdrant_svc.search_chunks(query_vec, limit=limit)
            if results:
                return results
        except Exception:
            pass

        # 2. Fallback qua SQLite embedding_json
        matched = []
        chunks = Chunk.objects.select_related('page__document').all()[:150]

        for c in chunks:
            sim = 0.0
            if c.embedding_json:
                try:
                    c_vec = json.loads(c.embedding_json)
                    sim = EmbeddingService.cosine_similarity(query_vec, c_vec)
                except Exception:
                    sim = 0.0

            matched.append({
                'chunk_id': c.id,
                'document_title': c.page.document.title,
                'doc_code': c.page.document.doc_code,
                'page_number': c.page.page_number,
                'chunk_type': c.chunk_type,
                'content': c.content,
                'bbox': c.get_bbox(),
                'image_url': c.page.image_path.url if c.page.image_path else '',
                'score': round(sim, 3)
            })

        matched.sort(key=lambda x: x['score'], reverse=True)
        return matched[:limit]


class ExpertRepository:
    """Repository quản lý Chuyên gia & Kỹ năng (A2)"""
    @staticmethod
    def get_all_experts() -> List[Expert]:
        return list(Expert.objects.prefetch_related('skills', 'cases').all())

    @staticmethod
    def get_expert_by_id(expert_id: int) -> Optional[Expert]:
        return Expert.objects.filter(id=expert_id).first()

    @staticmethod
    def find_best_expert_for_machine(machine_name: str) -> Optional[Expert]:
        """Tìm chuyên gia có nhiều kinh nghiệm nhất xử lý máy này"""
        q = machine_name.lower().strip()
        experts = Expert.objects.all()
        best_exp = None
        best_count = -1
        for e in experts:
            cnt = e.cases.filter(machine__icontains=q).count()
            if cnt > best_count:
                best_count = cnt
                best_exp = e
        return best_exp or experts.first()


class CaseRepository:
    """Repository quản lý Ca sự cố thực tế (Case-Based Reasoning - CBR) bằng Qdrant Vector Search"""
    @staticmethod
    def get_all_cases(limit: int = 50) -> List[Case]:
        return list(Case.objects.select_related('expert').all()[:limit])

    @staticmethod
    def get_case_by_id(case_id: int) -> Optional[Case]:
        return Case.objects.filter(id=case_id).first()

    @staticmethod
    def search_cases(query: str, limit: int = 4) -> List[Case]:
        """Tìm kiếm Ca sự cố tương tự bằng Qdrant HNSW Vector Search"""
        from core.services import EmbeddingService, QdrantVectorService
        query_vec = EmbeddingService.embed_text(query)
        if not query_vec:
            return []

        # 1. Ưu tiên truy vấn qua Qdrant HNSW Index
        try:
            qdrant_svc = QdrantVectorService()
            cases = qdrant_svc.search_cases(query_vec, limit=limit)
            if cases:
                return cases
        except Exception:
            pass

        # 2. Fallback qua SQLite embedding_json
        all_cases = Case.objects.select_related('expert').all()
        ranked = []
        for c in all_cases:
            sim = 0.0
            if c.embedding_json:
                try:
                    c_vec = json.loads(c.embedding_json)
                    sim = EmbeddingService.cosine_similarity(query_vec, c_vec)
                except Exception:
                    sim = 0.0
            c.sim_score = round(sim, 3)
            ranked.append((sim, c))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in ranked[:limit]]


class KnowledgeRepository:
    """Repository quản lý Tri thức chính thức (Rules / SOPs) bằng Qdrant Vector Search"""
    @staticmethod
    def get_approved_knowledge(limit: int = 50) -> List[Knowledge]:
        return list(Knowledge.objects.filter(status='APPROVED').select_related('approved_by')[:limit])

    @staticmethod
    def get_knowledge_by_id(k_id: int) -> Optional[Knowledge]:
        return Knowledge.objects.filter(id=k_id).first()

    @staticmethod
    def search_knowledge(query: str, limit: int = 4) -> List[Knowledge]:
        """Tìm kiếm Quy tắc tri thức bằng Qdrant HNSW Vector Search"""
        from core.services import EmbeddingService, QdrantVectorService
        query_vec = EmbeddingService.embed_text(query)
        if not query_vec:
            return []

        # 1. Ưu tiên truy vấn qua Qdrant HNSW Index
        try:
            qdrant_svc = QdrantVectorService()
            rules = qdrant_svc.search_knowledge(query_vec, limit=limit)
            if rules:
                return rules
        except Exception:
            pass

        # 2. Fallback qua SQLite embedding_json
        all_k = Knowledge.objects.filter(status='APPROVED')
        ranked = []
        for k in all_k:
            sim = 0.0
            if k.embedding_json:
                try:
                    k_vec = json.loads(k.embedding_json)
                    sim = EmbeddingService.cosine_similarity(query_vec, k_vec)
                except Exception:
                    sim = 0.0
            k.sim_score = round(sim, 3)
            ranked.append((sim, k))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in ranked[:limit]]

    @staticmethod
    def approve_knowledge(k_id: int, expert: Optional[Expert] = None) -> Optional[Knowledge]:
        k = Knowledge.objects.filter(id=k_id).first()
        if k:
            k.status = 'APPROVED'
            if expert:
                k.approved_by = expert
            k.save()
        return k


class InterviewRepository:
    """Repository quản lý Phỏng vấn Socratic & Lỗ hổng Tri thức (A2)"""
    @staticmethod
    def create_interview(expert: Expert, topic: str) -> Interview:
        count = Interview.objects.count() + 1
        code = f"INT-{count:03d}"
        return Interview.objects.create(expert=expert, topic=topic, interview_code=code, status='ACTIVE')

    @staticmethod
    def add_message(interview: Interview, sender: str, message: str) -> InterviewMessage:
        return InterviewMessage.objects.create(interview=interview, sender=sender, message=message)

    @staticmethod
    def get_messages(interview_id: int) -> List[InterviewMessage]:
        return list(InterviewMessage.objects.filter(interview_id=interview_id).order_by('created_at'))

    @staticmethod
    def create_gap(question: str, reason: str, expert: Optional[Expert] = None) -> KnowledgeGap:
        return KnowledgeGap.objects.create(
            question=question,
            reason=reason,
            recommended_expert=expert,
            status='PENDING'
        )
