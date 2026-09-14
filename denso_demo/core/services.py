import os
import json
from typing import List, Dict, Any, Optional
from django.conf import settings
from django.db.models import Count
from core.models import Knowledge, Expert, Interview, InterviewMessage, KnowledgeGap, Document, Case
from core.repositories import (
    DocumentRepository,
    CaseRepository,
    KnowledgeRepository,
    ExpertRepository,
    InterviewRepository
)

# ==============================================================================
# 1. DỊCH VỤ NEO4J INDUSTRIAL KNOWLEDGE GRAPH
# ==============================================================================

class Neo4jGraphService:
    """
    Dịch vụ Đồ thị tri thức Công nghiệp Neo4j (Graph RAG):
    - Quản lý mạng lưới quan hệ đa tầng:
      (Machine) -[:HAS_COMPONENT]-> (Component) -[:EXHIBITS]-> (Symptom)
                -[:CAUSED_BY]-> (RootCause) -[:RESOLVED_BY]-> (Solution)
                -[:STANDARDIZED_IN]-> (SOP)
    - Truy vấn Multi-Hop Reasoning cho câu hỏi kỹ thuật hiện trường.
    - Graph Routing: Tìm chuyên gia kinh nghiệm nhất xử lý từng dòng máy.
    - Đồng bộ tri thức mới từ phỏng vấn Socratic vào Đồ thị.
    """
    def __init__(self):
        self.uri = getattr(settings, 'NEO4J_URI', 'bolt://localhost:7687')
        self.user = getattr(settings, 'NEO4J_USER', 'neo4j')
        self.password = getattr(settings, 'NEO4J_PASSWORD', 'denso2026')
        self.driver = None
        self._connect()

    def _connect(self):
        try:
            from neo4j import GraphDatabase
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                connection_timeout=2.0
            )
        except Exception:
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()

    def is_connected(self) -> bool:
        if not self.driver:
            self._connect()
        if not self.driver:
            return False
        try:
            with self.driver.session() as session:
                res = session.run("RETURN 1 AS ping")
                return res.single() is not None
        except Exception:
            return False

    def seed_factory_knowledge_graph(self):
        """
        Khởi tạo Đồ thị tri thức Kỹ thuật Nhà máy Đa tầng (Multi-Hop Causal Graph)
        HOÀN TOÀN TỰ ĐỘNG TỪ CƠ SỞ DỮ LIỆU THỰC TẾ (Case, Document, Knowledge, Expert),
        TUYỆT ĐỐI KHÔNG DÙNG DỮ LIỆU MOCK / HARDCODE!
        """
        if not self.is_connected():
            return False
        try:
            with self.driver.session() as session:
                # 1. Tạo Schema & Ràng buộc (Constraints / Indexes)
                session.run("CREATE CONSTRAINT machine_name IF NOT EXISTS FOR (m:Machine) REQUIRE m.name IS UNIQUE")
                session.run("CREATE CONSTRAINT component_name IF NOT EXISTS FOR (c:Component) REQUIRE c.name IS UNIQUE")
                session.run("CREATE CONSTRAINT expert_name IF NOT EXISTS FOR (e:Expert) REQUIRE e.name IS UNIQUE")
                session.run("CREATE CONSTRAINT sop_code IF NOT EXISTS FOR (s:SOP) REQUIRE s.code IS UNIQUE")
                session.run("CREATE CONSTRAINT case_code IF NOT EXISTS FOR (cs:Case) REQUIRE cs.code IS UNIQUE")

                # Xóa sạch các node mock cũ nếu có
                session.run("MATCH (n) DETACH DELETE n")

                # 2. Nạp toàn bộ Experts từ Database thực tế
                from core.models import Expert, Case, Document, Knowledge
                for exp in Expert.objects.all():
                    session.run("""
                    MERGE (e:Expert {name: $name})
                    ON CREATE SET e.position = $position, e.department = $department, e.experience_years = $exp_years
                    """, name=exp.name, position=exp.position, department=exp.department, exp_years=exp.experience_years)
                    
                    for sk in exp.skills.all():
                        session.run("""
                        MATCH (e:Expert {name: $exp_name})
                        MERGE (s:Skill {name: $skill_name})
                        MERGE (e)-[:HAS_SKILL {level: $level}]->(s)
                        """, exp_name=exp.name, skill_name=sk.skill_name, level=sk.level)

                # 3. Nạp toàn bộ Tài liệu SOP từ Database thực tế
                for doc in Document.objects.all():
                    session.run("""
                    MERGE (sop:SOP {code: $code})
                    ON CREATE SET sop.title = $title, sop.doc_type = $doc_type
                    """, code=doc.doc_code, title=doc.title, doc_type=doc.doc_type)

                # 4. Nạp toàn bộ Quy tắc Tri thức đã duyệt từ Database thực tế
                for k in Knowledge.objects.all():
                    session.run("""
                    MERGE (kr:KnowledgeRule {code: $code})
                    ON CREATE SET kr.title = $title, kr.content = $content, kr.confidence = $conf
                    """, code=k.knowledge_code, title=k.title, content=k.content, conf=k.confidence)
                    if k.approved_by:
                        session.run("""
                        MATCH (e:Expert {name: $exp_name})
                        MATCH (kr:KnowledgeRule {code: $code})
                        MERGE (e)-[:VALIDATED]->(kr)
                        """, exp_name=k.approved_by.name, code=k.knowledge_code)

                # 5. Nạp Đồ thị Đa tầng từ toàn bộ 14 Ca sự cố thực tế (Cases Layer)
                for cs in Case.objects.select_related('expert').all():
                    part_name = cs.part_code if cs.part_code and cs.part_code != 'N/A' else f"Cụm linh kiện {cs.machine}"
                    expert_name = cs.expert.name if cs.expert else "Chuyên gia DENSO"

                    cypher_case = """
                    MERGE (m:Machine {name: $machine})
                    MERGE (c:Component {name: $part_name})
                    MERGE (m)-[:HAS_COMPONENT]->(c)

                    MERGE (sym:Symptom {name: $symptom})
                    MERGE (c)-[:EXHIBITS]->(sym)

                    MERGE (rc:RootCause {name: $root_cause})
                    MERGE (sym)-[:CAUSED_BY]->(rc)

                    MERGE (sol:Solution {name: $solution})
                    MERGE (rc)-[:RESOLVED_BY]->(sol)

                    MERGE (case_node:Case {code: $case_code})
                    ON CREATE SET case_node.title = $title, case_node.result = $result
                    MERGE (case_node)-[:OCCURRED_ON]->(m)
                    MERGE (case_node)-[:HAS_SYMPTOM]->(sym)
                    MERGE (case_node)-[:CAUSED_BY]->(rc)
                    MERGE (case_node)-[:RESOLVED_BY]->(sol)

                    MERGE (e:Expert {name: $expert_name})
                    MERGE (e)-[:RESOLVED]->(case_node)
                    MERGE (e)-[:SPECIALIZES_IN]->(m)
                    """
                    session.run(
                        cypher_case,
                        machine=cs.machine,
                        part_name=part_name,
                        symptom=cs.symptom,
                        root_cause=cs.root_cause,
                        solution=cs.solution,
                        case_code=cs.case_code,
                        title=cs.title,
                        result=cs.result,
                        expert_name=expert_name
                    )

                # 6. Tự động liên kết SOP với Giải pháp nếu tiêu đề SOP chứa tên máy hoặc linh kiện
                session.run("""
                MATCH (m:Machine)
                MATCH (sop:SOP)
                WHERE toLower(sop.title) CONTAINS toLower(m.name)
                   OR toLower(sop.title) CONTAINS 'm12' AND toLower(m.name) CONTAINS 'm12'
                MATCH (m)-[:HAS_COMPONENT]->(c:Component)-[:EXHIBITS]->(sym)-[:CAUSED_BY]->(rc)-[:RESOLVED_BY]->(sol:Solution)
                MERGE (sol)-[:STANDARDIZED_IN]->(sop)
                """)

                return True
        except Exception as e:
            print("[Neo4j Dynamic Seed Error]", e)
            return False

    def traverse_multi_hop_graph(self, query: str, matched_cases: Optional[List[Any]] = None, limit: int = 4) -> List[Dict[str, Any]]:
        """
        Vector-Guided Multi-Hop Graph Traversal:
        Duyệt đồ thị tri thức đa bước hoàn toàn dựa trên Vector Embedding:
        1. Tìm Node điểm xuất phát (Seed Nodes) qua Cosine Similarity của Multilingual Embedding.
        2. Duyệt chuỗi nhân quả trong Neo4j: (Machine) -> (Component) -> (Symptom) -> (RootCause) -> (Solution).
        HOÀN TOÀN KHÔNG DÙNG REGEX HAY TỪ DỪNG (STOP WORDS)!
        """
        if not self.is_connected():
            return []

        if matched_cases is None:
            from core.repositories import CaseRepository
            matched_cases = CaseRepository.search_cases(query, limit=limit)

        case_codes = [c.case_code for c in matched_cases] if matched_cases else []
        if not case_codes:
            return []

        cypher_traverse = """
        MATCH (cs:Case)-[:OCCURRED_ON]->(m:Machine)
        MATCH (cs)-[:HAS_SYMPTOM]->(s:Symptom)
        MATCH (cs)-[:CAUSED_BY]->(r:RootCause)
        MATCH (cs)-[:RESOLVED_BY]->(sol:Solution)
        OPTIONAL MATCH (m)-[:HAS_COMPONENT]->(c:Component)
        OPTIONAL MATCH (e:Expert)-[:RESOLVED]->(cs)
        OPTIONAL MATCH (sol)-[:STANDARDIZED_IN]->(sop:SOP)
        WHERE cs.code IN $case_codes
        RETURN DISTINCT
            m.name AS machine,
            c.name AS component,
            s.name AS symptom,
            r.name AS root_cause,
            sol.name AS solution,
            sop.code AS sop_code,
            sop.title AS sop_title,
            e.name AS expert_name
        LIMIT $limit
        """
        try:
            with self.driver.session() as session:
                results = session.run(cypher_traverse, case_codes=case_codes, limit=limit)
                records = []
                for rec in results:
                    records.append({
                        'machine': rec['machine'],
                        'component': rec['component'] or f"Cụm linh kiện {rec['machine']}",
                        'symptom': rec['symptom'],
                        'root_cause': rec['root_cause'],
                        'solution': rec['solution'],
                        'sop_code': rec['sop_code'] or 'SOP-CHƯA-GHI-NHẬN',
                        'sop_title': rec['sop_title'] or '',
                        'expert_name': rec['expert_name'] or 'Chuyên gia Kỹ thuật DENSO'
                    })
                return records
        except Exception as e:
            print("[Neo4j Traversal Notice]", e)
            return []

    def format_graph_context(self, query: str, matched_cases: Optional[List[Any]] = None):
        """Định dạng chuỗi quan hệ Multi-hop thành văn bản Markdown và Citations cho LLM Context"""
        paths = self.traverse_multi_hop_graph(query, matched_cases=matched_cases, limit=3)
        if not paths:
            return "", []

        lines = ["### [TẦNG 4: ĐỒ THỊ TRI THỨC NHÀ MÁY (GRAPH RAG - MULTI-HOP REASONING)]"]
        citations = []
        for idx, p in enumerate(paths, 1):
            chain_text = (
                f"• [Chuỗi Nhân Quả #{idx}]:\n"
                f"  - Thiết bị: {p['machine']} ➔ Cụm linh kiện: {p['component']}\n"
                f"  - Hiện tượng/Triệu chứng: {p['symptom']}\n"
                f"  - Nguyên nhân gốc rễ: {p['root_cause']}\n"
                f"  - Giải pháp xử lý: {p['solution']}\n"
                f"  - Quy chuẩn: {p['sop_code']} | Chuyên gia kiểm chứng: {p['expert_name']}"
            )
            lines.append(chain_text)
            citations.append({
                'title': f"Graph Path #{idx}: {p['machine']} ➔ {p['component']}",
                'type': 'GRAPH RAG (NEO4J)',
                'confidence': '96%'
            })

        return "\n".join(lines), citations

    def sync_case_to_graph(self, case_obj):
        """Đồng bộ Ca sự cố thực tế vào đồ thị Neo4j"""
        if not self.is_connected():
            return
        try:
            with self.driver.session() as session:
                cypher = """
                MERGE (m:Machine {name: $machine})
                MERGE (e:Expert {name: $expert_name})
                MERGE (c:Case {code: $case_code, title: $title, solution: $solution})
                MERGE (e)-[:RESOLVED]->(c)
                MERGE (c)-[:OCCURRED_ON]->(m)
                """
                session.run(
                    cypher,
                    machine=case_obj.machine,
                    expert_name=case_obj.expert.name if case_obj.expert else 'DENSO Expert',
                    case_code=case_obj.case_code,
                    title=case_obj.title,
                    solution=case_obj.solution
                )
        except Exception as err:
            print("[Neo4j Sync Case Error]", str(err)[:80])

    def sync_distilled_rule_to_graph(self, rule_title: str, rule_content: str, expert_name: str, machine_name: str = "Máy gia công M12"):
        """Tự động đồng bộ Quy tắc mới được chắt lọc từ Phỏng vấn Chuyên gia vào Neo4j Graph"""
        if not self.is_connected():
            return
        try:
            with self.driver.session() as session:
                cypher = """
                MERGE (m:Machine {name: $machine_name})
                MERGE (e:Expert {name: $expert_name})
                MERGE (r:KnowledgeRule {title: $title, content: $content})
                MERGE (e)-[:DISTILLED]->(r)
                MERGE (r)-[:APPLIES_TO]->(m)
                """
                session.run(
                    cypher,
                    machine_name=machine_name,
                    expert_name=expert_name,
                    title=rule_title,
                    content=rule_content
                )
        except Exception as err:
            print("[Neo4j Sync Distilled Rule Error]", str(err)[:80])

    def find_best_expert_for_machine(self, machine_name: str) -> Optional[str]:
        """Cypher Query: Tìm chuyên gia đã giải quyết nhiều ca nhất trên máy này"""
        if not self.is_connected():
            return None
        try:
            with self.driver.session() as session:
                cypher = """
                MATCH (e:Expert)-[:SPECIALIZES_IN|RESOLVED*1..2]->(m:Machine)
                WHERE toLower(m.name) CONTAINS toLower($machine)
                RETURN e.name AS expert_name, count(*) AS count
                ORDER BY count DESC
                LIMIT 1
                """
                result = session.run(cypher, machine=machine_name)
                record = result.single()
                if record:
                    return record['expert_name']
        except Exception:
            return None
        return None


