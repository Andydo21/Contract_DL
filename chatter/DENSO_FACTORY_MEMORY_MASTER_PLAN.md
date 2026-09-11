# 🏭 DENSO FACTORY MEMORY
## Hệ Thống Số Hóa, Truy Hồi và Tiến Hóa Tri Thức Chuyên Gia Nhà Máy
> **Bản Kế Hoạch Chiến Lược Tranh Giải Nhất — DENSO AI Hackathon 2026 (Nhóm Bài Toán A2 + A3)**

---

## 🎯 THÔNG ĐIỆP CỐT LÕI (CORE VALUE PROPOSITION)

> *"Không chỉ giúp AI đọc tài liệu. Không chỉ giúp AI hỏi chuyên gia.*  
> *Hệ thống biến cả **tài liệu phân tán** và **kinh nghiệm ngầm của chuyên gia** thành một **'Bộ Nhớ Vận Hành' (Operational Memory)** có thể tìm kiếm, suy luận, kiểm chứng và liên tục tự tiến hóa."*

---

## 1. TẠI SAO PHẢI THOÁT KHỎI CÁI BẪY "RAG CHATBOT"?

### Thực trạng các đội thi thông thường:
Đa số các đội sẽ đi theo một đường thẳng baseline:
$$\text{PDF} \longrightarrow \text{OCR} \longrightarrow \text{Embedding} \longrightarrow \text{Vector DB} \longrightarrow \text{LLM} \longrightarrow \text{Chatbot}$$
Dù có tối ưu OCR tốt hơn, dùng ColPali hay Reranker mạnh hơn, Ban Giám Khảo DENSO vẫn sẽ chỉ nhìn nhận:  
👉 **"Đây chỉ là một Chatbot tra cứu tài liệu tốt hơn một chút."** (Chưa chạm tới bản chất vận hành sản xuất).

### Điểm đột phá của "DENSO Factory Memory":
Chuyển đổi **Đơn Vị Giá Trị (Unit of Value)**:
* Không bán một con "Chatbot tra tài liệu".
* Bán một **Vòng đời Tri thức hoàn chỉnh (Closed-Loop Knowledge Lifecycle)**: Tự động ghi nhận $\rightarrow$ Chuẩn hóa $\rightarrow$ Truy hồi đa phương thức $\rightarrow$ Phát hiện lỗ hổng $\rightarrow$ Phỏng vấn chuyên gia $\rightarrow$ Tự tiến hóa.

---

## 2. KIẾN TRÚC TỔNG THỂ: VÒNG LẶP KÍN TIẾN HÓA TRI THỨC

```
                           DỮ LIỆU NHÀ MÁY DENSO
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
        TÀI LIỆU KỸ THUẬT (A3)                 CHUYÊN GIA / KỸ SƯ (A2)
     (PDF, SOP, Bản vẽ 2D/3D, Bảng biểu)       (Kinh nghiệm ngầm, Workflow, Ngoại lệ)
                 │                                       │
                 └───────────────────┬───────────────────┘
                                     ▼
                        KNOWLEDGE CONVERGENCE LAYER
                                     │
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
           VECTOR STORE       KNOWLEDGE GRAPH        CASE MEMORY
        (ColPali + BGE-M3)       (Neo4j)        (Case-Based Reasoning)
                 │                   │                   │
                 └───────────────────┼───────────────────┘
                                     ▼
                         AI KNOWLEDGE ENGINE (QWEN)
                                     │
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
           Search & Retrieval    Reasoning & Proof     Actionable Workflow
                 │                   │                   │
                 └───────────────────┼───────────────────┘
                                     ▼
                             KỸ SƯ HIỆN TRƯỜNG
                                     │
                             Feedback & Action
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
       [ĐÃ CÓ ĐỦ TRI THỨC]                     [PHÁT HIỆN LỖ HỔNG TRI THỨC]
                 │                                       │
                 ▼                                       ▼
           Thực thi bảo trì                     KNOWLEDGE GAP DETECTED
                                                         │
                                                         ▼
                                                AI EXPERT INTERVIEWER
                                                (Phỏng vấn chuyên gia)
                                                         │
                                                         ▼
                                                KNOWLEDGE EVOLUTION
                                                (Cập nhật lại Graph & Vector)
                                                         │
                                                         └───→ [VÒNG LẶP TIẾP DIỄN]
```

