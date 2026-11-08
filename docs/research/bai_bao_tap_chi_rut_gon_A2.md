# BẢO TOÀN CẤU TRÚC TÀI LIỆU TRONG HỆ THỐNG RAG CHO HỎI ĐÁP HỢP ĐỒNG VÀ TÀI LIỆU KỸ THUẬT: GIẢI PHÁP BIỂU DIỄN BẢNG BIỂU DẠNG MARKDOWN CHO MÔ HÌNH THUẦN VĂN BẢN VÀ THỊ GIÁC

*PRESERVING DOCUMENT STRUCTURE IN RAG FOR CONTRACTS AND TECHNICAL DOCUMENTS: A STRUCTURED MARKDOWN TABLE REPRESENTATION FOR NON-VISION AND VISION LANGUAGE MODELS*

Báo cáo nghiên cứu ứng dụng – Dự án Contract_DL
Thực nghiệm trên tài liệu kỹ thuật công nghiệp – Cập nhật tháng 10 năm 2026

---
> **Tóm tắt:** Trong các hệ thống hỏi đáp dựa trên tài liệu (RAG), việc xử lý các tài liệu kỹ thuật và hợp đồng có cấu trúc phức tạp (gồm các bảng biểu thông số nhiều tầng, phân cấp đề mục sâu và bố cục đa cột) thường gặp nhiều khó khăn. Nếu sử dụng cách tiếp cận cắt đoạn văn bản thông thường (text chunking), cấu trúc bảng biểu bị dàn phẳng thành các dòng chữ rời rạc, khiến mô hình ngôn ngữ dễ nhầm lẫn các dòng dữ liệu giữa các bảng khác nhau. Mặt khác, nếu gửi trực tiếp ảnh chụp trang tài liệu cho mô hình ngôn ngữ thị giác (VLM), kích thước ngữ cảnh sẽ tăng cao do lượng token thị giác lớn, làm tăng thời gian suy luận trên các máy chủ thử nghiệm và không thể áp dụng cho các mô hình ngôn ngữ thuần văn bản.
Trong nghiên cứu ứng dụng này, nhóm chúng em đề xuất một giải pháp tiền xử lý và đóng gói ngữ cảnh nhằm bảo toàn cấu trúc tài liệu. Quy trình gồm hai bước: (1) Bước A3 sử dụng công cụ phân tích bố cục và nhận diện bảng Surya để bóc tách cấu trúc lưới của bảng, đồng thời lưu trữ cây đề mục và luồng đọc văn bản trong đồ thị tri thức; (2) Bước A2 tổ chức lại các đoạn thông tin thành các nhóm nguồn (Source Pods), trong đó cấu trúc bảng biểu được tái hiện hoàn chỉnh dưới dạng văn bản có cấu trúc: bảng biểu được chuyển sang ma trận Markdown (giữ nguyên hàng, cột, ô gộp), còn hình ảnh và sơ đồ kỹ thuật được chuyển ngữ thành văn bản mô tả (gồm nhãn chữ/số OCR bên trong ảnh, chú thích caption và tóm tắt thành phần liên kết). Cách biểu diễn này cho phép các mô hình ngôn ngữ thông thường — kể cả các mô hình thuần văn bản không có bộ mã hóa thị giác — đều có thể đọc hiểu được cấu trúc bảng và vị trí đề mục mà không cần nạp ảnh trang.
Kết quả thử nghiệm trên tài liệu kỹ thuật của hệ thống robot công nghiệp hai cánh tay cho thấy: cách tổ chức bảng Markdown giúp giảm lượng token đầu vào xuống khoảng 6.100 token, rút ngắn thời gian phản hồi API từ trên 200 giây ở các lần thử nghiệm trước xuống còn 55,98 – 82,20 giây trên môi trường chạy thực tế. Đồng thời, mô hình ngôn ngữ phân biệt chính xác thông số đối kháng giữa hai bảng kỹ thuật tương đồng (nhận diện đúng tải nâng 8 kg của dòng robot HSR và 5 kg của dòng robot HS-A1 thay vì gộp chung như khi dùng dữ liệu thô). Giải pháp mang lại tính thực tiễn tốt cho các ứng dụng hỏi đáp tài liệu kỹ thuật trên hạ tầng máy chủ vừa và nhỏ.
>
> **Từ khóa:** Hỏi đáp tài liệu (RAG), Cấu trúc bảng biểu, Bảng Markdown, Đồ thị tri thức, Mô hình thuần văn bản, Tài liệu kỹ thuật.


