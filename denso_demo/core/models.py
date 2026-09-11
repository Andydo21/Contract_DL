import json
from django.db import models
from django.contrib.auth.models import User

# ==============================================================================
# NHÓM 1: TÀI LIỆU KỸ THUẬT & TRANG PDF (A3 DOCUMENT INTELLIGENCE)
# ==============================================================================

class Document(models.Model):
    """Bảng 1: documents — Lưu trữ thông tin tài liệu kỹ thuật, SOP, bản vẽ"""
    DOC_TYPE_CHOICES = (
        ('SOP', 'Standard Operating Procedure (SOP)'),
        ('MANUAL', 'Cẩm nang vận hành / Sách hướng dẫn'),
        ('DRAWING', 'Bản vẽ kỹ thuật 2D / 3D CAD'),
        ('CATALOG', 'Catalog thiết bị / Bảng thông số'),
        ('OTHER', 'Tài liệu khác'),
    )

    doc_code = models.CharField(max_length=64, unique=True, default='DOC001', verbose_name="Mã tài liệu")
    title = models.CharField(max_length=255, verbose_name="Tiêu đề tài liệu")
    doc_type = models.CharField(max_length=20, choices=DOC_TYPE_CHOICES, default='SOP', verbose_name="Loại tài liệu")
    description = models.TextField(blank=True, null=True, verbose_name="Mô tả tóm tắt")
    file_path = models.FileField(upload_to='documents/%Y/%m/', blank=True, null=True, verbose_name="File lưu trữ")
    language = models.CharField(max_length=64, default='Japanese/English/Vietnamese', verbose_name="Ngôn ngữ")
    status = models.CharField(max_length=30, default='PROCESSED', verbose_name="Trạng thái")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày tạo")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.doc_code}] {self.title}"

    @property
    def total_pages(self):
        return self.pages.count()


class DocumentPage(models.Model):
    """Bảng 2: document_pages — Mỗi trang PDF là một record kèm ảnh rendered"""
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='pages', verbose_name="Tài liệu")
    page_number = models.IntegerField(verbose_name="Số trang")
    image_path = models.ImageField(upload_to='pages/%Y/%m/', blank=True, null=True, verbose_name="Ảnh trang PDF")
    ocr_text = models.TextField(blank=True, null=True, verbose_name="Văn bản bóc tách")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['page_number']
        unique_together = ('document', 'page_number')

    def __str__(self):
        return f"{self.document.doc_code} — Trang {self.page_number}"


class Chunk(models.Model):
    """Bảng 3: chunks — Các khối văn bản, bảng biểu, sơ đồ kèm Bounding Box"""
    CHUNK_TYPE_CHOICES = (
        ('text', 'Đoạn văn bản'),
        ('table', 'Bảng thông số'),
        ('figure', 'Bản vẽ / Sơ đồ CAD'),
        ('header', 'Tiêu đề mục'),
    )

    page = models.ForeignKey(DocumentPage, on_delete=models.CASCADE, related_name='chunks', verbose_name="Trang tài liệu")
    content = models.TextField(verbose_name="Nội dung trích xuất")
    chunk_type = models.CharField(max_length=20, choices=CHUNK_TYPE_CHOICES, default='text', verbose_name="Loại chunk")
    bbox_json = models.TextField(default='[]', verbose_name="Tọa độ BBox [ymin, xmin, ymax, xmax]")
    embedding_json = models.TextField(blank=True, null=True, verbose_name="Vector Embedding JSON")
    created_at = models.DateTimeField(auto_now_add=True)

    def get_bbox(self):
        try:
            return json.loads(self.bbox_json)
        except Exception:
            return []

    def __str__(self):
        return f"Chunk {self.id} ({self.chunk_type}) - Trang {self.page.page_number}"


# ==============================================================================
# NHÓM 2: CHUYÊN GIA VÀ KỸ NĂNG HIỆN TRƯỜNG (A2 EXPERT KNOWLEDGE)
# ==============================================================================