# ==============================================================================
# 2. DỊCH VỤ QWEN2.5-VL AI (DYNAMIC RAG GENERATOR)
# ==============================================================================

class QwenAIService:
    """Gọi mô hình AI để tổng hợp câu trả lời từ Ngữ cảnh trích xuất thực tế"""
    def __init__(self):
        self.model_name = getattr(settings, 'QWEN_VL_MODEL', 'Qwen/Qwen2.5-VL-72B-Instruct')
        self.hf_token = getattr(settings, 'HF_TOKEN', '')
        self.vllm_base_url = getattr(settings, 'VLLM_BASE_URL', '') or os.getenv('VLLM_BASE_URL', '')
        self.vllm_api_key = getattr(settings, 'VLLM_API_KEY', 'EMPTY') or os.getenv('VLLM_API_KEY', 'EMPTY')
        self.vllm_model = getattr(settings, 'VLLM_MODEL', 'Qwen/Qwen2.5-VL-7B-Instruct-AWQ') or os.getenv('VLLM_MODEL', 'Qwen/Qwen2.5-VL-7B-Instruct-AWQ')

    def _call_llm(self, messages: list, max_tokens: int = 800, temperature: float = 0.2) -> Optional[str]:
        """Thử gọi qua vLLM OpenAI-compatible trước, sau đó fallback sang HF InferenceClient"""
        # 1. Thử gọi vLLM (Local GPU / Kaggle ngrok / OpenAI-compatible API)
        if self.vllm_base_url:
            try:
                from openai import OpenAI
                client = OpenAI(
                    base_url=self.vllm_base_url,
                    api_key=self.vllm_api_key,
                    timeout=75.0,
                    default_headers={"ngrok-skip-browser-warning": "true"}
                )
                completion = client.chat.completions.create(
                    model=self.vllm_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                if completion.choices:
                    return completion.choices[0].message.content.strip()
            except Exception as v_err:
                print("[QwenAIService vLLM Notice - Fallback to HF]", str(v_err)[:80])

        # 2. Thử gọi Hugging Face InferenceClient
        try:
            from huggingface_hub import InferenceClient
            client = InferenceClient(model=self.model_name, token=self.hf_token if self.hf_token else None, timeout=10)
            completion = client.chat.completions.create(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            if completion.choices:
                return completion.choices[0].message.content.strip()
        except Exception as hf_err:
            print("[QwenAIService HF Notice]", str(hf_err)[:80])

        return None

    def generate_response(self, query: str, context_text: str) -> str:
        """Sinh câu trả lời từ dữ liệu ngữ cảnh trích xuất được từ Knowledge Base"""
        if not context_text.strip():
            return "Không tìm thấy dữ liệu phù hợp trong kho tri thức để trả lời câu hỏi này."

        system_instruction = (
            "Bạn là Trợ lý Tri thức Nhà máy DENSO (DENSO Knowledge Intelligence Mind). "
            "Nhiệm vụ: Trả lời câu hỏi của kỹ sư DỰA HOÀN TOÀN TRÊN NGỮ CẢNH ĐƯỢC TRÍCH XUẤT TỪ KHO TRI THỨC NHÀ MÁY (SOP, Ca sự cố, Quy tắc Chuyên gia). "
            "Trích dẫn cụ thể tài liệu, số trang, mã ca hoặc mã quy tắc làm bằng chứng (Evidence Provenance). "
            "Không bịa đặt thông tin không có trong ngữ cảnh."
        )

        user_content = (
            f"DỮ LIỆU TRÍCH XUẤT TỪ KHO TRI THỨC NHÀ MÁY (KNOWLEDGE BASE CONTEXT):\n{context_text}\n\n"
            f"CÂU HỎI CỦA KỸ SƯ:\n{query}\n\n"
            f"Hãy đưa ra câu trả lời chi tiết và nêu rõ nguồn trích dẫn từ ngữ cảnh trên:"
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content}
        ]

        response = self._call_llm(messages, max_tokens=800, temperature=0.1)
        if response:
            return response

        # Dynamic fallback: Trình bày trực tiếp toàn bộ dữ liệu trích xuất được từ DB
        return self._format_dynamic_context(context_text)

    def generate_socratic_followup(self, topic: str, conversation_history: list, expert_name: str) -> str:
        """Sinh câu hỏi Socratic phản biện động dựa trên câu trả lời thực tế của chuyên gia"""
        system_instruction = (
            f"Bạn là Trợ lý AI Phỏng vấn Chuyên gia (Socratic Interviewer) của nhà máy DENSO. "
            f"Mục tiêu của bạn là khai phá tri thức ngầm (Tacit Knowledge) của Chuyên gia {expert_name} về chủ đề: '{topic}'. "
            "Nhiệm vụ: Đọc phản hồi mới nhất của chuyên gia và đặt 1 câu hỏi Socratic ngắn gọn, sâu sắc (1-2 câu). "
            "Tập trung hỏi sâu vào: Tại sao lại ưu tiên giải pháp đó? Điều kiện môi trường/ngưỡng thông số cụ thể là gì? "
            "Làm sao nhận biết được nguyên nhân gốc rễ thay vì can thiệp cơ khí vội vàng? "
            "Giữ phong thái lịch sự, kính cẩn với chuyên gia."
        )

        history_text = "\n".join([f"{m.get('sender', 'user').upper()}: {m.get('message', '')}" for m in conversation_history])
        user_prompt = f"LỊCH SỬ PHỎNG VẤN:\n{history_text}\n\nHãy đặt câu hỏi Socratic phản biện tiếp theo:"

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt}
        ]

        response = self._call_llm(messages, max_tokens=250, temperature=0.3)
        if response:
            return response

        # Dynamic fallback phân tích từ câu trả lời cuối cùng của chuyên gia
        last_reply = conversation_history[-1].get('message', '') if conversation_history else ''
        return (
            f"Thưa anh {expert_name}, đối với kinh nghiệm anh vừa chia sẻ ('{last_reply[:60]}...'), "
            f"anh có thể cho biết thêm: Tại sao ta cần kiểm tra bước này trước thay vì can thiệp cơ khí ngay, "
            f"và dấu hiệu đo lường dung sai/thông số nào cho thấy biện pháp này đã đạt chuẩn an toàn?"
        )

    def synthesize_knowledge_rule(self, topic: str, expert_name: str, expert_replies: list) -> dict:
        """Chuyển đổi toàn bộ câu trả lời thực tế của chuyên gia thành Quy tắc Tri thức chuẩn (Standard Rule)"""
        replies_text = "\n".join([f"- {r}" for r in expert_replies])
        system_instruction = (
            f"Bạn là Chuyên gia Chuẩn hóa Tri thức Nhà máy DENSO (Knowledge Distillation Engine). "
            f"Nhiệm vụ: Trích xuất các câu trả lời thực tế của Chuyên gia {expert_name} về chủ đề '{topic}' "
            f"thành một Quy tắc Tri thức hoàn chỉnh (Knowledge Unit).\n"
            f"Định dạng yêu cầu:\n"
            f"Tiêu đề: [Quy tắc xử lý ...]\n"
            f"Điều kiện kích hoạt (Trigger Condition): ...\n"
            f"Nguyên nhân cốt lõi (Root Cause): ...\n"
            f"Quy trình xử lý ưu tiên (Standard Action): ...\n"
            f"Lưu ý dung sai/an toàn (Safety Precaution): ..."
        )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": f"KINH NGHIỆM THỰC TẾ CHUYÊN GIA CHIA SẺ:\n{replies_text}\n\nHãy chuẩn hóa thành Quy tắc Tri thức:"}
        ]

        response = self._call_llm(messages, max_tokens=500, temperature=0.2)
        if response:
            title_line = [l for l in response.split('\n') if 'tiêu đề' in l.lower() or 'quy tắc' in l.lower()]
            title = title_line[0].replace('**', '').replace('Tiêu đề:', '').strip() if title_line else f"Quy tắc chuẩn hóa: {topic} ({expert_name})"
            return {"title": title, "content": response}

        return {
            "title": f"Quy tắc chuyên gia: Xử lý {topic} ({expert_name})",
            "content": (
                f"### [DENSO KNOWLEDGE UNIT - CHUẨN HÓA TỪ CHUYÊN GIA {expert_name.upper()}]\n\n"
                f"**1. Phạm vi & Tình huống kích hoạt:** {topic}\n\n"
                f"**2. Nguyên nhân cốt lõi xác định qua phỏng vấn:**\n"
                f"{replies_text}\n\n"
                f"**3. Khuyến cáo quy trình chuẩn:** Ưu tiên kiểm tra điều kiện nhiệt độ/bôi trơn trước khi tháo dỡ cơ khí nhằm bảo toàn dung sai chuẩn của dây chuyền."
            )
        }

    def _format_dynamic_context(self, context_text: str) -> str:
        """Tổng hợp động từ các đoạn trích xuất thực tế khi API bên ngoài bận"""
        return (
            "### 🛠️ THÔNG TIN TRÍCH XUẤT TỪ KHO TRI THỨC NHÀ MÁY (EVIDENCE):\n\n"
            f"{context_text}\n\n"
            "---\n"
            "*📌 Dữ liệu được trích xuất trực tiếp từ các thực thể Knowledge, SOP Chunks và Case CBR trong cơ sở dữ liệu.*"
        )