## 1. ĐẶT VẤN ĐỀ VÀ MỤC TIÊU NGHIÊN CỨU
Trong quá trình xây dựng hệ thống hỏi đáp và truy xuất thông tin cho các tài liệu hợp đồng và tài liệu kỹ thuật công nghiệp (hệ thống Contract_DL), nhóm nghiên cứu nhận thấy việc xử lý các tài liệu dạng PDF có bố cục phức tạp gặp phải thách thức lớn về cấu trúc trình bày.
Các tài liệu kỹ thuật và hợp đồng thường không phải là văn bản xuôi thuần túy. Chúng chứa đựng nhiều thành phần đa dạng: hệ thống đề mục phân cấp nhiều tầng (chương, điều khoản, mục nhỏ), các khối bảng biểu thông số kỹ thuật có nhiều hàng và cột (thậm chí có các ô gộp hàng hoặc gộp cột), cùng với các ghi chú và hình vẽ minh họa đặt xen kẽ giữa các cột chữ.
Khi áp dụng kiến trúc Truy xuất Tăng cường Sinh (RAG) [1] thông thường vào bài toán này, nhóm gặp phải hai vấn đề thực tế:
1) Nếu dùng phương pháp cắt đoạn văn bản phẳng (chunking theo độ dài ký tự hoặc số dòng): Bảng biểu bị chuyển thành một chuỗi chữ dàn ngang hoặc các dòng rời rạc. Khi đó, sự liên kết giữa tiêu đề cột và giá trị từng hàng bị mất đi. Đồng thời, các đoạn thông số nằm sâu trong bảng bị tách rời khỏi tên đề mục cha, dẫn đến việc mô hình ngôn ngữ không rõ con số đó áp dụng cho đối tượng nào.
2) Nếu dùng phương pháp gửi ảnh nguyên trang cho các mô hình ngôn ngữ có thị giác (Vision-Language Models - VLM) [3, 4]: Mỗi ảnh trang tài liệu chiếm từ 1.000 đến hơn 1.500 token thị giác. Khi câu hỏi cần tham khảo nhiều bảng hoặc nhiều trang khác nhau, tổng lượng token ngữ cảnh tăng rất nhanh, dẫn đến thời gian xử lý qua mạng và suy luận trên máy chủ thử nghiệm kéo dài (có trường hợp vượt quá 200 giây). Bên cạnh đó, cách làm này giới hạn hệ thống chỉ chạy được với các mô hình hỗ trợ thị giác; các mô hình ngôn ngữ mã nguồn mở thuần văn bản thông thường (chỉ nhận đầu vào là text) sẽ không thể sử dụng được.
Mục tiêu nghiên cứu cụ thể của nhóm chúng em là: Thiết kế một giải pháp tiền xử lý và đóng gói dữ liệu phù hợp, sao cho cấu trúc của bảng biểu và cây đề mục trong tài liệu được giữ lại dưới dạng văn bản có cấu trúc (bảng Markdown). Nhờ đó, bất kỳ mô hình ngôn ngữ nào — kể cả các mô hình thuần văn bản không có khả năng đọc ảnh — cũng có thể hiểu đúng mối liên hệ giữa các hàng, cột và phân biệt chính xác thông số kỹ thuật, đồng thời giảm bớt lượng token tiêu thụ và rút ngắn thời gian phản hồi.
Bài báo trình bày các kết quả thử nghiệm cụ thể sau:
• Trình bày quy trình bóc tách tài liệu A3 bằng cách kết hợp nhận diện bố cục/bảng biểu Surya, xây dựng quan hệ sở hữu đề mục (CONTAINS) và thứ tự đọc (NEXT) trong đồ thị tri thức Neo4j.
• Xây dựng cơ chế đóng gói ngữ cảnh Source Pods tại tầng A2: tự động chuyển đổi bảng trích xuất thành định dạng bảng Markdown có cấu trúc kèm theo đường dẫn đề mục phân cấp, phục vụ cho cả mô hình thuần văn bản lẫn mô hình thị giác.
• Đo đạc thực tế trên hệ thống chạy thử với 4 câu hỏi kỹ thuật: ghi nhận lượng token ngữ cảnh giảm xuống mức ~6.100 token, thời gian phản hồi qua API giảm xuống còn 55,98 – 82,20 giây, và mô hình phân biệt đúng thông số giữa hai bảng có cùng tên thuộc tính.

