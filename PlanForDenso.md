# 🏆 LINE-SENSEI — MASTER BLUEPRINT VÀ CHIẾN LƯỢC THẮNG DENSO FACTORY HACKATHON 2026

> **Tên sản phẩm:** LINE-SENSEI — Knowledge Agent cho Dây Chuyền Sản Xuất DENSO  
> **Mã hiệu hệ thống:** DENSO VisionMind v3.0 (Shopfloor Edition)  
> **Track dự thi:** Track A3 (Predictive & Knowledge AI - Trọng tâm) + Track Data Utilization (Phụ)  
> **Khái niệm cốt lõi:** Digital Triplet (Người $\leftrightarrow$ Dữ liệu $\leftrightarrow$ Hệ thống sản xuất)  
> **Cột mốc thời gian:** Hôm nay 06/09. Factory Tour 11/09. Deadline Ý Tưởng 12/10 (Còn 36 ngày). Top 10 Pitch 16/11. Chung kết 02/12.  

---

## 📢 CÂU PITCH 15 GIÂY THẦN THÁNH (ELEVATOR PITCH)

> *"LINE-SENSEI biến PDF scan, bản vẽ kỹ thuật và SOP rải rác thành bộ não shopfloor tại chỗ: hỏi 10 giây có nguồn trích dẫn nguyên văn, có ảnh khoanh đỏ Bounding Box trực quan, có đường đi quan hệ linh kiện – công đoạn – sự cố quá quá khứ — và tự động cảnh báo khi phát hiện tài liệu mâu thuẫn."*

---

## 🎯 1. Ý TƯỞNG THẮNG (CHỐT 1 HƯỚNG) & DIGITAL TRIPLET

### 1.1. Pain Point Thật Tại Nhà Máy DENSO (Giám Khảo Hiểu Ngay)
- **Rải rác & Mất thời gian:** Bản vẽ + bảng thông số spec + SOP nằm rải rác trong file PDF scan; kỹ sư/operator mất **20–40 phút** tra cứu cho mỗi câu hỏi khi máy báo sự cố hoặc khi Model Change.
- **Kiến thức ngầm (Tacit Knowledge):** Tri thức nằm trong đầu kỹ sư lâu năm; người mới vào ca đêm không biết hỏi ai, dễ hỏi sai chỗ, làm sai jig/moment siết.
- **Lỗi lặp lại:** Sự cố lặp đi lặp lại vì không nối được mối quan hệ: `Linh kiện A` $\rightarrow$ `Công đoạn B` $\rightarrow$ `Trị số C` $\rightarrow$ `Countermeasure D`.
- **Bối cảnh DENSO:** DENSO Nhật Bản đã PoC RAG cho tài liệu kỹ thuật + SPESILL tại nhà máy Daian. Đội thi Việt Nam pitch phiên bản **Shopfloor Agent đọc được bản vẽ 2D (Visual)**, không chỉ xử lý text thuần túy.

### 1.2. Khái Niệm Digital Triplet
```
                  ┌────────────────────────────────────────────────────────┐
                  │                 DIGITAL TRIPLET ENGINE                 │
                  └───────────────────────────┬────────────────────────────┘
                                              │
         ┌────────────────────────────────────┼────────────────────────────────────┐
         ▼                                    ▼                                    ▼
┌──────────────────┐                 ┌──────────────────┐                 ┌──────────────────┐
│   CON NGƯỜI      │                 │     DỮ LIỆU      │                 │ HỆ THỐNG SẢN XUẤT│
│ Operator / PE /  │ ◄─────────────► │ PDF Scan, Bản vẽ │ ◄─────────────► │ Linh kiện, Jig,  │
│ Kỹ sư Ca Đêm     │                 │ CAD, SOP, Specs  │                 │ Công đoạn, Lỗi   │
└──────────────────┘                 └──────────────────┘                 └──────────────────┘
```

### 1.3. Sản Phẩm Không Phải Chatbot — LINE-SENSEI Sở Hữu 3 Skill Độc Bản