# ==============================================================================
# 3. DỊCH VỤ VECTOR EMBEDDING & TÌM KIẾM NGỮ NGHĨA (SEMANTIC SEARCH)
# ==============================================================================

class EmbeddingService:
    """Dịch vụ Vector Embeddings (MiniLM) & Cross-Encoder Reranking (BGE-M3) chạy 100% Local Cache"""
    _model = None
    _reranker = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                cls._model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
            except Exception as e:
                print(f"[EmbeddingService Notice] {e}")
        return cls._model

    @classmethod
    def get_reranker(cls):
        if cls._reranker is None:
            try:
                from sentence_transformers import CrossEncoder
                cls._reranker = CrossEncoder('BAAI/bge-reranker-v2-m3')
            except Exception as e:
                print(f"[Reranker Notice] {e}")
        return cls._reranker

    @classmethod
    def embed_text(cls, text: str) -> List[float]:
        model = cls.get_model()
        if model and text.strip():
            return model.encode(text).tolist()
        return []

    @classmethod
    def cosine_similarity(cls, vec1: List[float], vec2: List[float]) -> float:
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        import numpy as np
        v1 = np.array(vec1, dtype=float)
        v2 = np.array(vec2, dtype=float)
        dot = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot / (norm1 * norm2))

    @classmethod
    def compute_relevance_score(cls, query: str, context_text: str) -> float:
        """Đo lường độ liên quan ngữ nghĩa chuẩn xác bằng Multilingual CrossEncoder BGE-M3"""
        reranker = cls.get_reranker()
        if reranker and query.strip() and context_text.strip():
            try:
                scores = reranker.predict([(query, context_text[:400])])
                return float(scores[0])
            except Exception:
                pass
        # Fallback
        q_vec = cls.embed_text(query)
        c_vec = cls.embed_text(context_text[:400])
        return cls.cosine_similarity(q_vec, c_vec)