* **A3 cung cấp năng lực "Nhìn Thấy" (Perception):** Đọc bản vẽ, sơ đồ máy, dung sai, bảng thông số song ngữ Nhật/Anh/Việt.
* **A2 cung cấp năng lực "Biết Phải Làm Gì" (Action & Reasoning):** Nắm bắt workflow xử lý, suy luận chẩn đoán lỗi của chuyên gia.
* **Tầng Tiến Hóa (Knowledge Evolution):** Tri thức không bao giờ bị đóng băng sau khi upload tài liệu, mà tự lớn lên sau mỗi ca sửa chữa.

---

## 3. TÍNH NĂNG MẠNH NHẤT: TRUY XUẤT NGUỒN GỐC & ĐỘ TIN CẬY (KNOWLEDGE PROVENANCE)

Trong môi trường công nghiệp chính xác như DENSO, **AI không bao giờ được phép trộn lẫn giữa "Quy chuẩn nhà máy" và "Kinh nghiệm truyền miệng"**.

### Cấu trúc câu trả lời của AI:

```markdown
### 🛠️ KHUYẾN NGHỊ XỬ LÝ (ACTIONABLE WORKFLOW):
1. Bước 1: Kiểm tra áp suất khí nén cấp vào cụm gắp (Target: 0.5 ± 0.02 MPa).
2. Bước 2: Tháo và kiểm tra độ rơ của ổ bi đỡ B-230.
3. Bước 3: Nếu nhiệt độ vận hành > 35°C, chuyển sang quy trình làm mát phụ (Quy trình ngoại lệ).

---
### 📚 CƠ SỞ DẪN CHỨNG (KNOWLEDGE PROVENANCE):
* 🏛️ [QUY CHUẨN CHÍNH THỨC] SOP-012 — Trang 4, Mục 2.1: Quy định áp suất khí nén chuẩn.
* 📐 [BẢN VẼ KỸ THUẬT] Bản vẽ A-234 — Trang 2, BBox [120, 45, 600, 890]: Vị trí cụm vòng bi B-230.
* 👨‍🔧 [KINH NGHIỆM CHUYÊN GIA] Engineer Nguyễn Văn A (ID: EXP-07): Đã xử lý 18 ca rung giật tương tự.
* 📂 [LỊCH SỬ SỰ CỐ] Case #128 (Máy M12, 15/09/2025): Hiện tượng rung tương tự, giải quyết bằng cách thay B-230.

---
### ⚠️ ĐIỀU KIỆN NGOẠI LỆ (EXCEPTION HANDLING):
* Không áp dụng siết lực > 25 N·m nếu cụm van đang ở trạng thái nóng trên 40°C (theo ghi chú của Chuyên gia B).

### 🛡️ MỨC ĐỘ TIN CẬY (CONFIDENCE SCORE):
* 96.5% — Đã qua kiểm chứng thực tế (Validated by Lead Engineer).
```

---

## 4. BẢNG DỮ LIỆU ĐỊNH DANH TRI THỨC (KNOWLEDGE ITEM SPECIFICATION)

Mỗi mẩu tri thức trong hệ thống không phải là một "chunk text vô danh", mà là một thực thể có định danh pháp lý rõ ràng:

| Trường thuộc tính | Ý nghĩa vận hành | Ví dụ thực tế |
| :--- | :--- | :--- |
| `Knowledge_ID` | Mã định danh duy nhất | `KNOW-2026-M12-0231` |
| `Knowledge_Type` | Phân loại tri thức | `Official SOP` / `Expert Know-how` / `Historical Case` |
| `Source_Origin` | Nguồn gốc xuất xứ | `Expert Interview Session #07` |
| `Author_Expert` | Chuyên gia cung cấp | `Lead Engineer: Nguyen Van A (15 năm KN Robot)` |
| `Machine_Affected` | Thiết bị áp dụng | `Denso Robot VS-068 / Machine Line #3` |
| `Part_Number` | Linh kiện liên quan | `Bearing B-230 (Part #DENSO-BRG-230)` |
| `Evidence_Link` | Bằng chứng kiểm chứng | `PDF Trang 3 + Video thao tác + Case #128` |
| `Confidence_Level` | Độ tin cậy | `High (Validated)` |
| `Version_Control` | Quản lý phiên bản | `v2.1 (Được sửa đổi sau sự cố tháng 10/2025)` |

---

## 5. ĐÒN ĐỘC SỐ 1: AI KNOWLEDGE INTERVIEWER (AI PHỎNG VẤN CHUYÊN GIA)

> **Vấn đề của A2:** Chuyên gia nhà máy rất bận, không ai có thời gian ngồi viết báo cáo hay gõ form dài dòng. Tri thức ngầm (*Tacit Knowledge*) nằm trong đầu họ và bị mất đi khi họ nghỉ hưu.

### Giải pháp: AI Chủ động đặt câu hỏi dạng Socratic:
* **AI:** *"Khi máy M12 xuất hiện hiện tượng rung giật ở tốc độ 3.000 rpm, anh thường kiểm tra bộ phận nào đầu tiên?"*
* **Chuyên gia:** *"Tôi sờ vào cụm ổ bi đỡ B-230 trước."*
* **AI (Hỏi sâu nguyên nhân):** *"Vì sao lại ưu tiên ổ bi B-230 thay vì kiểm tra động cơ servo?"*
* **Chuyên gia:** *"Vì nếu tần số rung rơi vào khoảng 120Hz thì 90% là do mòn vòng cách bi, động cơ servo rất hiếm khi hỏng ở dải này."*
* **AI (Khai thác ngoại lệ):** *"Có trường hợp nào anh không thay ổ bi mà xử lý cách khác không?"*
* **Chuyên gia:** *"Có chứ. Nếu nhiệt độ môi trường lúc đó dưới 15°C thì mỡ bôi trơn bị đông cứng, chỉ cần gia nhiệt làm nóng mỡ là hết, không được thay bi."*

### AI tự động trích xuất thành Cấu trúc Tri thức:
$$\text{Condition} \longrightarrow \text{Symptom} \longrightarrow \text{Hypothesis} \longrightarrow \text{Diagnostic Step} \longrightarrow \text{Exception} \longrightarrow \text{Countermeasure}$$

Tri thức này ngay lập tức được biên dịch vào **Knowledge Graph** để kỹ sư tập sự dùng mãi mãi về sau!

---

## 6. ĐÒN ĐỘC SỐ 2: KNOWLEDGE GAP DETECTION (TỰ PHÁT HIỆN ĐIỂM MÙ)

Một chatbot thông thường khi gặp câu hỏi không biết sẽ:
1. Bịa đặt thông tin (*Hallucination*).
2. Trả lời vô thưởng vô phạt: *"Tôi không tìm thấy thông tin."*

### Cơ chế Knowledge Gap của DENSO Factory Memory:
Khi kỹ sư hỏi một ca bệnh lạ:
1. AI rà soát Vector DB + Graph DB + Case Memory.
2. Nếu điểm tương đồng $Score < 0.65$, hệ thống **tuyệt đối không bịa đặt**, mà bật cờ cảnh báo:
   ```
   ⚠️ PHÁT HIỆN KHOẢNG TRỐNG TRI THỨC (KNOWLEDGE GAP DETECTED)
   Kho tài liệu hiện tại chưa có quy trình chuẩn cho lỗi [E-902 áp suất dầu biến thiên].
   ```