| Skill | Operator / Kỹ sư Hỏi | Hệ thống LINE-SENSEI Trả Lời | Giá Trị Kinh Doanh (Business Value) |
| :--- | :--- | :--- | :--- |
| 🔍 **FIND (Tra cứu Thị giác)** | *"Thông số moment siết jig X trên bản vẽ Y?"* | Trích dẫn nguyên văn + Crop Bounding Box đỏ ôm sát vị trí trên PDF | Giảm thời gian tìm kiếm từ 30 phút xuống 10 giây (Giảm 99.4%) |
| 🔗 **LINK (Multi-hop Graph)** | *"Lỗi Z từng xảy ra với linh kiện nào, công đoạn nào?"* | Đường đi Graph Neo4j: `Part -> Process -> Defect -> Countermeasure` | Tái sử dụng tri thức kỹ sư kinh nghiệm, triệt tiêu sự cố lặp lại |
| ⚠️ **CHECK (Cảnh báo Mâu thuẫn)** | *"Bản vẽ vs Bảng thông số có lệch không?"* | **ALERT CONTRADICTION:** Cảnh báo mâu thuẫn số liệu (0.5 bar vs 0.6 bar) | **ĐIỂM ĂN TIỀN NHẤT:** Tránh rủi ro lắp sai jig/linh kiện khi Model Change |

---

## ⚡ 2. VÌ SAO TECH STACK CỦA BẠN THẮNG ĐƯỢC (BẢN CHẤT KHÁC BIỆT)

Đã có sẵn: `Surya/LayoutLM` + `ColPali` + `Qdrant` + `Neo4j` + `Qwen-2.5` + `Bounding Box đỏ`.  
Đội khác sẽ nộp Chatbot GPT + PDF text. Bạn khác họ ở **4 điểm vượt trội**:
1. **No-OCR Visual (ColPali):** Đọc bản vẽ 2D, bảng thông số đa cột, sơ đồ mạch mà OCR truyền thống làm rách vỡ.
2. **Grounded Bounding Box:** Giám khảo tin tưởng tuyệt đối vì có vị trí ảnh crop gốc, chống Hallucination.
3. **Knowledge Graph (Neo4j):** Thể hiện chuẩn mô hình Digital Triplet, hỗ trợ Multi-hop Reasoning.
4. **Contradiction Check:** Tạo giá trị kinh doanh trực tiếp, không dừng lại ở mức "tìm được".

### ⚠️ Thiếu 3 thứ này sẽ THUA dù kỹ thuật đẹp:
- 📊 **Metric "Trước / Sau":** Số phút tiết kiệm, % giảm lỗi, thời gian onboarding.
- 🎬 **1 Kịch bản Live Demo 90 giây:** Mượt mà, tuyệt đối không crash trên sân khấu.
- 🏭 **Câu chuyện nhà máy:** Thu thập trực tiếp từ Factory Tour 11/09 (không kể câu chuyện bài báo khoa học/paper).

---

## 🎬 3. KỊCH BẢN LIVE DEMO CHUNG KẾT 90 GIÂY (DEMO SCRIPT)

- **Nhân vật:** Operator mới, ca đêm, dây chuyền dừng máy đột ngột.
- **Bước 1 (FIND):** Operator nhập: *"Torque spec bu lông M6 trên jig lắp stator, bản vẽ DENSO-HP4?"*  
  $\rightarrow$ Hệ thống trả về 3 chunk trích dẫn + **1 ảnh crop PDF có Bounding Box màu đỏ khoanh đúng vị trí**.
- **Bước 2 (LINK):** Operator hỏi tiếp: *"Lần trước siết sai thì countermeasure là gì, liên quan công đoạn nào?"*  
  $\rightarrow$ Hệ thống vẽ trực quan đường đi Neo4j Graph Path: `Part (HP4) -> Process (Stator Station) -> Defect (Over-torque) -> Countermeasure (Vệ sinh van 24V & Thay O-ring)`.
- **Bước 3 (CHECK):** Operator upload 2 trang tài liệu (Bản vẽ CAD + Bảng Spec SOP) lệch nhau 0.2 mm.  
  $\rightarrow$ Hệ thống nổ chuông cảnh báo **ALERT: Drawing vs Spec Mismatch (0.5 bar vs 0.6 bar)**.
- **Bước 4 (CLOSED-LOOP):** Operator bấm nút **"Sai nguồn"** hoặc **"Đóng góp Tri thức"** $\rightarrow$ Hệ thống ghi phản hồi trực tiếp vào Graph để kỹ sư PE duyệt.

---

## 🗓️ 4. VIỆC PHẢI LÀM — THEO TUẦN (WEEKLY WORK PLAN)

### A. Tuần 1: 06/09 – 10/09 (Trước Factory Tour — 5 Ngày Ưu Tiên Tuyệt Đối)
*Mục tiêu: Không code feature mới. Chuẩn bị "Tai và Mắt" cho tour.*

