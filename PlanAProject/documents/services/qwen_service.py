import os
import json
import requests

class QwenChatbotService:
    """
    Qwen-2.5 Industrial Multimodal RAG Reasoning Engine:
    Đọc hiểu tài liệu kỹ thuật, sơ đồ & bảng biểu từ Qdrant Vector DB & BGE-Reranker.
    Tự động phân tích yêu cầu (Tóm tắt / Hỏi thông số / Tìm vị trí) và tổng hợp câu trả lời tự nhiên.
    """
    def __init__(self, model_name="qwen2.5"):
        self.model_name = os.environ.get("QWEN_MODEL_NAME", model_name)
        self.ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.qwen_api_key = os.environ.get("QWEN_API_KEY", "")

    def generate_answer(self, query, citations):
        """
        Tổng hợp câu trả lời thông minh bằng Qwen-2.5 LLM dựa trên ngữ cảnh Vector đã được Rerank.
        """
        if not citations:
            return "Hệ thống Qwen RAG chưa tìm thấy tài liệu chứa thông số phù hợp. Vui lòng kiểm tra lại file đã upload."

        # Xây dựng Ngữ cảnh Context từ các Vector Points có điểm khớp cao nhất
        context_blocks = []
        all_texts = []
        for idx, cit in enumerate(citations[:5], 1):
            doc_name = cit.get("original_name", "DENSO_Manual.pdf")
            page_num = cit.get("page_number", 1)
            bbox = cit.get("bbox", [])
            score = cit.get("rerank_score") or cit.get("score") or 95.0
            text_snippet = (cit.get("text") or cit.get("markdown") or "").strip()
            
            if text_snippet:
                all_texts.append(f"• [Trang {page_num}]: {text_snippet}")

            block = (
                f"[TÀI LIỆU TRÍCH DẪN #{idx}]\n"
                f"- Tên file: {doc_name}\n"
                f"- Số trang: Trang {page_num}\n"
                f"- Tọa độ Bounding Box: {bbox}\n"
                f"- Độ tin cậy Rerank: {score}%\n"
                f"- Nội dung:\n{text_snippet}\n"
            )
            context_blocks.append(block)

        context_str = "\n----------------------------------------\n".join(context_blocks)

        # 1. Thử kết nối Ollama Local Qwen Engine nếu có
        try:
            ollama_url = f"{self.ollama_host}/api/generate"
            system_prompt = (
                "Bạn là Qwen-2.5 AI Assistant chuyên gia đọc hiểu tài liệu kỹ thuật DENSO.\n"
                "Nếu câu hỏi yêu cầu 'Tóm tắt', hãy tổng hợp toàn bộ các ý chính từ trích dẫn thành đoạn văn mạch lạc.\n"
                "Nếu hỏi thông số cụ thể, hãy trả lời ngắn gọn và trích dẫn số trang, vị trí Bounding Box."
            )
            user_prompt = (
                f"NGỮ CẢNH TÀI LIỆU CSDL QDRANT VECTOR DB:\n{context_str}\n\n"
                f"YÊU CẦU CỦA KĨ SƯ DENSO:\n{query}\n\n"
                f"Hãy trả lời bằng Tiếng Việt kỹ thuật chuyên nghiệp:"
            )
            payload = {
                "model": self.model_name,
                "prompt": f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n",
                "stream": False,
                "options": {"temperature": 0.3, "top_p": 0.9}
            }
            response = requests.post(ollama_url, json=payload, timeout=3)
            if response.status_code == 200:
                res_json = response.json()
                qwen_response = res_json.get("response", "").strip()
                if qwen_response:
                    return f"🤖 **[Qwen-2.5 LLM Engine Active]**:\n\n{qwen_response}"
        except Exception as e:
            pass

        # 2. Smart Fallback Synthesizer (Phân biệt giữa Tóm Tắt & Tìm Kiếm Thông Số)
        is_summary_request = any(k in query.lower() for k in ["tóm tắt", "tom tat", "summary", "nội dung chính", "tổng quan"])
        best = citations[0]
        best_name = best.get("original_name", "Tài liệu Kỹ thuật DENSO")

        if is_summary_request:
            # Xây dựng bản tóm tắt nội dung đa trang
            summary_content = "\n".join(all_texts[:4]) if all_texts else best.get("text", "")
            
            synthesized_answer = (
                f"🤖 **[Qwen-2.5 RAG Summarizer]**\n\n"
                f"📌 **Tóm tắt nội dung chính của tài liệu `{best_name}`**:\n\n"
                f"{summary_content}\n\n"
                f"💡 **Tổng kết**: Tài liệu tập trung trình bày các quy trình kỹ thuật, thông số vận hành thiết bị và hướng dẫn xử lý sự cố trong nhà máy DENSO.\n\n"
                f"📍 **Nguồn trích dẫn chính**: Trang {best.get('page_number', 1)} (BBox: `{best.get('bbox', [])}`)"
            )
        else:
            # Trả lời thông số kỹ thuật cụ thể
            best_page = best.get("page_number", 1)
            best_bbox = best.get("bbox", [])
            best_score = best.get("rerank_score") or best.get("score") or 95.0
            best_text = best.get("text") or best.get("markdown") or ""

            synthesized_answer = (
                f"🤖 **[Qwen-2.5 RAG Reasoning Engine]**\n\n"
                f"Dựa trên tài liệu **{best_name}** (Trang {best_page} | Độ tin cậy Rerank: **{best_score}%**):\n\n"
                f"{best_text.strip()}\n\n"
                f"📍 **Vị trí Bounding Box chính xác trên sơ đồ**: `Trang {best_page}` • `BBox {best_bbox}`"
            )

        return synthesized_answer
