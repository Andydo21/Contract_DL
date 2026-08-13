import os
from PIL import Image, ImageDraw, ImageFont

def draw_e2e_flow():
    # Modern professional colors
    bg_color = (255, 255, 255)       # White
    text_color = (15, 23, 42)        # Slate 900
    primary_color = (79, 70, 229)    # Indigo 600
    accent_color = (30, 41, 59)      # Slate 800
    arrow_color = (99, 102, 241)     # Indigo 500
    light_indigo = (238, 242, 255)   # Indigo 50
    
    # Create image
    img = Image.new("RGB", (1200, 700), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Load Font
    try:
        font_title = ImageFont.truetype("arial.ttf", 26)
        font_box = ImageFont.truetype("arial.ttf", 16)
        font_box_bold = ImageFont.truetype("arial.ttf", 18)
        font_sub = ImageFont.truetype("arial.ttf", 14)
    except IOError:
        font_title = ImageFont.load_default()
        font_box = ImageFont.load_default()
        font_box_bold = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # Draw Title
    draw.text((600, 30), "SƠ ĐỒ LUỒNG NGHIỆP VỤ ĐẦU - CUỐI (END-TO-END FLOW)", fill=primary_color, font=font_title, anchor="mm")
    
    # Define steps
    steps = [
        ("1. Upload Contract", "Front-end SPA gửi file/text\nlên Django Backend API.", (80, 120)),
        ("2. AES-256 Encryption", "Mã hóa tệp tin bằng AES\ntrước khi lưu trữ vật lý.", (360, 120)),
        ("3. OCR / PDF Extraction", "PaddleOCR & PyMuPDF trích\nvăn bản, chia trang Context.", (640, 120)),
        ("4. Clause Splitting", "Phân tách điều khoản qua\nAI (hoặc Fallback Regex).", (920, 120)),
        ("5. Entity Extraction", "Trích xuất thực thể pháp lý\n(Bên A, Bên B, Giá trị...).", (920, 380)),
        ("6. LLM Risk Analysis", "Qwen 2.5 3B (NF4) tìm lỗi\nrủi ro, đề xuất khắc phục.", (640, 380)),
        ("7. Blockchain Anchoring", "Neo băm SHA-256 & Merkle\nRoot lên Fabric ledger.", (360, 380)),
        ("8. Digital Signature", "Ký duyệt số bước phê duyệt\ngắn với HashProof & Cert.", (80, 380)),
    ]
    
    box_w, box_h = 220, 100
    
    # Draw Boxes
    for i, (title, desc, pos) in enumerate(steps):
        x, y = pos
        # Rounded box
        draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=10, fill=light_indigo, outline=primary_color, width=2)
        # Title
        draw.text((x + box_w/2, y + 25), title, fill=primary_color, font=font_box_bold, anchor="mm")
        # Desc
        draw.text((x + box_w/2, y + 65), desc, fill=accent_color, font=font_sub, anchor="mm")
        
    # Draw Arrows
    def draw_arrow(start, end):
        draw.line([start, end], fill=arrow_color, width=3)
        # Draw small arrow head
        # Simple line drawing for arrow tip
        # Horizontal / Vertical check
        sx, sy = start
        ex, ey = end
        if sx < ex: # Right arrow
            draw.polygon([(ex, ey), (ex - 8, ey - 5), (ex - 8, ey + 5)], fill=arrow_color)
        elif sx > ex: # Left arrow
            draw.polygon([(ex, ey), (ex + 8, ey - 5), (ex + 8, ey + 5)], fill=arrow_color)
        elif sy < ey: # Down arrow
            draw.polygon([(ex, ey), (ex - 5, ey - 8), (ex + 5, ey - 8)], fill=arrow_color)
        elif sy > ey: # Up arrow
            draw.polygon([(ex, ey), (ex - 5, ey + 8), (ex + 5, ey + 8)], fill=arrow_color)

    # Connecting arrows
    draw_arrow((80 + box_w, 120 + box_h/2), (360, 120 + box_h/2)) # 1 -> 2
    draw_arrow((360 + box_w, 120 + box_h/2), (640, 120 + box_h/2)) # 2 -> 3
    draw_arrow((640 + box_w, 120 + box_h/2), (920, 120 + box_h/2)) # 3 -> 4
    
    draw_arrow((920 + box_w/2, 120 + box_h), (920 + box_w/2, 380)) # 4 -> 5
    
    draw_arrow((920, 380 + box_h/2), (640 + box_w, 380 + box_h/2)) # 5 -> 6
    draw_arrow((640, 380 + box_h/2), (360 + box_w, 380 + box_h/2)) # 6 -> 7
    draw_arrow((360, 380 + box_h/2), (80 + box_w, 380 + box_h/2)) # 7 -> 8
    
    # Legend
    draw.rectangle([100, 580, 1100, 650], fill=(241, 245, 249), outline=(203, 213, 225))
    draw.text((600, 615), "Chú thích: Dữ liệu được bảo mật bằng AES-256 | OCR hỗ trợ tiếng Việt | Blockchain Hyperledger Fabric xác thực chống từ chối.", fill=accent_color, font=font_sub, anchor="mm")
    
    os.makedirs(r"d:\Django_project\RiskDL\scratch", exist_ok=True)
    img.save(r"d:\Django_project\RiskDL\scratch\flow_e2e.png")
    print("Generated flow_e2e.png successfully.")