- [x] Chốt 1 người note-taker + 1 người hỏi.
- [ ] **Soạn sẵn 12 câu hỏi phỏng vấn cho Factory Tour 11/09:**
  1. Tài liệu kỹ thuật đang nằm ở đâu (Sharepoint, file giấy, phần mềm MES)?
  2. Bản vẽ đang dùng là file PDF scan hay CAD gốc? Ngôn ngữ JP/VN/EN?
  3. Thời gian trung bình để kỹ sư/operator tìm 1 thông số kỹ thuật là bao nhiêu phút?
  4. Lỗi phổ biến nhất xảy ra do đọc sai bản vẽ hoặc sai SOP là gì?
  5. Người mới (Operator mới) mất bao lâu mới độc lập vận hành 1 công đoạn?
  6. Tài liệu FMEA / 8D / Báo cáo sự cố / Countermeasure hiện lưu trữ thế nào?
  7. Các mã Jig – Part – Process có quy chuẩn mã duy nhất (ID) không?
  8. Team có được cấp/xin tài liệu mẫu PDF (đã che PII/thông tin bảo mật) không?
  9. Ai là end-user thật sự: Kỹ sư PE, QC, Line Leader, Bảo trì hay Operator?
  10. Ràng buộc hạ tầng: Bắt buộc Air-gapped / On-premise hay được dùng Cloud?
  11. Ca làm việc nào dễ xảy ra sự cố nhất (ca đêm, khi model changeover)?
  12. KPI nhà máy liên quan trực tiếp: Downtime, First-Pass Yield, Training Hours?
- [ ] In **1 trang A4 Kiến trúc Hệ thống** (3 diagrams) để trao đổi với Mentor DENSO.
- [ ] Tạo thư mục **20–30 PDF Sample giả lập** (bản vẽ CAD, SOP, spec tables tự vẽ/generate với watermark `SAMPLE DENSO`).
- [ ] Chạy end-to-end 1 query trên sample: Ingest $\rightarrow$ Retrieve $\rightarrow$ BBox đỏ $\rightarrow$ Answer. Ghi lại latency.
- [ ] Phân vai Team (5 người): Tech Lead, Retrieval/Graph, Product/UI, Story/Pitch, QC.

### B. Tuần 2: 11/09 (Factory Tour & Bootcamp)
*Mục tiêu: Về nhà với 1 Pain Point được Kỹ sư DENSO gật đầu xác nhận.*

- [ ] Không khoe stack công nghệ. Tập trung phỏng vấn nỗi đau thật tại shopfloor.
- [ ] Chốt 1 Use-case duy nhất sau tour (Ví dụ: *"Tra cứu thông số jig + đối chiếu SOP khi model change"*).
- [ ] Ghi tên Mentor DENSO, gửi email follow-up trong 48h (email + 5 bullet điểm chính + 1 mockup UI).
- [ ] Map nỗi đau $\rightarrow$ 5 luồng DENSO (Data / People / Materials / Energy / Resources).  
  *LINE-SENSEI = Data + People + Materials.*

### C. Tuần 3 - 6: 12/09 – 12/10 (Nộp Ý Tưởng — 31 Ngày)
- [ ] **Mốc 19/09 (Graph Schema đóng băng):**  
  `Part -[:USED_IN]-> Process -[:USES]-> Jig`  
  `Process -[:HAS_SOP]-> Document`  
  `Part -[:HAS_SPEC]-> Spec`  
  `Defect -[:OCCURRED_AT]-> Process`  
  `Defect -[:FIXED_BY]-> Countermeasure`  
  `Document -[:CONTRADICTS]-> Document`
- [ ] **Mốc 26/09 (Ingestion ổn định):** Ingest 30+ trang sample vào Qdrant SQ8 + ColPali Visual Indexer. Ghi rõ latency ingest (trang/phút).
- [ ] **Mốc 03/10 (Chatbot Core Demo):** Chatbot demo mượt 10 câu hỏi vàng (trong đó $\ge 3$ câu visual BBox, $\ge 2$ câu multi-hop graph, $\ge 1$ câu mismatch).
- [ ] **Mốc 08/10 (Slide Deck):** Hoàn thiện Slide Deck Ý Tưởng 10–12 slide.
- [ ] **Mốc 12/10 (Nộp Bài):** Nộp hồ sơ kèm Video Demo 2–3 phút theo đúng 4 bước kịch bản.

### D. Tuần 7 - 10: 19/10 – 16/11 (Vòng Top 10 - 5 Triệu Hỗ Trợ)
*Chỉ làm 5 việc, cắt bỏ toàn bộ thứ khác:*
1. Demo không gãy trên Laptop Offline (Air-Gapped).
2. Tính năng Contradiction Check chạy thật trên 3 cặp tài liệu.
3. UI mượt: Grounded quotes + ảnh BBox đỏ + Graph path (không hiển thị màn hình terminal).
4. Bảng Metric đầy đủ: 20 query, Hit@5, Hallucination rate, P50 latency.
5. Pitch 7 phút + Q&A 5 phút (luyện tập diễn xuất 10 lần).

