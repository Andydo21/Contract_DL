import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from core.models import Document, DocumentPage, Chunk, Expert, Case, Knowledge, Interview, KnowledgeGap, Feedback
from core.repositories import DocumentRepository, ExpertRepository, CaseRepository, KnowledgeRepository, InterviewRepository
from core.services import KnowledgeIntelligenceService, SocraticInterviewService

# ==============================================================================
# 1. CÁC MÀN HÌNH GIAO DIỆN CHÍNH (HTML TEMPLATE VIEWS)
# ==============================================================================

def dashboard_view(request):
    """Màn hình 1: Dashboard tổng quan hệ thống DENSO Knowledge Intelligence"""
    ctx = {
        'total_documents': Document.objects.count(),
        'total_experts': Expert.objects.count(),
        'total_cases': Case.objects.count(),
        'total_knowledge': Knowledge.objects.filter(status='APPROVED').count(),
        'recent_cases': Case.objects.select_related('expert')[:5],
        'recent_knowledge': Knowledge.objects.filter(status='APPROVED')[:5],
        'pending_gaps': KnowledgeGap.objects.filter(status='PENDING')[:5],
    }
    return render(request, 'dashboard.html', ctx)


def documents_view(request):
    """Màn hình 2: Danh sách tài liệu kỹ thuật (SOP, Bản vẽ, Manual)"""
    docs = DocumentRepository.get_all_documents()
    return render(request, 'documents.html', {'documents': docs})


def document_detail_view(request, pk):
    """Màn hình Chi tiết Tài liệu: Xem PDF Page Image bên trái + Thông số bóc tách bên phải"""
    doc = get_object_or_404(Document, pk=pk)
    selected_page_num = int(request.GET.get('page', 1))
    page = doc.pages.filter(page_number=selected_page_num).first() or doc.pages.first()
    chunks = page.chunks.all() if page else []

    return render(request, 'document_detail.html', {
        'document': doc,
        'selected_page': page,
        'chunks': chunks,
        'all_pages': doc.pages.all()
    })


def search_view(request):
    """Màn hình 3: Tìm kiếm đa phương thức (Text, Image, Case Memory)"""
    query = request.GET.get('q', '').strip()
    search_type = request.GET.get('type', 'all')
    
    docs_results = []
    cases_results = []
    knowledge_results = []

    if query:
        docs_results = DocumentRepository.search_chunks(query, limit=5)
        cases_results = CaseRepository.search_cases(query, limit=5)
        knowledge_results = KnowledgeRepository.search_knowledge(query, limit=5)

    return render(request, 'search.html', {
        'query': query,
        'search_type': search_type,
        'docs_results': docs_results,
        'cases_results': cases_results,
        'knowledge_results': knowledge_results
    })


def chat_view(request):
    """Màn hình 4: Chatbot RAG Thông minh (Phát hiện Knowledge Gap)"""
    return render(request, 'chat.html', {
        'total_documents': Document.objects.count(),
        'total_cases': Case.objects.count()
    })


def experts_view(request):
    """Danh sách chuyên gia và kỹ năng"""
    experts = ExpertRepository.get_all_experts()
    interviews = Interview.objects.select_related('expert').order_by('-id')
    return render(request, 'experts.html', {
        'experts': experts,
        'interviews': interviews
    })


def interview_view(request, pk):
    """Màn hình 5: AI Phỏng vấn chuyên gia & Duyệt Rule tri thức mới"""
    interview = get_object_or_404(Interview, pk=pk)
    messages = InterviewRepository.get_messages(interview.id)
    generated_rule = Knowledge.objects.filter(source_id=f"INT-{interview.id}").first()

    return render(request, 'interview.html', {
        'interview': interview,
        'messages': messages,
        'generated_rule': generated_rule
    })


def knowledge_view(request):
    """Màn hình 6: Kho Tri thức Chuyên gia đã được phê duyệt (Active Knowledge)"""
    rules = KnowledgeRepository.get_approved_knowledge()
    return render(request, 'knowledge.html', {'knowledge_list': rules})


# ==============================================================================
# 2. CÁC API ENDPOINTS PHỤC VỤ AJAX / VANILLA JS
# ==============================================================================