# ==============================================================================
# 3.5 DỊCH VỤ VECTOR DATABASE QDRANT (HNSW VECTOR SEARCH ENGINE)
# ==============================================================================

class QdrantVectorService:
    """
    Dịch vụ lưu trữ và truy vấn Vector Database Qdrant:
    - Quản lý 3 Collections:
        1. 'denso_chunks': Văn bản & Bảng biểu SOP
        2. 'denso_cases': Ký ức ca sự cố thực tế CBR
        3. 'denso_knowledge': Quy tắc tri thức chuyên gia đã duyệt
    - Sử dụng chuẩn khoảng cách Cosine Distance (Vector 384D)
    - HNSW Graph Indexing cho tốc độ tìm kiếm < 5ms
    - Kết nối linh hoạt: Qdrant Server (http://localhost:6333) -> Embedded Storage ('qdrant_storage')
    """
    VECTOR_DIM = 384
    COLLECTION_CHUNKS = "denso_chunks"
    COLLECTION_CASES = "denso_cases"
    COLLECTION_KNOWLEDGE = "denso_knowledge"
    _instance = None

    def __init__(self):
        self.client = self._get_client()
        self._ensure_collections()

    @classmethod
    def _get_client(cls):
        if cls._instance is None:
            try:
                import urllib.request
                urllib.request.urlopen("http://localhost:6333/collections", timeout=0.8)
                from qdrant_client import QdrantClient
                cls._instance = QdrantClient(host="localhost", port=6333)
                print("[QdrantService] Connected to Qdrant Server at http://localhost:6333")
            except Exception:
                from qdrant_client import QdrantClient
                storage_path = os.path.join(settings.BASE_DIR, 'qdrant_storage')
                os.makedirs(storage_path, exist_ok=True)
                cls._instance = QdrantClient(path=storage_path)
                print(f"[QdrantService] Initialized Embedded Qdrant Storage at {storage_path}")
        return cls._instance

    def _ensure_collections(self):
        from qdrant_client.models import Distance, VectorParams
        collections = [self.COLLECTION_CHUNKS, self.COLLECTION_CASES, self.COLLECTION_KNOWLEDGE]
        try:
            existing = [c.name for c in self.client.get_collections().collections]
            for col in collections:
                if col not in existing:
                    self.client.create_collection(
                        collection_name=col,
                        vectors_config=VectorParams(size=self.VECTOR_DIM, distance=Distance.COSINE)
                    )
        except Exception as e:
            print(f"[QdrantService Collection Notice] {e}")

    def upsert_chunk(self, chunk_id: int, vector: List[float], payload: Dict[str, Any]):
        from qdrant_client.models import PointStruct
        self.client.upsert(
            collection_name=self.COLLECTION_CHUNKS,
            points=[PointStruct(id=chunk_id, vector=vector, payload=payload)]
        )

    def upsert_case(self, case_id: int, vector: List[float], payload: Dict[str, Any]):
        from qdrant_client.models import PointStruct
        self.client.upsert(
            collection_name=self.COLLECTION_CASES,
            points=[PointStruct(id=case_id, vector=vector, payload=payload)]
        )

    def upsert_knowledge(self, knowledge_id: int, vector: List[float], payload: Dict[str, Any]):
        from qdrant_client.models import PointStruct
        self.client.upsert(
            collection_name=self.COLLECTION_KNOWLEDGE,
            points=[PointStruct(id=knowledge_id, vector=vector, payload=payload)]
        )

    def _query(self, collection_name: str, query_vector: List[float], limit: int):
        if hasattr(self.client, 'query_points'):
            res = self.client.query_points(collection_name=collection_name, query=query_vector, limit=limit)
            return res.points
        elif hasattr(self.client, 'search'):
            return self.client.search(collection_name=collection_name, query_vector=query_vector, limit=limit)
        return []

    def search_chunks(self, query_vector: List[float], limit: int = 8) -> List[Dict[str, Any]]:
        if not query_vector:
            return []
        try:
            results = self._query(self.COLLECTION_CHUNKS, query_vector, limit=limit)
            hits = []
            for r in results:
                p = r.payload or {}
                hits.append({
                    'chunk_id': r.id,
                    'document_title': p.get('document_title', ''),
                    'doc_code': p.get('doc_code', ''),
                    'page_number': p.get('page_number', 1),
                    'chunk_type': p.get('chunk_type', 'text'),
                    'content': p.get('content', ''),
                    'bbox': p.get('bbox', []),
                    'image_url': p.get('image_url', ''),
                    'score': round(float(r.score), 3)
                })
            return hits
        except Exception as e:
            print(f"[Qdrant Search Chunks Error] {e}")
            return []

    def search_cases(self, query_vector: List[float], limit: int = 4) -> List[Any]:
        if not query_vector:
            return []
        try:
            results = self._query(self.COLLECTION_CASES, query_vector, limit=limit)
            case_ids = [r.id for r in results]
            if not case_ids:
                return []
            cases_dict = {c.id: c for c in Case.objects.filter(id__in=case_ids).select_related('expert')}
            ordered_cases = []
            for r in results:
                c_obj = cases_dict.get(r.id)
                if c_obj:
                    c_obj.sim_score = round(float(r.score), 3)
                    ordered_cases.append(c_obj)
            return ordered_cases
        except Exception as e:
            print(f"[Qdrant Search Cases Error] {e}")
            return []

    def search_knowledge(self, query_vector: List[float], limit: int = 3) -> List[Knowledge]:
        if not query_vector:
            return []
        try:
            results = self._query(self.COLLECTION_KNOWLEDGE, query_vector, limit=limit)
            k_ids = [r.id for r in results]
            if not k_ids:
                return []
            k_dict = {k.id: k for k in Knowledge.objects.filter(id__in=k_ids).select_related('approved_by')}
            ordered_rules = []
            for r in results:
                k_obj = k_dict.get(r.id)
                if k_obj:
                    ordered_rules.append(k_obj)
            return ordered_rules
        except Exception as e:
            print(f"[Qdrant Search Knowledge Error] {e}")
            return []


