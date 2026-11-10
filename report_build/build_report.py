from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Flowable, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle, KeepTogether, NextPageTemplate,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "Bao_cao_do_an_tot_nghiep_Contract_Guard_AI.pdf"
FONT_DIR = Path(r"C:\Windows\Fonts")
for name, file in (("Times", "times.ttf"), ("Times-Bold", "timesbd.ttf"),
                   ("Times-Italic", "timesi.ttf"), ("Times-BoldItalic", "timesbi.ttf")):
    pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
pdfmetrics.registerFontFamily("Times", normal="Times", bold="Times-Bold",
                              italic="Times-Italic", boldItalic="Times-BoldItalic")

INK = colors.HexColor("#111111")
NAVY = colors.HexColor("#17365D")
PALE = colors.HexColor("#EAF0F6")
GRID = colors.HexColor("#AAB4C0")
PAGE_W, PAGE_H = A4
LEFT = RIGHT = 25 * mm
TOP = 23 * mm
BOTTOM = 22 * mm
WIDTH = PAGE_W - LEFT - RIGHT


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodyVN", fontName="Times", fontSize=12.5, leading=19,
    alignment=TA_JUSTIFY, firstLineIndent=10 * mm, spaceAfter=5, textColor=INK,
    allowWidows=0, allowOrphans=0))
styles.add(ParagraphStyle(name="BodyFlush", parent=styles["BodyVN"], firstLineIndent=0))
styles.add(ParagraphStyle(name="TitleVN", fontName="Times-Bold", fontSize=17, leading=23,
    alignment=TA_CENTER, textColor=INK, spaceAfter=9))
styles.add(ParagraphStyle(name="ChapterVN", fontName="Times-Bold", fontSize=15, leading=21,
    alignment=TA_CENTER, textColor=INK, spaceBefore=8, spaceAfter=15, keepWithNext=True))
styles.add(ParagraphStyle(name="H1VN", fontName="Times-Bold", fontSize=13.5, leading=18,
    alignment=TA_LEFT, textColor=INK, spaceBefore=13, spaceAfter=6, keepWithNext=True))
styles.add(ParagraphStyle(name="H2VN", fontName="Times-Bold", fontSize=12.5, leading=17,
    alignment=TA_LEFT, textColor=INK, spaceBefore=9, spaceAfter=4, keepWithNext=True))
styles.add(ParagraphStyle(name="CaptionVN", fontName="Times-Italic", fontSize=10.5, leading=14,
    alignment=TA_CENTER, textColor=INK, spaceBefore=5, spaceAfter=8, keepWithNext=True))
styles.add(ParagraphStyle(name="TableVN", fontName="Times", fontSize=9.4, leading=12,
    alignment=TA_LEFT, textColor=INK))
styles.add(ParagraphStyle(name="TableHeadVN", parent=styles["TableVN"], fontName="Times-Bold",
    alignment=TA_CENTER, textColor=INK))
styles.add(ParagraphStyle(name="SmallVN", fontName="Times", fontSize=9.5, leading=13,
    alignment=TA_JUSTIFY, textColor=INK, spaceAfter=4))
styles.add(ParagraphStyle(name="TOC0VN", fontName="Times-Bold", fontSize=11, leading=16,
    leftIndent=0, firstLineIndent=0, spaceBefore=4))
styles.add(ParagraphStyle(name="TOC1VN", fontName="Times", fontSize=10.5, leading=14,
    leftIndent=9 * mm, firstLineIndent=0))
styles.add(ParagraphStyle(name="CoverSmall", fontName="Times-Bold", fontSize=13, leading=18,
    alignment=TA_CENTER, textColor=INK))


def P(text, style="BodyVN"):
    return Paragraph(text, styles[style])