@csrf_exempt
def api_chat(request):
    """API xử lý tin nhắn của Kỹ sư hiện trường & Cảnh báo Gap"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Chỉ chấp nhận POST'}, status=405)

    try:
        data = json.loads(request.body)
        question = data.get('question', '').strip()
    except Exception:
        question = request.POST.get('question', '').strip()

    if not question:
        return JsonResponse({'error': 'Câu hỏi không được rỗng'}, status=400)

    try:
        service = KnowledgeIntelligenceService()
        result = service.process_chat(question)
        return JsonResponse(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'has_gap': False,
            'answer': f"⚠️ Lỗi hệ thống khi trích xuất tri thức: {str(e)}",
            'citations': []
        }, status=200)


@csrf_exempt
def api_start_interview(request):
    """API bắt đầu phiên phỏng vấn chuyên gia từ Knowledge Gap (KHÔNG mock tin nhắn giả)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    expert_id = data.get('expert_id')
    topic = data.get('topic', 'Xử lý rung lắc máy M12 khi nhiệt độ cao (>40°C)')

    expert = ExpertRepository.get_expert_by_id(expert_id) or Expert.objects.first()
    interview = InterviewRepository.create_interview(expert, topic)

    salutation = expert.name if expert.name.strip().lower().startswith(('kỹ sư', 'anh', 'chị')) else f"Kỹ sư {expert.name}"
    refined_question = data.get('refined_question') or (
        f"Chào {salutation}. Hệ thống ghi nhận chủ đề kỹ thuật cần xin ý kiến: '{topic}'. "
        f"Kho quy chuẩn SOP hiện chưa có hướng dẫn chính thức đầy đủ cho trường hợp này. "
        f"Theo kinh nghiệm thực tế của anh, anh thường kiểm tra và xử lý quy trình này thế nào?"
    )

    # KHÔNG DÙNG LUẬT CỨNG MOCK DIALOGUE: Chỉ gửi duy nhất câu hỏi đầu tiên của AI tới chuyên gia
    InterviewRepository.add_message(
        interview,
        sender='ai',
        message=refined_question
    )

    return JsonResponse({
        'success': True,
        'interview_id': interview.id,
        'interview_code': interview.interview_code,
        'redirect_url': f"/interviews/{interview.id}/"
    })


@csrf_exempt
def api_interview_reply(request, pk):
    """API tiếp nhận phản hồi thực tế của Chuyên gia & Gọi AI sinh câu hỏi Socratic tiếp theo"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    try:
        data = json.loads(request.body)
        expert_message = data.get('message', '').strip()
    except Exception:
        expert_message = request.POST.get('message', '').strip()

    if not expert_message:
        return JsonResponse({'error': 'Vui lòng nhập câu trả lời của chuyên gia'}, status=400)

    interview = get_object_or_404(Interview, pk=pk)

    # 1. Lưu phản hồi thực tế của chuyên gia
    InterviewRepository.add_message(
        interview=interview,
        sender='expert',
        message=expert_message
    )

    # 2. AI phản biện Socratic dựa trên câu trả lời vừa rồi
    ai_question = SocraticInterviewService.generate_socratic_question(interview, expert_message)

    # 3. Lưu câu hỏi Socratic tiếp theo của AI
    InterviewRepository.add_message(
        interview=interview,
        sender='ai',
        message=ai_question
    )

    return JsonResponse({
        'success': True,
        'expert_message': expert_message,
        'ai_question': ai_question
    })



@csrf_exempt
def api_generate_knowledge(request, pk):
    """API trích xuất nội dung phỏng vấn thành Rule tri thức mới"""
    interview = get_object_or_404(Interview, pk=pk)
    rule = SocraticInterviewService.generate_rule_from_interview(
        expert_id=interview.expert.id,
        topic=interview.topic,
        interview_id=interview.id
    )
    return JsonResponse({
        'success': True,
        'rule_id': rule.id,
        'knowledge_code': rule.knowledge_code,
        'title': rule.title,
        'content': rule.content,
        'confidence': rule.confidence
    })


@csrf_exempt
def api_approve_knowledge(request, pk):
    """API Chuyên gia bấm [✓ Approved] để chính thức đưa vào Knowledge Base"""
    rule = get_object_or_404(Knowledge, pk=pk)
    rule.status = 'APPROVED'
    rule.save()
    return JsonResponse({
        'success': True,
        'message': f"Đã phê duyệt tri thức {rule.knowledge_code} thành công!"
    })
