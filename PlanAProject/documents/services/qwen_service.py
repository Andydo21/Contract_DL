import os
import re
import base64
import io
from typing import List, Dict, Any, Optional
from pathlib import Path
from PIL import Image
from django.conf import settings
from dotenv import load_dotenv

# Nạp các biến môi trường từ .env nếu có
# Nạp các biến môi trường từ PlanAProject/.env
base_dir = Path(__file__).resolve().parent.parent.parent
env_file = base_dir / ".env"
if env_file.exists():
    load_dotenv(env_file)
else:
    load_dotenv()


class QwenChatbotService:
    """
    Qwen Multimodal Vision-Language Service (Qwen2.5-VL) qua Hugging Face Inference API:
    - Tổng hợp câu trả lời đa phương thức dựa trên Context văn bản & HÌNH ẢNH THỰC TẾ trích xuất từ tài liệu
    - Trực tiếp soi ảnh bản vẽ 2D CAD, sơ đồ phân rã linh kiện, bảng thông số kỹ thuật
    - Đọc chi tiết từng đường gióng, số đo phi (Ø), dung sai, bán kính R, mã phụ tùng (Part Numbers)
    - 100% chạy qua Hugging Face API tốc độ cao, không tốn RAM/VRAM máy chủ cục bộ
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = (
            model_name
            or os.environ.get("QWEN_VL_MODEL")
            or getattr(settings, "QWEN_VL_MODEL", "Qwen/Qwen2.5-VL-72B-Instruct")
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
        return InferenceClient(model=self.model_name, token=token, timeout=75)

    def _prepare_image_payloads(self, images: Optional[List[Dict[str, Any]]], max_images: int = 3) -> List[str]:
        """
        Nạp các ảnh bản vẽ / biểu đồ thực tế từ đĩa, resize tối ưu và mã hóa Base64
        để gửi trực tiếp vào thị giác của Qwen2.5-VL.
        """
        if not images:
            return []

        media_root = getattr(settings, "MEDIA_ROOT", "")
        base64_images = []

        for item in images:
            if len(base64_images) >= max_images:
                break

            img_path = None
            url = item.get("image_url") or item.get("full_page_url") or ""

            if not url or not isinstance(url, str):
                continue

            # 1. Nếu là đường dẫn tuyệt đối
            if os.path.isabs(url) and os.path.exists(url):
                img_path = url
            else:
                # 2. Chuẩn hóa đường dẫn tương đối từ media/
                clean_rel = url.replace("\\", "/").lstrip("/")
                if clean_rel.startswith("media/"):
                    clean_rel = clean_rel[len("media/"):]

                cand_path = os.path.join(media_root, clean_rel)
                if os.path.exists(cand_path):
                    img_path = cand_path
                else:
                    # Thử tìm với full_page_url nếu có
                    full_page = item.get("full_page_url", "")
                    if full_page and full_page != url:
                        clean_full = full_page.replace("\\", "/").lstrip("/")
                        if clean_full.startswith("media/"):
                            clean_full = clean_full[len("media/"):]
                        cand_full = os.path.join(media_root, clean_full)
                        if os.path.exists(cand_full):
                            img_path = cand_full

            if img_path and os.path.isfile(img_path):
                try:
                    with Image.open(img_path) as pil_img:
                        pil_img = pil_img.convert("RGB")
                        # Giới hạn kích thước tối đa 1024 để tiết kiệm token và đảm bảo tốc độ phản hồi nhanh
                        max_dim = 1024
                        if max(pil_img.width, pil_img.height) > max_dim:
                            pil_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                        buf = io.BytesIO()
                        pil_img.save(buf, format="JPEG", quality=85)
                        b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                        base64_images.append(b64_str)
                except Exception as e:
                    print(f"[QwenService] Không thể xử lý ảnh {img_path}: {e}")
                    continue

        return base64_images

    def generate_answer(
        self,
        query: str,
        citations: List[Dict[str, Any]],
        images: Optional[List[Dict[str, Any]]] = None,
        mode: str = "hybrid"
    ) -> str:
        """
        Tổng hợp câu trả lời Đa phương thức (Multimodal) từ Text Citations và Hình ảnh thực tế:
        - Qwen2.5-VL trực tiếp quan sát ảnh bản vẽ CAD, sơ đồ phân rã, đọc số đo và chi tiết linh kiện
        - Phân tích sâu sắc về cơ cấu cơ khí, vị trí lắp ráp và nguyên lý vận hành
        """
        if not citations and not images:
            return "Hệ thống RAG chưa tìm thấy thông tin phù hợp với truy vấn trong kho tài liệu. Vui lòng thử lại với từ khóa khác."

        # Chuẩn bị context văn bản từ các trích dẫn vector
        context_blocks = []
        for c in (citations or [])[:6]:
            txt = (c.get("text") or c.get("markdown") or "").strip()
            txt_clean = self._clean_block_text(txt)
            if txt_clean:
                doc_name = c.get("original_name", "Tài liệu")
                page = c.get("page_number") or c.get("page_num", 1)
                bbox_info = f" | BBox: {c.get('bbox')}" if c.get('bbox') else ""
                context_blocks.append(f"• [Tài liệu: {doc_name} | Trang {page}{bbox_info}]:\n{txt_clean}")

        context_text = "\n\n".join(context_blocks) if context_blocks else "Không có đoạn văn bản trích dẫn rời rạc."

        # Chuẩn bị hình ảnh cho mắt nhìn của Qwen-VL
        image_payloads = self._prepare_image_payloads(images, max_images=3)
        has_images = len(image_payloads) > 0

        # Định hình System Instruction chuyên gia thị giác cơ khí
        system_instruction = (
            "Bạn là Trợ lý AI Qwen-2.5-VL Đa Phương Thức (DENSO Multimodal VisionMind) — "
            "Chuyên gia Cao cấp về Đọc hiểu Bản vẽ Kỹ thuật Cơ khí 2D/3D, Sơ đồ Lắp ráp Phân rã, "
            "Bảng Thông số & Quy trình Bảo trì của Nhà máy DENSO.\n\n"
            "QUY TẮC PHÂN TÍCH KỸ SƯ CƠ KHÍ:\n"
            "1. QUAN SÁT TRỰC QUAN TOÀN DIỆN: Nếu có hình ảnh đính kèm, hãy soi kỹ vào từng chi tiết trong ảnh: "
            "đọc rõ các đường gióng kích thước, số đo đường kính phi (Ø), bán kính (R), khoảng cách tâm lỗ bu-lông, "
            "dung sai (±), góc vát (chamfer), độ nhám bề mặt và mã phụ tùng (Part Numbers).\n"
            "2. MÔ TẢ HÌNH HỌC VÀ CẤU TẠO: Mô tả rõ chi tiết cơ khí này có cấu tạo như thế nào (dạng trục bậc, mặt bích, "
            "thân vỏ hộp, gân tăng cứng, mộng ren, rãnh then trượt...).\n"
            "3. NGUYÊN LÝ VÀ CHỨC NĂNG LẮP RÁP: Giải thích chi tiết máy này lắp ghép vào vị trí nào trong cụm máy/robot, "
            "vai trò chịu lực, định vị hay truyền động trong dây chuyền sản xuất DENSO.\n"
            "4. TRẢ LỜI CỰC KỲ CHI TIẾT & CHÍNH XÁC: Tuyệt đối không trả lời chung chung hoặc né tránh. "
            "Hãy trình bày mạch lạc, sử dụng các đầu mục, gạch đầu dòng và số liệu cụ thể tìm thấy trong tài liệu và bản vẽ.\n"
            "5. ĐỊNH VỊ CHÍNH XÁC NGUỒN VÀ TỌA ĐỘ ẢNH: Luôn chỉ rõ tên tài liệu, số trang và vùng Bounding Box [ymin, xmin, ymax, xmax] "
            "của hình ảnh/bản vẽ được trích dẫn để kỹ sư dễ dàng đối chiếu trực tiếp trên trang PDF gốc."
        )

        visual_note = f" (Kèm {len(image_payloads)} hình ảnh/bản vẽ thực tế được đính kèm bên dưới)" if has_images else ""
        header_prompt = f"DỮ LIỆU NGỮ CẢNH KỸ THUẬT{visual_note}:\n"

        image_metadata_text = ""
        if has_images:
            img_lines = []
            for idx, img in enumerate((images or [])[:len(image_payloads)]):
                doc = img.get("original_name", "Tài liệu")
                pg = img.get("page_number", 1)
                bb = img.get("bbox", [])
                ltype = img.get("layout_type", "hình ảnh")
                img_lines.append(f"• [Hình ảnh #{idx+1}]: Thuộc tài liệu '{doc}', Trang {pg}, Vùng BBox: {bb} (Loại: {ltype})")
            image_metadata_text = "\nVỊ TRÍ HÌNH ẢNH TRÍCH XUẤT TRÊN TÀI LIỆU:\n" + "\n".join(img_lines) + "\n"

        user_prompt_text = (
            f"{header_prompt}{context_text}\n"
            f"{image_metadata_text}\n"
            f"CÂU HỎI TRUY VẤN CỦA KỸ SƯ:\n{query}\n\n"
            f"Dựa trên hình ảnh bản vẽ/sơ đồ đính kèm và ngữ cảnh kỹ thuật trên, hãy trả lời chi tiết, "
            f"phân tích cụ thể các thông số, kích thước, cấu tạo hình học, nêu rõ số trang và tọa độ BBox tìm thấy:"
        )

        llm_response = ""
        try:
            client = self._get_hf_client()

            # Xây dựng message đa phương thức nếu có hình ảnh
            if has_images:
                user_content = [{"type": "text", "text": user_prompt_text}]
                for b64_str in image_payloads:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"}
                    })
                messages = [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content}
                ]
            else:
                messages = [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt_text}
                ]

            chat_completion = client.chat.completions.create(
                messages=messages,
                max_tokens=1500,        # Nâng lên 1500 tokens để Qwen phân tích sâu sắc, đầy đủ
                temperature=0.2,        # Nhiệt độ thấp đảm bảo thông số cơ khí chuẩn xác, không bị ảo giác
                top_p=0.9
            )
            if chat_completion.choices and len(chat_completion.choices) > 0:
                llm_response = chat_completion.choices[0].message.content.strip()

        except Exception as hf_err:
            error_msg = str(hf_err)
            print(f"[Qwen Multimodal HF API Inference Error] {error_msg}")

            # Cơ chế Fallback an toàn: nếu gửi ảnh bị lỗi mạng, tự động thử lại bằng text-only
            if has_images:
                try:
                    print("[Qwen Multimodal] Đang thử lại với chế độ Text-Only Fallback...")
                    fallback_client = self._get_hf_client()
                    fb_res = fallback_client.chat.completions.create(
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_prompt_text}
                        ],
                        max_tokens=1000,
                        temperature=0.2
                    )
                    if fb_res.choices and len(fb_res.choices) > 0:
                        return fb_res.choices[0].message.content.strip()
                except Exception as fb_err:
                    error_msg += f" | Fallback Error: {fb_err}"

            if "api_key" in error_msg.lower() or "token" in error_msg.lower() or "401" in error_msg:
                llm_response = (
                    "⚠️ **Chưa cấu hình Hugging Face Token (`HF_TOKEN`)**:\n"
                    "Vui lòng cấu hình token trong file `.env`:\n"
                    "```bash\nHF_TOKEN=hf_your_token_here\n```"
                )
            elif "loading" in error_msg.lower() or "503" in error_msg:
                llm_response = (
                    f"⏳ Mô hình thị giác **{self.model_name}** trên Hugging Face đang khởi động. "
                    "Vui lòng gửi lại câu hỏi sau 10-15 giây."
                )
            else:
                llm_response = f"⚠️ Lỗi kết nối Hugging Face Vision API ({self.model_name}): {error_msg}"

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