## 2. CÁC THÁCH THỨC VỀ CẤU TRÚC TÀI LIỆU TRONG THỰC TẾ
Qua quá trình thử nghiệm trên tập tài liệu của dự án, nhóm ghi nhận ba khó khăn chính liên quan đến cấu trúc tài liệu:

### 2.1. Mất liên kết giữa thông số và đề mục cha
Tài liệu kỹ thuật thường có cấu trúc cây: Tài liệu → Mục lớn → Tiểu mục → Bảng thông số. Ví dụ trong tài liệu robot công nghiệp của nhóm thử nghiệm: Mục 4.1 nói về dòng robot HSR có bảng thông số ghi 'Tải nâng tối đa: 8 kg'; trong khi Mục 4.2 nói về dòng robot HS-A1 có bảng thông số ghi 'Tải nâng tối đa: 5 kg'.
Nếu công cụ trích xuất chỉ cắt đoạn văn bản theo kích thước cố định, dòng 'Tải nâng tối đa: 5 kg' có thể bị tách riêng thành một đoạn không có tiêu đề 'HS-A1'. Khi người dùng hỏi so sánh tải nâng của hai dòng robot, mô hình ngôn ngữ không đủ thông tin để biết con số 5 kg hay 8 kg thuộc về dòng máy nào.

### 2.2. Vỡ cấu trúc ma trận hàng và cột của bảng biểu
Bảng biểu kỹ thuật chứa thông tin theo dạng ma trận hai chiều. Hàng đầu tiên thường là tiêu đề các cột (tên thông số, đơn vị, điều kiện), các hàng tiếp theo là giá trị cụ thể. Một số ô còn gộp nhiều cột hoặc nhiều hàng.
Nếu chuyển bảng thành một đoạn văn thô bằng cách nối các từ lại với nhau, mô hình ngôn ngữ chỉ thấy một chuỗi số liệu liên tục mà không phân biệt được số nào nằm ở cột nào. Điều này dễ dẫn đến việc mô hình trả lời sai hoặc gộp nhầm các số liệu với nhau.

### 2.3. Bố cục nhiều cột và chữ xen trong hình vẽ
Một số trang tài liệu có bố cục 2 cột hoặc có các hộp ghi chú đặt cạnh hình minh họa. Nếu quét OCR theo thứ tự từ trái sang phải trên toàn trang, các dòng chữ của cột bên trái có thể bị đọc nối tiếp ngay với cột bên phải nếu chúng có cùng độ cao tọa độ y. Việc này làm câu văn bị ngắt quãng và làm mô hình khó hiểu đúng nội dung nguyên bản.

## 3. QUY TRÌNH BÓC TÁCH VÀ LƯU TRỮ CẤU TRÚC TÀI LIỆU (BƯỚC A3)
Để chuẩn bị dữ liệu cho việc hỏi đáp, nhóm xây dựng quy trình tiền xử lý A3 nhằm phát hiện bố cục trang và lưu giữ các mối quan hệ cấu trúc:
1) Phân tích bố cục trang (Layout Analysis): Từng trang PDF được chuyển thành ảnh. Công cụ Surya Layout [12] được sử dụng để phân loại các vùng trên trang thành: tiêu đề (Heading), đoạn văn bản (Text), bảng biểu (Table), và hình ảnh (Figure).
2) Nhận diện bảng biểu (Table Recognition): Với các vùng được xác định là bảng, công cụ Surya Table tiến hành nhận diện lưới tọa độ, xác định các ô (cells), hàng tiêu đề và các vị trí ô gộp (rowspan, colspan). Thông tin này được lưu lại dưới dạng cấu trúc hàng và cột thay vì chỉ lưu chữ thô.
3) Lưu trữ đồ thị phân cấp và luồng đọc: Hệ thống sử dụng Neo4j để lưu các khối nội dung. Mối quan hệ CONTAINS thể hiện cấu trúc sở hữu (Trang chứa Đề mục, Đề mục chứa Bảng biểu). Mối quan hệ NEXT liên kết các đoạn văn bản theo đúng thứ tự đọc từ trên xuống dưới trong cùng một cột, tránh việc ghép lẫn chữ giữa hai cột khác nhau.
3) Xử lý hình ảnh và sơ đồ (Image-to-Text Ingestion): Đối với các khối hình vẽ (Figure), hệ thống cắt ảnh vùng hình, chạy OCR để bóc tách các nhãn chữ/ký hiệu kỹ thuật bên trong ảnh, đồng thời liên kết với chú thích (caption) của hình và lưu lại mô tả các thành phần kết nối chính. Cách làm này giúp chuyển ngữ hình ảnh thành dữ liệu văn bản có cấu trúc ngay từ bước nạp.
4) Lưu trữ đồ thị phân cấp và luồng đọc: Hệ thống sử dụng Neo4j để lưu các khối nội dung. Mối quan hệ CONTAINS thể hiện cấu trúc sở hữu (Trang chứa Đề mục, Đề mục chứa Bảng biểu hoặc Hình ảnh). Mối quan hệ NEXT liên kết các đoạn văn bản theo đúng thứ tự đọc từ trên xuống dưới trong cùng một cột, tránh việc ghép lẫn chữ giữa hai cột khác nhau.
5) Lập chỉ mục tìm kiếm: Các đoạn văn bản, bảng biểu và mô tả hình ảnh được lập chỉ mục trên BM25 (tìm kiếm từ khóa) và mô hình BGE-M3 [9] (tìm kiếm ngữ nghĩa vector). Đối với các vùng hình vẽ, nhóm sử dụng thêm ColPali [4] để tạo vector hình ảnh phục vụ tìm kiếm trực quan.