class Expert(models.Model):
    """Bảng 4: experts — Hồ sơ Kỹ sư / Chuyên gia Line Master"""
    expert_code = models.CharField(max_length=64, unique=True, default='EXP001', verbose_name="Mã chuyên gia")
    name = models.CharField(max_length=128, verbose_name="Họ tên chuyên gia")
    department = models.CharField(max_length=128, default='Bảo trì Cơ điện (Maintenance)', verbose_name="Phòng ban")
    position = models.CharField(max_length=128, default='Senior Line Master', verbose_name="Chức vụ")
    experience_years = models.IntegerField(default=10, verbose_name="Số năm kinh nghiệm")
    avatar_url = models.CharField(max_length=255, blank=True, null=True, verbose_name="Ảnh đại diện")
    description = models.TextField(blank=True, null=True, verbose_name="Mô tả năng lực chuyên môn")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.position})"

    @property
    def total_cases_count(self):
        return self.cases.count()


class ExpertSkill(models.Model):
    """Bảng 5: expert_skills — Kỹ năng cụ thể của chuyên gia (Vd: Bearing, Machine M12)"""
    expert = models.ForeignKey(Expert, on_delete=models.CASCADE, related_name='skills', verbose_name="Chuyên gia")
    skill_name = models.CharField(max_length=128, verbose_name="Tên kỹ năng")
    level = models.IntegerField(default=5, verbose_name="Mức độ thành thạo (1-5)")

    def __str__(self):
        return f"{self.expert.name} - {self.skill_name}: {self.level}/5"


# ==============================================================================
# NHÓM 3: CA SỰ CỐ THỰC TẾ & KHO TRI THỨC (CBR & KNOWLEDGE)
# ==============================================================================

class Case(models.Model):
    """Bảng 6: cases — Ca xử lý sự cố thực tế trên dây chuyền (Case-Based Reasoning)"""
    case_code = models.CharField(max_length=64, unique=True, default='CASE-101', verbose_name="Mã ca sự cố")
    title = models.CharField(max_length=255, verbose_name="Tiêu đề sự cố")
    machine = models.CharField(max_length=128, verbose_name="Thiết bị / Cụm máy")
    part_code = models.CharField(max_length=64, default='N/A', verbose_name="Mã linh kiện / Phụ tùng")
    symptom = models.TextField(verbose_name="Triệu chứng lỗi")
    root_cause = models.TextField(verbose_name="Nguyên nhân gốc rễ")
    solution = models.TextField(verbose_name="Biện pháp xử lý đã thực hiện")
    result = models.CharField(max_length=64, default='Resolved (Đã khắc phục)', verbose_name="Kết quả")
    expert = models.ForeignKey(Expert, on_delete=models.SET_NULL, null=True, blank=True, related_name='cases', verbose_name="Chuyên gia xử lý")
    embedding_json = models.TextField(blank=True, null=True, verbose_name="Vector Embedding JSON")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.case_code}] {self.title} ({self.machine})"


class Knowledge(models.Model):
    """Bảng 7: knowledge — Các quy tắc, SOP ngầm đã được phê duyệt chính thức"""
    KNOWLEDGE_TYPE_CHOICES = (
        ('RULE', 'Quy tắc phán đoán / Xử lý lỗi'),
        ('SOP', 'Quy trình vận hành bổ sung'),
        ('EXCEPTION', 'Quy tắc xử lý ngoại lệ an toàn'),
    )
    STATUS_CHOICES = (
        ('PENDING', 'Chờ phê duyệt'),
        ('APPROVED', 'Đã phê duyệt (Active)'),
        ('REJECTED', 'Đã từ chối'),
    )

    knowledge_code = models.CharField(max_length=64, unique=True, default='K001', verbose_name="Mã tri thức")
    title = models.CharField(max_length=255, verbose_name="Tiêu đề tri thức")
    content = models.TextField(verbose_name="Nội dung quy tắc / tri thức")
    knowledge_type = models.CharField(max_length=20, choices=KNOWLEDGE_TYPE_CHOICES, default='RULE', verbose_name="Loại tri thức")
    source_type = models.CharField(max_length=50, default='EXPERT', verbose_name="Nguồn gốc (EXPERT / DOCUMENT)")
    source_id = models.CharField(max_length=64, default='EXP001', verbose_name="Mã nguồn (Expert ID hoặc Doc ID)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='APPROVED', verbose_name="Trạng thái phê duyệt")
    confidence = models.FloatField(default=0.92, verbose_name="Độ tin cậy (Confidence Score)")
    approved_by = models.ForeignKey(Expert, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_rules', verbose_name="Chuyên gia phê duyệt")
    embedding_json = models.TextField(blank=True, null=True, verbose_name="Vector Embedding JSON")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.knowledge_code}] {self.title} ({self.status})"


