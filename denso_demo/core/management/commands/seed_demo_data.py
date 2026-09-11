from django.core.management.base import BaseCommand
from core.models import Document, DocumentPage, Chunk, Expert, ExpertSkill, Case, Knowledge, KnowledgeGap
from core.services import Neo4jGraphService

class Command(BaseCommand):
    help = 'Nạp dữ liệu mẫu cho DENSO Factory Hackathon 2026 (Problem A2 & A3)'

    def handle(self, *args, **options):
        self.stdout.write("Starting DENSO Factory Memory seeding...")

        # 1. Chuyên gia
        exp_a, _ = Expert.objects.get_or_create(
            expert_code='EXP-001',
            defaults={
                'name': 'Kỹ sư Nguyễn Văn A',
                'department': 'Phòng Bảo trì Cơ điện (Maintenance Line 4)',
                'position': 'Senior Line Master & Chuyên gia Chẩn đoán Rung',
                'experience_years': 16,
                'avatar_url': 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150',
                'description': 'Hơn 16 năm kinh nghiệm bảo trì hệ thống gia công chính xác DENSO. Đã xử lý thành công hơn 14 ca sự cố phức tạp trên cụm máy M12.'
            }
        )

        exp_b, _ = Expert.objects.get_or_create(
            expert_code='EXP-002',
            defaults={
                'name': 'Kỹ sư Trần Thị B',
                'department': 'Phòng Kỹ thuật Tự động hóa (Automation)',
                'position': 'Automation & Sensor Specialist',
                'experience_years': 11,
                'avatar_url': 'https://images.unsplash.com/photo-1580489944761-15a19d654956?w=150',
                'description': 'Chuyên sâu về PLC, cảm biến quang học, phân tích áp suất thủy lực cho dây chuyền lắp ráp linh kiện ô tô.'
            }
        )

        # Kỹ năng chuyên gia
        ExpertSkill.objects.get_or_create(expert=exp_a, skill_name='Machine M12 Diagnostics', defaults={'level': 5})
        ExpertSkill.objects.get_or_create(expert=exp_a, skill_name='Bearing B-230 High Speed', defaults={'level': 5})
        ExpertSkill.objects.get_or_create(expert=exp_a, skill_name='Thermal & Vibration Analysis', defaults={'level': 5})

        ExpertSkill.objects.get_or_create(expert=exp_b, skill_name='Hydraulic Pressure Control', defaults={'level': 5})
        ExpertSkill.objects.get_or_create(expert=exp_b, skill_name='DENSO Robot Arm Calibration', defaults={'level': 4})

        # 2. Tài liệu kỹ thuật SOP & Bóc tách Chunks
        doc, _ = Document.objects.get_or_create(
            doc_code='SOP-023',
            defaults={
                'title': 'SOP-023: Quy trình Bảo dưỡng Trục chính & Căn chỉnh Bearing B-230',
                'doc_type': 'SOP',
                'description': 'Quy chuẩn tiêu chuẩn vận hành, giới hạn rung lắc trục chính và quy trình tháo lắp ổ bi B-230 trên máy M12.',
                'language': 'Vietnamese / Japanese',
                'status': 'PROCESSED'
            }
        )

        page1, _ = DocumentPage.objects.get_or_create(
            document=doc,
            page_number=1,
            defaults={
                'ocr_text': 'QUY CHUẨN ĐỘ RUNG TRỤC CHÍNH MÁY M12. Mức vận hành bình thường: < 2.5 mm/s RMS. Ngưỡng cảnh báo: 2.5 - 4.5 mm/s. Dừng khẩn cấp: > 4.5 mm/s. Tiêu chuẩn áp dụng cho cụm Bearing B-230.'
            }
        )

        page2, _ = DocumentPage.objects.get_or_create(
            document=doc,
            page_number=2,
            defaults={
                'ocr_text': 'QUY TRÌNH THAY THẾ VÒNG BI BEARING B-230. Bước 1: Ngắt nguồn điện máy M12. Bước 2: Tháo nắp chắn dầu. Bước 3: Dùng cảo thủy lực tháo vòng bi cũ. Bước 4: Vệ sinh trục và tra mỡ chịu nhiệt DENSO-HT2.'
            }
        )

        # Chunks
        Chunk.objects.get_or_create(
            page=page1,
            content='Mức rung cho phép trục chính máy M12 dưới 2.5 mm/s RMS. Khi độ rung nằm trong dải 2.5 - 4.5 mm/s cần theo dõi sát sao. Nếu vượt quá 4.5 mm/s, phải dừng máy ngay lập tức để kiểm tra bearing B-230.',
            defaults={'chunk_type': 'table', 'bbox_json': '[120, 45, 310, 520]'}
        )

        Chunk.objects.get_or_create(
            page=page2,
            content='Quy trình tiêu chuẩn căn chỉnh trục và thay thế Bearing B-230: Dùng dụng cụ chuyên dụng cảo vòng bi, tuyệt đối không dùng búa gõ trực tiếp. Tra mỡ bôi trơn chuyên dụng DENSO-HT2 với định lượng 15g.',
            defaults={'chunk_type': 'text', 'bbox_json': '[450, 60, 780, 500]'}
        )

        # 3. Ca sự cố thực tế (Case-Based Reasoning - CBR)
        case1, _ = Case.objects.get_or_create(
            case_code='CASE-101',
            defaults={
                'title': 'Rung trục chính máy M12 do mòn Bearing B-230 sau 6 tháng vận hành',
                'machine': 'Machine M12',
                'part_code': 'Bearing B-230',
                'symptom': 'Cảm biến rung đo được 4.8 mm/s, phát tiếng kêu rít kim loại khi đạt 3,000 RPM.',
                'root_cause': 'Vòng bi Bearing B-230 bị rỗ bề mặt lăn do thiếu mỡ bôi trơn định kỳ.',
                'solution': 'Thay thế Bearing B-230 mới theo SOP-023, tra đầy đủ mỡ DENSO-HT2. Cân bằng động lại trục.',
                'result': 'Resolved (Độ rung hạ xuống 1.1 mm/s RMS)',
                'expert': exp_a
            }
        )

        case2, _ = Case.objects.get_or_create(
            case_code='CASE-102',
            defaults={
                'title': 'Máy M12 rung giật bất thường khi nhiệt độ phòng máy xưởng tăng cao (>40°C)',
                'machine': 'Machine M12',
                'part_code': 'Bearing B-230 / Chiller Unit',
                'symptom': 'Nhiệt độ môi trường chạm 42°C, độ rung máy M12 tăng vọt lên 4.2 mm/s dù bearing mới thay 2 tuần.',
                'root_cause': 'Lọc gió cụm làm mát Chiller bị bám bụi nặng, dầu làm mát quá nhiệt khiến trục máy giãn nở nở nhiệt cưỡng bức gây bó kẹp bearing.',
                'solution': 'Chuyên gia Nguyễn Văn A xử lý: Vệ sinh lưới lọc chiller, bổ sung dung dịch làm mát. Chờ máy hạ nhiệt về 32°C trước khi cân chỉnh. KHÔNG ĐƯỢC THAY BEARING KHI MÁY NÓNG.',
                'result': 'Resolved (Độ rung ổn định 1.3 mm/s)',
                'expert': exp_a
            }
        )

        # Tạo thêm 12 cases mẫu để chuyên gia A đạt đúng 14 cases trên Machine M12
        for i in range(3, 15):
            c_code = f"CASE-{100+i}"
            c_obj, _ = Case.objects.get_or_create(
                case_code=c_code,
                defaults={
                    'title': f'Hiệu chuẩn và căn chỉnh khe hở trục máy M12 định kỳ ca #{i}',
                    'machine': 'Machine M12',
                    'part_code': 'Bearing B-230',
                    'symptom': f'Kiểm tra định kỳ sai số dung sai gia công ca #{i}',
                    'root_cause': 'Độ rơ cơ học sau chu kỳ hoạt động',
                    'solution': 'Siết lại bu lông bệ gá, cân chỉnh đồng trục bằng laser quang học.',
                    'result': 'Resolved (Đạt chuẩn 100%)',
                    'expert': exp_a
                }
            )

        # 4. Tri thức chuẩn đã duyệt (Active Knowledge)
        Knowledge.objects.get_or_create(
            knowledge_code='K-001',
            defaults={
                'title': 'Tiêu chuẩn đánh giá độ rung động cơ và trục chính máy M12',
                'content': 'Vận hành an toàn: <2.5 mm/s RMS. Mức cảnh báo chú ý: 2.5 - 4.5 mm/s. Ngưỡng bắt buộc ngắt dừng khẩn cấp: >4.5 mm/s. Tham chiếu SOP-023.',
                'knowledge_type': 'RULE',
                'source_type': 'DOCUMENT',
                'source_id': 'SOP-023',
                'status': 'APPROVED',
                'confidence': 0.99,
                'approved_by': exp_a
            }
        )

        # 5. Đồng bộ vào Neo4j nếu Neo4j đang bật
        try:
            graph_service = Neo4jGraphService()
            for c in Case.objects.all():
                graph_service.sync_case_to_graph(c)
            self.stdout.write(self.style.SUCCESS("Neo4j Knowledge Graph synced successfully!"))
            graph_service.close()
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Neo4j sync skipped: {e}"))

        self.stdout.write(self.style.SUCCESS("DENSO Factory Memory demo data seeded SUCCESSFULLY!"))