![Hình 1. Sơ đồ quy trình hệ thống: Tiền xử lý cấu trúc A3 và Truy xuất đóng gói ngữ cảnh A2.](article_figures/01_architecture.png)
*Hình 1. Sơ đồ quy trình hệ thống: Tiền xử lý cấu trúc A3 và Truy xuất đóng gói ngữ cảnh A2.*

![Hình 2. Cây phân cấp đề mục (CONTAINS) và Luồng đọc tuần tự (NEXT) được lưu trong đồ thị tri thức.](article_figures/02_tree_streams.png)
*Hình 2. Cây phân cấp đề mục (CONTAINS) và Luồng đọc tuần tự (NEXT) được lưu trong đồ thị tri thức.*

```text
Thuật toán 1: Quy trình bóc tách và lưu trữ cấu trúc tài liệu (Bước A3)
-----------------------------------------------------------------------
Đầu vào: Tài liệu PDF kỹ thuật D
Đầu ra: Đồ thị tri thức G (Neo4j), Chỉ mục vector I_vec (Qdrant), Chỉ mục từ khóa I_bm25
1:  Khởi tạo đỉnh tài liệu v_doc trong G
2:  Tách D thành danh sách các ảnh trang Pages
3:  Với mỗi trang p trong Pages:
4:      Tạo đỉnh v_p; thêm quan hệ (v_doc, CONTAINS, v_p)
5:      Blocks <- Nhận diện bố cục bằng SuryaLayout(p)
6:      Với mỗi block trong Blocks:
7:          Nếu block là Bảng biểu (Table):
8:              grid, cells, spans <- Nhận diện cấu trúc ô bằng SuryaTable(block)
9:              Tạo đỉnh v_tab lưu cấu trúc lưới; thêm (v_p, CONTAINS, v_tab)
10:         Nếu block là Hình vẽ (Figure):
11:             Cắt ảnh vùng hình; tính vector ColPali
12:             Trích xuất chữ/nhãn trong hình bằng OCR và ghép chú thích (Caption)
13:             Tạo tóm tắt thành phần và mối liên kết trong sơ đồ
14:             Tạo đỉnh v_fig lưu ảnh, nhãn chữ, chú thích; thêm (v_p, CONTAINS, v_fig)
13:         Nếu block là Văn bản thường:
14:             Đọc chữ bằng SuryaOCR; tạo đỉnh v_txt; thêm (v_p, CONTAINS, v_txt)
15:     Xây dựng quan hệ luồng đọc NEXT nối các khối văn bản kế tiếp nhau
16:     Tạo vector văn bản bằng BGE-M3 cho các đỉnh và lưu vào I_vec
17:     Lập chỉ mục tìm kiếm từ khóa BM25 cho toàn văn
18: Trả về đồ thị G và các chỉ mục tìm kiếm
```