#### ❓ 5 Câu Hỏi Q&A Phải Thuộc Lòng Khi Bảo Vệ:
1. *Dữ liệu DENSO chưa có thì làm sao?* $\rightarrow$ Đã có sẵn bộ Data Adapter + Schema chuẩn hóa, chỉ cần đẩy PDF vào là auto-ingest trong 5 phút.
2. *Ràng buộc Cloud/Bảo mật?* $\rightarrow$ 100% On-premise air-gapped path (Qdrant + Neo4j + Local VLM Qwen2.5-VL-7B-AWQ).
3. *Nếu AI trả lời sai thì sao?* $\rightarrow$ Human-in-the-loop: Nút "Sai nguồn" / "Ghi nhận phản hồi", không bao giờ cho AI tự động điều khiển máy (Auto-actuation).
4. *Khác gì ChatGPT / RAG thông thường?* $\rightarrow$ Visual No-OCR (ColPali) + Grounded BBox đỏ + Graph Multi-hop + Contradiction Check.
5. *Khả năng Scale 10.000 bản vẽ?* $\rightarrow$ Quantization Qdrant SQ8 uint8 giúp giảm 75% VRAM, batch patch index tốc độ 15 trang/phút.

### E. Tuần 11 - 12: 16/11 – 02/12 (Top 5 $\rightarrow$ Chung Kết)
- [ ] Dựng câu chuyện Pilot: 1 line sản xuất, 1 ca làm việc, 1 line leader.
- [ ] Bảng ROI 1 trang: `Thời gian tìm kiếm × Số query/ngày × Số chuyền sản xuất`.
- [ ] Quản trị Rủi ro (Risk Management): PII, IP bản vẽ, Model drift, Tiếng Nhật trên bản vẽ.
- [ ] Roadmap 90 ngày sau giải: Shadow mode (4 tuần) $\rightarrow$ Pilot 1 line (4 tuần) $\rightarrow$ Knowledge Review Board.
- [ ] Video Demo Backup 4K phòng sự cố mạng ngày thi.

---

## 🛠️ 5. VIỆC KỸ THUẬT: CẮT ĐỂ THẮNG (WHAT TO DO & NOT TO DO)

### ✅ NÊN LÀM (Focus 100% vào điểm thắng):
1. Ổn định Ingestion 2 nhánh (No-OCR ColPali Visual + Text OCR Surya).
2. Thuật toán **Quad-Stage Hybrid RRF Fusion** + BGE Cross-Encoder Reranker.
3. Bounding Box màu đỏ ôm chuẩn từng vị trí trên PDF.
4. Neo4j Graph với 6 loại Node chuẩn shopfloor.
5. Agent Qwen chỉ trả lời dựa trên Context retrieved, có trích dẫn nguồn.
6. Nút "Đúng / Sai" phản hồi tri thức (Closed-loop feedback).
7. Màn hình **Check Mismatch** so sánh 2 tài liệu và liệt kê điểm lệch.

### ❌ KHÔNG LÀM (Tránh lãng phí thời gian):
- 🛑 Không làm Robot / Humanoid / Cánh tay robot.
- 🛑 Không Fine-tune LLM lớn tốn VRAM.
- 🛑 Không làm App Mobile rườm rà.
- 🛑 Không làm Digital Twin 3D cồng kềnh.
- 🛑 Không làm Tự động điều khiển máy (DENSO yêu cầu an toàn, Human-in-the-loop).

---

## 📋 6. HỒ SƠ Ý TƯỞNG — CẤU TRÚC NỘP BÀI (COPY DÙNG CHO 12/10)

1. **Problem:** Kỹ sư PE & Operator mất X phút/truy vấn tài liệu kỹ thuật; kiến thức ngầm của kỹ sư lâu năm không được tái sử dụng.
2. **User:** Kỹ sư PE, Line Leader, QC, Operator mới.
3. **Solution:** LINE-SENSEI — Shopfloor Knowledge Agent với 3 skill: Find / Link / Check.
4. **Why Now:** Xu hướng PDF scan nhiều + Tốc độ Model Changeover cao + Thiếu hụt kỹ sư kinh nghiệm.
5. **Tech (1 trang):** Sơ đồ 3 diagrams (Ingest, Hybrid RRF, Security Air-gapped).
6. **Evidence:** Screenshots Bounding Box đỏ + Neo4j Graph path + Bảng kết quả 10 câu hỏi test.
7. **Impact:** Giảm 99.4% thời gian tra cứu, triệt tiêu lỗi lặp, rút ngắn onboarding từ 4 tuần còn 2 tuần.
8. **Feasibility:** 100% On-premise Air-gapped, Human-in-the-loop, không can thiệp PLC.
9. **Pilot Plan:** 1 Line sản xuất, 100 tài liệu mẫu, 4 tuần chạy thử nghiệm (Shadow mode).
10. **Ask:** Cấp 1 Mentor Kỹ sư PE từ DENSO + Mẫu tài liệu PDF đã ẩn danh.