# ==============================================================================
# NHÓM 4: PHỎNG VẤN CHUYÊN GIA & LỖ HỔNG TRI THỨC (A2 INTERVIEW & GAP)
# ==============================================================================

class Interview(models.Model):
    """Bảng 8: interviews — Phiên phỏng vấn Socratic trích xuất kinh nghiệm ngầm"""
    STATUS_CHOICES = (
        ('ACTIVE', 'Đang phỏng vấn'),
        ('COMPLETED', 'Đã hoàn thành'),
        ('CONVERTED_TO_KNOWLEDGE', 'Đã chuyển đổi thành Tri thức'),
    )

    interview_code = models.CharField(max_length=64, unique=True, default='INT-001', verbose_name="Mã phiên phỏng vấn")
    expert = models.ForeignKey(Expert, on_delete=models.CASCADE, related_name='interviews', verbose_name="Chuyên gia được phỏng vấn")
    topic = models.CharField(max_length=255, verbose_name="Chủ đề trích xuất tri thức")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='ACTIVE', verbose_name="Trạng thái")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.interview_code}] {self.topic} ({self.expert.name})"


class InterviewMessage(models.Model):
    """Bảng 9: interview_messages — Các lượt hỏi đáp giữa AI và Chuyên gia"""
    SENDER_CHOICES = (
        ('ai', 'Trợ lý AI (Interviewer)'),
        ('expert', 'Chuyên gia (Expert)'),
    )

    interview = models.ForeignKey(Interview, on_delete=models.CASCADE, related_name='messages', verbose_name="Phiên phỏng vấn")
    sender = models.CharField(max_length=20, choices=SENDER_CHOICES, default='ai', verbose_name="Người gửi")
    message = models.TextField(verbose_name="Nội dung thông điệp")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.sender.upper()}]: {self.message[:50]}..."


class KnowledgeGap(models.Model):
    """Bảng 10: knowledge_gaps — Điểm ăn tiền: Lỗ hổng tri thức AI tự phát hiện"""
    STATUS_CHOICES = (
        ('PENDING', 'Chờ phỏng vấn'),
        ('IN_PROGRESS', 'Đang thu thập'),
        ('RESOLVED', 'Đã giải quyết & Tạo Knowledge'),
    )

    question = models.TextField(verbose_name="Câu hỏi chưa có đủ căn cứ trả lời")
    reason = models.TextField(default='Không tìm thấy SOP chính thức hoặc bằng chứng đủ mạnh', verbose_name="Lý do phát hiện")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name="Trạng thái")
    recommended_expert = models.ForeignKey(Expert, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_gaps', verbose_name="Chuyên gia được đề xuất")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Gap: {self.question[:60]}..."


# ==============================================================================
# NHÓM 5: PHẢN HỒI KỸ SƯ (FEEDBACK)
# ==============================================================================

class Feedback(models.Model):
    """Bảng 11: feedback — Đánh giá của kỹ sư hiện trường sau câu trả lời AI"""
    question = models.TextField(verbose_name="Câu hỏi kỹ sư")
    answer = models.TextField(verbose_name="Câu trả lời của AI")
    rating = models.IntegerField(default=5, verbose_name="Đánh giá sao (1-5)")
    comment = models.TextField(blank=True, null=True, verbose_name="Góp ý của kỹ sư")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Feedback ({self.rating}★): {self.question[:40]}..."
