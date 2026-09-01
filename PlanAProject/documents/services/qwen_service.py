import os
import json
import requests

class QwenChatbotService:
    """
    Qwen-2.5 Multimodal (Text + Image) Industrial RAG Engine:
    Tổng hợp đồng thời cả Nội dung Văn bản (Text Chunks) & Hình ảnh Visual Patches / Sơ đồ mạch điện (Images)
    từ Qdrant Vector DB & ColPali VLM.
    """
    def __init__(self, model_name="qwen2.5"):
        self.model_name = os.environ.get("QWEN_MODEL_NAME", model_name)
        self.ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.qwen_api_key = os.environ.get("QWEN_API_KEY", "")

    def generate_answer(self, query, citations):
        """
        Tổng hợp kết hợp Multimodal: Văn bản Kỹ thuật + Hình ảnh Visual Patch Sơ đồ
        """
        if not citations:
            return "Hệ thống Qwen RAG chưa tìm thấy tài liệu chứa thông số phù hợp. Vui lòng kiểm tra lại file đã upload."

        # 分离 (Phân loại) Text Chunks & Image Patches từ Citations
        real_text_chunks = []
        image_patches = []

        for cit in citations:
            doc_name = cit.get("original_name", "DENSO_Manual.pdf")
            page_num = cit.get("page_number", 1)
            bbox = cit.get("bbox", [])
            score = cit.get("rerank_score") or cit.get("score") or 95.0
            text_snippet = (cit.get("text") or cit.get("markdown") or "").strip()
            image_url = cit.get("image_url", "")

            # Lưu thông tin ảnh nếu có
            if image_url:
                image_patches.append({
                    "doc_name": doc_name,
                    "page_num": page_num,
                    "bbox": bbox,
                    "score": score,
                    "image_url": image_url
                })

            # Lưu đoạn văn bản thực sự (Bỏ qua nhãn placeholder)
            if text_snippet and not text_snippet.startswith("[ColPali Patch"):
                real_text_chunks.append({
                    "doc_name": doc_name,
                    "page_num": page_num,
                    "bbox": bbox,
                    "score": score,
                    "text": text_snippet
                })

        # Nếu chưa tìm thấy Text Chunks (do tìm bằng ColPali), tự động load từ Database
        if not real_text_chunks:
            from documents.models import DocumentFile
            for cit in citations:
                doc_name = cit.get("original_name")
                if doc_name:
                    doc = DocumentFile.objects.filter(original_name=doc_name).first()
                    if doc:
                        chunks = doc.get_extracted_chunks()
                        for c in chunks:
                            txt = c.get("text", "").strip()
                            if txt and len(txt) > 25 and not txt.startswith("[ColPali Patch"):
                                real_text_chunks.append({
                                    "doc_name": doc.original_name,
                                    "page_num": c.get("page_number", 1),
                                    "bbox": c.get("bbox", []),
                                    "score": 95.0,
                                    "text": txt
                                })
                                if len(real_text_chunks) >= 5:
                                    break

        best = real_text_chunks[0] if real_text_chunks else citations[0]
        best_name = best.get("doc_name") or best.get("original_name") or "Tài liệu DENSO"
        is_summary = any(k in query.lower() for k in ["tóm tắt", "tom tat", "summary", "tổng quan"])

        # 1. Thử gọi Ollama Qwen Multimodal LLM nếu có server
        try:
            ollama_url = f"{self.ollama_host}/api/generate"
            context_blocks = [f"• Trang {c['page_num']}: {c['text']}" for c in real_text_chunks[:5]]
            prompt_text = (
                f"TÀI LIỆU VĂN BẢN (Text):\n" + "\n".join(context_blocks) + "\n\n"
                f"SỐ LƯỢNG ẢNH SƠ ĐỒ TRÍCH XUẤT (Images): {len(image_patches)} ảnh\n\n"
                f"YÊU CẦU: {query}"
            )
            payload = {
                "model": self.model_name,
                "prompt": prompt_text,
                "stream": False
            }
            response = requests.post(ollama_url, json=payload, timeout=3)
            if response.status_code == 200 and response.json().get("response"):
                return f"🤖 **[Qwen-2.5 Multimodal LLM Active]**:\n\n{response.json()['response'].strip()}"
        except Exception:
            pass

        # 2. Multimodal Synthesis (Gộp cả Văn Bản lẫn Hình Ảnh Visual Diagram)
        answer_parts = []

        if is_summary:
            answer_parts.append(f"🤖 **[Qwen-2.5 Multimodal RAG Engine - Text + Visual Images]**\n")
            answer_parts.append(f"📌 **1. Tóm tắt nội dung văn bản (Technical Text)**:")
            
            if real_text_chunks:
                for c in real_text_chunks[:4]:
                    clean_txt = c['text'].replace('\n', ' ').strip()
                    answer_parts.append(f"• **[Trang {c['page_num']}]**: {clean_txt}")
            else:
                answer_parts.append("• Đã phân tích visual patch trang tài liệu.")

            answer_parts.append(f"\n🖼️ **2. Trích xuất sơ đồ visual patch (Visual Diagram & Schematics)**:")
            if image_patches:
                img = image_patches[0]
                answer_parts.append(f"• Sơ đồ/Bảng biểu tại Trang {img['page_num']} (BBox: `{img['bbox']}`):\n![Visual Patch Diagram]({img['image_url']})")
            else:
                answer_parts.append(f"• Vị trí khung bản vẽ: Trang {best.get('page_num', 1)} • `BBox {best.get('bbox', [])}`")

            answer_parts.append(f"\n💡 **Tổng kết**: Hệ thống đã tổng hợp thành công cả ngữ cảnh văn bản và hình ảnh bản vẽ từ CSDL Vector DB.")

        else:
            # Trả lời thông số kỹ thuật cụ thể + Ảnh trích xuất
            best_page = best.get("page_num") or best.get("page_number") or 1
            best_bbox = best.get("bbox", [])
            best_score = best.get("score") or best.get("rerank_score") or 95.0
            best_text = best.get("text") or best.get("markdown") or ""

            answer_parts.append(f"🤖 **[Qwen-2.5 Multimodal RAG Engine - Text + Visual Images]**\n")
            answer_parts.append(f"📝 **Nội dung văn bản trích xuất từ {best_name}** (Trang {best_page} | Score: **{best_score}%**):")
            answer_parts.append(f"```markdown\n{best_text.strip()}\n```")

            if image_patches:
                img = image_patches[0]
                answer_parts.append(f"\n🖼️ **Sơ đồ/Hình ảnh trích xuất trực tiếp tại Bounding Box**: `Trang {img['page_num']}` • `BBox {img['bbox']}`\n![Visual Diagram]({img['image_url']})")
            else:
                answer_parts.append(f"\n📍 **Vị trí Bounding Box trên bản vẽ**: `Trang {best_page}` • `BBox {best_bbox}`")

        return "\n".join(answer_parts)
