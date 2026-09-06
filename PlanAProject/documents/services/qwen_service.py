import os
import re
from typing import List, Dict, Any, Optional
from django.conf import settings
from dotenv import load_dotenv

# Nạp các biến môi trường từ .env nếu có
load_dotenv()


class QwenChatbotService:
    """
    Qwen LLM Service qua Hugging Face Inference API:
    - Tổng hợp câu trả lời dựa trên Context thu được từ Vector Search (ColPali, Qdrant, BGE-Reranker, Neo4j)
    - Nhận ngữ cảnh trích xuất từ các vector embeddings của kho tài liệu nhà máy
    - Phân tích và giải thích ý nghĩa các thông số kỹ thuật, bản vẽ CAD, tiêu chuẩn ISO, quy trình SOP
    - 100% chạy qua Hugging Face API (đã loại bỏ hoàn toàn việc nạp model nặng cục bộ)
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = (
            model_name
            or os.environ.get("QWEN_VL_MODEL")
            or getattr(settings, "QWEN_VL_MODEL", "Qwen/Qwen2.5-72B-Instruct")
        )
        self.hf_token = (
            os.environ.get("HF_TOKEN")
            or os.environ.get("HUGGING_FACE_HUB_TOKEN")
            or getattr(settings, "HF_TOKEN", "")
        )

    def _get_hf_client(self):
        """Khởi tạo Hugging Face InferenceClient"""
        from huggingface_hub import InferenceClient
        token = self.hf_token if self.hf_token else None
        return InferenceClient(model=self.model_name, token=token, timeout=60)

    def generate_answer(self, query: str, citations: List[Dict[str, Any]]) -> str:
        """
        Tổng hợp câu trả lời từ các trích dẫn vector retrieval:
        Nhận trực tiếp context dữ liệu từ các vector được trích xuất và rerank từ hệ thống.
        """
        if not citations:
            return "Hệ thống RAG chưa tìm thấy thông tin phù hợp với truy vấn trong kho tài liệu. Vui lòng thử lại với từ khóa khác."

        # Chuẩn bị context văn bản từ các trích dẫn vector
        context_blocks = []
        for c in citations[:4]:
            txt = (c.get("text") or c.get("markdown") or "").strip()
            txt_clean = self._clean_block_text(txt)
            if txt_clean:
                doc_name = c.get("original_name", "Tài liệu")
                page = c.get("page_number") or c.get("page_num", 1)
                context_blocks.append(f"• [Tài liệu: {doc_name} | Trang {page}]:\n{txt_clean}")

        context_text = "\n\n".join(context_blocks)

        # 1. Gọi Hugging Face Inference API với mô hình Qwen
        llm_response = None
        system_instruction = (
            "Bạn là Trợ lý AI Chuyên gia Phân tích Bản vẽ Kỹ thuật & Tài liệu Nhà máy DENSO (DENSO VisionMind AI).\n"
            "Phong cách trả lời:\n"
            "1. ĐÚNG TRỌNG TÂM: Trả lời trực tiếp và chính xác câu hỏi của người dùng dựa trên Dữ liệu Ngữ cảnh trích xuất.\n"
            "2. PHÂN TÍCH KỸ THUẬT CHUYÊN SÂU: Giải thích ý nghĩa chức năng cơ khí, dung sai lắp ghép hoặc an toàn của chính thông số được hỏi. Tránh giải thích lan man sang các thông số khác không liên quan đến câu hỏi.\n"
            "3. NGÔN NGỮ TỰ NHIÊN: Trình bày mạch lạc, súc tích, chuyên nghiệp bằng Tiếng Việt."
        )

        user_prompt = (
            f"DỮ LIỆU NGỮ CẢNH TRÍCH XUẤT:\n{context_text}\n\n"
            f"CÂU HỎI TRUY VẤN CỦA KỸ SƯ:\n{query}\n\n"
            f"Hãy trả lời chính xác câu hỏi trên và phân tích ý nghĩa kỹ thuật liên quan trực tiếp đến thông số được hỏi:"
        )

        try:
            client = self._get_hf_client()
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ]

            chat_completion = client.chat.completions.create(
                messages=messages,
                max_tokens=800,
                temperature=0.3,
                top_p=0.9
            )
            if chat_completion.choices and len(chat_completion.choices) > 0:
                llm_response = chat_completion.choices[0].message.content.strip()
        except Exception as hf_err:
            error_msg = str(hf_err)
            print(f"[Qwen HF API Inference Error] {error_msg}")

            if "api_key" in error_msg.lower() or "token" in error_msg.lower() or "401" in error_msg:
                llm_response = (
                    "⚠️ **Chưa cấu hình Hugging Face Token (`HF_TOKEN`)**:\n"
                    "Vui lòng cấu hình token trong file `.env`:\n"
                    "```bash\nHF_TOKEN=hf_your_token_here\n```"
                )
            elif "loading" in error_msg.lower() or "503" in error_msg:
                llm_response = (
                    f"⏳ Mô hình **{self.model_name}** trên Hugging Face đang khởi động (Cold boot). "
                    "Vui lòng gửi lại câu hỏi sau 15-20 giây."
                )
            else:
                llm_response = f"⚠️ Lỗi kết nối Hugging Face Inference API ({self.model_name}): {error_msg}"

        if llm_response:
            return llm_response
        return "Hệ thống AI chưa thể tạo câu trả lời cho truy vấn này. Vui lòng thử lại."

    def _clean_block_text(self, text: str) -> str:
        """Gộp các dòng văn bản bị ngắt dòng rời rạc thành các cụm thông tin liền mạch, dễ đọc"""
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("[")]
        if not lines:
            return ""

        grouped = []
        buf = ""
        for line in lines:
            if line in ["(", ")"]:
                continue
            # Nếu dòng hiện tại bắt đầu bằng chữ thường hoặc từ nối, ghép vào dòng trước
            if buf and (
                re.match(r"^[a-z0-9\+\-\(]", line)
                or line.lower().startswith(
                    (
                        "for ", "screw", "face", "mounting", "dimensions",
                        "space", "depth", "type", "from", "of", "with",
                        "and", "or", "to", "in", "at"
                    )
                )
            ):
                buf += " " + line
            else:
                if buf:
                    grouped.append(buf)
                buf = line
        if buf:
            grouped.append(buf)

        return "\n".join(grouped)