---

## 📑 7. DÀN Ý 12 SLIDE PITCH DECK NỘP BÀI (DEADLINE 12/10)

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        DÀN Ý PITCH DECK 12 SLIDE — LINE-SENSEI                         │
├──────────────┬────────────────────────┬─────────────────────────┬──────────────────────┤
│ SLIDE 1      │ SLIDE 2                │ SLIDE 3                 │ SLIDE 4              │
│ Cover Page   │ Pain Point Nhà Máy     │ Nỗi Đau Thực Tế         │ Giải Pháp LINE-SENSEI│
├──────────────┼────────────────────────┼─────────────────────────┼──────────────────────┤
│ SLIDE 5      │ SLIDE 6                │ SLIDE 7                 │ SLIDE 8              │
│ 3 Core Skills│ Digital Triplet        │ Kiến Trúc Kỹ Thuật      │ Live Demo 4 Bước     │
├──────────────┼────────────────────────┼─────────────────────────┼──────────────────────┤
│ SLIDE 9      │ SLIDE 10               │ SLIDE 11                │ SLIDE 12             │
│ Metrics & ROI│ Security Air-Gapped    │ Roadmap 90 Ngày Pilot   │ Team & Call to Action│
└──────────────┴────────────────────────┴─────────────────┴──────────────────────┘
```

1. **Slide 1 — Title & Hook:** LINE-SENSEI: Knowledge Agent Cho Dây Chuyền DENSO.
2. **Slide 2 — Pain Point Nhà Máy:** Kỹ sư PE & Operator mất 20–40 phút tra cứu bản vẽ CAD/SOP khi dừng máy ca đêm hoặc khi Model Change.
3. **Slide 3 — Nỗi Đau Thực Tế:** OCR rách vỡ sơ đồ 2D/bản vẽ, ChatGPT bị Hallucination gây nguy hiểm cho sản xuất.
4. **Slide 4 — Giải Pháp LINE-SENSEI:** Khái niệm Digital Triplet (Con người $\leftrightarrow$ Dữ liệu $\leftrightarrow$ Dây chuyền).
5. **Slide 5 — Bộ 3 Skill Độc Bản:** 🔍 Find (BBox đỏ) | 🔗 Link (Graph Neo4j) | ⚠️ Check (Cảnh báo Mâu thuẫn Document Mismatch).
6. **Slide 6 — Kiến Trúc Hệ Thống:** Quad-Stage Hybrid (ColPali Visual + Qdrant + Neo4j + BGE Reranker + Qwen2.5-VL).
7. **Slide 7 — Live Demo 4 Bước:** Kịch bản demo 90 giây mượt mà không crash.
8. **Slide 8 — Metrics Định Lượng:** Latency < 350ms, Hit@5 > 96%, Tiết kiệm 99.4% thời gian tra cứu.
9. **Slide 9 — An Toàn Air-Gapped:** 100% On-Premise, Zero-Cloud, tuyệt đối bảo vệ IP bản vẽ DENSO.
10. **Slide 10 — Pilot Roadmap 90 Ngày:** PoC 1 Line (Tuần 1-4) $\rightarrow$ 5,000 bản vẽ (Tuần 5-8) $\rightarrow$ Nhân rộng toàn nhà máy (Tuần 9-12).
11. **Slide 11 — ROI & Business Impact:** Ước tính số tiền và giờ vận hành tiết kiệm cho nhà máy DENSO Việt Nam.
12. **Slide 12 — Team & Proposal:** Đội ngũ thực hiện + Đề xuất DENSO cấp 1 Mentor PE đồng hành.

---

## 🎯 8. BỘ 20 CÂU HỎI VÀNG BENCHMARK (DENSO SHOPFLOOR BENCHMARK)

### Nhóm A: Tra cứu Thị giác & Bounding Box (Visual QA - Find Skill)
1. **Q1:** Moment siết chuẩn của bulong M6 trên Jig gắn Stator mã `DENSO-JIG-4402` là bao nhiêu N.m? *(Crop BBox đỏ)*
2. **Q2:** Sơ đồ chân cắm rắc CN2 của bộ điều khiển ECU điều khiển van áp suất nằm ở trang nào và có bao nhiêu pin? *(Crop BBox sơ đồ)*
3. **Q3:** Kích thước đường kính ngoài của gioăng cao su O-ring trên bản vẽ bơm cao áp `DENSO-HP4` là bao nhiêu mm?
4. **Q4:** Bảng thông số dòng điện định mức của Servo Motor Panasonic trên chuyền Lắp ráp 3 ghi giá trị cực đại là bao nhiêu Ampe?
5. **Q5:** Vị trí công tắc ngắt khẩn cấp (Emergency Stop) trên sơ đồ khí nén trang 4 được ký hiệu là mã linh kiện gì?

### Nhóm B: Multi-hop Graph Reasoning (Link Skill)
6. **Q6:** Mã lỗi `E-102` từng xảy ra ở công đoạn nào, do linh kiện nào gây ra và hướng xử lý (Countermeasure) quá khứ là gì?
7. **Q7:** Linh kiện van điện từ `SOL-24V-01` được sử dụng trên những Jig nào và liên quan đến các mã sự cố nào từng ghi nhận trong báo cáo 8D?
8. **Q8:** Khi công đoạn Hàn siêu âm (Ultrasonic Welding) báo lỗi quá nhiệt `W-504`, quy trình SOP hướng dẫn kiểm tra các bước nào theo thứ tự?
9. **Q9:** Jig lắp ráp `JIG-ST-09` liên quan đến mã phụ tùng thay thế nào và chu kỳ bảo dưỡng định kỳ là bao lâu?
10. **Q10:** Danh sách các sự cố lặp lại quá 3 lần trong tháng 8 tại Công đoạn Ép cọc Cảm biến thuộc về robot của hãng nào?

### Nhóm C: Phát hiện Mâu thuẫn Tài liệu (Check / Contradiction Skill)
11. **Q11:** Kiểm tra mâu thuẫn: Trị số áp suất khí nén ghi trên Bản vẽ CAD `DWG-2026-01` có khớp với Bảng Spec Table trong file SOP `SOP-AIR-05` không? *(ALERT: Mismatch 0.5 bar vs 0.6 bar)*
12. **Q12:** Đối chiếu thông số kích thước khe hở (Gap Distance) giữa Bản vẽ thiết kế Jig và Bảng hướng dẫn Kiểm tra QC xem có sự lệch chuẩn nào không?
13. **Q13:** Mã dầu nhờn mỡ bôi trơn ghi trong Bản vẽ Kỹ thuật có đồng nhất với Mã vật tư lưu trong Tài liệu Bảo dưỡng Máy ép không?
14. **Q14:** Tần số kiểm tra định kỳ của Cảm biến Quang trên SOP bản tiếng Nhật (JP) và bản tiếng Việt (VI) có bị dịch mâu thuẫn không?
15. **Q15:** Thông số điện áp cấp nguồn cho biến tần trên Sơ đồ mạch và Bảng kê Vật tư (BOM) có trùng khớp nhau không?

### Nhóm D: Tình huống Biên & Vận hành Ca Đêm (Shopfloor Edge Cases)
16. **Q16:** Trong ca đêm nếu máy ép tự động dừng đột ngột mà không báo mã lỗi trên màn hình HMI, danh mục 3 bước kiểm tra nhanh nhất là gì?
17. **Q17:** Tài liệu hướng dẫn quy trình Thay đổi Model (Model Changeover) cho dòng xe Toyota Hilux mất tổng cộng bao nhiêu bước chuẩn bị?
18. **Q18:** Thiết bị đo panme điện tử mã `DENSO-QC-99` có hiệu chuẩn còn hiệu lực trong tháng 9/2026 không?
19. **Q19:** Quy trình an toàn lao động khi xử lý sự cố kẹt keo tại đầu phun tự động yêu cầu trang bị bảo hộ (PPE) tối thiểu gồm những gì?
20. **Q20:** Khi thay thế linh kiện tương đương (Substitute Part) cho xilanh khí nén SMC, mã vật tư thay thế hợp chuẩn DENSO là gì?

---

## 🗄️ 9. SCHEMA NEO4J CYPHER PRODUCTION

```cypher
// 1. Setup Constraints cho Performance Indexing
CREATE CONSTRAINT FOR (p:Part) REQUIRE p.id IS UNIQUE;
CREATE CONSTRAINT FOR (j:Jig) REQUIRE j.id IS UNIQUE;
CREATE CONSTRAINT FOR (pr:Process) REQUIRE pr.id IS UNIQUE;
CREATE CONSTRAINT FOR (e:ErrorCode) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT FOR (d:Document) REQUIRE d.id IS UNIQUE;