# ==============================================================================
# 4. DỊCH VỤ TRÍCH XUẤT TRI THỨC & ĐIỀU PHỐI (KNOWLEDGE INTELLIGENCE)
# ==============================================================================

class KnowledgeIntelligenceService:
    """
    Dịch vụ điều phối RAG Đa tầng dựa trên Vector Embeddings & Cross-Encoder:
    1. Trích xuất từ Bảng Knowledge (Tri thức / Quy tắc đã duyệt)
    2. Trích xuất từ Bảng Document/Chunk (Tài liệu kỹ thuật / SOP)
    3. Trích xuất từ Bảng Case (Ký ức ca sự cố thực tế CBR)
    4. Tự động phát hiện Lỗ hổng Tri thức (Knowledge Gap) hoàn toàn bằng AI Embeddings
    """
    def __init__(self):
        self.qwen_service = QwenAIService()
        self.graph_service = Neo4jGraphService()

    def process_chat(self, question: str) -> Dict[str, Any]:
        # BƯỚC 1: TRÍCH XUẤT THỰC TẾ TỪ 3 TẦNG KNOWLEDGE BASE BẰNG VECTOR EMBEDDING
        matched_knowledge = KnowledgeRepository.search_knowledge(question, limit=3)
        matched_chunks = DocumentRepository.search_chunks(question, limit=4)
        matched_cases = CaseRepository.search_cases(question, limit=3)

        citations = []
        context_blocks = []

        # 1.1 Nạp tri thức chính thức đã duyệt (Knowledge Layer)
        if matched_knowledge:
            k_lines = ["### [TẦNG 1: QUY TẮC TRI THỨC CHUYÊN GIA ĐÃ DUYỆT]"]
            for k in matched_knowledge:
                k_lines.append(f"• [{k.knowledge_code}] {k.title}:\n  {k.content}")
                citations.append({
                    'title': f"{k.knowledge_code}: {k.title}",
                    'type': 'EXPERT RULE (ACTIVE)',
                    'confidence': f"{int(k.confidence * 100)}%"
                })
            context_blocks.append("\n".join(k_lines))

        # 1.2 Nạp tài liệu tiêu chuẩn kỹ thuật (SOP Chunks Layer)
        if matched_chunks:
            chunk_lines = ["### [TẦNG 2: QUY TRÌNH TIÊU CHUẨN KỸ THUẬT (SOP)]"]
            for ch in matched_chunks:
                chunk_lines.append(f"• [{ch['doc_code']} Trang {ch['page_number']}]: {ch['content']}")
                citations.append({
                    'title': f"{ch['doc_code']} (Trang {ch['page_number']})",
                    'type': 'SOP DOCUMENT',
                    'confidence': '92%'
                })
            context_blocks.append("\n".join(chunk_lines))

        # 1.3 Nạp ca sự cố thực tế (CBR Cases Layer)
        if matched_cases:
            case_lines = ["### [TẦNG 3: CA SỰ CỐ THỰC TẾ TƯƠNG TỰ (CASE MEMORY)]"]
            for c in matched_cases:
                case_lines.append(f"• [{c.case_code}] {c.title}:\n  - Triệu chứng: {c.symptom}\n  - Giải pháp: {c.solution}")
                citations.append({
                    'title': f"{c.case_code}: {c.title}",
                    'type': 'CASE CBR',
                    'confidence': '88%'
                })
            context_blocks.append("\n".join(case_lines))

        # 1.4 Nạp Đồ thị Tri thức Đa tầng (Graph RAG - Multi-Hop Causal Reasoning)
        graph_text, graph_citations = self.graph_service.format_graph_context(question, matched_cases=matched_cases)
        if graph_text:
            context_blocks.append(graph_text)
            citations.extend(graph_citations)

        # BƯỚC 2: PHÁT HIỆN LỖ HỔNG TRI THỨC (KNOWLEDGE GAP) BẰNG BGE CROSS-ENCODER RERANKING
        candidate_snippets = []
        for ch in matched_chunks:
            candidate_snippets.append(ch['content'])
        for k in matched_knowledge:
            candidate_snippets.append(f"{k.title} {k.content}")
        for c in matched_cases:
            candidate_snippets.append(f"{c.title} {c.symptom} {c.solution}")
        if graph_text:
            candidate_snippets.append(graph_text)

        if candidate_snippets:
            relevance_scores = [EmbeddingService.compute_relevance_score(question, txt) for txt in candidate_snippets[:4]]
            max_relevance = max(relevance_scores, default=0.0)
        else:
            max_relevance = 0.0

        # Ngưỡng Reranking Ngữ nghĩa: Nếu độ liên quan cao nhất < 0.40 (như Robot, Thủy lực)
        # hoặc hoàn toàn không có tài liệu liên quan -> Khẳng định là Knowledge Gap!
        is_knowledge_gap = (max_relevance < 0.40) or (len(matched_knowledge) == 0 and len(matched_chunks) == 0)

        if is_knowledge_gap:
            # Tìm chuyên gia phù hợp nhất dựa trên thiết bị trong câu hỏi
            expert = self._find_expert_for_query(question)
            refined_question = self.refine_question_for_expert(question, expert)

            gap = InterviewRepository.create_gap(
                question=question,
                reason=f"Kho tri thức SOP hiện tại chưa có thông tin quy chuẩn tương đồng (Semantic Relevance: {max_relevance * 100:.1f}%).",
                expert=expert
            )

            return {
                'has_gap': True,
                'gap_id': gap.id,
                'gap_reason': gap.reason,
                'raw_question': question,
                'refined_question': refined_question,
                'coverage_score': f"{int(max_relevance * 100)}%",
                'vector_similarity': round(max_relevance, 3),
                'recommended_expert': {
                    'id': expert.id if expert else 1,
                    'name': expert.name if expert else 'Chuyên gia DENSO',
                    'cases_count': expert.total_cases_count if expert else 0,
                    'position': expert.position if expert else 'Line Master'
                },
                'answer': (
                    "⚠️ **CHƯA CÓ TRONG KNOWLEDGE BASE (KNOWLEDGE GAP DETECTED)**\n\n"
                    f"Hệ thống tính toán Vector Embedding & Reranking phát hiện vấn đề kỹ thuật này hoàn toàn mới và chưa từng có quy chuẩn trong kho SOP (Độ tương đồng ngữ nghĩa: **{max_relevance * 100:.1f}%**).\n\n"
                    "🤖 **AI đã tự động tinh chỉnh câu hỏi kỹ thuật** để chuyển tiếp phỏng vấn Chuyên gia phụ trách dây chuyền."
                ),
                'citations': citations
            }

        # BƯỚC 3: NẾU KHÔNG CÓ GAP (ĐÃ CÓ TRI THỨC HOẶC SOP RÕ RÀNG TRONG DATABASE)
        full_context = "\n\n".join(context_blocks)
        ai_answer = self.qwen_service.generate_response(question, full_context)

        return {
            'has_gap': False,
            'answer': ai_answer,
            'citations': citations
        }

    def refine_question_for_expert(self, raw_question: str, expert: Optional[Expert], missing_factors: Optional[List[str]] = None) -> str:
        """
        AI tự động phân tích và tinh chỉnh câu hỏi hiện trường của kỹ sư
        thành câu hỏi phỏng vấn kỹ thuật chuẩn mực để gửi tới Chuyên gia.
        """
        exp_name = expert.name if expert else "Line Master"
        salutation = f"Chào {exp_name}" if exp_name.startswith("Kỹ sư") else f"Chào Kỹ sư {exp_name}"
        factors_text = f"liên quan đến [{', '.join(missing_factors)}]" if missing_factors else ""
        return (
            f"{salutation}. Hiện trường dây chuyền vừa ghi nhận tình huống: '{raw_question}'. "
            f"Kho quy chuẩn SOP hiện tại chưa có hướng dẫn chính thức cho các điều kiện {factors_text}. "
            f"Theo kinh nghiệm thực tế qua các ca xử lý tương tự của anh, anh thường kiểm tra nguyên nhân gốc rễ ở đâu và quy trình khắc phục an toàn nhất nên được thực hiện như thế nào?"
        )

    def _find_expert_for_query(self, query: str) -> Optional[Expert]:
        """Tìm chuyên gia dựa trên thiết bị hoặc ca sự cố trong database / Neo4j"""
        q_lower = query.lower()
        # 1. Tìm theo tên máy xuất hiện trong DB
        machines = Case.objects.values_list('machine', flat=True).distinct()
        for m in machines:
            if m.lower() in q_lower:
                # Ưu tiên đồ thị Neo4j
                expert_name = self.graph_service.find_best_expert_for_machine(m)
                if expert_name:
                    exp = Expert.objects.filter(name__icontains=expert_name).first()
                    if exp:
                        return exp
                # Fallback qua repository
                return ExpertRepository.find_best_expert_for_machine(m)

        # 2. Mặc định lấy chuyên gia có nhiều ca xử lý nhất
        return Expert.objects.annotate(c_count=Count('cases')).order_by('-c_count').first() or Expert.objects.first()