def safe(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class Diagram(Flowable):
    """Compact vector diagrams generated from the application's implemented layers."""
    def __init__(self, kind, title=""):
        super().__init__()
        self.kind, self.title = kind, title
        self.width = WIDTH
        self.height = 275 if kind in {"architecture", "usecases", "class", "erd"} else 250

    def box(self, c, x, y, w, h, title, body="", fill=colors.white, fs=8.2):
        c.setFillColor(fill); c.setStrokeColor(NAVY); c.setLineWidth(0.8)
        c.roundRect(x, y, w, h, 4, fill=1, stroke=1)
        c.setFillColor(INK)
        p = Paragraph(f"<b>{title}</b>" + (f"<br/>{body}" if body else ""),
                      ParagraphStyle("d", fontName="Times", fontSize=fs, leading=fs+2,
                                     alignment=TA_CENTER, textColor=INK))
        pw, ph = p.wrap(w-8, h-5); p.drawOn(c, x+4, y+(h-ph)/2)

    def arrow(self, c, x1, y1, x2, y2, label=""):
        if x1 == x2:
            x2 = x1 + 22
        c.setStrokeColor(NAVY); c.setFillColor(NAVY); c.setLineWidth(0.8)
        c.line(x1, y1, x2, y2)
        import math
        a = math.atan2(y2-y1, x2-x1); d = 5
        c.line(x2, y2, x2-d*math.cos(a-.45), y2-d*math.sin(a-.45))
        c.line(x2, y2, x2-d*math.cos(a+.45), y2-d*math.sin(a+.45))
        if label:
            label_width = min(110, max(48, abs(x2-x1)-6))
            label_style = ParagraphStyle("arrow-label", fontName="Times", fontSize=7,
                                         leading=8.2, alignment=TA_CENTER, textColor=INK)
            p = Paragraph(safe(label), label_style)
            pw, ph = p.wrap(label_width, 20)
            lx, ly = (x1+x2-pw)/2, (y1+y2)/2+3
            c.setFillColor(colors.white); c.rect(lx-1, ly-1, pw+2, ph+2, fill=1, stroke=0)
            p.drawOn(c, lx, ly)

    def draw(self):
        c = self.canv; w = self.width
        c.saveState()
        c.setStrokeColor(GRID); c.setLineWidth(.5); c.roundRect(1, 1, w-2, self.height-2, 5, stroke=1, fill=0)
        if self.kind == "architecture":
            self.box(c, 12, 185, 92, 56, "Người dùng", "Chuyên viên · reviewer · quản trị", PALE)
            self.box(c, 124, 185, 102, 56, "Trình duyệt", "HTML · CSS · JavaScript", PALE)
            self.box(c, 250, 170, 190, 83, "Django Web", "contracts · ai_extract · NewIdea<br/>legal_kb · phân quyền · giao diện")
            self.arrow(c, 104, 213, 124, 213); self.arrow(c, 226, 213, 250, 213, "HTTP/API")
            self.box(c, 18, 72, 128, 62, "AI Extract", "Surya · GLiNER · cấu trúc<br/>BGE · ColPali · Qwen", PALE)
            self.box(c, 164, 72, 128, 62, "AI Summary", "Đọc · tóm tắt · so sánh phiên bản", PALE)
            self.box(c, 310, 83, 128, 50, "Workflow", "Bước · duyệt · phụ thuộc")
            self.box(c, 18, 15, 128, 42, "PostgreSQL", "Hợp đồng · người dùng · trích xuất", PALE)
            self.box(c, 164, 15, 128, 42, "Qdrant / Neo4j", "Vector · cấu trúc liên kết", PALE)
            self.box(c, 310, 15, 128, 42, "Fabric Gateway", "Peer · orderer · chaincode", PALE)
            self.arrow(c, 292, 190, 164, 134); self.arrow(c, 292, 184, 292, 134)
            self.arrow(c, 345, 170, 374, 133); self.arrow(c, 68, 72, 68, 57)
            self.arrow(c, 208, 72, 228, 57); self.arrow(c, 374, 83, 374, 57)
            c.setFont("Times-Italic", 8); c.setFillColor(INK)
            c.drawString(14, 260, "Sơ đồ thành phần theo cấu hình và mô-đun đang có trong repo; không khẳng định mọi dịch vụ đang chạy.")
        elif self.kind == "usecases":
            self.box(c, 120, 222, 250, 35, "Contract Guard AI", "Quản lý vòng đời hợp đồng", PALE)
            actors = [(48, 177, "Chuyên viên"), (48, 117, "Reviewer"), (48, 57, "Quản trị")]
            for x,y,t in actors: self.box(c,x,y,95,31,t,fill=PALE,fs=8)
            cases = [(190,177,"Tải hợp đồng / phiên bản"),(315,177,"Trích xuất & xem cấu trúc"),
                     (190,117,"Phân tích rủi ro"),(315,117,"Tra cứu có nguồn"),
                     (190,57,"Tạo workflow / duyệt"),(315,57,"Ký · neo hash · kiểm chứng")]
            for x,y,t in cases: self.box(c,x,y,120,35,t,fill=colors.white,fs=7.7)
            for x,y,_ in actors: self.arrow(c,x+95,y+15,190,y+17)
            self.arrow(c,143,192,315,194); self.arrow(c,143,132,190,134)
            self.arrow(c,143,72,190,74); self.arrow(c,143,72,315,74)
            c.setFont("Times",8); c.setFillColor(INK); c.drawString(14, 20, "Các ca sử dụng thể hiện quyền theo vai trò; API vẫn kiểm tra tài khoản, công ty và quyền trước khi đọc dữ liệu.")
        elif self.kind.startswith("sequence"):
            if self.kind == "sequence_search":
                actors = ["Người dùng", "Django Web", "Search service", "Qdrant / Neo4j", "Qwen"]
                events = [(0,1,"Gửi câu hỏi"),(1,2,"Xác thực và lọc phiên bản"),
                          (2,3,"Tìm keyword/vector/ảnh"),(3,2,"Trả ứng viên"),
                          (2,4,"Gửi nguồn đã chọn"),(4,2,"Đáp án + source IDs"),
                          (2,0,"Hiển thị câu trả lời và nguồn")]
            elif self.kind == "sequence_risk":
                actors = ["Reviewer", "Django Web", "Risk service", "Legal KB", "Qwen"]
                events = [(0,1,"Yêu cầu phân tích"),(1,2,"Kiểm tra quyền, lấy điều khoản"),
                          (2,3,"Truy vấn quy định liên quan"),(3,2,"Trả nguồn luật"),
                          (2,4,"Gửi ngữ cảnh và câu hỏi"),(4,2,"Nhận findings có căn cứ"),
                          (2,1,"Lưu và trả kết quả review")]
            elif self.kind == "sequence_ledger":
                actors = ["Signer", "Ledger service", "Workflow", "Fabric Gateway", "Ledger book"]
                events = [(0,1,"Ký manifest ở client"),(1,1,"Xác minh chữ ký, tạo outbox"),
                          (1,2,"Kiểm tra step / quyền"),(1,3,"Gửi operation có idempotency"),
                          (3,4,"Ghi transaction đã commit"),(4,3,"Đọc receipt / block"),
                          (3,1,"Trả xác nhận; đồng bộ workflow")]
            else:
                actors = ["Người dùng", "Django Web", "AI Extract", "Kho dữ liệu", "Qdrant / Neo4j"]
                events = [(0,1,"Gửi tệp / yêu cầu"),(1,3,"Lưu phiên bản"),(1,2,"Tạo việc trích xuất"),
                          (2,2,"Đọc trang, nhận dạng, dựng cấu trúc"),(2,3,"Lưu run / trang / block"),
                          (2,4,"Lập chỉ mục / liên kết graph"),(1,0,"Trả trạng thái và nguồn")]
            xs = [48, 135, 225, 315, 405]
            top = self.height - 28
            for x,t in zip(xs,actors):
                self.box(c,x-34,top-23,68,22,t,fill=PALE,fs=7)
                c.setStrokeColor(GRID); c.setDash(2,2); c.line(x,top-25,x,28); c.setDash()
            yy = top-52
            for a,b,label in events:
                self.arrow(c,xs[a],yy,xs[b],yy,label); yy -= 26
            c.setFont("Times-Italic",8); c.drawString(14, 10, "Thông điệp là luồng logic theo service/repository; thời gian xử lý phụ thuộc cấu hình AI và tài liệu.")
        elif self.kind == "class":
            self.box(c,145,220,150,38,"Contract", "company · code · title · status", PALE)
            self.box(c,145,160,150,40,"ContractVersion", "contract · number · files")
            self.box(c,18,55,115,52,"Clause", "version · title · content", PALE)
            self.box(c,165,75,125,52,"AIAnalysis", "version · result · status")
            self.box(c,315,55,125,52,"RiskFinding", "analysis · rule · severity", PALE)
            self.box(c,325,160,115,40,"Review", "analysis · reviewer", PALE, fs=7)
            self.arrow(c,220,220,220,200,"1 : N")
            self.arrow(c,155,160,110,107,"1 : N")
            self.arrow(c,230,160,230,127,"1 : N")
            self.arrow(c,290,95,315,83,"1 : N")
            self.arrow(c,295,95,355,160,"1 : N")
            c.setFont("Times",8); c.drawString(15, 18, "Mô hình khái niệm rút gọn; bảng trích xuất và workflow nằm ở các Django app/dịch vụ tương ứng.")
        elif self.kind == "erd":
            self.box(c,20,165,125,70,"Hợp đồng", "Company · Role · User<br/>Contract · Version · File", PALE)
            self.box(c,165,165,125,70,"Phân tích", "Clause · Entity · Run<br/>AIAnalysis · Finding · Review")
            self.box(c,310,165,125,70,"Tri thức", "SearchLog · Inquiry<br/>KnowledgeCase · Evidence", PALE)
            self.box(c,20,55,125,70,"Workflow DB", "Workflow · Step · Approval<br/>Dependency · Key · Signature")
            self.box(c,165,55,125,70,"Ledger book DB", "Transaction · HashProof<br/>Certificate · Audit · Verify", PALE)
            self.box(c,310,55,125,70,"Fabric ledger", "Operation ID · manifest hash<br/>block / transaction receipt")
            self.arrow(c,145,195,165,195); self.arrow(c,290,195,310,195)
            self.arrow(c,82,165,82,125); self.arrow(c,210,165,210,125); self.arrow(c,370,165,370,125)
            self.arrow(c,145,90,165,90); self.arrow(c,290,90,310,90)
            c.setFont("Times",8); c.drawString(15, 20, "Sơ đồ tách các miền dữ liệu; các dịch vụ đồng bộ qua API/outbox thay vì gộp mọi bảng vào một CSDL.")
        c.restoreState()


class ThesisDoc(BaseDocTemplate):
    def __init__(self, filename, **kwargs):
        super().__init__(filename, pagesize=A4, leftMargin=LEFT, rightMargin=RIGHT,
                         topMargin=TOP, bottomMargin=BOTTOM, title="Đồ án tốt nghiệp - Contract Guard AI",
                         author="", **kwargs)
        cover = Frame(LEFT, BOTTOM, WIDTH, PAGE_H-TOP-BOTTOM, id="cover", leftPadding=0,
                      rightPadding=0, topPadding=0, bottomPadding=0)
        main = Frame(LEFT, BOTTOM, WIDTH, PAGE_H-TOP-BOTTOM, id="main", leftPadding=0,
                     rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="cover", frames=cover, onPage=self._cover_page),
            PageTemplate(id="front", frames=main, onPage=self._front_page),
            PageTemplate(id="body", frames=main, onPage=self._body_page),
        ])
        self.toc = None

    def _cover_page(self, canvas, doc):
        canvas.saveState(); canvas.restoreState()

    def _front_page(self, canvas, doc):
        canvas.saveState(); canvas.setFont("Times", 9); canvas.setFillColor(INK)
        canvas.drawRightString(PAGE_W-RIGHT, 12*mm, roman(max(1, doc.page-1)))
        canvas.restoreState()

    def _body_page(self, canvas, doc):
        canvas.saveState(); canvas.setFont("Times", 8.5); canvas.setFillColor(INK)
        canvas.drawString(LEFT, PAGE_H-14*mm, "CONTRACT GUARD AI | ĐỒ ÁN TỐT NGHIỆP")
        canvas.drawRightString(PAGE_W-RIGHT, 12*mm, str(max(1, doc.page-8)))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        style = flowable.style.name
        text = flowable.getPlainText()
        if style in ("ChapterVN", "H1VN", "H2VN"):
            level = 0 if style == "ChapterVN" else (1 if style == "H1VN" else 2)
            key = f"h{self.page}_{len(text)}_{abs(hash(text))%1000000}"
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (min(level,1), safe(text), max(1,self.page-8), key))
        elif style in ("CaptionVN",):
            if text.startswith("Hình"):
                self.notify("FigureEntry", (0, safe(text), max(1,self.page-8), None))
            elif text.startswith("Bảng"):
                self.notify("TableEntry", (0, safe(text), max(1,self.page-8), None))