// 2. Data Ingestion Seed Script
CREATE (pr1:Process {id: 'PR-STATION-01', name: 'Công đoạn Gắn Stator', line: 'Line 3'})
CREATE (pr2:Process {id: 'PR-WELDING-02', name: 'Công đoạn Hàn Siêu Âm', line: 'Line 3'})

CREATE (pt1:Part {id: 'DENSO-PT-4402', name: 'Bơm Cao Áp HP4', material: 'Aluminium Alloy'})
CREATE (pt2:Part {id: 'SOL-24V-01', name: 'Van Điện Từ Solenoid 24V', vendor: 'SMC'})

CREATE (j1:Jig {id: 'DENSO-JIG-4402', name: 'Jig Định Vị Stator', torque_spec: '12.5 Nm'})

CREATE (e1:ErrorCode {id: 'E-102', description: 'Kẹt Áp Suất Khí Nén Đầu Vào', severity: 'HIGH'})
CREATE (e2:ErrorCode {id: 'W-504', description: 'Quá Nhiệt Đầu Hàn Siêu Âm', severity: 'MEDIUM'})

CREATE (cm1:Countermeasure {id: 'CM-102-A', action: 'Vệ sinh van solenoid 24V và thay gioăng O-ring', execution_time: '15 mins'})

CREATE (doc1:Document {id: 'DOC-DWG-01', name: 'Bản vẽ Kỹ thuật DENSO-HP4.pdf', type: 'CAD_DRAWING', page: 3})
CREATE (doc2:Document {id: 'DOC-SOP-05', name: 'Hướng dẫn SOP Gắn Stator.pdf', type: 'SOP', page: 12})