## 4. ĐÓNG GÓI NGỮ CẢNH DẠNG BẢNG MARKDOWN (BƯỚC A2)
Khi người dùng gửi câu hỏi, hệ thống thực hiện tìm kiếm các đoạn thông tin liên quan qua BM25, vector BGE-M3 và ColPali, kết hợp sắp xếp lại bằng thuật toán RRF (Reciprocal Rank Fusion) và mô hình BGE-Reranker-Large. Tuy nhiên, khâu quan trọng nhất để giúp mô hình trả lời chính xác chính là cách tổ chức lại các dữ liệu tìm được trước khi đưa vào prompt.

### 4.1. Chuyển đổi bảng biểu sang định dạng Markdown
Thay vì gửi dữ liệu JSON dạng cây phức tạp hoặc chuỗi văn bản thô, hàm render_source_pods của hệ thống thực hiện chuyển đổi bảng sang định dạng Markdown chuẩn:
• Dòng tiêu đề cột được đặt ở hàng đầu tiên, phân cách bởi dấu gạch đứng (| Cột 1 | Cột 2 |) và thanh phân tách (|---|---|).
• Các hàng nội dung được ghi lần lượt, mỗi giá trị tương ứng đúng vị trí cột đã xác định trong bước A3.
• Với các ô gộp nhiều cột hoặc nhiều hàng, giá trị được điền lặp lại vào các ô tương ứng để bảo đảm mỗi hàng đều có đủ số lượng cột, giúp mô hình ngôn ngữ không bị lệch cột khi đọc tuần tự.

### 4.2. Gắn kèm đường dẫn phân cấp (Breadcrumb Heading) và mã bằng chứng
Mỗi nhóm thông tin được đóng gói thành một 'Source Pod' độc lập, bao gồm:
1) Đường dẫn đề mục: Ví dụ '[Tài liệu HSR > Thông số kỹ thuật > Tải nâng và Tốc độ]', giúp mô hình nhận biết ngay phạm vi đối tượng của đoạn văn.
2) Mã bằng chứng: Mỗi đoạn hoặc bảng được gắn mã trích dẫn (ví dụ: [E1], [E2]) để mô hình có thể trích dẫn nguồn khi trả lời.
3) Nội dung: Là đoạn văn bản đã giữ đúng thứ tự đọc hoặc bảng biểu đã định dạng Markdown.

### 4.3. Biến đổi hình ảnh thành văn bản có cấu trúc (Image-to-Text) cho mô hình thuần văn bản
Đối với các mô hình ngôn ngữ thuần văn bản (như các mô hình Llama-Text, Qwen-Text thông thường), mô hình hoàn toàn không thể nhìn thấy pixel hình ảnh. Để các mô hình này có thể hiểu và trả lời được các câu hỏi liên quan đến hình vẽ hoặc sơ đồ kỹ thuật, nguyên lý cốt lõi là: Ở khâu tiền xử lý (Ingestion), hệ thống thực hiện chuyển đổi toàn bộ nội dung trong ảnh thành văn bản có cấu trúc. Một khối nguồn (Source Pod) dành cho hình ảnh sẽ bao gồm ba thành phần dữ liệu rõ ràng:
1) Chữ và số trong ảnh: Toàn bộ nhãn cổng (Port), mã hiệu linh kiện, thông số điện áp/tải trọng được trích xuất bằng OCR vùng ảnh.
2) Tiêu đề và chú thích (Caption): Đoạn văn bản mô tả mục đích của hình được liên kết từ trang tài liệu.
3) Tóm tắt thành phần và liên kết: Mô tả các khối chính và luồng kết nối trong sơ đồ (ví dụ: 'Bộ điều khiển nối với Driver qua cổng EtherCAT').
Cách tiếp cận này mang lại ba ưu điểm lớn trong thực tế: Cực kỳ tiết kiệm token (chỉ vài chục text tokens thay vì hàng nghìn visual tokens), bất kỳ mô hình ngôn ngữ nào cũng đọc hiểu được, và không đòi hỏi máy chủ phải trang bị GPU thị giác đắt tiền lúc trả lời câu hỏi.

### 4.4. Cơ chế thích ứng linh hoạt giữa mô hình thuần văn bản và mô hình thị giác
Nhờ việc chuẩn hóa cả bảng biểu (sang Markdown) và hình ảnh (sang văn bản có cấu trúc), hệ thống đạt được tính tương thích linh hoạt:
• Đối với mô hình thuần văn bản: Nhận toàn bộ ngữ cảnh dưới dạng các Source Pods văn bản (bảng Markdown + mô tả cấu trúc hình ảnh). Mô hình có đầy đủ dữ kiện để suy luận mà không cần xử lý ảnh.
• Đối với mô hình có thị giác: Khi câu hỏi thực sự đòi hỏi kiểm tra hình học hoặc sơ đồ chi tiết, hệ thống có thể gửi kèm thêm ảnh cắt cục bộ (crop image). Lúc này, phần văn bản mô tả đóng vai trò định hướng giúp mô hình thị giác trả lời nhanh và không bị nhìn nhầm chi tiết.