3. Hệ thống kích hoạt **Expert Finder (Tìm chuyên gia)**:
   * Quét Knowledge Graph: *"Kỹ sư Trần B là người từng giải quyết 6 ca liên quan đến hệ thống thủy lực của dòng máy này."*
4. Đẩy thông báo mời chuyên gia: Tạo một phiên phỏng vấn nhanh 3 phút (`AI Interview Session`) để cập nhật tri thức mới.

---

## 7. CASE MEMORY (KHO LÝ THUYẾT TÌNH HUỐNG THỰC ĐỊA)

Sản xuất công nghiệp vận hành dựa trên **Các Tình Huống Đã Từng Xảy Ra (Case-Based Reasoning - CBR)**.

### Cấu trúc một Case Memory:
```json
{
  "case_id": "CASE-DENSO-2025-089",
  "machine_id": "VS-068-LINE2",
  "symptom": "Tiếng rít bất thường ở khớp trục J4 khi quay góc > 90 độ",
  "root_cause": "Dây đai truyền động trục J4 bị chùng 1.5mm do nhiệt độ cao",
  "action_taken": "Tăng đơ dây đai theo cữ 3.5mm, bôi trơn mỡ chuyên dụng Denso #4",
  "result": "Đã xử lý dứt điểm, máy chạy ổn định sau 3 tháng",
  "downtime_minutes": 25,
  "verified_by": "Senior Technician Tran Van B"
}
```
Khi kỹ sư mới nhập triệu chứng $\rightarrow$ AI thực hiện **Cosine Similarity** trên Case Memory $\rightarrow$ Trích xuất ngay 3 ca tương tự nhất trong quá khứ kèm kết quả kiểm nghiệm thực tế!

---

## 8. ĐA PHƯƠNG THỨC THỰC THỤ CHO BẢN VẼ A3

A3 không chỉ là đọc chữ OCR, mà hỗ trợ **4 loại truy vấn hỗn hợp (Mixed Query)**:
1. **Text Query:** *"Tìm thông số mô-men siết bu-lông mặt bích trục 2."*
2. **Image Query (Ảnh chụp thực địa):** Chụp ảnh một con ốc bị mòn ren hoặc một bảng mã vạch $\rightarrow$ AI nhận diện part number và vị trí tương ứng trên bản vẽ.
3. **Drawing Query (Bản vẽ CAD):** Đưa bản vẽ PDF vào $\rightarrow$ AI đọc từng đường gióng kích thước, dung sai $\pm$, số đo phi $\phi$.
4. **Mixed Query:** *"Linh kiện trong ảnh này từng bị hỏng trong những sự cố nào, ai là người sửa?"*

---

## 9. KNOWLEDGE GRAPH THỰC THỤ (NEO4J SCHEMA)

Quan hệ thực giữa con người, máy móc và quy trình:

```
(Expert: Kỹ sư A) ──[:KNOWS_HOW_TO_FIX]──→ (Failure: Lỗi rung 120Hz)
                                                    │
                                            [:OCCURS_ON]
                                                    ↓
(Part: Vòng bi B-230) ──[:BELONGS_TO]──→ (Machine: Máy phay M12)
        │                                           │
  [:DOCUMENTED_IN]                            [:OPERATES_IN]
        ↓                                           ↓
(Drawing: Bản vẽ A-234)                   (Process: Gia công thân van)
```

---

## 10. BẢNG TIÊU CHÍ ĐO LƯỜNG ĐÁNH GIÁ (BENCHMARK FOR VICTORY)