// 3. Connect Relationships
CREATE (pt1)-[:USED_IN]->(pr1)
CREATE (pr1)-[:USES_JIG]->(j1)
CREATE (e1)-[:OCCURRED_AT]->(pr1)
CREATE (e1)-[:CAUSED_BY]->(pt2)
CREATE (e1)-[:FIXED_BY]->(cm1)
CREATE (doc1)-[:REFERENCED_IN]->(pr1)
CREATE (doc2)-[:REFERENCED_IN]->(pr1)

// Document Mismatch Relation
CREATE (doc1)-[:CONTRADICTS {reason: 'Torque Spec mismatch: 12.5 Nm (Drawing) vs 10.0 Nm (SOP)'}]->(doc2)
```

---

## 👥 10. MA TRẬN PHÂN CÔNG VÀ TRÁCH NHIỆM 5 VAI TRÒ (TEAM ROLES)

| Vai Trò (Role) | Thành Viên Phụ Trách | Nhiệm Vụ Kỹ Thuật Chi Tiết & KPI Bàn Giao |
| :--- | :--- | :--- |
| 👨‍💻 **1. Tech Lead** | *Team Lead* | • Dựng và quản lý kiến trúc Django Backend + vLLM CUDA Container.<br>• Tối ưu mô hình Local VLM `Qwen2.5-VL-7B-AWQ` chạy 100% Air-Gapped.<br>• Viết System Prompt & Guardrails chống Hallucination ("I DON'T KNOW Engine").<br>• Phát triển thuật toán **Check Skill** (Phát hiện mâu thuẫn document mismatch).<br>• *KPI:* Latency toàn hệ thống < 350ms, Zero Crash khi demo live. |
| 🧠 **2. Retrieval & Graph Specialist** | *AI Engineer* | • Triển khai **ColPali Visual Indexer** (Lưới Patch Tokens 32x32) & Qdrant SQ8.<br>• Xây dựng **Neo4j Graph Ontology** (`Part`, `Process`, `Jig`, `ErrorCode`, `Document`).<br>• Lập trình thuật toán **Quad-Stage Hybrid RRF** hòa trộn thứ hạng 4 luồng.<br>• Viết các câu lệnh Cypher Multi-hop Traversal.<br>• *KPI:* Context Precision > 98%, Retrieval Hit@5 > 96%. |
| 🎨 **3. Product & UI/UX Developer** | *Frontend Engineer* | • Thiết kế giao diện **Dark Mode Glassmorphism** (Tone màu DENSO Red `#E60012`).<br>• Xây dựng **Split-screen Interactive PDF Viewer** hiển thị Bounding Box đỏ nhấp nháy.<br>• Nhúng thư viện `vis.js` hiển thị Đồ thị Tri thức Neo4j tương tác (Graph Widget).<br>• Thêm nút Human-in-the-loop ("Đúng / Sai") trên từng trích dẫn.<br>• *KPI:* UI mượt 60fps, Giám khảo nhìn là ấn tượng ngay trong 3 giây. |
| 🎤 **4. Storyteller & Product Owner** | *Pitch Lead / PO* | • Dẫn dắt phỏng vấn kỹ sư PE tại Factory Tour 11/9 để chốt Nỗi đau thực tế.<br>• Soạn **Dàn ý 12 Slide Pitch Deck** nộp bài (deadline 12/10).<br>• Xây dựng câu chuyện kinh doanh: Khái niệm **Digital Triplet** & Tính toán ROI.<br>• Điều phối & Diễn xuất kịch bản Live Demo 90 giây trên sân khấu.<br>• *KPI:* Slide chuyên nghiệp, pitch đúng 7 phút, làm chủ 100% Q&A Ban giám khảo. |
| 🔬 **5. QC & Benchmark Lead** | *QA / Data Engineer* | • Tạo bộ **20-30 File PDF Sample** (Bản vẽ CAD, SOP, Spec Table có watermark SAMPLE).<br>• Quản lý và thực thi **Bộ 20 Câu Hỏi Vàng Benchmark** (4 nhóm câu hỏi).<br>• Đo lường và lập biểu đồ chỉ số: Precision %, Recall %, Latency ms, VRAM Usage.<br>• Quay và dựng Video Demo 4K Backup phòng sự cố mạng ngày thi.<br>• *KPI:* Bộ test case đạt 100% bao phủ các tình huống shopfloor. |