![Hình 3. Sơ đồ xử lý tại tầng A2: Tìm kiếm, mở rộng ngữ cảnh, đóng gói Source Pods Markdown và sinh câu trả lời.](article_figures/09_current_qa_flow.png)
*Hình 3. Sơ đồ xử lý tại tầng A2: Tìm kiếm, mở rộng ngữ cảnh, đóng gói Source Pods Markdown và sinh câu trả lời.*

```text
Thuật toán 2: Truy xuất và đóng gói ngữ cảnh dạng Source Pods (Bước A2)
-----------------------------------------------------------------------
Đầu vào: Câu hỏi q, Đồ thị tri thức G, Các chỉ mục tìm kiếm, Giới hạn token B_ctx = 16384
Đầu ra: Câu trả lời kèm mã trích dẫn bằng chứng
1:  Tách câu hỏi q thành các ý hỏi con SubQueries
2:  Tìm kiếm ứng viên bằng BM25, BGE-M3 và ColPali
3:  Dung hợp kết quả bằng thuật toán RRF và chọn 20 ứng viên hàng đầu
4:  Xếp hạng lại bằng BGE-Reranker-Large kèm lọc trùng lặp hạt nhân
5:  Từ các hạt nhân đã chọn, mở rộng ngữ cảnh lân cận trên đồ thị G (quan hệ CONTAINS, NEXT)
6:  Gom nhóm các đoạn tìm được theo phạm vi tài liệu và đề mục (Source Pods)
7:  Với mỗi nhóm thông tin (Pod):
8:      Nếu nội dung là Bảng biểu: Chuyển đổi cấu trúc ô sang bảng Markdown chuẩn
9:      Gắn kèm đường dẫn đề mục cha và mã định danh bằng chứng [E_i]
10: Nối các Pods thành chuỗi văn bản ngữ cảnh PromptText
11: Kiểm tra dung lượng token trước khi gửi (Preflight check)
12: Gửi PromptText cho mô hình ngôn ngữ (LLM) để sinh câu trả lời
13: Trả về câu trả lời và mã nguồn đối chiếu
```

## 5. KẾT QUẢ THỬ NGHIỆM THỰC TẾ

### 5.1. Môi trường thử nghiệm
Hệ thống được thử nghiệm trên môi trường máy chủ của dự án Contract_DL:
• Cơ sở dữ liệu: Neo4j 5.x (lưu đồ thị) và Qdrant 1.9 (lưu vector) chạy trong Docker container.
• Mô hình ngôn ngữ: Mô hình Qwen2.5-VL-7B chạy thử nghiệm trên máy chủ GPU thông qua ngrok tunnel với giới hạn ngữ cảnh 16.384 token.
• Tài liệu thử nghiệm: Cẩm nang hướng dẫn kỹ thuật của hệ thống robot công nghiệp hai cánh tay (khoảng hơn 80 trang), chứa nhiều bảng thông số kích thước, tải nâng, điều kiện môi trường và các điều khoản hướng dẫn an toàn.

*Bảng 1. Cấu hình các công cụ và mô hình trong môi trường thử nghiệm.*


### 5.2. Kết quả đo đạc thời gian và lượng token
Nhóm tiến hành đo thời gian xử lý thực tế qua API (/api/newidea/jobs/) trên 4 câu hỏi mẫu đại diện cho các nội dung kỹ thuật khác nhau:

*Bảng 2. Kết quả đo đạc thực tế qua API.*


![Hình 4. Biểu đồ thời gian đáp ứng qua 4 câu hỏi và lần chạy lại câu hỏi số 2 với bảng Markdown.](article_figures/10_current_qa_times.png)
*Hình 4. Biểu đồ thời gian đáp ứng qua 4 câu hỏi và lần chạy lại câu hỏi số 2 với bảng Markdown.*

### 5.3. Nhận xét về việc phân biệt thông số kỹ thuật đối kháng
Câu hỏi số 2 là trường hợp thử nghiệm rõ nét nhất cho thấy sự ảnh hưởng của cách trình bày bảng biểu đến câu trả lời của mô hình ngôn ngữ:

![Hình 5. So sánh kết quả: Dữ liệu thô gây nhầm lẫn thông số giữa hai dòng robot (trái) và Bảng Markdown giúp phân biệt chính xác thông số (phải).](article_figures/14_duplicate_answer_example.png)
*Hình 5. So sánh kết quả: Dữ liệu thô gây nhầm lẫn thông số giữa hai dòng robot (trái) và Bảng Markdown giúp phân biệt chính xác thông số (phải).*
Trong tài liệu, hai dòng robot HSR và HS-A1 có hai bảng thông số độc lập ở các trang khác nhau. Cả hai bảng đều có dòng chữ 'Maximum lifting load'. Bảng của HSR ghi 8 kg, bảng của HS-A1 ghi 5 kg.
• Khi gửi dữ liệu dạng JSON thô (lượt 2a): Mặc dù trong dữ liệu có cả hai số 8 kg và 5 kg, nhưng do thiếu cấu trúc dòng cột trực quan, mô hình ngôn ngữ bị nhầm lẫn và trả lời rằng cả hai dòng robot đều có tải nâng tối đa là 8 kg.
• Khi chuyển bảng sang định dạng Markdown chuẩn (lượt 2b): Các cột và hàng được phân tách rõ ràng, kèm theo đường dẫn đề mục trên đầu mỗi bảng. Mô hình đã nhận diện chính xác: dòng HSR có tải nâng 8 kg, còn dòng HS-A1 có tải nâng 5 kg. Đồng thời, mô hình không bị lẫn các thông số nhiễu từ các tài liệu khác vào câu trả lời.
Kết quả thử nghiệm này cho thấy: Việc tổ chức lại bảng biểu thành dạng Markdown có cấu trúc rõ ràng đã giúp cải thiện đáng kể khả năng đọc hiểu của mô hình ngôn ngữ trên các bảng kỹ thuật có thuộc tính tương đồng.

## 6. THẢO LUẬN VÀ MỘT SỐ HẠN CHẾ

### 6.1. Ưu điểm của biểu diễn bảng Markdown trong ứng dụng thực tế
Từ kết quả thử nghiệm, nhóm rút ra một số nhận xét thực tế:
1) Tiết kiệm tài nguyên: Một bảng Markdown thường chỉ chiếm vài trăm text tokens, ít hơn nhiều so với việc gửi ảnh trang tài liệu (thường tốn hơn 1.000 visual tokens). Điều này giúp giảm chi phí tính toán và giúp hệ thống hoạt động ổn định hơn trên các máy chủ có cấu hình GPU vừa phải.
2) Tính linh hoạt: Bảng Markdown là văn bản thông thường nên có thể sử dụng được cho hầu hết các mô hình ngôn ngữ mã nguồn mở phổ biến (như các mô hình kích thước 7B/8B), không bắt buộc hệ thống phải triển khai các mô hình có thị giác đắt tiền nếu tài liệu chủ yếu là bảng thông số.
3) Cân bằng thời gian: Việc xử lý cấu trúc bảng trong bước tiền xử lý A3 có thể tốn thời gian khi nạp tài liệu lần đầu, nhưng tài liệu kỹ thuật thường chỉ nạp một lần và phục vụ nhiều lượt hỏi đáp sau đó. Thời gian phản hồi trong lượt hỏi đáp (A2) được rút ngắn là yếu tố quan trọng hơn.

### 6.2. Các hạn chế còn tồn tại
Nghiên cứu ứng dụng của nhóm vẫn còn một số điểm hạn chế cần hoàn thiện thêm:
• Phụ thuộc vào chất lượng nhận diện của Surya: Nếu bảng gốc quá mờ hoặc có các đường kẻ đứt đoạn phức tạp, công cụ nhận diện có thể xác định sai số cột hoặc gộp nhầm ô, dẫn đến bảng Markdown tạo ra chưa hoàn toàn chuẩn xác.
• Chú thích điều kiện đo lường: Mô hình trả lời đúng con số 8 kg và 5 kg, nhưng đối với các chú thích kỹ thuật đi kèm (ví dụ: chú thích về điều kiện nhiệt độ môi trường ổn định khi đo độ lặp vị trí), mô hình đôi khi vẫn chưa giải thích cặn kẽ trong câu trả lời.