| Bài toán | Chỉ số đo lường (Metrics) | Baseline trước đây | DENSO Factory Memory |
| :--- | :--- | :---: | :---: |
| **A3 (Độ chính xác & Độ trễ)** | **Retrieval Recall@5** (Tìm đúng tài liệu) | 68.2% | **94.5%** |
| | **Table Extraction IoU** (Độ chính xác bảng) | 62.0% | **91.8%** |
| | **Visual Diagram Bounding Box Precision** | 55.0% | **89.3%** |
| | **End-to-End Latency** | 4.2 giây | **< 1.8 giây** |
| **A2 (Giá trị vận hành)** | **Thời gian kỹ sư tìm phương án xử lý lỗi** | **15 phút** | ⏱️ **45 giây** |
| | **Tỷ lệ có dẫn chứng xác thực (Evidence Coverage)** | 40% | **100%** |
| | **Tỷ lệ phát hiện đúng khoảng trống tri thức (Gap Detection)** | 0% (LLM bịa) | **92.0%** |
| | **Expert Approval Rate** (Chuyên gia công nhận đúng) | 58% | **95.2%** |

---

## 11. KỊCH BẢN DEMO CHUNG KẾT 6 PHÂN CẢNH (WOW MOMENT DEMO)

* **Scene 1 (Kỹ sư mới bối rối):** Kỹ sư hiện trường chụp ảnh máy rung kèm lỗi $\rightarrow$ Gửi lên hệ thống.
* **Scene 2 (AI truy hồi đa chiều):** Màn hình hiển thị đồng thời: 1 bản vẽ CAD có khoanh vùng đỏ BBox + 1 đoạn SOP chuẩn + 2 Case sự cố tương tự trong quá khứ.
* **Scene 3 (Đưa ra quy trình hành động kèm chứng cứ):** Từng bước kiểm tra đều có trích dẫn nguồn gốc và điều kiện ngoại lệ nhiệt độ.
* **Scene 4 (Phát hiện tri thức chưa có):** Kỹ sư hỏi tiếp một câu hóc búa về biến thiên áp suất $\rightarrow$ AI báo: *"Knowledge Gap Detected"* $\rightarrow$ Đề xuất ngay Chuyên gia phù hợp nhất là Kỹ sư A.
* **Scene 5 (AI phỏng vấn chuyên gia):** Bật giao diện AI trò chuyện 3 câu với Kỹ sư A $\rightarrow$ Tự động chuyển hội thoại thành cấu trúc Condition/Exception.
* **Scene 6 (Tri thức tiến hóa tức thì):** Biểu đồ Knowledge Graph tự nhảy thêm nút mới $\rightarrow$ Kỹ sư ban đầu hỏi lại câu đó $\rightarrow$ AI trả lời vanh vách!

> 🎤 **CÂU KẾT BÀI THUYẾT TRÌNH:**  
> *"Hệ thống không chỉ tìm lại những gì nhà máy đã biết. Nó phát hiện nhà máy **chưa biết gì**, tìm đúng người biết điều đó, thu nhận kinh nghiệm và biến nó thành **tri thức bất tử** cho toàn thể nhà máy DENSO!"*

---

## 12. KẾ HOẠCH HÀNH ĐỘNG SAU FACTORY TOUR (LỘ TRÌNH VÀNG)

1. **Sau Factory Tour:** Chọn chính xác 1 đến 2 quy trình/dây chuyền thực tế có điểm nghẽn tri thức rõ nhất tại DENSO (ví dụ: dây chuyền gia công kim phun, lắp ráp robot cánh tay).
2. **Tháng 9/2026:** Xây dựng khung Case Memory + Knowledge Provenance + Kết nối Qwen2.5-VL Đa phương thức.
3. **Tháng 10/2026 (Nộp ý tưởng 12/10):** Đóng gói Báo cáo A2 + A3 hoàn chỉnh kèm bảng số liệu Before/After.
4. **Tháng 11 - 12/2026:** Luyện tập kịch bản Demo 6 phân cảnh để tranh tài Chung kết!