def roman(n):
    vals = ((1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),
            (50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I"))
    out = ""
    for value, label in vals:
        while n >= value: out += label; n -= value
    return out.lower()


def h1(text): return P(text, "H1VN")
def h2(text): return P(text, "H2VN")


def chapter(title):
    return [PageBreak(), P(title, "ChapterVN")]


def fig(story, n, caption, kind):
    story.extend([KeepTogether([Diagram(kind), P(f"Hình {n}. {caption}", "CaptionVN")]), Spacer(1, 4)])


def grid_table(story, n, caption, rows, widths=None):
    data = []
    for ri, row in enumerate(rows):
        sty = "TableHeadVN" if ri == 0 else "TableVN"
        data.append([P(safe(cell).replace("\n", "<br/>"), sty) for cell in row])
    t = Table(data, colWidths=widths or [WIDTH*.27, WIDTH*.73], repeatRows=1,
              hAlign="LEFT", splitByRow=0)
    t.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), .45, GRID), ("BACKGROUND", (0,0), (-1,0), PALE),
        ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6), ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.extend([KeepTogether([t, P(f"Bảng {n}. {caption}", "CaptionVN")]), Spacer(1, 4)])


def usecase(story, n, name, actor, pre, post, main, alternate):
    rows = [("Thuộc tính", "Mô tả"), ("Tên use case", name), ("Tác nhân chính", actor),
            ("Tiền điều kiện", pre), ("Hậu điều kiện", post),
            ("Kịch bản chuẩn", "\n".join(f"{i+1}. {x}" for i,x in enumerate(main))),
            ("Ngoại lệ", "\n".join(f"- {x}" for x in alternate))]
    grid_table(story, n, f"Đặc tả use case {name}", rows, [WIDTH*.25, WIDTH*.75])