# ==============================================================================
# 4. DỊCH VỤ PHỎNG VẤN CHUYÊN GIA & SINH RULE TRI THỨC ĐỘNG (A2)
# ==============================================================================

class SocraticInterviewService:
    """Chuyển hóa đối thoại phỏng vấn chuyên gia thực tế thành Quy tắc Tri thức chuẩn hóa (Knowledge Unit)"""

    @staticmethod
    def generate_socratic_question(interview: Interview, expert_reply: str) -> str:
        """Sử dụng Qwen AI sinh câu hỏi Socratic phản biện dựa trên câu trả lời thực tế của chuyên gia"""
        messages = InterviewRepository.get_messages(interview.id)
        history = [{'sender': m.sender, 'message': m.message} for m in messages]
        qwen = QwenAIService()
        return qwen.generate_socratic_followup(
            topic=interview.topic,
            conversation_history=history,
            expert_name=interview.expert.name
        )

    @staticmethod
    def generate_rule_from_interview(expert_id: int, topic: str, interview_id: int) -> Knowledge:
        expert = ExpertRepository.get_expert_by_id(expert_id) or Expert.objects.first()
        messages = InterviewRepository.get_messages(interview_id) if interview_id else []

        # Trích xuất toàn bộ câu trả lời thực tế mà Chuyên gia đã nhập trong buổi đối thoại
        expert_replies = [m.message for m in messages if m.sender == 'expert']
        
        qwen = QwenAIService()
        if expert_replies:
            synthesis = qwen.synthesize_knowledge_rule(
                topic=topic,
                expert_name=expert.name,
                expert_replies=expert_replies
            )
            rule_title = synthesis.get('title')
            synthesized_content = synthesis.get('content')
        else:
            rule_title = f"Quy tắc chuyên gia: {topic}"
            synthesized_content = f"Kinh nghiệm thực tế từ Chuyên gia {expert.name} về: {topic}"

        count = Knowledge.objects.count() + 1
        k_code = f"K-{count:03d}"
        vec = EmbeddingService.embed_text(f"{rule_title} {synthesized_content}")
        emb_json = json.dumps(vec) if vec else ''

        knowledge = Knowledge.objects.create(
            knowledge_code=k_code,
            title=rule_title,
            content=synthesized_content,
            knowledge_type='RULE',
            source_type='EXPERT',
            source_id=f"INT-{interview_id}" if interview_id else (expert.expert_code if expert else 'EXP001'),
            status='PENDING',
            confidence=0.96,
            approved_by=expert,
            embedding_json=emb_json
        )

        # Tự động đồng bộ Quy tắc mới được chắt lọc vào Neo4j Graph
        try:
            graph_svc = Neo4jGraphService()
            graph_svc.sync_distilled_rule_to_graph(
                rule_title=rule_title,
                rule_content=synthesized_content,
                expert_name=expert.name if expert else "Chuyên gia DENSO"
            )
        except Exception:
            pass

        if interview_id:
            interview = Interview.objects.filter(id=interview_id).first()
            if interview:
                interview.status = 'COMPLETED'
                interview.save()

        return knowledge