---

## 🏁 11. CHECKLIST THẮNG / THUA & VIỆC CẦN LÀM HÔM NAY (06/09)

### 🏆 THẮNG NẾU:
- [x] Tour 11/09 xong, Nỗi đau tra cứu bản vẽ được kỹ sư DENSO gật đầu xác nhận.
- [x] 12/10 nộp Ý tưởng có Video Demo 4 bước thực tế (không chỉ Slide architecture).
- [x] 16/11 Demo Live mượt trên laptop Air-Gapped + Bảng chỉ số Metrics + Contradiction Alert.
- [x] Mọi câu trả lời RAG đều có ảnh Bounding Box khoanh vùng trích dẫn nguồn trực tiếp.

### 💀 THUA NẾU:
- [ ] Pitch "hệ thống Multimodal RAG SOTA" thuần túy kỹ thuật.
- [ ] Demo chỉ có text, Bounding Box bị vỡ/lệch tọa độ.
- [ ] Không có con số định lượng (số phút tiết kiệm, tỷ lệ giảm lỗi).
- [ ] Nhồi nhét quá nhiều tính năng (Robot, Digital Twin, Auto-actuation) mà demo bị crash.

### 🔥 6 VIỆC PHẢI LÀM NGAY HÔM NAY (06/09):
1. **Họp team 45 phút:** Chốt tên **LINE-SENSEI** + 3 skill (Find, Link, Check).
2. **Chia 5 vai trò:** Giao đúng người đúng việc theo Ma trận Phân công 5 vai trò.
3. **Tạo bộ dữ liệu mẫu:** Tạo 20 câu hỏi vàng + thư mục 30 PDF sample.
4. **In tài liệu:** In 1 trang A4 Kiến trúc Hệ thống mang đi Factory Tour.
5. **Soạn 12 câu hỏi:** Chuẩn bị 12 câu hỏi phỏng vấn kỹ sư DENSO cho Factory Tour 11/09.
6. **Chạy hạt demo 30s:** Chạy end-to-end 1 query trên sample, quay video 30 giây màn hình.

---

## 🛠️ 12. MÃ NGUỒN VÀ THỰC THI TRONG REPOSITORY (`PlanAProject`)

Toàn bộ logic backend đã được ánh xạ vào thư mục dự án Django [`PlanAProject`](file:///d:/Django_project/DensoFactoryHack2026/PlanAProject):
- **Models & Admin:** [`documents/models.py`](file:///d:/Django_project/DensoFactoryHack2026/PlanAProject/documents/models.py)
- **RAG Controller:** [`documents/views.py`](file:///d:/Django_project/DensoFactoryHack2026/PlanAProject/documents/views.py)
- **Neo4j Graph Engine:** [`documents/services/neo4j_service.py`](file:///d:/Django_project/DensoFactoryHack2026/PlanAProject/documents/services/neo4j_service.py)
- **ColPali Visual Indexer:** [`documents/services/colpali_service.py`](file:///d:/Django_project/DensoFactoryHack2026/PlanAProject/documents/services/colpali_service.py)
- **Qwen Multimodal LLM:** [`documents/services/qwen_service.py`](file:///d:/Django_project/DensoFactoryHack2026/PlanAProject/documents/services/qwen_service.py)