## 7. KẾT LUẬN
Bài báo đã trình bày giải pháp tiền xử lý và đóng gói ngữ cảnh nhằm bảo toàn cấu trúc bảng biểu trong hệ thống RAG phục vụ hỏi đáp hợp đồng và tài liệu kỹ thuật. Bằng cách kết hợp nhận diện bố cục Surya ở bước A3 và chuyển đổi bảng biểu sang dạng Markdown có cấu trúc kèm đường dẫn đề mục ở bước A2, hệ thống giúp các mô hình ngôn ngữ vừa và nhỏ — kể cả các mô hình thuần văn bản — có thể đọc hiểu đúng các thông số dạng bảng mà không cần xử lý ảnh trang.
Kết quả đo đạc thực tế trên cẩm nang kỹ thuật robot công nghiệp cho thấy giải pháp giúp giảm lượng token đầu vào xuống mức ~6.100 token, rút ngắn thời gian phản hồi qua API xuống còn 55,98 – 82,20 giây, và khắc phục được hiện tượng nhầm lẫn số liệu giữa hai bảng đối kháng có cùng tên thuộc tính. Trong thời gian tới, nhóm sẽ tiếp tục cải tiến thuật toán ghép ô đối với các bảng không có đường kẻ rõ ràng và thử nghiệm thêm trên các tài liệu hợp đồng kinh tế có biểu mẫu phức tạp hơn.

## TÀI LIỆU THAM KHẢO
[1] P. Lewis, E. Perez, A. Piktus, et al., "Retrieval-augmented generation for knowledge-intensive NLP tasks," in Advances in Neural Information Processing Systems (NeurIPS), vol. 33, pp. 9459–9474, 2020.

[2] D. Edge, H. Trinh, N. Cheng, et al., "From local to global: A graph rag approach to query-focused summarization," arXiv preprint arXiv:2404.16130, 2024.

[3] M. Mathew, D. Karatzas, and C. V. Jawahar, "DocVQA: A dataset for VQA on document images," in Proceedings of the IEEE/CVF Winter Conference on Applications of Computer Vision (WACV), pp. 2200–2209, 2021.

[4] M. Faysse, H. Touvron, et al., "ColPali: Efficient document retrieval with vision language models," arXiv preprint arXiv:2407.01449, 2024.

[5] Qwen Team, "Qwen2.5-VL technical report: Enhancing vision-language capabilities for complex document reasoning," Alibaba Group, Tech. Rep., 2024.

[6] J. Wang, X. Meng, et al., "BGE-M3: A versatile multi-lingual, multi-functionality, multi-granularity dense retrieval model," BAAI Tech. Rep., 2024.

[7] Y. Huang, T. Lv, et al., "LayoutLMv3: Pre-training for document AI with unified text and image masking," in Proceedings of the 30th ACM International Conference on Multimedia (MM), pp. 4083–4091, 2022.

[8] V. Blecher, et al., "Surya: Accurate multilingual document layout analysis and text detection," GitHub Repository, 2024.

[9] V. Zaratiana, et al., "GLiNER: Generalist model for named entity recognition using bidirectional transformers," in Proc. NAACL, 2024.

[10] G. V. Cormack, C. L. Clarke, and S. Büttcher, "Reciprocal rank fusion outperforms Condorcet and individual machine learning methods," in Proc. ACM SIGIR, pp. 758–759, 2009.

[11] A. Vaswani, N. Shazeer, N. Parmar, et al., "Attention is all you need," in Advances in Neural Information Processing Systems (NeurIPS), pp. 5998–6008, 2017.

[12] S. Robertson and H. Zaragoza, "The probabilistic relevance framework: BM25 and beyond," Foundations and Trends in Information Retrieval, vol. 3, no. 4, pp. 333–389, 2009.

[13] B. Wang, et al., "Evaluating retrieval quality in RAG systems: A comprehensive benchmark," ACM Computing Surveys, 2024.

[14] Y. Gao, et al., "Modular RAG: Transforming RAG architectures from linear to adaptive paradigms," IEEE Intelligent Systems, 2024.

[15] C. Clark and M. Gardner, "Simple and effective multi-paragraph reading comprehension," in Proc. ACL, pp. 845–855, 2018.

[16] Mã nguồn dự án Contract_DL, Hệ thống truy xuất tài liệu hợp đồng và đặc tả kỹ thuật, Đối chiếu thực nghiệm ngày 22 tháng 10 năm 2026.