def draw_entity_flow():
    bg_color = (255, 255, 255)
    text_color = (15, 23, 42)
    primary_color = (79, 70, 229)
    accent_color = (30, 41, 59)
    arrow_color = (148, 163, 184) # Slate 400
    light_slate = (241, 245, 249)
    light_indigo = (238, 242, 255)
    
    img = Image.new("RGB", (1200, 700), bg_color)
    draw = ImageDraw.Draw(img)
    
    try:
        font_title = ImageFont.truetype("arial.ttf", 26)
        font_box = ImageFont.truetype("arial.ttf", 16)
        font_box_bold = ImageFont.truetype("arial.ttf", 18)
        font_sub = ImageFont.truetype("arial.ttf", 14)
    except IOError:
        font_title = ImageFont.load_default()
        font_box = ImageFont.load_default()
        font_box_bold = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.text((600, 30), "SƠ ĐỒ TƯƠNG TÁC THỰC THỂ CSDL (ENTITY INTERACTION DIAGRAM)", fill=primary_color, font=font_title, anchor="mm")
    
    # Entities Layout
    # Center: Contract -> Version -> Clause -> ExtractedEntity / RiskFinding
    # Left: Company -> User -> Review
    # Right: SignatureCertificate -> HashProof -> BlockchainTransaction & DigitalSignature
    
    entities = [
        ("Company", "contracts.Company\nDoanh nghiệp sử dụng", (100, 150), light_slate),
        ("User", "contracts.User\nTài khoản người dùng", (100, 350), light_slate),
        ("Contract", "contracts.Contract\nVăn bản hợp đồng", (450, 150), light_indigo),
        ("ContractVersion", "contracts.ContractVersion\nPhiên bản hợp đồng", (450, 350), light_indigo),
        ("Clause", "ai_extract.Clause\nĐiều khoản bóc tách", (450, 520), light_indigo),
        ("ExtractedEntity", "ai_extract.ExtractedEntity\nThực thể pháp lý trích xuất", (150, 520), light_indigo),
        ("RiskFinding", "contracts.RiskFinding\nLỗi rủi ro phát hiện", (750, 520), light_indigo),
        ("HashProof", "blockchain.HashProof\nBằng chứng băm", (850, 150), light_slate),
        ("BlockchainTransaction", "blockchain.BlockchainTransaction\nGiao dịch Fabric ledger", (850, 350), light_slate),
    ]
    
    box_w, box_h = 240, 80
    
    for name, desc, pos, bg in entities:
        x, y = pos
        draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=8, fill=bg, outline=primary_color, width=1)
        draw.text((x + box_w/2, y + 25), name, fill=primary_color, font=font_box_bold, anchor="mm")
        draw.text((x + box_w/2, y + 55), desc, fill=accent_color, font=font_sub, anchor="mm")
        
    def draw_arrow(start, end, label=""):
        draw.line([start, end], fill=arrow_color, width=2)
        sx, sy = start
        ex, ey = end
        # Draw tip
        if sx < ex:
            draw.polygon([(ex, ey), (ex - 6, ey - 4), (ex - 6, ey + 4)], fill=arrow_color)
        elif sx > ex:
            draw.polygon([(ex, ey), (ex + 6, ey - 4), (ex + 6, ey + 4)], fill=arrow_color)
        elif sy < ey:
            draw.polygon([(ex, ey), (ex - 4, ey - 6), (ex + 4, ey - 6)], fill=arrow_color)
        elif sy > ey:
            draw.polygon([(ex, ey), (ex - 4, ey + 6), (ex + 4, ey + 6)], fill=arrow_color)
            
        if label:
            mx, my = (sx + ex)/2, (sy + ey)/2
            draw.text((mx, my - 10), label, fill=accent_color, font=font_sub, anchor="mm")

    # Connect Entities
    draw_arrow((100 + box_w, 150 + box_h/2), (450, 150 + box_h/2), "1-n") # Company -> Contract
    draw_arrow((100 + box_w/2, 150 + box_h), (100 + box_w/2, 350), "1-n") # Company -> User
    draw_arrow((450 + box_w/2, 150 + box_h), (450 + box_w/2, 350), "1-n") # Contract -> Version
    draw_arrow((450 + box_w/2, 350 + box_h), (450 + box_w/2, 520), "1-n") # Version -> Clause
    draw_arrow((450, 520 + box_h/2), (150 + box_w, 520 + box_h/2), "1-n") # Clause -> ExtractedEntity
    draw_arrow((450 + box_w, 520 + box_h/2), (750, 520 + box_h/2), "1-n") # Clause -> RiskFinding
    
    # Cross connections
    draw_arrow((450 + box_w, 350 + box_h/2), (850, 150 + box_h/2), "1-1") # Version -> HashProof
    draw_arrow((850 + box_w/2, 150 + box_h), (850 + box_w/2, 350), "1-n") # HashProof -> Transaction
    
    img.save(r"d:\Django_project\RiskDL\scratch\flow_entity.png")
    print("Generated flow_entity.png successfully.")

if __name__ == "__main__":
    draw_e2e_flow()
    draw_entity_flow()