def make_story():
    story = []
    # Bìa
    story += [Spacer(1, 9*mm), P("HỌC VIỆN CÔNG NGHỆ BƯU CHÍNH VIỄN THÔNG", "CoverSmall"),
              P("KHOA CÔNG NGHỆ THÔNG TIN I", "CoverSmall"), Spacer(1, 13*mm),
              P("PTIT", "TitleVN"), Spacer(1, 34*mm),
              P("ĐỒ ÁN TỐT NGHIỆP ĐẠI HỌC", "TitleVN"), Spacer(1, 8*mm),
              P("HỆ THỐNG QUẢN LÝ, PHÂN TÍCH VÀ TRA CỨU HỢP ĐỒNG<br/>CONTRACT GUARD AI", "TitleVN"),
              Spacer(1, 19*mm)]
    cover_rows = [["Sinh viên thực hiện", "........................................................"],
                  ["Mã sinh viên", "........................................................"],
                  ["Lớp", "........................................................"],
                  ["Giảng viên hướng dẫn", "........................................................"],
                  ["Hệ đào tạo", "........................................................"]]
    ct = Table([[P(a,"TableHeadVN"),P(b,"TableVN")] for a,b in cover_rows], colWidths=[55*mm,105*mm], hAlign="CENTER")
    ct.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story += [ct, Spacer(1, 16*mm), P("HÀ NỘI - 2026", "CoverSmall"), NextPageTemplate("front"), PageBreak()]

    story += [P("LỜI CẢM ƠN", "TitleVN"),
        P("Em xin chân thành cảm ơn các thầy cô Khoa Công nghệ thông tin I đã trang bị kiến thức nền tảng và phương pháp học tập trong quá trình đào tạo. Em cũng xin cảm ơn giảng viên hướng dẫn, gia đình và bạn bè đã góp ý, động viên trong quá trình khảo sát, thiết kế và hoàn thiện đồ án. Do giới hạn về thời gian và phạm vi triển khai, báo cáo khó tránh khỏi thiếu sót; em mong nhận được góp ý để tiếp tục hoàn thiện hệ thống.") ,
        Spacer(1, 8*mm), P("Hà Nội, tháng 11 năm 2026", "BodyFlush"),
        P("Sinh viên thực hiện", "BodyFlush"), Spacer(1, 15*mm), P("........................................", "BodyFlush"), PageBreak(),
        P("TÓM TẮT", "TitleVN"),
        P("Contract Guard AI là hệ thống hỗ trợ quản lý vòng đời hợp đồng doanh nghiệp. Hệ thống tổ chức dữ liệu hợp đồng theo công ty và phiên bản, tiếp nhận tài liệu, trích xuất cấu trúc điều khoản, hỗ trợ phân tích rủi ro và tra cứu tri thức có dẫn nguồn. Các kết quả được đưa vào quy trình review/workflow; thao tác ký, neo mã băm và kiểm chứng được tách thành luồng ledger kết nối Hyperledger Fabric.") ,
        P("Thiết kế chia hệ thống thành các miền Django cho hợp đồng, trích xuất, tìm kiếm và tri thức; dịch vụ workflow và sổ ghi nghiệp vụ blockchain có tiến trình riêng. Lớp dịch vụ kiểm tra quyền và điều phối nghiệp vụ, repository phụ trách truy vấn và lưu trữ. Các dịch vụ AI được gọi qua gateway/cấu hình triển khai, vì vậy khả năng hoạt động phụ thuộc cấu hình model, dữ liệu và dịch vụ ngoài.") ,
        P("Báo cáo mô tả yêu cầu, ca sử dụng, mô hình dữ liệu, kiến trúc, các luồng xử lý chính và cách kiểm thử. Nội dung được đối chiếu với code và tài liệu trong repo tại thời điểm lập báo cáo. Báo cáo không thay thế kết quả chạy nghiệm thu; các chỉ số định lượng chỉ được nêu khi có bản ghi nguồn xác thực.") ,
        P("Từ khóa: quản lý hợp đồng; trích xuất tài liệu; phân tích rủi ro; RAG; workflow; Hyperledger Fabric.", "BodyFlush"), PageBreak(),
        P("DANH MỤC TỪ VIẾT TẮT", "TitleVN")]
    grid_table(story, 1, "Danh mục từ viết tắt", [
        ("Từ viết tắt", "Giải thích"), ("AI", "Trí tuệ nhân tạo (Artificial Intelligence)"),
        ("API", "Giao diện lập trình ứng dụng (Application Programming Interface)"),
        ("A3", "Luồng đọc, trích xuất và chuẩn bị chỉ mục tài liệu trong dự án"),
        ("A2", "Luồng tìm kiếm, truy xuất và trả lời từ nguồn đã lập chỉ mục"),
        ("BM25", "Thuật toán xếp hạng tìm kiếm văn bản theo từ khóa"),
        ("DB", "Cơ sở dữ liệu (Database)"), ("ERD", "Sơ đồ thực thể - liên kết"),
        ("OCR", "Nhận dạng ký tự quang học"), ("RAG", "Sinh câu trả lời có truy xuất tài liệu"),
        ("RBAC", "Kiểm soát truy cập dựa trên vai trò"), ("RRF", "Hợp nhất thứ hạng nghịch đảo"),
        ("UI", "Giao diện người dùng"), ("UML", "Ngôn ngữ mô hình hóa thống nhất"),
    ])
    story += [PageBreak(), P("MỤC LỤC", "TitleVN")]
    toc = TableOfContents(); toc.levelStyles = [styles["TOC0VN"], styles["TOC1VN"]]; toc.dotsMinLevel = 0
    story.extend([toc, PageBreak(), P("DANH MỤC HÌNH ẢNH", "TitleVN")])
    fl = TableOfContents(notifyKind="FigureEntry"); fl.levelStyles = [styles["TOC1VN"]]; fl.dotsMinLevel = 0
    story.extend([fl, PageBreak(), P("DANH MỤC BẢNG BIỂU", "TitleVN")])
    tl = TableOfContents(notifyKind="TableEntry"); tl.levelStyles = [styles["TOC1VN"]]; tl.dotsMinLevel = 0
    story.extend([tl, NextPageTemplate("body"), PageBreak(), P("MỞ ĐẦU", "ChapterVN")])
    # link to the three indexes for afterFlowable
    global DOC_TOC
    DOC_TOC = (toc, fl, tl)

    story += [h1("1. Lý do chọn đề tài"),
        P("Hợp đồng chứa nội dung quan trọng về quyền, nghĩa vụ, mốc thời gian, giá trị và điều kiện thực hiện. Trong thực tế, thông tin được phân bố giữa nhiều phiên bản, điều khoản, tệp đính kèm và tài liệu tham chiếu. Việc tìm thủ công làm tăng thời gian rà soát và khó duy trì dấu vết từ nhận định đến nguồn gốc.") ,
        P("Đề tài xây dựng một nền tảng hỗ trợ tổ chức tài liệu, trích xuất cấu trúc, tìm kiếm có nguồn và quản lý luồng phê duyệt. Hệ thống kết hợp mô hình ngôn ngữ với kiểm tra quyền, lưu vết và xác minh nguồn ở tầng ứng dụng; phần ledger dùng để ghi nhận thao tác được xác nhận trên mạng Fabric, không thay thế việc thẩm định pháp lý của con người.") ,
        h1("2. Mục tiêu"), P("Mục tiêu là thiết kế và hoàn thiện một hệ thống web cho phép người dùng quản lý hợp đồng theo công ty và phiên bản; trích xuất thông tin phục vụ tìm kiếm; hiển thị kết quả phân tích cùng căn cứ; hỗ trợ reviewer và workflow; ghi nhận chữ ký, mã băm, giao dịch và lịch sử kiểm chứng. Mục tiêu kỹ thuật gồm phân lớp code, giới hạn truy cập theo tenant, lưu dữ liệu nguồn có thể truy vết và cho phép kiểm thử các nhánh nghiệp vụ bằng gateway cô lập.") ,
        h1("3. Phạm vi và phương pháp"), P("Báo cáo khảo sát code và cấu hình hiện có trong workspace: Django web, AI extraction, tra cứu tri thức NewIdea, dịch vụ tóm tắt, workflow, blockchain-service và Fabric. Phần thiết kế mô tả luồng đã triển khai trong mã; không coi mọi dịch vụ là đang hoạt động ở môi trường production. Phương pháp gồm đọc mô hình dữ liệu, route, service, repository, cấu hình Docker Compose, tài liệu vận hành và bộ kiểm thử. Không thực hiện phép đo trực tiếp trong lượt lập báo cáo này.") ,
        h1("4. Bố cục báo cáo"), P("Chương 1 giới thiệu hệ thống, yêu cầu và công nghệ. Chương 2 phân tích actor, use case, luồng nghiệp vụ, lớp và dữ liệu. Chương 3 trình bày cài đặt, kiến trúc triển khai, các module, giao diện theo template và chiến lược kiểm thử. Chương 4 nêu kết luận, giới hạn và hướng phát triển.")]

    # Chapter 1
    story += chapter("CHƯƠNG 1. GIỚI THIỆU HỆ THỐNG")
    story += [h1("1.1. Tổng quan"),
        P("Contract Guard AI là ứng dụng web hướng tới quy trình xử lý hợp đồng từ khi tạo hồ sơ đến khi phân tích, review, phê duyệt và lưu bằng chứng giao dịch. Mô hình dữ liệu đặt Contract làm hồ sơ cấp cao, ContractVersion quản lý phiên bản, ContractFile lưu tệp theo phiên bản. Các nội dung trích xuất gắn với phiên bản để kết quả tìm kiếm và chữ ký không bị tách khỏi bản tài liệu đã dùng.") ,
        P("Các module chính gồm contracts (tài khoản, hợp đồng, phân tích, review, ledger), ai_extract (trích xuất bố cục, điều khoản, thực thể và ảnh), NewIdea (tìm kiếm, hỏi đáp, tri thức chuyên gia), ai_summary (đọc, tóm tắt và so sánh văn bản), legal_kb (kho tri thức pháp luật), workflow_service và blockchain_service. Các module không nhất thiết cùng tiến trình; Django web gọi service hoặc API thích hợp theo cấu hình triển khai [1, 2].") ,
        h1("1.2. Bài toán nghiệp vụ"),
        P("Bài toán thứ nhất là quản lý thông tin có phiên bản và phạm vi công ty. Người dùng cần mở đúng bản tài liệu, tệp, điều khoản, bên tham gia và nhãn. Bài toán thứ hai là chuyển tài liệu không cấu trúc thành các đối tượng truy vấn được mà vẫn giữ trang, vị trí và quan hệ cấu trúc. Bài toán thứ ba là đưa ra nhận định có căn cứ: người đọc phải phân biệt nội dung nguồn, kết quả model và quyết định phê duyệt. Bài toán cuối là lưu vết các bước review, ký và xác minh theo bản hợp đồng cụ thể.") ,
        h1("1.3. Yêu cầu chức năng"),
        P("Hệ thống cần hỗ trợ đăng nhập và đăng ký tài khoản; quản lý công ty, vai trò và quyền; tạo hợp đồng, tải tệp và tạo phiên bản; khởi chạy hoặc xem trạng thái trích xuất; đọc điều khoản, thực thể, bảng và vị trí trang; gắn bên và nhãn; phân tích rủi ro và xem gợi ý soạn thảo riêng; tìm kiếm hoặc hỏi đáp với nguồn; lưu câu hỏi cần chuyên gia xử lý; tạo workflow và duyệt bước; quản lý khóa công khai; ký số, neo hash, kiểm chứng file và xem lịch sử.") ,
        h1("1.4. Yêu cầu phi chức năng"),
        P("Bảo mật: endpoint kiểm tra xác thực, công ty và quyền trước khi truy cập dữ liệu; không đưa bí mật môi trường vào báo cáo hoặc phản hồi. Toàn vẹn: tách phiên bản, manifest và dấu băm; thao tác ledger có định danh, trạng thái và khả năng retry. Truy vết: kết quả phân tích giữ căn cứ, trạng thái và bản ghi nguồn. Khả năng bảo trì: phân lớp URL, view, service, repository và model. Khả năng chịu lỗi: các tích hợp ngoài có timeout, trạng thái chờ/lỗi và cơ chế chạy lại phù hợp. Khả năng mở rộng: các dịch vụ AI, workflow và blockchain có thể triển khai độc lập theo Docker Compose.") ,
        h1("1.5. Tác nhân"),
        P("Chuyên viên hợp đồng tạo hồ sơ, tải tài liệu, theo dõi trích xuất, nhập thông tin bên và đặt câu hỏi. Reviewer xem phân tích, gửi nhận xét và chấp thuận hoặc yêu cầu chỉnh sửa. Người phê duyệt workflow xử lý bước theo vai trò; signer sử dụng khóa riêng của mình để ký đúng manifest. Quản trị viên quản lý tài khoản, công ty, vai trò, quyền, quy tắc và trạng thái dịch vụ. Chuyên gia tri thức có thể tạo câu trả lời cho inquiry và reviewer chuyên gia duyệt case trước khi case được sử dụng làm tri thức.") ,
        h1("1.6. Công nghệ và vai trò"),
        P("Backend chính dùng Django/Python; dịch vụ đọc và tóm tắt AI có thể dùng FastAPI; giao diện sử dụng template Django cùng JavaScript/CSS. PostgreSQL lưu dữ liệu nghiệp vụ; Qdrant hỗ trợ truy xuất vector; Neo4j lưu graph nội dung khi được bật; Fabric cung cấp sổ ghi phân tán cho thao tác đã xác nhận. Surya hỗ trợ nhận dạng bố cục/OCR; GLiNER hỗ trợ trích xuất thực thể và đề xuất quan hệ; BGE-M3 và reranker phục vụ truy xuất văn bản; ColPali phục vụ truy vấn vùng ảnh; Qwen được gọi qua gateway/cấu hình model. Tên model và endpoint có thể thay đổi theo `.env`; báo cáo không cố định một model chưa được xác nhận cho mọi môi trường [1, 3].") ,
        h1("1.7. Kết chương"), P("Hệ thống giải quyết một chuỗi công việc liên tục, không chỉ là trang tải file hay hộp thoại hỏi đáp. Các yêu cầu về phiên bản, quyền, bằng chứng và trạng thái ledger chi phối thiết kế dữ liệu và điều phối ở các chương tiếp theo.")]

    # Chapter 2
    story += chapter("CHƯƠNG 2. PHÂN TÍCH VÀ THIẾT KẾ")
    story += [h1("2.1. Mô tả hệ thống"),
        P("Luồng tổng quát bắt đầu từ việc người dùng tạo hợp đồng và tải một phiên bản tài liệu. Tệp được lưu cùng thông tin phiên bản; A3 tạo extraction run, trang, block và cấu trúc. Kết quả trích xuất được dùng để lập chỉ mục và tìm kiếm. A2 chọn nguồn phù hợp với câu hỏi và quyền người dùng, mở rộng theo liên kết được lưu rồi tạo câu trả lời có mã nguồn. Phân tích rủi ro đi theo nhánh riêng, tham chiếu điều khoản và tài liệu pháp luật phù hợp. Sau review, workflow ghi lại bước xử lý; thao tác ký hoặc neo hash được gửi qua outbox đến Fabric và đối chiếu lại kết quả xác nhận [1, 4, 5].") ,
        h1("2.2. Phân tích use case"), P("Sơ đồ tổng quan gom các ca sử dụng theo bốn nhóm: quản lý hồ sơ, phân tích và tri thức, phê duyệt, và bằng chứng giao dịch. Mỗi ca vẫn chịu kiểm tra quyền ở phía server; giao diện chỉ điều khiển thao tác chứ không quyết định thay dữ liệu phân quyền.")]
    fig(story, 1, "Sơ đồ use case tổng quan theo actor và nghiệp vụ", "usecases")
    story += [h2("2.2.1. Quy tắc phạm vi truy cập"), P("Hồ sơ hợp đồng gắn với company. Service xác định người dùng và quyền từ phiên đăng nhập, không tin company_id hoặc role do phía trình duyệt tự khai. Các route workflow kiểm tra điều kiện bước và vai trò; thao tác ledger kiểm tra công ty, quyền ký/neo, credential và phiên bản. Thông tin quản trị toàn hệ thống không đồng nghĩa người dùng được đọc mọi hợp đồng.")]

    story += [h1("2.3. Đặc tả use case")]
    uc = [
        (2,"Đăng nhập","Người dùng", "Tài khoản tồn tại và chưa bị vô hiệu hóa.", "Phiên đăng nhập được tạo; người dùng đến màn hình phù hợp.", ["Mở trang đăng nhập.","Nhập tên tài khoản và mật khẩu.","Server xác thực thông tin và tạo session/token theo cấu hình."], ["Sai thông tin thì hiển thị lỗi chung.","Tài khoản bị khóa hoặc không hoạt động thì từ chối truy cập."]),
        (3,"Đăng ký nhân sự","Quản trị viên", "Quản trị viên có quyền tạo tài khoản; công ty và vai trò hợp lệ.", "Tài khoản được tạo và yêu cầu đăng ký danh tính ledger được gửi theo cấu hình.", ["Nhập thông tin người dùng, công ty và vai trò.","Server xác thực dữ liệu và quyền quản trị.","Tạo tài khoản rồi gọi dịch vụ ledger book để ghi đăng ký.","Trả trạng thái tài khoản/chứng thư."], ["Thiếu quyền hoặc trùng username/email thì từ chối.","Dịch vụ ledger không sẵn sàng thì ghi nhận trạng thái lỗi để quản trị viên thử lại."]),
        (4,"Tạo hợp đồng và tải phiên bản","Chuyên viên hợp đồng", "Người dùng đã đăng nhập và thuộc công ty được phép.", "Hồ sơ, phiên bản và tệp được liên kết; có thể bắt đầu xử lý.", ["Tạo hồ sơ với mã, tiêu đề, loại và công ty.","Tải một hay nhiều tệp.","Server kiểm tra định dạng, quyền và tính hợp lệ.","Lưu ContractVersion/ContractFile và trả mã hồ sơ."], ["Tệp không hợp lệ hoặc vượt giới hạn thì báo lỗi.","Công ty không khớp quyền người dùng thì không lưu."]),
        (5,"Trích xuất cấu trúc tài liệu","Chuyên viên hợp đồng", "Phiên bản có tệp đọc được; dịch vụ A3 được cấu hình.", "Run, trang, block và dữ liệu cấu trúc được lưu theo phiên bản.", ["Yêu cầu trích xuất hoặc chạy lại.","Service tạo job/run và đọc các trang.","Nhận dạng bố cục, chữ, bảng, thực thể/quan hệ theo cấu hình.","Lưu kết quả và trạng thái; giao diện hiển thị tiến trình."], ["Runtime AI lỗi thì run báo lỗi và có thể chạy lại.","Một trang hỏng không làm mất file gốc; trạng thái trang được giữ để chẩn đoán."]),
        (6,"Kiểm tra nguồn trích xuất","Chuyên viên / Reviewer", "Đã có dữ liệu run và trang.", "Người dùng xem được nội dung cùng trang và vị trí nguồn.", ["Mở trang kiểm tra.","Chọn run, trang hoặc quan hệ.","Đối chiếu văn bản, block, bbox, điều khoản và graph.","Ghi nhận hoặc yêu cầu chạy lại khi cần."], ["Không có quyền hoặc run không tồn tại thì trả lỗi.","Trang không có ảnh nguồn thì hiển thị trạng thái khả dụng thay vì suy đoán vị trí."]),
        (7,"Gắn bên và tag","Chuyên viên hợp đồng", "Có hồ sơ/phiên bản và quyền chỉnh sửa.", "Bên, nhãn và quan hệ hợp đồng được cập nhật.", ["Mở hồ sơ.","Nhập bên tham gia hoặc chọn tag.","Server kiểm tra dữ liệu và quyền.","Lưu quan hệ theo hợp đồng."], ["Bên/tag không hợp lệ thì giữ dữ liệu cũ.","Phiên bản đã có thao tác ledger bị ràng buộc thì không đổi liên kết trái chính sách."]),
        (8,"Phân tích rủi ro","Chuyên viên / Reviewer", "Phiên bản có điều khoản; dịch vụ phân tích và kho luật phù hợp sẵn sàng.", "Phân tích và findings được lưu kèm điều khoản/căn cứ.", ["Yêu cầu phân tích phiên bản.","Hệ thống lấy điều khoản và ngữ cảnh liên quan.","Tìm quy tắc/điều khoản pháp lý hỗ trợ.","Sinh nhận định, kiểm tra dẫn chiếu và lưu kết quả."], ["Thiếu điều khoản hoặc nguồn luật thì nêu giới hạn.","Gợi ý soạn thảo được tách khỏi risk score và không được trình bày như kết luận vi phạm."]),
        (9,"Tra cứu và hỏi đáp có nguồn","Người dùng được cấp quyền", "Đã có chỉ mục nguồn; câu hỏi thuộc phạm vi được xem.", "Kết quả trả lời đi kèm nguồn, trạng thái và dấu vết truy xuất.", ["Nhập câu hỏi và phạm vi.","Server lọc phiên bản theo quyền.","Tìm từ khóa/vector/ảnh và hợp nhất, xếp hạng ứng viên.","Mở rộng cấu trúc có liên quan, tạo câu trả lời và gắn source IDs.","Hiển thị lời giải thích và liên kết nguồn riêng."], ["Không có nguồn hỗ trợ thì nêu thiếu bằng chứng.","Lỗi model hoặc vượt context được ghi vào chẩn đoán; không coi trích dẫn hợp lệ là bảo đảm ngữ nghĩa đúng."]),
        (10,"Tạo và duyệt tri thức chuyên gia","Chuyên gia / Reviewer", "Có inquiry hoặc hồ sơ nguồn; actor được gán quyền.", "Case được lưu ở trạng thái nháp/đã duyệt/ngừng dùng.", ["Chuyên gia ghi vấn đề, suy luận, phương án và khả năng áp dụng.","Liên kết case với phiên bản và snapshot bằng chứng.","Reviewer kiểm tra nguồn, phạm vi và nội dung.","Duyệt, yêu cầu sửa hoặc đánh dấu ngừng sử dụng."], ["Không đủ bằng chứng thì chưa duyệt.","Case đã có revision mới thì giữ lịch sử phiên bản thay vì ghi đè nội dung cũ."]),
        (11,"Tạo workflow và duyệt bước","Quản trị quy trình / Người duyệt", "Phiên bản tồn tại; người tạo có quyền; các vai trò được cấu hình.", "Workflow có các bước, dependency và trạng thái xử lý.", ["Tạo workflow cho phiên bản.","Khai báo bước, vai trò và quan hệ phụ thuộc.","Người duyệt mở bước đến lượt.","Server kiểm tra role/dependency rồi ghi approval và chuyển trạng thái."], ["Bước phụ thuộc chưa xong thì từ chối duyệt.","Bước cần chữ ký không thể force-complete bằng endpoint duyệt thông thường."]),
        (12,"Đăng ký và duyệt khóa ký","Signer / Manager", "Signer thuộc công ty; có quyền ledger.sign; manager khác có quyền duyệt.", "Public key có trạng thái chờ, hoạt động hoặc bị thu hồi.", ["Signer tạo khóa RSA trên trình duyệt.","Gửi public key và fingerprint để đăng ký.","Manager khác kiểm tra và duyệt khóa.","Server lưu credential và đồng bộ sự kiện phù hợp."], ["Khóa riêng không được tải lên server.","Người đăng ký không tự duyệt credential của mình."]),
        (13,"Ký số hoặc neo hash phiên bản","Signer / Người có quyền ledger.anchor", "Phiên bản đúng công ty; quyền và credential hợp lệ; workflow step đúng nếu có.", "Yêu cầu được ghi outbox và chỉ thành CONFIRMED sau khi đối chiếu receipt Fabric.", ["Chọn phiên bản và thao tác ký/neo.","Server dựng manifest gắn file hash, công ty, hợp đồng, phiên bản và người ký.","Signer ký manifest bằng khóa riêng; server xác minh chữ ký.","Worker gửi giao dịch có idempotency đến Fabric.","Đọc lại transaction/block và lưu kết quả xác nhận."], ["Sai chữ ký, khóa bị thu hồi hoặc scope sai thì từ chối.","Mất kết nối thì giữ trạng thái retry; không tạo trạng thái xác nhận giả."]),
        (14,"Kiểm chứng tài liệu","Người có quyền xem phiên bản", "Có hash proof/giao dịch đã ghi hoặc đủ quyền kiểm chứng.", "Kết quả so sánh file tải lên với hash đã ghi được lưu và hiển thị.", ["Chọn phiên bản và tải file cần đối chiếu.","Tính hash file và truy xuất bằng chứng ledger.","So sánh hash, chữ ký, giao dịch, block và trạng thái khóa.","Lưu VerificationHistory và hiển thị kết quả."], ["Không tìm thấy receipt thì báo chưa có bằng chứng.","Hash khác nhau thì kết luận mismatch theo dữ liệu đối chiếu, không tự sửa file."]),
    ]
    for args in uc: usecase(story, *args)

    story += [h1("2.4. Thiết kế luồng xử lý"),
        h2("2.4.1. Tiếp nhận và trích xuất tài liệu"),
        P("View tiếp nhận yêu cầu, service kiểm tra quyền và tạo run; repository ghi nhận phiên bản, trang và block. A3 gọi các adapter trích xuất phù hợp, giữ vị trí trang và metadata. Các bước lập chỉ mục có thể được tách hoặc trì hoãn tùy cấu hình. Kết quả có trạng thái để UI không nhầm dữ liệu chưa hoàn tất với dữ liệu đã sẵn sàng.")]
    fig(story, 2, "Trình tự tiếp nhận và trích xuất một phiên bản", "sequence")
    story += [h2("2.4.2. Tìm kiếm và sinh câu trả lời"),
        P("Luồng tìm kiếm xác định tập phiên bản được phép trước khi chạy các backend. Các truy vấn con được gom, kết quả từ BM25/vector/ảnh được hợp nhất và rerank, sau đó chọn nguồn và mở rộng ngữ cảnh có liên kết. Model chỉ nhận nội dung nguồn đã chọn theo chính sách prompt; kết quả được gắn source IDs và lưu trace. Tầng giao diện trình bày nội dung và liên kết nguồn ở hai trường riêng.")]
    fig(story, 3, "Trình tự tìm kiếm và trả lời có dẫn nguồn", "sequence_search")
    story += [h2("2.4.3. Phân tích và review"),
        P("Phân tích rủi ro được tạo từ điều khoản, quy tắc và nguồn pháp lý truy xuất được. Service giữ căn cứ và kiểm tra dẫn chiếu; view trả kết quả để reviewer xem. Review được lưu riêng khỏi nội dung phân tích. Các đề xuất sửa câu chữ được đánh dấu riêng để không cộng thành mức rủi ro pháp lý.")]
    fig(story, 4, "Trình tự phân tích rủi ro và gửi review", "sequence_risk")
    story += [h2("2.4.4. Ký, neo hash và kiểm chứng"),
        P("Yêu cầu được chuẩn hóa thành manifest gắn đúng phiên bản. Server xác minh chữ ký trước khi đưa thao tác vào outbox. Worker nhận việc có lease, gửi operation có idempotency và truy vấn lại trạng thái thực tế từ Fabric. Sau commit, dịch vụ sổ ghi lưu transaction, proof, audit và đồng bộ workflow; kiểm chứng so hash file với proof đã ghi [5, 6].")]
    fig(story, 5, "Trình tự tạo thao tác ledger và xác nhận commit", "sequence_ledger")

    story += [h1("2.5. Thiết kế lớp và dữ liệu"),
        P("Các lớp nghiệp vụ được chia theo miền. Contract và ContractVersion quản lý hồ sơ và phiên bản; Clause, ExtractedEntity, LayoutExtractionRun, LayoutExtractionPage và LayoutExtractionBlock lưu kết quả đọc; AIAnalysis, RiskFinding và Review quản lý phân tích; workflow_service quản lý bước và phê duyệt; blockchain_service lưu receipt, proof, chứng thư, audit và lịch sử kiểm chứng. Mô hình dưới đây là sơ đồ khái niệm, không thay thế migration hoặc schema đầy đủ.")]
    fig(story, 6, "Mô hình lớp rút gọn của miền hợp đồng và phân tích", "class")
    fig(story, 7, "Phân tách các miền dữ liệu hợp đồng, workflow và ledger", "erd")
    story += [h2("2.5.1. Quy tắc toàn vẹn"),
        P("Các findings gắn với analysis và căn cứ điều khoản; khóa ngoại bảo vệ những bản ghi cần giữ lịch sử. ContractVersion không được thay đổi bất hợp lý sau khi thao tác ledger đã được chấp nhận. Manifest dùng nội dung chuẩn hóa để chữ ký được kiểm tra nhất quán. Giao dịch có operation ID và hash payload nhằm chống gửi trùng. Khi dịch vụ ngoài tạm lỗi, trạng thái chưa xác nhận phải được giữ để retry; không suy diễn thành giao dịch thành công.") ,
        h2("2.5.2. Kiến trúc phân lớp"),
        P("Luồng xử lý theo URLs → views → services → repositories → models/database. View xử lý HTTP và session; service chứa quy tắc nghiệp vụ, kiểm tra quyền, transaction và điều phối tích hợp; repository gom truy vấn và thao tác lưu dữ liệu; model khai báo cấu trúc và ràng buộc. Cách phân lớp giúp kiểm thử nghiệp vụ với database cô lập và thay adapter bên ngoài mà không phải đưa logic HTTP vào service [1].")]
    fig(story, 8, "Kiến trúc triển khai theo cấu hình Docker Compose", "architecture")
    story += [h1("2.6. An toàn, quyền và phạm vi tin cậy"),
        P("Phân quyền theo công ty được áp dụng ở tầng ứng dụng. Token service-to-service được đưa qua biến môi trường và header nội bộ; không lưu khóa riêng của signer trên server. Tính đúng của nội dung AI được giới hạn bởi chất lượng OCR, nguồn truy xuất và việc diễn giải của model; mã nguồn có thể kiểm tra ID nguồn và binding nhưng không thể tự chứng minh mọi suy luận ngữ nghĩa. Fabric bảo đảm dấu vết giao dịch theo network/chaincode cấu hình, không tự làm cho nội dung hợp đồng đúng luật.") ,
        h1("2.7. Kết chương"), P("Phân tích cho thấy hệ thống có nhiều miền dữ liệu và trạng thái nên cần phân tách trách nhiệm. Use case và sơ đồ thiết kế liên kết các yêu cầu với service, model và tích hợp tương ứng. Chương 3 trình bày việc hiện thực và cách xác nhận các hành vi này.")]

    # Chapter 3
    story += chapter("CHƯƠNG 3. CÀI ĐẶT VÀ THỬ NGHIỆM")
    story += [h1("3.1. Môi trường và thành phần triển khai"),
        P("Docker Compose mô tả các thành phần web, AI extraction, AI summary, workflow, blockchain ledger book, worker và các dịch vụ Fabric. Các service kết nối qua mạng Compose và URL nội bộ; cấu hình bí mật nằm trong môi trường triển khai. Mạng lưu trữ sử dụng PostgreSQL và các dịch vụ chỉ mục như Qdrant/Neo4j khi được cấu hình. Việc có service trong Compose là mô tả khả năng triển khai, không phải bằng chứng container đang chạy tại thời điểm lập báo cáo [7].") ,
        P("Web Django là cổng giao tiếp chính và proxy một số luồng workflow. AI Extract thực hiện đọc tài liệu và lập chỉ mục; AI Summary đọc, tóm tắt, so sánh nội dung; NewIdea điều phối hỏi đáp và tri thức chuyên gia; legal_kb nhập và tra cứu nội dung pháp luật. Workflow service lưu bước, dependency, approval và key management. Blockchain service nhận sự kiện đã xác nhận, đồng thời cung cấp ledger book cho đăng ký người dùng, thao tác, credential và kiểm chứng.") ,
        h1("3.2. Cài đặt quản lý hợp đồng"),
        P("Các route của contracts cung cấp dashboard, trang chi tiết, lịch sử phân tích, danh sách hợp đồng, tạo hồ sơ, tải tệp, lấy phiên bản, nhập parties/tags, phân tích, review, workflow, identity và quản trị. Service/repository giữ các điều kiện truy cập và cập nhật. Mô hình phiên bản giúp phân biệt nội dung đang phân tích với file gốc và các lần cập nhật sau.") ,
        h1("3.3. Cài đặt đọc và trích xuất"),
        P("A3 điều phối pipeline trên tài liệu theo trang. Surya nhận diện layout và chữ; parser hỗ trợ định dạng văn phòng; các dịch vụ cấu trúc, heading, table và quan hệ gắn kết block với nguồn. GLiNER hỗ trợ trích xuất thực thể và đề xuất liên kết. BGE-M3, ColPali và Qdrant/Neo4j xuất hiện trong nhánh chỉ mục/truy xuất theo cấu hình. Extraction run, page, block và metadata được lưu riêng để có thể xem lại trạng thái và vị trí.") ,
        h1("3.4. Cài đặt phân tích rủi ro và tra cứu"),
        P("NewIdea/services/clause_risk_service.py chia điều khoản thành các đơn vị rà soát, truy xuất nguồn luật, dựng ngữ cảnh, yêu cầu model sinh kết quả có cấu trúc và kiểm tra quote/nguồn. Gợi ý soạn thảo được biểu diễn riêng với phát hiện rủi ro. Các điều khoản liên quan được thêm vào ngữ cảnh khi cần nhưng không được gộp thành một nguồn duy nhất.") ,
        P("knowledge_search_service.py xác định tập phiên bản hợp lệ, lập kế hoạch câu hỏi, thu ứng viên, hợp nhất/rerank, mở rộng ngữ cảnh và gọi answer service. Kết quả giữ danh sách sources và trace. NewIdea còn có case tri thức chuyên gia, inquiry, trạng thái duyệt và evidence snapshot. Kho pháp luật legal_kb quản lý nguồn nhập riêng; dữ liệu pháp luật cần được cập nhật và đánh giá theo chính sách của đơn vị sử dụng [4, 8].") ,
        h1("3.5. Cài đặt workflow và ledger"),
        P("Workflow service lưu Workflow, WorkflowStep, Approval, StepDependency, KeyManagement và DigitalSignature. Rule/service kiểm tra thứ tự, dependency, vai trò và chính sách ký. Contract ledger service tạo operation có manifest, fingerprint và idempotency; worker gửi giao dịch đến gateway Fabric, đọc lại receipt, ghi trạng thái và thực hiện đồng bộ workflow. Blockchain service đóng vai trò ledger book cho bản ghi giao dịch, proof, audit, credential và verification. Khóa riêng được tạo và giữ bởi signer; server dùng public key để kiểm tra.") ,
        h1("3.6. Giao diện người dùng"),
        P("Giao diện được khai báo trong các Django templates và static assets của contracts, ai_extract và workflow. Các màn hình thể hiện dashboard, danh sách hồ sơ, chi tiết hợp đồng, thông tin parties/tags, kết quả AI, trang kiểm tra trích xuất, màn hình quản trị và board workflow. Vì repo hiện tại không chứa bộ ảnh chụp giao diện chạy thật và các dịch vụ không được khởi động trong lượt lập báo cáo, mục này mô tả các luồng và điểm vào đã xác nhận từ template/URL; không trình bày wireframe giả như ảnh chụp hệ thống.") ,
        h1("3.7. Thiết kế kiểm thử"),
        P("Bộ test trong repo bao phủ service, endpoint và một số tích hợp. Có thể phân loại thành: kiểm thử đơn vị cho quy tắc và mapping; kiểm thử service với mock gateway/model; kiểm thử endpoint cho xác thực, quyền và định dạng; kiểm thử kiến trúc để giữ ranh giới view/service/repository; kiểm thử workflow và ledger cho idempotency, retry, chữ ký và trạng thái. Tài liệu kiến trúc nêu lệnh chạy các nhóm test cô lập bằng cấu hình test riêng [1, 9].") ,
        P("Trong lần hoàn thiện báo cáo này không chạy lại test, không khởi động Docker, không gọi model/gateway và không gửi thao tác Fabric. Vì vậy báo cáo không công bố số test pass, thời gian phản hồi, độ chính xác OCR hay tỷ lệ phát hiện rủi ro mới. Khi nghiệm thu, cần lưu commit, phiên bản dữ liệu, cấu hình model, log, sample size và điều kiện máy để kết quả có thể tái lập.") ,
        h1("3.8. Giới hạn đã ghi nhận"),
        P("Chất lượng trích xuất phụ thuộc bố cục, chất lượng ảnh, ngôn ngữ và mô hình; các vùng bảng hoặc ảnh phức tạp có thể cần kiểm tra thủ công. Tìm kiếm chỉ bao phủ nội dung đã lập chỉ mục và được phép xem. Câu trả lời sinh có thể diễn giải thiếu hoặc sai dù citation/source ID hợp lệ; cần reviewer đối chiếu nguyên văn. Kho luật cần quy trình cập nhật và kiểm soát phiên bản. Ledger Fabric là một phần của kiến trúc thử nghiệm; chữ ký ứng dụng bằng public key đã duyệt không tự tương đương chứng thư CA độc lập, HSM hay chứng nhận pháp lý. Hệ thống vẫn cần sao lưu, giám sát, quản lý khóa và kiểm thử tải trước khi triển khai chính thức.") ,
        h1("3.9. Kết chương"), P("Chương này nối thiết kế với các module trong source tree và phân biệt năng lực được cấu hình với kết quả đã chạy. Việc nghiệm thu cần bổ sung ảnh chụp môi trường thật, kịch bản test có dữ liệu kiểm soát và log triển khai tại nơi sử dụng.")]

    # Chapter 4
    story += chapter("CHƯƠNG 4. KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN")
    story += [h1("4.1. Kết luận"),
        P("Đồ án trình bày Contract Guard AI như một hệ thống hỗ trợ quản lý và rà soát hợp đồng theo phiên bản. Kiến trúc kết hợp quản lý hồ sơ, trích xuất nội dung, tìm kiếm có nguồn, phân tích rủi ro, quản lý tri thức, workflow và ledger. Cấu trúc service/repository cùng các ràng buộc phân quyền là nền tảng để nối các bước mà vẫn giữ nguồn gốc và trạng thái.") ,
        P("Một điểm thiết kế quan trọng là không nhập nhằng kết quả AI với bằng chứng: nguồn tài liệu được giữ riêng, nhận định trỏ về evidence, quyết định của reviewer lưu theo luồng riêng, còn giao dịch ledger chỉ được coi là xác nhận khi đọc được receipt thực tế. Cách phân tách này giúp người dùng kiểm tra và giảm khả năng biến kết quả chưa xác minh thành sự thật hệ thống.") ,
        h1("4.2. Hạn chế"),
        P("Độ chính xác đầu cuối chưa thể suy ra từ kiểm thử logic đơn lẻ. Cần bộ dữ liệu đánh giá đại diện cho nhiều mẫu hợp đồng, ngôn ngữ và bố cục; cần đo riêng OCR, trích xuất điều khoản, retrieval, grounding, rủi ro pháp lý và latency. Mô hình ngôn ngữ còn có thể bỏ sót điều kiện hoặc chuyển thuộc tính giữa chủ thể. Dịch vụ ngoài có thể gián đoạn; dữ liệu chỉ mục có thể lỗi thời; quy trình chữ ký cần quản lý khóa và chính sách tổ chức phù hợp.") ,
        h1("4.3. Hướng phát triển"),
        P("Hướng thứ nhất là hoàn thiện đánh giá định lượng có kiểm soát, dùng test set phân tầng theo loại hợp đồng, có ground truth được chuyên gia rà soát và báo cáo precision/recall cùng độ phủ nguồn. Hướng thứ hai là nâng chất lượng kiểm tra bảng, quan hệ và tham chiếu chéo; đưa phản hồi reviewer thành dữ liệu đánh giá có provenance. Hướng thứ ba là bổ sung dashboard quan sát chất lượng, latency, lỗi provider và tiến độ worker. Hướng thứ tư là củng cố triển khai production: backup/restore, rotation và thu hồi khóa, phân tách tenant trên hạ tầng, quản trị secret, kiểm thử phục hồi và đánh giá bảo mật độc lập. Hướng cuối là quản lý phiên bản tri thức pháp luật và quy trình duyệt nội dung chuyên gia theo thẩm quyền.") ,
        h1("4.4. Kết luận chung"), P("Contract Guard AI cung cấp một nền tảng kỹ thuật để tổ chức quy trình hợp đồng có AI hỗ trợ và có dấu vết kiểm tra. Giá trị của hệ thống phụ thuộc đồng thời vào chất lượng nguồn, kiểm soát quyền, hiệu quả retrieval, review của con người và vận hành an toàn. Vì vậy, AI và blockchain được xem là thành phần hỗ trợ quy trình; quyết định pháp lý và phê duyệt cuối cùng vẫn thuộc về người có thẩm quyền.")]

    story += [PageBreak(), P("TÀI LIỆU THAM KHẢO", "ChapterVN")]
    refs = [
        "[1] Contract_DL, docs/ARCHITECTURE.md và docs/RUNTIME.md, tài liệu kiến trúc và vận hành trong repository.",
        "[2] Contract_DL, contracts/models.py; ai_extract/models.py; NewIdea/core/models.py, các mô hình nghiệp vụ hiện hành.",
        "[3] Contract_DL, ai_extract/services/layout_service.py; layout_extractor.py; surya_inference_service.py; gliner_entity_service.py; contract_pipeline_service.py.",
        "[4] Contract_DL, NewIdea/services/knowledge_search_service.py; knowledge_answer_service.py; search_evidence_service.py; clause_risk_service.py.",
        "[5] Contract_DL, contracts/services/ledger_service.py; contracts/services/ledger_book_service.py; workflow_service/workflow/services.py.",
        "[6] Contract_DL, fabric/chaincode/enterprise.go; signatures.go; blockchain_service/blockchain/book.py và models.py.",
        "[7] Contract_DL, docker-compose.yml và docker-compose.web-local.yml, cấu hình các service và mạng triển khai.",
        "[8] Contract_DL, legal_kb/README.md; legal_kb/services/search_service.py; legal_kb/services/import_service.py.",
        "[9] Contract_DL, docs/testing/TEST_REPORT.md và các thư mục tests của contracts, ai_extract, NewIdea, workflow_service và blockchain_service.",
        "[10] Django Software Foundation, Django documentation, https://docs.djangoproject.com/.",
        "[11] Hyperledger Foundation, Hyperledger Fabric documentation, https://hyperledger-fabric.readthedocs.io/.",
        "[12] Qdrant, Qdrant documentation, https://qdrant.tech/documentation/.",
        "[13] Neo4j, Neo4j documentation, https://neo4j.com/docs/.",
    ]
    story.extend(P(ref, "BodyFlush") for ref in refs)
    story += [PageBreak(), P("PHỤ LỤC A. CẤU TRÚC MÃ NGUỒN", "ChapterVN"),
        P("Cấu trúc chính trong repository hiện tại:", "BodyFlush")]
    tree_rows = [("Thư mục", "Vai trò trong hệ thống"),
        ("contracts/", "Ứng dụng Django chính: hồ sơ, người dùng, phân tích, review, workflow gateway và ledger."),
        ("ai_extract/", "Trích xuất, layout/OCR, điều khoản, entity, indexing, snapshot và summary orchestration."),
        ("NewIdea/", "Tra cứu tri thức, hỏi đáp, evidence, risk review và expert submissions."),
        ("ai_summary/", "Dịch vụ đọc, tóm tắt và so sánh hợp đồng."),
        ("legal_kb/", "Nhập và tìm kiếm kho pháp luật."),
        ("workflow_service/", "Workflow, bước duyệt, dependency, key management và chữ ký."),
        ("blockchain_service/", "Ledger book cho giao dịch, hash proof, chứng thư, audit và verification."),
        ("fabric/", "Gateway, chaincode và cấu hình mạng Hyperledger Fabric."),
        ("shared/", "Thư viện dùng chung như retrieval và gateway AI."),
        ("docs/", "Kiến trúc, vận hành, hướng dẫn đánh giá và kiểm thử."),]
    grid_table(story, 15, "Ánh xạ thư mục và chức năng", tree_rows, [45*mm, WIDTH-45*mm])
    story += [P("PHỤ LỤC B. ĐIỂM VÀO API TIÊU BIỂU", "ChapterVN")]
    api_rows = [("Nhóm", "Một số route trong source"),
        ("Hợp đồng", "api/contracts/; api/analyses/; api/risks/; api/identity/"),
        ("Trích xuất", "api/ai/bulk/; api/ai/contracts/<id>/extraction-status/; api/ai/contracts/<id>/summary/"),
        ("Tri thức", "api/newidea/search/; api/newidea/jobs/; api/newidea/versions/<id>/sources/"),
        ("Workflow", "workflows/; workflows/steps/<id>/approve/; dependencies/"),
        ("Ledger book", "book/users/; book/operations/; book/credentials/; book/verifications/"),
        ("Legal KB", "api/legal/"),]
    grid_table(story, 16, "Route tiêu biểu được khai báo trong URL configuration", api_rows, [38*mm, WIDTH-38*mm])
    story += [P("Các route đầy đủ và quyền truy cập cần được kiểm tra trực tiếp trong URL/view/service của nhánh triển khai. Phụ lục này chỉ chọn route đại diện để định hướng đọc mã, không phải tài liệu API chuẩn hóa.", "SmallVN")]
    return story


DOC_TOC = None


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = ThesisDoc(str(OUT))
    doc.multiBuild(make_story(), maxPasses=8)
    print(f"created={OUT} bytes={OUT.stat().st_size} pages via PDF metadata")


if __name__ == "__main__":
    build()
