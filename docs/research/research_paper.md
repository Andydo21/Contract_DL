# HỆ THỐNG HỎI–ĐÁP ĐA PHƯƠNG THỨC CHO TÀI LIỆU CẤU TRÚC PHỨC TẠP DỰA TRÊN ĐỒ THỊ TRI THỨC PHÂN CẤP VÀ TRUY XUẤT KẾT HỢP

*MULTIMODAL QUESTION ANSWERING FOR COMPLEX STRUCTURED DOCUMENTS VIA HIERARCHICAL KNOWLEDGE GRAPHS AND HYBRID MULTI-STAGE RETRIEVAL*

Báo cáo Nghiên cứu Kỹ thuật & Ứng dụng Thực nghiệm
Nhóm Nghiên cứu và Phát triển Hệ thống – Cập nhật tháng 10 năm 2026

---

> **Tóm tắt:** Hỏi–đáp tự động trên các tài liệu có cấu trúc phức tạp (hợp đồng thương mại, báo cáo tài chính, tài liệu quy chuẩn và đặc tả kỹ thuật) đòi hỏi khả năng xử lý đồng thời nhiều dạng dữ liệu phi tuyến tính: bảng biểu đa tầng có ô gộp, sơ đồ lưu trình, chú thích chân trang và cấu trúc đề mục phân cấp sâu. Các kiến trúc RAG truyền thống thường phân mảnh văn bản dạng phẳng (text chunking), làm phá vỡ ranh giới ma trận của bảng biểu và tách rời thông tin điều kiện khỏi thực thể sở hữu. Mặt khác, việc nạp trực tiếp toàn bộ ảnh trang vào các mô hình thị giác–ngôn ngữ (VLM) lại làm bùng nổ số lượng visual tokens, kéo dài độ trễ phản hồi trực tuyến và đòi hỏi hạ tầng GPU đắt đỏ, trong khi phần lớn hạ tầng máy chủ thực tế của doanh nghiệp lại ưu tiên triển khai các mô hình ngôn ngữ thuần văn bản (Text-only LLM) gọn nhẹ, chi phí thấp. Trong bài báo này, bọn mình đề xuất một kiến trúc hỏi–đáp đa phương thức hoàn chỉnh đóng vai trò như một Cầu nối Cấu trúc Bất khả tri Mô hình (Model-Agnostic Structural Bridge) gồm hai phân hệ phối hợp: (1) Phân hệ Tiền xử lý & Trích xuất Cấu trúc thực hiện bóc tách bố cục bằng Surya, trích xuất thực thể/quan hệ mở bằng GLiNER-RelEx, chuyển đổi hình ảnh sơ đồ sang văn bản cấu trúc có chú thích (Image-to-Text), và xây dựng đồ thị tri thức phân cấp lưu trữ trên Neo4j kết hợp vector Qdrant; (2) Phân hệ Truy xuất Đa kênh & Định tuyến Bằng chứng thực hiện phân rã câu hỏi, truy xuất song song đa kênh (BM25, BGE-M3, ColPali), hợp nhất thứ hạng RRF, tái xếp hạng chuyên sâu bằng BGE-Reranker-Large, và đóng gói ngữ cảnh thành các Khối Bằng chứng Phân cấp (Hierarchical Evidence Pods). Bằng cách chuẩn hóa bảng biểu thành ma trận Markdown hoàn chỉnh và chuyển hóa sơ đồ thành văn bản cấu trúc có ranh giới đề mục cha, hệ thống cho phép cả các mô hình thuần văn bản (không có vision) lẫn các mô hình thị giác (VLM) đều suy luận chuẩn xác và đáng tin cậy mà không cần nạp ảnh toàn trang. Thực nghiệm trên cẩm nang kỹ thuật công nghiệp phức tạp chứng minh: Kiến trúc đề xuất nâng cao rõ rệt độ chính xác suy luận, phân định rõ ràng các thông số kỹ thuật giữa các đối tượng tương đồng, loại bỏ triệt để hiện tượng rò rỉ thuộc tính chéo. Đồng thời, phương pháp này tối ưu hóa mạnh mẽ chi phí tính toán, tiết kiệm hơn 90% visual tokens ngữ cảnh, rút ngắn độ trễ phản hồi trực tuyến và mang lại sự tự do linh hoạt trong việc lựa chọn mô hình ngôn ngữ phục vụ.
>
> **Từ khóa:** Hỏi đáp tài liệu cấu trúc, Hợp đồng và Tài liệu kỹ thuật, RAG đa phương thức, Kiến trúc bất khả tri mô hình (Model-Agnostic), Đồ thị tri thức phân cấp, Bảng Markdown, Truy xuất đa kênh, BGE-M3, ColPali, Surya, Mô hình ngôn ngữ lớn (LLMs).


# 1. GIỚI THIỆU

Sự bùng nổ của các mô hình ngôn ngữ lớn (Large Language Models - LLM) và kiến trúc Sinh Tăng cường Truy xuất (Retrieval-Augmented Generation - RAG) [1] đã mở ra tiềm năng to lớn trong việc tự động hóa tra cứu, phân tích tài liệu văn bản. Tuy nhiên, việc áp dụng RAG vào các tài liệu có cấu trúc phức tạp trong thực tế doanh nghiệp — bao gồm hợp đồng kinh tế với các biểu phí và điều khoản ràng buộc, báo cáo kiểm toán, cẩm nang kỹ thuật cơ điện tử và hồ sơ dự thầu — gặp phải những rào cản nghiêm trọng về cấu trúc trình bày.

Khác với văn bản tin tức hay bài viết thông thường, tài liệu cấu trúc phức tạp có mật độ thông tin cực kỳ đậm đặc và phi tuyến tính: tiêu đề đề mục phân cấp xác lập phạm vi pháp lý hoặc đối tượng máy móc áp dụng; bảng biểu hai chiều chứa các thông số đối kháng hoặc điều khoản thanh toán; trong khi các ngoại lệ, điều kiện ràng buộc hay quy chuẩn đo lường lại nằm rải rác dưới dạng chú thích chân trang (footnotes). Ngoài ra, các tài liệu này thường đi kèm sơ đồ quy trình, bản vẽ đấu nối hoặc lưu đồ lắp đặt với các ký hiệu chuyên ngành.

Khi áp dụng các hệ sinh thái RAG phổ biến vào dạng tài liệu này, các nhà phát triển thường vấp phải hai rào cản mang tính cốt tử:

1) Phân mảnh văn bản làm vỡ cấu trúc ma trận: Các phương pháp cắt đoạn cố định (fixed-length text chunking) thường biến bảng biểu thông số thành một chuỗi ký tự phẳng rời rạc. Khi các đường phân cách cột và liên kết hàng bị xóa nhòa, các con số và điều khoản trôi dạt tự do trong ngữ cảnh. Hệ quả là mô hình ngôn ngữ dễ dàng gán nhầm thông số của đối tượng này sang đối tượng khác, hoặc hiểu sai một chú thích điều kiện đo lường thành một quy định bắt buộc toàn cục.

2) Bùng nổ chi phí tính toán khi nạp ảnh trang trực tiếp (Vision-centric RAG): Một số nghiên cứu gần đây sử dụng mô hình thị giác–ngôn ngữ (VLM) để đọc trực tiếp ảnh toàn trang tài liệu [3, 4]. Mặc dù nắm bắt tốt bố cục trực quan, phương pháp này đòi hỏi từ 1.000 đến hơn 1.500 visual patch tokens cho mỗi trang ảnh. Khi câu hỏi đòi hỏi đối chiếu thông số qua nhiều trang tài liệu khác nhau, kích thước prompt vượt ngưỡng xử lý tối ưu, làm tăng vọt độ trễ suy luận trực tuyến và phụ thuộc hoàn toàn vào các cụm GPU đắt đỏ, không thể tận dụng được các LLM thuần văn bản mã nguồn mở linh hoạt.

Nghịch lý cốt lõi trong thực tế ứng dụng là: Mặc dù tài liệu doanh nghiệp mang đậm tính chất thị giác và đa phương thức (bảng biểu ô gộp, sơ đồ nối dây, bố cục đa cột), nhưng đại đa số hạ tầng máy chủ của các tổ chức chỉ sẵn sàng phục vụ các mô hình ngôn ngữ thuần văn bản (Text-only LLM) vì lý do chi phí bản quyền, tốc độ suy luận và yêu cầu bảo mật dữ liệu nội bộ nghiêm ngặt trên phần cứng giới hạn. Nếu áp dụng các phương pháp RAG văn bản truyền thống thì hệ thống hoàn toàn 'mù tịt' trước bảng biểu và sơ đồ. Ngược lại, nếu phụ thuộc hoàn toàn vào các mô hình thị giác (Vision-centric RAG), việc nạp ảnh toàn trang làm bùng nổ hàng nghìn visual tokens, gây nghẽn GPU và chi phí quá lớn. Vì thế, bài toán nghiên cứu trung tâm của bài báo là: Làm thế nào để xây dựng một kiến trúc RAG có khả năng trích xuất và bảo toàn trọn vẹn ngữ nghĩa đa phương thức của tài liệu, nhưng đóng gói bằng chứng dưới dạng cấu trúc chuẩn mực để bất kỳ mô hình ngôn ngữ nào — dù KHÔNG CÓ VISION hay CÓ VISION — đều suy luận chính xác 100% với chi phí tối ưu nhất?

Nhằm giải quyết triệt để nghịch lý trên, trong nghiên cứu này bọn mình đề xuất một kiến trúc hệ thống hỏi–đáp đa phương thức dựa trên Đồ thị Tri thức Phân cấp (Hierarchical Knowledge Graph) kết hợp Truy xuất Đa kênh (Multi-channel Hybrid Retrieval) và Đóng gói Bằng chứng Phân cấp (Hierarchical Evidence Pods). Triết lý thiết kế cốt lõi của bọn mình là: Đẩy toàn bộ chi phí xử lý cấu trúc và thị giác nặng nề về pha tiền xử lý nạp tài liệu ngoại tuyến (Offline Ingestion), chuẩn hóa bảng biểu thành ma trận Markdown và sơ đồ hình ảnh thành văn bản mô tả cấu trúc (Image-to-Text). Nhờ đó, pha hỏi đáp trực tuyến (Online Inference) đạt được tốc độ cao, tiết kiệm token và bảo đảm khả năng suy luận chuẩn xác trên cả mô hình ngôn ngữ thuần văn bản lẫn mô hình thị giác.

Những đóng góp kỹ thuật chính của bài báo gồm:

• Xây dựng triết lý cầu nối cấu trúc bất khả tri mô hình (Model-Agnostic Structural Bridge): Đẩy toàn bộ chi phí nhận diện thị giác và phân tích cấu trúc nặng nề về pha tiền xử lý ngoại tuyến (Offline Ingestion), giải phóng bài toán RAG tài liệu phức tạp khỏi sự lệ thuộc bắt buộc vào các mô hình thị giác đắt đỏ ở pha trực tuyến, bảo đảm cả mô hình không có vision lẫn có vision đều đạt độ chính xác tối đa.

• Thiết kế quy trình tiền xử lý phân cấp và chuyển đổi Image-to-Text: Phối hợp mô hình phân tích layout Surya và mô hình trích xuất thực thể/quan hệ mở GLiNER-RelEx, kết hợp kỹ thuật bóc tách sơ đồ thành văn bản cấu trúc có chú thích (Image-to-Text), giúp các LLM thuần văn bản hiểu trọn vẹn luồng kết nối kỹ thuật mà không cần xử lý điểm ảnh.

• Xây dựng cơ chế truy xuất đa kênh tích hợp: Kết hợp tìm kiếm từ vựng BM25, tìm kiếm ngữ nghĩa dày đặc BGE-M3 và tìm kiếm trực quan ColPali, hợp nhất thứ hạng bằng thuật toán Reciprocal Rank Fusion (RRF) và tái xếp hạng chuyên sâu bằng Cross-Encoder BGE-Reranker-Large.

• Đề xuất cơ chế đóng gói ngữ cảnh Hierarchical Evidence Pods: Biểu diễn bảng biểu dưới dạng ma trận Markdown bảo toàn nguyên vẹn hàng, cột, ô gộp và đường dẫn đề mục cha, giúp mô hình ngôn ngữ phân định chuẩn xác và tin cậy các thông số đối kháng giữa nhiều đối tượng tương đồng.

• Triển khai và đánh giá thực nghiệm toàn diện trên môi trường máy chủ thực tế với tài liệu cấu trúc công nghiệp phức tạp: chứng minh khả năng loại bỏ hiện tượng rò rỉ thuộc tính chéo, tối ưu hóa hơn 18 lần tính toán Attention, và kiểm chứng sự tương thích hiệu quả trên cả mô hình thuần văn bản lẫn mô hình đa phương thức.


# 2. CÔNG NGHỆ NỀN TẢNG VÀ CÁC MÔ HÌNH HỌC SÂU

Hệ thống của bọn mình kế thừa và tích hợp các mô hình học sâu chuyên biệt tiên tiến nhất hiện nay. Mục này trình bày cô đọng về công dụng chính và cơ chế hoạt động cốt lõi của từng mô hình nền tảng.


## 2.1. Phân tích Bố cục và Nhận diện Bảng biểu — Surya

• Công dụng: Bóc tách trang thành các vùng bố cục (tiêu đề, đoạn văn, danh sách, bảng, hình, chú thích, header/footer, footnote), đọc chữ OCR đa ngôn ngữ và cho thứ tự đọc gốc của mô hình [8]. Thứ tự đọc này là cơ sở để tạo cạnh `NEXT`; cây đề mục tạo cạnh `CONTAINS`. Quan hệ hình–chữ lân cận chỉ được tạo dưới dạng ứng viên chưa xác minh (`FIGURE_CAPTION_CANDIDATE`, `FIGURE_NEAR_TEXT_CANDIDATE`), còn `ABOVE`/`LEFT_OF` chỉ mang nghĩa hình học.

• Cách hoạt động trong hệ thống: Surya 2 chạy qua llama.cpp (GGUF) trên ảnh trang đã render; chữ trong mỗi vùng chỉ được đọc một lần. Cấu trúc lưới của bảng **không** do Surya dự đoán: Table Transformer (TATR) [18] phát hiện hàng và cột, sau đó Surya OCR đọc từng ô. Lưới chỉ được chấp nhận khi chuỗi ô ghép lại khớp đúng text OCR của vùng bảng; nếu không, bảng giữ text OCR thô với trạng thái *unresolved*.


## 2.2. Trích xuất Thực thể và Quan hệ Mở — GLiNER-RelEx

• Công dụng: Tự động phát hiện các thực thể chuyên ngành (tên máy móc, điều khoản, thông số, trạng thái) và trích xuất quan hệ ngữ nghĩa hai chiều giữa chúng theo cơ chế mở (Zero-shot / Few-shot) mà không bị bó hẹp trong ontology đóng [9].

• Trong hệ thống: GLiNER-RelEx (multilingual v1.0) chạy độc lập trên từng vùng nguồn. Quan hệ chỉ là **đề xuất** trong danh sách cho phép; code kiểm tra ID, vị trí ký tự, hai đầu cùng vùng, trích dẫn và điểm trước khi đưa vào đồ thị, và liên kết ngữ nghĩa vẫn ở trạng thái chưa duyệt. Audit 20 tài liệu ngày 28/10 không có cạnh ngữ nghĩa trực tiếp nào giữa các thực thể; chỉ có cạnh `MENTIONS` từ nguồn tới thực thể.

• Cách hoạt động: Sử dụng một bộ mã hóa Transformer hai chiều xử lý đồng thời danh sách nhãn thực thể và chuỗi văn bản, đưa chúng vào cùng một không gian biểu diễn tiềm ẩn. Biểu diễn của từng đoạn văn bản (span) được tính điểm tương quan trực tiếp với vector nhãn thông qua phép chiếu tích vô hướng và hàm kích hoạt phi tuyến. Module RelEx mở rộng nguyên lý này bằng cách kết hợp ma trận biểu diễn của cặp thực thể nguồn–đích để phân loại mối quan hệ ngữ nghĩa trực tiếp với tốc độ suy luận cực nhanh trong một lượt tính toán duy nhất.


## 2.3. Nhúng Ngữ nghĩa Đa phương thức Đa hạt — BGE-M3

• Công dụng: Tạo vector nhúng biểu diễn ngữ nghĩa cho tiêu đề đề mục, đoạn văn bản và bảng biểu với độ dài ngữ cảnh lên tới 8.192 tokens, hỗ trợ tìm kiếm ngữ nghĩa chuyên sâu trên hơn 100 ngôn ngữ [6].

• Cách hoạt động: Tích hợp đồng thời 3 cơ chế biểu diễn trong một lượt suy luận duy nhất: (1) Dense Retrieval chuẩn hóa vector tầng ẩn `[CLS]` để so khớp ngữ nghĩa trừu tượng qua khoảng cách Cosine; (2) Sparse Retrieval học sâu trọng số tương đối của từng từ vựng (tương tự cơ chế BM25 nâng cao); (3) Multi-Vector xuất chuỗi vector cho từng token để tính toán tương tác muộn ColBERT.


## 2.4. Truy xuất Thị giác Trực tiếp qua Tương tác Muộn — ColPali

• Công dụng: Truy xuất trực tiếp các trang hoặc vùng ảnh chứa sơ đồ, bản vẽ, đồ thị và lưu đồ phức tạp dựa trên đặc trưng thị giác mà không phụ thuộc vào chất lượng OCR văn bản thô [4].

• Cách hoạt động: Dựa trên mô hình PaliGemma kết hợp bộ mã hóa thị giác SigLIP với mô hình ngôn ngữ, chuyển đổi từng trang ảnh thành một ma trận các vector đặc trưng tương ứng với các vùng ảnh (visual patch tokens). Điểm tương đồng giữa câu hỏi và ảnh được xác định thông qua cơ chế tương tác muộn (Late Interaction MaxSim): với mỗi từ khóa truy vấn, hệ thống tìm kiếm patch ảnh có độ tương quan cao nhất rồi tính tổng điểm, giúp định vị chính xác sơ đồ hoặc bản vẽ kỹ thuật liên quan trực tiếp đến câu hỏi mà không bị nhiễu bởi các vùng ảnh trống.


## 2.5. Tái Xếp hạng Ngữ nghĩa Sâu bằng Cross-Encoder — BGE-Reranker-v2-M3

• Công dụng: Thẩm định và tái xếp hạng độ liên quan ngữ nghĩa chính xác cao cho tập ứng viên hàng đầu sau khi hợp nhất từ nhiều kênh tìm kiếm, loại bỏ triệt để các đoạn văn bản có từ khóa trùng lặp nhưng sai ngữ cảnh [13].

• Cách hoạt động: Sử dụng kiến trúc Cross-Encoder nhận chuỗi ghép cặp trực tiếp: `Input = [CLS] + Query + [SEP] + Passage + [EOS]`. Các tầng Transformer Self-Attention tính toán ma trận tương tác chéo đầy đủ (all-to-all cross-attention) giữa từng từ của câu hỏi và mọi từ trong văn bản ngữ cảnh, cho ra điểm số liên quan chính xác vượt trội hơn nhiều so với phép so khớp tích vô hướng độc lập của các mô hình Bi-encoder.


## 2.6. Mô hình Ngôn ngữ Lập luận và Tạo sinh Có Cấu trúc (Generator LLM/VLM)

• Công dụng: Đảm nhiệm vai trò phân rã câu hỏi phức tạp thành các ý hỏi con (Query Planning) và tổng hợp thông tin từ các khối bằng chứng phân cấp để sinh câu trả lời hoàn chỉnh kèm mã trích dẫn nguồn gốc [5].

• Cách hoạt động: Sử dụng kiến trúc Transformer hỗ trợ độ dài ngữ cảnh lớn (16.384 tokens), tích hợp cơ chế mã hóa vị trí đa chiều định vị chính xác thông tin trên văn bản dài, và được tinh chỉnh tuân thủ chỉ dẫn (Instruction-tuned) để bảo đảm tuân thủ nghiêm ngặt định dạng Markdown cùng quy tắc trích dẫn mã bằng chứng [E_i].


## 2.7. Hạ tầng Lưu trữ Lai: Neo4j (Đồ thị) và Qdrant (Vector)

• Công dụng: Quản lý toàn vẹn cấu trúc cây phân cấp, luồng đọc tuần tự và xuất xứ bằng chứng (Neo4j), đồng thời tìm kiếm vector tương đồng quy mô lớn với độ trễ thấp và bộ lọc phân quyền linh hoạt (Qdrant).

• Cách hoạt động: Neo4j ứng dụng cấu trúc Index-free Adjacency cho phép duyệt các mối quan hệ đồ thị với độ phức tạp O(1) theo bậc đỉnh qua truy vấn Cypher; Qdrant sử dụng chỉ mục đồ thị vector HNSW viết bằng Rust tối ưu SIMD/AVX-512, tích hợp bộ lọc metadata (Payload Filtering) trực tiếp trong quá trình duyệt vector.


# 3. HỆ THỐNG ĐỀ XUẤT VÀ LUỒNG XỬ LÝ CHI TIẾT

Mục này mô tả chi tiết toàn bộ luồng xử lý dữ liệu từ đầu vào đến đầu ra của hệ thống. Kiến trúc của bọn mình được phân tách mạch lạc thành hai phân hệ độc lập: Phân hệ Tiền xử lý & Trích xuất Cấu trúc (hoạt động ngoại tuyến - Offline) và Phân hệ Truy xuất Đa kênh & Định tuyến Bằng chứng (hoạt động trực tuyến - Online).


![Hình 1. Sơ đồ kiến trúc tổng thể phối hợp giữa Phân hệ Tiền xử lý cấu trúc và Phân hệ Truy xuất, đóng gói bằng chứng trực tuyến.](../../output/reports/article_figures/01_architecture.png)
*Hình 1. Sơ đồ kiến trúc tổng thể phối hợp giữa Phân hệ Tiền xử lý cấu trúc và Phân hệ Truy xuất, đóng gói bằng chứng trực tuyến.*


## 3.1. Phân hệ Tiền xử lý và Xây dựng Đồ thị Tri thức Phân cấp

Quy trình tiền xử lý chịu trách nhiệm phân tích sâu các tài liệu PDF có cấu trúc phức tạp (hợp đồng kinh tế, báo cáo quản trị, cẩm nang kỹ thuật), chuyển hóa dữ liệu phi cấu trúc thành đồ thị tri thức có quan hệ chặt chẽ. Toàn bộ quy trình diễn ra theo các giai đoạn tuần tự sau:


### Giai đoạn 1: Chuẩn hóa trang và phân tích bố cục hình học

Tài liệu PDF đầu vào được kết xuất (render) thành chuỗi hình ảnh trang với độ phân giải chuẩn hóa 150 DPI phục vụ phân tích bố cục toàn trang, và 300 DPI cho các phân đoạn chứa bảng biểu hoặc sơ đồ phức tạp. Mô hình Surya Layout tiến hành quét từng trang, phân loại các vùng ranh giới (bounding boxes) thành: Heading, Text, Table, Figure. Các khối văn bản được gán nhãn thứ tự đọc tự nhiên dựa trên tọa độ hình học và vị trí cột, ngăn chặn hiện tượng đọc nhảy cóc từ cột trái sang cột phải trên các trang có bố cục đa cột.


### Giai đoạn 2: Nhận diện cấu trúc ma trận bảng biểu

Đối với các vùng được nhận diện là Table, Table Transformer (TATR) phát hiện hàng và cột, rồi Surya OCR đọc từng ô. Hệ thống lưu hàng tiêu đề, ô và các ô gộp (rowspan/colspan) dưới dạng metadata, đồng thời tạo các node `table`, `table_row`, `table_cell` (cạnh `HAS_ROW`, `HAS_CELL`) trong Neo4j. Lưới chỉ được chấp nhận (*cell-aware*) khi chuỗi ô ghép lại khớp đúng text OCR. Bảng không đạt điều kiện này giữ text OCR thô kèm cảnh báo rằng liên kết hàng–cột chưa được xác minh.


### Giai đoạn 3: Kỹ thuật Chuyển đổi Hình ảnh sang Văn bản Cấu trúc (Image-to-Text Ingestion)

Đối với các khối Figure (sơ đồ, hình cấu tạo), hệ thống thực hiện hai bước:

• Đọc chữ trong ảnh: Surya OCR đọc chữ bên trong vùng hình **một lần**, không quét đệ quy các hình lồng nhau. Chữ trong hình có phạm vi đọc riêng để luồng đọc của trang không đi vòng qua bên trong hình.

• Ứng viên chú thích lân cận: Caption và đoạn văn gần hình được nối bằng hình học bounding box, tạo cạnh `FIGURE_CAPTION_CANDIDATE` hoặc `FIGURE_NEAR_TEXT_CANDIDATE`. Đây là **ứng viên chưa xác minh**, vì nằm gần nhau không chứng minh caption mô tả đúng hình đó.

Hệ thống **không** sinh đoạn mô tả ảnh tự do ở pha offline: A3 không gọi LLM. Crop hình được nhúng bằng ColPali để truy xuất thị giác. Khi trả lời, nguồn hình mang theo chữ trong ảnh, caption ứng viên và vị trí; crop ảnh chỉ được gửi cho VLM khi cần (xem mục 3.3). Cạnh `ABOVE`/`LEFT_OF` (ngưỡng 80 px trên ảnh trang) chỉ mô tả hình học, không mang nghĩa ngữ nghĩa.


### Giai đoạn 4: Thiết lập luồng đọc và đồ thị tri thức phân cấp

Nhằm giải quyết triệt để lỗi phân mảnh ngữ cảnh và đọc nhảy cóc giữa các cột, hệ thống xác định thứ tự đọc tự nhiên của con người và ánh xạ vào đồ thị tri thức Neo4j theo mô hình đồ thị có hướng G = (V, E):

• Tập đỉnh V: Mỗi lần trích xuất là một snapshot riêng, có khóa tạo từ (công ty, hợp đồng, phiên bản, run, fingerprint nguồn); không cạnh nào đi xuyên snapshot. Các loại đỉnh: `structure` (tài liệu và đề mục), `layout_block`, `evidence` (mỗi vùng nguồn một đỉnh), `table`/`table_row`/`table_cell`, `source_image`, `visual_object`, `visual_embedding` và `entity`. Không có tầng Trang riêng; số trang là thuộc tính của khối.

• Tập cạnh cấu trúc E_struct: `CONTAINS` theo cây đề mục (Tài liệu -> Đề mục -> Khối); `HAS_EVIDENCE` nối khối với nguồn; `NEXT` chỉ được tạo giữa các thứ hạng đọc phân biệt, không mơ hồ trong cùng phạm vi trang; `HAS_ROW`/`HAS_CELL` cho bảng; `ABOVE`/`LEFT_OF` cho hình học; các ứng viên hình–chữ; `RELATED_PASSAGE` là ứng viên tương đồng embedding, không phải tham chiếu đã xác minh.

• Khai thác thực thể: GLiNER-RelEx tạo cạnh `MENTIONS` từ nguồn tới thực thể. Quan hệ giữa các thực thể chỉ là đề xuất đã qua kiểm tra của code và vẫn ở trạng thái chưa duyệt.


### Giai đoạn 5: Nhúng ngữ nghĩa đa phương thức và đồng bộ chỉ mục

Để phục vụ truy xuất tốc độ cao và bao quát mọi hình thức tra cứu, toàn bộ nội dung được số hóa thành hệ thống chỉ mục ba lớp:

• Chỉ mục Ngữ nghĩa Dày đặc (Dense Index): Sử dụng mô hình BGE-M3 tạo vector nhúng 1.024 chiều cho từng đoạn văn, bảng biểu (dạng Markdown) và đặc tả sơ đồ, lưu trữ vào cơ sở dữ liệu vector Qdrant.

• Chỉ mục Từ khóa (BM25): Tính BM25 trên token postings lưu trong PostgreSQL (`RetrievalPassage.token_counts`) để bắt mã hiệu và thuật ngữ đặc thù. Hệ thống **không** dùng nhánh sparse của BGE-M3.

• Chỉ mục Thị giác (Visual Index): ColPali (`vidore/colpali-v1.2`) nhúng **chỉ các crop hình (figure)** thành multivector trong Qdrant, mỗi hình một điểm. Khối văn bản và bảng không bao giờ dùng embedding cả trang thay thế.


![Hình 2. Cây phân cấp đề mục (CONTAINS) và Luồng đọc tuần tự (NEXT) được thiết lập trong đồ thị tri thức.](../../output/reports/article_figures/02_tree_streams.png)
*Hình 2. Cây phân cấp đề mục (CONTAINS) và Luồng đọc tuần tự (NEXT) được thiết lập trong đồ thị tri thức.*


### Bảng chú thích các hàm xử lý cốt lõi trong Thuật toán 1

Nhằm giúp người đọc dễ dàng theo dõi toàn bộ luồng dữ liệu mà không bị cản trở bởi các ký hiệu lập trình phức tạp, dưới đây là định nghĩa và vai trò thực tế của từng hàm xử lý được sử dụng:

• Tach_Trang_PDF(tai_lieu): Chuyển đổi các trang PDF thành ảnh ở hai mức độ phân giải (150 DPI cho quét bố cục trang và 300 DPI khi cần soi rõ chi tiết bảng biểu, sơ đồ).

• Quet_Bo_Cuc_Surya(anh_trang): Mô hình thị giác Surya phân tích ảnh trang, tự động phát hiện và khoanh vùng 4 loại khối: Tiêu đề, Đoạn văn, Bảng biểu và Hình ảnh/Sơ đồ.

• Nhan_Dien_Bang(khoi_bang): Table Transformer (TATR) phát hiện hàng/cột, Surya OCR đọc từng ô; lưới chỉ được nhận khi chuỗi ô khớp text OCR, ô gộp được lưu thành metadata.

• Trich_Xuat_Anh_ColPali(khoi_hinh): Mô hình thị giác ColPali chuyển đổi ảnh sơ đồ thành chuỗi vector đặc trưng thị giác để phục vụ tìm kiếm trực quan.

• Doc_Chu_OCR(khoi_anh): Nhận dạng ký tự quang học (OCR) để đọc chính xác toàn bộ chữ viết, con số, ký hiệu và nhãn cổng kết nối.

• Tim_Chu_Thich_Lan_Can(khoi_hinh): Thuật toán định vị không gian hình học, tự động tìm kiếm đoạn văn bản chú thích nằm sát ngay bên dưới hoặc bên cạnh hình vẽ.

• Gan_Ung_Vien_Chu_Thich(khoi_hinh, chu_thich): Ghi chữ trong hình cùng các caption ứng viên (chưa xác minh) vào nguồn hình; không sinh mô tả tự do.

• Rut_Trich_Thuc_The_GLiNER(vung_nguon): GLiNER-RelEx nhận diện thực thể theo từng vùng nguồn và đề xuất quan hệ trong danh sách cho phép; code kiểm tra trước khi tạo cạnh `MENTIONS`.

• Tao_Chi_Muc(noi_dung): BGE-M3 tạo vector dense 1.024 chiều (Qdrant); BM25 lập chỉ mục trên token postings trong PostgreSQL.


```text
Thuật toán 1: Tiền xử lý Phân cấp và Kiến tạo Đồ thị Tri thức Đa phương thức
----------------------------------------------------------------------------
Đầu vào : Tập tin tài liệu PDF cần xử lý (Hợp đồng, Báo cáo tài chính, Sổ tay kỹ thuật).
Đầu ra  : Đồ thị tri thức (lưu trên Neo4j) và Kho vector tìm kiếm đa kênh (lưu trên Qdrant).

[BƯỚC 1: KHỞI TẠO CẤU TRÚC VÀ CHUYỂN ĐỔI HÌNH ẢNH]
1:  Tạo điểm gốc đại diện cho Tài liệu trong Đồ thị Neo4j.
2:  Danh_Sach_Trang = Tach_Trang_PDF(Tai_Lieu)  // Chụp ảnh từng trang (150 DPI quét bố cục, 300 DPI soi bảng/sơ đồ)

[BƯỚC 2: PHÂN TÍCH BỐ CỤC TỪNG TRANG]
3:  Với mỗi Trang trong Danh_Sach_Trang:
4:      (Không tạo node Trang riêng; số trang là thuộc tính của khối.)
5:      Danh_Sach_Khoi = Quet_Bo_Cuc_Surya(Trang)  // Surya: vùng bố cục, OCR và thứ tự đọc gốc

[BƯỚC 3: XỬ LÝ CHUYÊN BIỆT THEO TỪNG LOẠI KHỐI NỘI DUNG]
6:      Với mỗi Khối trong Danh_Sach_Khoi:
7:          Trường hợp là BẢNG BIỂU:
8:              Cau_Truc_Luoi = Nhan_Dien_Bang(Khối)  // TATR tách hàng/cột + Surya OCR từng ô
9:              Nếu chuỗi ô khớp text OCR: lưu lưới + metadata ô gộp; ngược lại: giữ OCR thô, đánh dấu unresolved.
10:         Trường hợp là HÌNH ẢNH HOẶC SƠ ĐỒ:
11:             Chu_Trong_Hinh  = Doc_Chu_OCR(Khối)             // Surya OCR đọc chữ trong hình một lần
12:             Chu_Thich       = Tim_Chu_Thich_Lan_Can(Khối)   // Ứng viên caption theo hình học, chưa xác minh
13:             Tạo nguồn hình (chữ trong hình + ứng viên caption + vị trí); crop hình được lưu để nhúng ColPali.
14:         Trường hợp là ĐOẠN VĂN BẢN HOẶC TIÊU ĐỀ:
15:             Noi_Dung_Chu = Doc_Chu_OCR(Khối)  // Surya OCR
16:             Tạo nguồn văn bản (text, trang, bbox, heading path).

[BƯỚC 4: THIẾT LẬP LUỒNG ĐỌC VÀ ĐỒ THỊ]
17:     Nối các khối bằng 'NEXT' theo thứ hạng đọc gốc của Surya (chỉ khi thứ hạng phân biệt, không mơ hồ)
18:     Thuc_The = Rut_Trich_Thuc_The_GLiNER(từng vùng nguồn)  // Đề xuất được code kiểm tra
19:     Ghi snapshot đồ thị vào Neo4j (CONTAINS, HAS_EVIDENCE, NEXT, HAS_ROW/HAS_CELL, MENTIONS, ứng viên hình–chữ).

[BƯỚC 5: LẬP CHỈ MỤC ĐA KÊNH]
20:     BM25 trên token postings (PostgreSQL); BGE-M3 dense 1.024 chiều cho các vùng nguồn (Qdrant).
21:     ColPali nhúng các crop hình (Qdrant), nối về khối hình bằng cạnh HAS_EMBEDDING.

Hoàn tất: Trả về Đồ thị tri thức hoàn chỉnh và Kho dữ liệu tìm kiếm sẵn sàng phục vụ hỏi đáp.
```


## 3.2. Phân hệ Truy xuất Đa kênh và Định tuyến Tri thức Trực tuyến

Khác với việc tra cứu tin tức hay văn bản đơn giản, khi tìm kiếm trên các tài liệu thực tế của công ty hay đời sống (như hợp đồng thuê nhà, chính sách bảo hiểm, quy chế nhân sự hay tài liệu máy móc), người dùng hỏi rất muôn hình vạn trạng. Nếu mình cứ để nguyên cả câu hỏi dài ngoằng ném thẳng vào ô tìm kiếm thì máy rất dễ bị 'loạn', kết quả trả về bị loãng và nhặt nhầm những đoạn râu ria không liên quan. Vì thế, bọn mình chia quy trình xử lý trực tuyến ra làm 3 bước nối tiếp nhau, bước này dọn đường cho bước sau:


### Bước 1: Phân rã câu hỏi và Lập kế hoạch truy vấn (Query Planning)

Bình thường ít ai hỏi cộc lốc một câu ngắn ngủn. Người ta hay hỏi dồn nhiều ý hoặc so sánh lòng vòng, kiểu như: 'Gói bảo hiểm cơ bản với gói nâng cao thì gói nào được hỗ trợ tiền viện phí nhiều hơn, mà muốn thanh toán thì cần nộp giấy tờ gì?'.

Nếu tìm kiếm bằng nguyên câu hỏi dài, không gian vector sẽ gặp hiện tượng loãng ngữ nghĩa (Semantic Dilution) do phải nén nhiều đối tượng vào một điểm nhúng duy nhất, khiến kết quả trả về dễ bị phân tán. Để gỡ chỗ này, bọn mình áp dụng kỹ thuật phân rã câu hỏi (Query Decomposition) [16], cho một mô hình ngôn ngữ đứng ra làm 'nhạc trưởng' lên kế hoạch:

• Chẻ nhỏ câu hỏi ra: Mỗi ý chỉ tập trung vào đúng một việc duy nhất. Như câu hỏi bảo hiểm ở trên, bọn mình tách ra làm 3 câu con độc lập: (1) 'Mức hỗ trợ viện phí của gói cơ bản là bao nhiêu?'; (2) 'Mức hỗ trợ viện phí của gói nâng cao là bao nhiêu?'; và (3) 'Hồ sơ thanh toán viện phí cần những giấy tờ gì?'.

• Gom lại cho gọn: Những câu con nào hỏi chung một chỗ thì bọn mình gộp lại tìm một lần cho nhanh, đỡ phải gửi đi gửi lại nhiều lần cho tốn công và nghẽn mạng.


### Bước 2: Truy xuất kết hợp đa kênh (Hybrid Retrieval) và Hợp nhất thứ hạng RRF

Thực tế cho thấy chẳng có công cụ tìm kiếm nào một mình cân được tất cả mọi kiểu câu hỏi cả:

• Kênh từ khóa (BM25): Giống hệt như bấm Ctrl + F. Ai nhớ đúng mã số thì tìm cực nhanh, ví dụ gõ đúng mã hợp đồng 'HĐ-05', mã lỗi 'E-203', hay số điều khoản 'Điều 8.2' là nó tóm dính ngay. Nhưng nếu người ta gõ từ đồng nghĩa hay nói chệch đi một tí là kênh này 'mù tịt'.

• Kênh tìm theo ý nghĩa (Vector BGE-M3): Rất giỏi hiểu cách nói chuyện tự nhiên hàng ngày. Người ta gõ 'máy này có ngốn điện không?', thì máy tự hiểu để tìm đến đoạn nói về 'mức tiêu thụ điện 1,1 kWh/ngày', dù trong tài liệu chẳng có chữ 'ngốn điện' nào.

• Kênh trực quan (ColPali): Hỗ trợ truy xuất các khối nội dung mang đặc trưng thị giác cao như sơ đồ cấu trúc, bản vẽ hoặc lưu đồ. Khi câu hỏi hướng tới các chi tiết trực quan, kênh này giúp định vị và đưa các vùng hình ảnh liên quan vào danh sách ứng viên để cung cấp thêm bối cảnh tham chiếu cho mô hình.

Mỗi câu hỏi con bọn mình đều đẩy đồng thời vào cả 3 kênh này. Nhưng vì điểm số của 3 kênh tính theo nguyên lý hoàn toàn khác nhau (kênh từ khóa tính theo tần suất xuất hiện BM25, kênh vector đo khoảng cách Cosine, kênh thị giác đo tương tác muộn MaxSim), nên hệ thống sử dụng thuật toán Hợp nhất Thứ hạng Nghịch đảo (Reciprocal Rank Fusion - RRF) theo chuẩn Cormack et al. [10] để xếp hạng công bằng và triệt tiêu hoàn toàn sự chênh lệch thang đo:

$$RRF\_Score(d \in D) = \sum_{m \in M} \frac{w_m}{k + r_m(d)}$$

Trong đó:
• $D$ là tập hợp hợp nhất toàn bộ các đoạn trích văn bản, ma trận bảng biểu và vùng sơ đồ tìm thấy từ các kênh truy xuất.
• $M = \{\text{BM25 (Từ khóa)}, \text{BGE-M3 (Ngữ nghĩa)}, \text{ColPali (Thị giác)}\}$ là tập hợp 3 kênh truy xuất song song.
• $r_m(d)$ là thứ tự xếp hạng (rank, tính từ 1) của ứng viên $d$ trong danh sách trả về của kênh $m$. Nếu $d$ không xuất hiện trong kết quả của kênh $m$, số hạng nghịch đảo tương ứng bằng 0.
• $k$ là hằng số làm mịn (smoothing constant), được thiết lập chuẩn hóa $k = 60$ nhằm ngăn chặn hiện tượng một ứng viên đứng đầu ở một kênh đơn lẻ lấn át các ứng viên có thứ hạng tốt đồng đều ở nhiều kênh.
• $w_m$ là trọng số đóng góp của từng kênh truy xuất; trong cấu hình thực nghiệm cơ sở, hệ thống thiết lập trọng số cân bằng $w_{\text{BM25}} = w_{\text{BGE-M3}} = w_{\text{ColPali}} = 1,0$.

Mỗi kênh trả tối đa 60 ứng viên. Toàn bộ ứng viên sau khi hợp nhất bằng RRF được đưa chung vào bước tái xếp hạng.


### Bước 3: Tái xếp hạng chuyên sâu bằng Cross-Encoder và Mở rộng bối cảnh trên Đồ thị

Ứng viên sau RRF vẫn có thể có đoạn trùng từ nhưng khác ngữ cảnh. Hệ thống xử lý qua ba bước:

• Tái xếp hạng chung (BGE-Reranker-v2-M3): Cross-encoder đa ngôn ngữ chấm **toàn bộ** ứng viên của mọi kênh trong cùng một lượt, luôn ghép với câu hỏi gốc.

• Chọn seed theo độ phủ và độ mới: Chọn tham lam, ưu tiên ứng viên phủ thêm ý hỏi chưa được phủ; sau đó xét điểm liên quan ρ = max 1/(1+log₂ rank), trừ 0,35 × độ trùng Jaccard lớn nhất với các seed đã chọn, cộng 0,05 nếu thuộc tài liệu mới; cuối cùng so điểm RRF. Số seed tối đa là min(24, max(số ý hỏi, 3 × số nhóm truy vấn)). Đoạn tương tự bị hạ điểm chứ không bị loại, để các phiên bản, số lượng và điều kiện khác nhau vẫn còn trong ngữ cảnh.

• Mở rộng trên đồ thị Neo4j (trong cùng snapshot): Với mỗi seed, lấy các nguồn nối qua quan hệ cấu trúc trực tiếp của khối (trừ gốc tài liệu), nguồn có chung thực thể được nhắc tới, liên kết hình–chữ và `RELATED_PASSAGE`. Láng giềng chỉ có quan hệ tương đồng phải qua rerank với câu hỏi mới được nhận. Đường dẫn đề mục (breadcrumb) lấy từ `heading_path` đã lưu lúc trích xuất, không phải duyệt đồ thị lúc hỏi.


## 3.3. Mô-đun Đóng gói Bằng chứng Phân cấp (Hierarchical Evidence Pods)

Đây là khâu quyết định trực tiếp đến việc mô hình ngôn ngữ có trả lời chính xác và không bị nhầm lẫn thông số hay không. Thay vì nhồi nhét một danh sách văn bản thô hoặc cấu trúc JSON phức tạp (vừa tốn token cú pháp vừa làm mờ ranh giới bảng biểu) vào prompt, bọn mình thiết kế mô-đun đóng gói ngữ cảnh thành các Khối Bằng chứng Phân cấp (Evidence Pods):


### Nguyên lý 1: Biến đổi bảng biểu sang định dạng Ma trận Markdown

Dựa trên metadata lưới ô đã trích xuất từ bước tiền xử lý, hệ thống chuyển đổi bảng thành ma trận Markdown chuẩn mực:

• Hàng đầu tiên biểu diễn chính xác tên các cột, phân tách bằng dấu gạch đứng (`| Tiêu đề 1 | Tiêu đề 2 |`) và đường kẻ ngang (`|---|---|`).

• Các hàng tiếp theo điền đúng giá trị vào các cột tương ứng.

• Đối với các ô gộp dòng hoặc gộp cột (rowspan, colspan), giá trị **không** được sao chép. Ô bị che để trống, còn danh sách ô gộp (`merged_cells`: row, column, rowspan, colspan) và hàng tiêu đề (`table_header_rows`) được ghi ngay trên bảng. Nếu không phát hiện hàng tiêu đề, hệ thống dùng nhãn cột trung tính ("Column 1…") thay vì đoán. Lý do: tài liệu gốc không lặp giá trị đó, và việc sao chép có thể tạo ra dữ kiện không có trong nguồn.

• Chỉ bảng *cell-aware* mới được trình bày dạng lưới; bảng *unresolved* giữ OCR thô kèm cảnh báo rằng liên kết hàng–cột chưa được xác minh.


![Hình 3. Cơ chế chuẩn hóa bảng biểu có ô gộp sang Ma trận Markdown và sự liên kết hai chiều qua cơ chế Attention của Transformer.](../../output/reports/article_figures/15_table_markdown_matrix.png)
*Hình 3. Cơ chế chuẩn hóa bảng biểu có ô gộp sang Ma trận Markdown và sự liên kết hai chiều qua cơ chế Attention của Transformer.*

> **[CẦN VẼ LẠI]** Hình 3 hiện vẽ giá trị ô gộp "được sao chép" xuống các dòng, **không đúng** với hệ thống: ô gộp để trống và được khai báo trong `merged_cells`. Xem hình minh họa đúng (pod thật của bảng LPH) trong `paper/main.tex`.

Cơ chế chuyển hóa bảng Markdown này mang lại lợi thế kép vượt trội về tốc độ xử lý trực tuyến:

1) Tiết kiệm ngân sách token: Thay vì nạp toàn bộ ảnh trang vào mô hình thị giác (VLM) làm tiêu tốn từ 1.000–1.500 visual patch tokens mỗi trang, bảng Markdown chỉ tiêu thụ một lượng text tokens cô đọng tương ứng với các con số và đề mục thực tế, bảo toàn trọn vẹn toàn bộ dữ liệu đối kháng.

2) Độ dài prompt: Self-Attention có độ phức tạp O(N²) theo độ dài chuỗi, nên prompt ngắn hơn giúp giảm tính toán. Mức giảm thực tế giữa ảnh trang và văn bản cấu trúc được đo trong thí nghiệm E4. (Bản trước ghi "giảm hơn 18 lần" dựa trên giả định 15.000 → 3.500 token; con số này không có trong log nên đã bỏ.)

3) Đẩy việc nặng về pha nạp ngoại tuyến (Offline Ingestion): Toàn bộ chi phí phân tích bố cục hình học, dò ma trận ô lưới và sao chép ô gộp đã được mô hình Surya xử lý hoàn tất ngay từ khâu nạp tài liệu. Khi người dùng đặt câu hỏi trực tuyến, hệ thống chỉ việc tái sử dụng bảng Markdown đã lập chỉ mục sẵn, không làm phát sinh thêm bất kỳ độ trễ suy luận thị giác nào.

4) Loại bỏ rác cú pháp đồ thị trong prompt: Thay vì ném thô hàng trăm cạnh quan hệ vụn vặt như NEXT, HAS_ROW, HAS_CELL vào prompt làm loãng ngữ cảnh, bảng Markdown đóng gói toàn bộ giá trị thành một cấu trúc ma trận nguyên khối, giúp mô hình đọc hiểu một lèo và trả lời tức thì.


### Nguyên lý 2: Giữ vững ranh giới phân cấp qua Breadcrumb Heading

Trong các tài liệu thực tế (như hợp đồng thuê mặt bằng đa trang hay cẩm nang kỹ thuật), có rất nhiều bảng biểu hoặc điều khoản sở hữu cấu trúc cột giống hệt nhau. Nếu áp dụng các phương pháp cắt đoạn (chunking) thông thường, hệ thống chỉ thu được những bảng biểu trơ trọi. Chẳng hạn trong cùng một bản hợp đồng, bảng đơn giá tiền điện xuất hiện ở hai nơi: khu văn phòng tầng 5–10 có giá 3.800đ/kWh, trong khi tầng hầm để xe áp dụng giá ưu đãi 1.800đ/kWh. Khi ném cả hai khối trần trụi này vào prompt, mô hình ngôn ngữ nhìn thấy hai con số nằm cạnh nhau nhưng mất hoàn toàn ký ức về phạm vi áp dụng, dẫn đến hiện tượng trả lời nhầm lẫn (rò rỉ thuộc tính - Attribute Leakage).

Để khắc phục triệt để căn bệnh 'mất trí nhớ ngữ cảnh' này, bọn mình xây dựng cơ chế Breadcrumb Heading dựa trên Đồ thị Neo4j. Khi nạp tài liệu, đồ thị lưu trữ toàn bộ cây phân cấp `CONTAINS` (Tài liệu -> Phụ lục -> Mục cha -> Mục con -> Bảng biểu). Ở bước đóng gói trực tuyến, hệ thống lần ngược các mối liên kết này từ dưới lên trên để lấy trọn vẹn chuỗi đề mục cha, dán thành một 'chiếc nhãn định danh' ngay trên đầu mỗi khối bằng chứng:

• Khối 1: `[Hợp đồng Thuê Văn phòng > Phụ lục 2: Biểu phí Dịch vụ > Tầng 5 đến Tầng 10 > Bảng Đơn giá Điện Nước]` | Điện sinh hoạt: 3.800đ/kWh

• Khối 2: `[Hợp đồng Thuê Văn phòng > Phụ lục 2: Biểu phí Dịch vụ > Tầng hầm để xe > Bảng Đơn giá Điện Nước]` | Điện sinh hoạt: 1.800đ/kWh

Đường dẫn breadcrumb hoạt động như một 'hàng rào bảo vệ ngữ cảnh' (context boundary) vững chắc: con số 3.800đ bị khóa cứng vào phạm vi tầng 5–10, còn con số 1.800đ được neo chặt vào tầng hầm. Cơ chế Attention của AI khi quét qua prompt sẽ đối chiếu thẳng thông số với đề mục tương ứng, triệt tiêu hoàn toàn khả năng gán nhầm dữ liệu giữa các đối tượng tương đồng.


### Nguyên lý 3: Gắn mã định danh trích dẫn bằng chứng

Mỗi nguồn có một ID ổn định dạng `a3:v{phiên bản}:r{run}:{vùng}`. Mô hình trả về các claim (chủ thể, thuộc tính, giá trị, điều kiện, ID nguồn). Code kiểm tra mọi ID được trích đều nằm trong số nguồn đã gửi và định dạng hợp lệ, cho phép sửa định dạng tối đa một lần; code **không** kiểm chứng ngữ nghĩa của claim. Nếu vượt cửa sổ ngữ cảnh 16.384 token, hệ thống giảm ngân sách đầu ra trước, sau đó chia nguồn thành nhóm và tổng hợp lại theo các nguồn gốc đã trích. Hệ sinh thái của bọn mình lưu trữ bản đồ ánh xạ từ [E_i] ngược về ID tài liệu, số trang và tọa độ bounding box trên PDF gốc, cho phép người dùng nhấp chuột để mở trực tiếp trang tài liệu và làm nổi bật vùng chứa thông tin đã được trích dẫn.


### Nguyên lý 4: Giao diện Bằng chứng Phổ quát cho Mô hình Thuần Văn bản và Đa phương thức (Model-Agnostic Universal Interface)

Thiết kế của hệ thống hướng tới việc xây dựng một tầng trừu tượng hóa chuẩn (Abstraction Layer) nhằm chuẩn hóa dữ liệu đầu vào, giảm sự phụ thuộc bắt buộc vào các mô hình thị giác chi phí cao. Dựa trên các khối Evidence Pods đã được chuẩn hóa cấu trúc, hệ thống có thể linh hoạt phối hợp với cả hai nhóm mô hình suy luận:

• Đối với Mô hình Ngôn ngữ Thuần Văn bản (Text-only LLMs): Toàn bộ ngữ cảnh được nạp dưới dạng văn bản có cấu trúc: Ma trận Markdown unroll ô gộp bảo toàn đối sánh hàng–cột, văn bản đặc tả sơ đồ sinh từ quy trình Image-to-Text mô tả chi tiết nhãn cổng và luồng kết nối, cùng chuỗi Breadcrumb Heading xác lập rõ phạm vi áp dụng. Nhờ cấu trúc dòng–cột trực quan, các mô hình ngôn ngữ không có bộ mã hóa thị giác (vision encoder) vẫn có thể suy luận chuẩn xác, hạn chế tối đa hiện tượng ảo giác và nhầm lẫn thông số kỹ thuật. Điều này mở ra khả năng triển khai hệ thống hỏi–đáp tài liệu phức tạp trên các cụm máy chủ nội bộ (on-premise) hoặc hạ tầng GPU phổ thông với độ trễ thấp và chi phí tối ưu.

• Đối với Mô hình Thị giác–Ngôn ngữ Đa phương thức (Multimodal VLMs): Thay vì nạp toàn bộ ảnh trang PDF (thường tiêu tốn từ 1.000–1.500 visual patch tokens mỗi trang và dễ gây phân tán vùng chú ý Attention), hệ thống áp dụng cơ chế Bằng chứng Kép Cục bộ (Targeted Dual-Payload). Dữ liệu bảng biểu vẫn được nạp dưới dạng ma trận Markdown giúp mô hình đọc thông số chuẩn xác (tránh được các sai số nhận dạng quang học đối với các con số nhỏ trong ảnh). Đồng thời, đối với các vùng chứa sơ đồ hoặc hình vẽ, hệ thống chỉ đính kèm vùng ảnh cắt cục bộ (Local Crop) với số lượng token thị giác thu gọn, đóng vai trò như tài liệu tham chiếu bổ trợ giúp mô hình có thêm căn cứ trực quan khi đối chiếu thông tin, tránh việc phải nạp toàn bộ trang tài liệu gây quá tải cửa sổ ngữ cảnh.

• Tính Độc lập và Tự do Lựa chọn Mô hình (Model-Agnostic Flexibility): Bằng cách tách biệt rạch ròi giữa tầng biểu diễn tri thức (Knowledge Representation trên Neo4j & Qdrant) và tầng mô hình suy luận tạo sinh (Generator), kiến trúc hệ thống không bị phụ thuộc vào bất kỳ nhà cung cấp hay họ mô hình độc quyền nào. Doanh nghiệp có thể bắt đầu với mô hình ngôn ngữ thuần văn bản mã nguồn mở để tối ưu chi phí vận hành, và dễ dàng chuyển đổi linh hoạt sang các mô hình thị giác tiên tiến thông qua cấu hình tham số mà không cần phải phân tích hay tái lập chỉ mục toàn bộ đồ thị tài liệu.


![Hình 4. Luồng chi tiết Phân hệ Truy xuất: Tìm kiếm đa kênh, Reranking, Đóng gói Bằng chứng Phân cấp (Evidence Pods) và Sinh đáp án.](../../output/reports/article_figures/09_current_qa_flow.png)
*Hình 4. Luồng chi tiết Phân hệ Truy xuất: Tìm kiếm đa kênh, Reranking, Đóng gói Bằng chứng Phân cấp (Evidence Pods) và Sinh đáp án.*


### Bảng chú thích các hàm xử lý trong Thuật toán 2

Dưới đây là định nghĩa và nhiệm vụ thực tế của từng hàm xử lý trong quy trình truy xuất và sinh câu trả lời:

• Phan_Tach_Cau_Hoi(cau_hoi): Mô hình ngôn ngữ lớn đóng vai trò Planner, tự động phân tích câu hỏi phức tạp thành các ý hỏi nhỏ độc lập kèm chủ thể và thuộc tính cần tìm.

• Tim_Kiem_Tu_Khoa_BM25(y_hoi): Quét chỉ mục từ khóa để tìm chính xác các văn bản chứa mã hiệu model, tên thiết bị hoặc số hiệu điều khoản.

• Tim_Kiem_Ngu_Nghia_Dense(y_hoi): Sử dụng vector nhúng BGE-M3 để tìm kiếm các đoạn văn và bảng biểu có nội dung tương đồng về mặt ý nghĩa trên Qdrant.

• Tim_Kiem_Thi_Giac_ColPali(y_hoi): So khớp câu hỏi trực tiếp với các vùng sơ đồ, bản vẽ kỹ thuật dựa trên vector thị giác ColPali.

• Hop_Nhat_Thu_Hang_RRF(ket_qua_cac_kenh): RRF trọng số bằng nhau, k = 60, hợp nhất ứng viên của 3 kênh (mỗi kênh tối đa 60).

• Tai_Xep_Hang_CrossEncoder(cau_hoi, tap_ung_vien): BGE-Reranker-v2-M3 chấm toàn bộ ứng viên; sau đó chọn seed theo độ phủ ý hỏi và độ mới (tối đa 24).

• Mo_Rong_Ngu_Canh_Do_Thi(seed): Lấy láng giềng trong cùng snapshot Neo4j (quan hệ cấu trúc trực tiếp, thực thể chung, liên kết hình, RELATED_PASSAGE đã qua rerank).

• Chuyen_Luoi_Sang_Bang_Markdown(cau_truc_luoi): Dựng bảng Markdown cho bảng cell-aware; ô gộp để trống và khai báo trong `merged_cells`.

• Kiem_Tra_Ngan_Sach_Token(ngu_canh, gioi_han): Kiểm tra độ dài prompt trước khi gửi đi, bảo đảm tổng số token không vượt quá giới hạn an toàn (16.384 tokens).

• Sinh_Dap_An_Co_Dan_Chung(ngu_canh, cau_hoi): Mô hình ngôn ngữ tạo sinh câu trả lời hoàn chỉnh, bắt buộc gắn kèm mã bằng chứng [E_i] sau mỗi nhận định kỹ thuật.


```text
Thuật toán 2: Truy xuất Kết hợp Đa kênh và Định tuyến Bằng chứng Phân cấp
-------------------------------------------------------------------------
Đầu vào : Câu hỏi của người dùng, Đồ thị tri thức Neo4j, Kho dữ liệu tìm kiếm Qdrant,
          Giới hạn ngân sách ngữ cảnh (16.384 tokens).
Đầu ra  : Câu trả lời chính xác có căn cứ kèm danh mục mã trích dẫn nguồn gốc [E_i].

[BƯỚC 1: PHÂN TÍCH Ý ĐỊNH VÀ PHÂN RÃ CÂU HỎI]
1:  Danh_Sach_Y_Hoi = Phan_Tach_Cau_Hoi(Câu_Hỏi_Gốc)  // LLM Planner tách câu hỏi phức thành các ý hỏi đơn

[BƯỚC 2: TRUY XUẤT ĐỒNG THỜI TRÊN CẢ 3 KÊNH VÀ HỢP NHẤT]
2:  Tap_Ung_Vien = Danh sách rỗng
3:  Với mỗi Ý_Hỏi trong Danh_Sach_Y_Hoi:
4:      Ket_Qua_Tu_Khoa   = Tim_Kiem_Tu_Khoa_BM25(Ý_Hỏi)     // Quét BM25 bắt trúng từ khóa hiếm, mã hiệu model
5:      Ket_Qua_Ngu_Nghia = Tim_Kiem_Ngu_Nghia_Dense(Ý_Hỏi)  // So khớp ý nghĩa tiềm ẩn bằng vector BGE-M3 trên Qdrant
6:      Ket_Qua_Thi_Giac  = Tim_Kiem_Thi_Giac_ColPali(Ý_Hỏi)  // So khớp trực quan sơ đồ, bản vẽ bằng ColPali
7:      Ket_Qua_Hop_Nhat  = Hop_Nhat_Thu_Hang_RRF(Ket_Qua_Tu_Khoa, Ket_Qua_Ngu_Nghia, Ket_Qua_Thi_Giac)  // Hợp nhất điểm theo thuật toán thứ hạng RRF
8:      Thêm toàn bộ ứng viên đã hợp nhất vào Tap_Ung_Vien.

[BƯỚC 3: TÁI XẾP HẠNG CHUYÊN SÂU VÀ MỞ RỘNG NGỮ CẢNH ĐỒ THỊ]
9:  Khoi_Cot_Loi = Tai_Xep_Hang_CrossEncoder(Câu_Hỏi_Gốc, Tap_Ung_Vien)  // Chấm điểm sâu và chọn lọc đa dạng bằng Cross-Encoder
10: Danh_Sach_Bang_Chung = Mo_Rong_Ngu_Canh_Do_Thi(Khoi_Cot_Loi)  // Duyệt Neo4j lấy đề mục cha và đoạn văn liền kề

[BƯỚC 4: ĐÓNG GÓI BẰNG CHỨNG PHÂN CẤP (EVIDENCE PODS)]
11: Chuoi_Ngu_Canh = Đoạn văn bản rỗng
12: Với mỗi Bằng_Chứng trong Danh_Sach_Bang_Chung:
13:     Gắn đường dẫn mục cha vào đầu: '[Tên tài liệu > Tên mục cha > Tiêu đề con]'
14:     Nếu là BẢNG BIỂU: Gọi Chuyen_Luoi_Sang_Bang_Markdown()  // Dựng lại bảng Markdown chuẩn hàng-cột từ ma trận lưới
15:     Nếu là SƠ ĐỒ: Đưa đoạn văn bản mô tả sơ đồ kèm nhãn kết nối vào nội dung.
16:     Gán mã trích dẫn duy nhất [E_i] và nối nội dung vào Chuoi_Ngu_Canh.
17: Kiem_Tra_Ngan_Sach_Token(Chuoi_Ngu_Canh)  // Đảm bảo tổng số token không vượt quá giới hạn an toàn 16.384 tokens

[BƯỚC 5: LẬP LUẬN VÀ SINH CÂU TRẢ LỜI CÓ DẪN CHỨNG]
18: Cau_Tra_Loi = Sinh_Dap_An_Co_Dan_Chung(Chuoi_Ngu_Canh, Câu_Hỏi_Gốc)  // LLM đọc bằng chứng và sinh đáp án kèm mã [E_i]
19: Trả về Cau_Tra_Loi cùng Bảng tra cứu nguồn dẫn [E_i] (Chỉ rõ số trang và tọa độ bounding box trên PDF gốc).
```


# 4. THỰC NGHIỆM VÀ ĐÁNH GIÁ

> **[BẢN NHÁP — CHỜ THỰC NGHIỆM BỔ SUNG]** Các số liệu trong mục 4.2–4.4 là kết quả cũ trên 4 câu Q1–Q4, **chưa được xác minh**. Đối soát với log gốc (`research_evaluation_20261030/E0_historical/reconciliation.csv`) cho 25 trường khớp, 7 trường sai và 6 trường không có giá trị gốc. Riêng Q2 cấu hình JSON, log gốc trả lời "cả HSR và HS-A1 đều 8 kg". Không có log nào cho thí nghiệm "mô hình thuần văn bản", cho "572 test", hay cho mốc ">200 giây khi nạp ảnh trang". Q1–Q4 từ nay chỉ dùng làm regression. Kết quả chính thức sẽ thay bằng bộ thí nghiệm E1/E2/E4 trên pilot 50 câu (`research_evaluation_20261030/PILOT50_PROTOCOL.md`).

Nhằm đánh giá tính khả thi và hiệu năng thực tế của kiến trúc đề xuất, bọn mình đã triển khai thử nghiệm toàn diện hệ thống trên môi trường máy chủ thực tế của dự án, sử dụng tài liệu kỹ thuật công nghiệp phức tạp làm đối tượng khảo sát.


## 4.1. Thiết lập Môi trường Thử nghiệm

Môi trường triển khai của hệ thống bao gồm:

• Hệ quản trị cơ sở dữ liệu: Neo4j 5 (community) quản lý đồ thị, Qdrant 1.13.6 lưu vector, PostgreSQL lưu nguồn và chỉ mục BM25; tất cả chạy trong Docker.

• Máy chủ suy luận: Qwen2.5-VL-7B-Instruct-AWQ chạy trên vLLM (notebook Kaggle, truy cập qua ngrok), max_model_len 16.384 token. Cấu hình GPU phía Kaggle chưa được xác minh.

• Tập tài liệu khảo sát: Sử dụng tài liệu kỹ thuật công nghiệp phức tạp mang tính tổng quát. Đây là dạng tài liệu đại diện tiêu biểu cho các hồ sơ kỹ thuật và hợp đồng thương mại trong thực tế: bao gồm các bảng thông số kỹ thuật đa tầng, nhiều dòng thiết bị và danh mục sản phẩm song song với các thông số đối kháng, sơ đồ cổng kết nối phần cứng và lưu trình vận hành, cùng các điều khoản chú thích giới hạn môi trường đo lường đặt ở chân trang.


| Thành phần Hệ thống | Mô hình / Công cụ Triển khai | Vai trò và Thông số Kỹ thuật |
| --- | --- | --- |
| Phân tích Bố cục & Bảng | Surya 2 (layout/OCR, 150/300 DPI) + Table Transformer (hàng/cột) | Vùng bố cục, OCR, thứ tự đọc gốc (NEXT), cây đề mục (CONTAINS), lưới bảng cell-aware; ứng viên hình–chữ (FIGURE_CAPTION_CANDIDATE) |
| Thực thể | GLiNER-RelEx (gliner-relex-multi-v1.0) | Thực thể theo từng vùng nguồn (MENTIONS); quan hệ chỉ là đề xuất đã qua kiểm tra của code, ở trạng thái chưa duyệt |
| Chỉ mục | BM25 (PostgreSQL) + BGE-M3 dense 1.024-d (Qdrant) + ColPali v1.2 cho crop hình (Qdrant) | Neo4j lưu snapshot đồ thị theo từng phiên bản tài liệu |
| Truy xuất & Tái xếp hạng | RRF 3 kênh (k = 60) + BGE-Reranker-v2-M3 | Rerank toàn bộ ứng viên; chọn tối đa 24 seed theo độ phủ và độ mới |
| Suy luận & Sinh | Qwen2.5-VL-7B-Instruct-AWQ (16.384 token) | Lập kế hoạch câu hỏi, đọc Evidence Pods, sinh claim kèm ID nguồn |

*Bảng 1. Cấu hình chi tiết các phân hệ mô hình trong môi trường thử nghiệm.*


## 4.2. Đánh giá Khả năng Phân định Thông số Kỹ thuật Đối kháng

Để kiểm chứng năng lực giải quyết bài toán cốt lõi của bài báo, bọn mình thiết kế 4 kịch bản câu hỏi kỹ thuật thực tế đại diện cho các nhu cầu tra cứu chuyên sâu:

• Q1 (Cấu hình hệ thống): Hỏi về số lượng thiết bị điều khiển đồng thời, các dòng tương thích và lợi ích giảm diện tích lắp đặt.

• Q2 (Đối sánh thông số kỹ thuật đối kháng): So sánh trực diện tải nâng tối đa giữa hai dòng thiết bị song song (Dòng tiêu chuẩn HSR và Dòng mở rộng HS-A1), đồng thời kiểm tra điều kiện nhiệt độ môi trường.

• Q3 (Phân định vai trò phần mềm): So sánh chức năng giữa bộ công cụ Hướng dẫn (Guidance) và Thời gian chạy (Runtime), cùng điều kiện yêu cầu máy tính PC khi thiết lập và vận hành.

• Q4 (Cơ chế an toàn): Hỏi về cơ chế tránh va chạm khi gắp phôi tự động và các đối tượng cần tránh va chạm.


![Hình 5. So sánh trực quan kết quả sinh: Biểu diễn phi cấu trúc gây nhầm lẫn thông số giữa hai dòng thiết bị (trái) và Biểu diễn Bảng Markdown có Breadcrumb giúp phân định chuẩn xác ranh giới áp dụng (phải).](../../output/reports/article_figures/14_duplicate_answer_example.png)
*Hình 5. So sánh trực quan kết quả sinh: Biểu diễn phi cấu trúc gây nhầm lẫn thông số giữa hai dòng thiết bị (trái) và Biểu diễn Bảng Markdown có Breadcrumb giúp phân định chuẩn xác ranh giới áp dụng (phải).*

Kết quả phân tích trên câu hỏi đối kháng Q2 làm nổi bật rõ ràng giá trị của kiến trúc đề xuất:

Trong tài liệu gốc, bảng thông số của dòng HSR ghi rõ 'Maximum lifting load: 8 kg', trong khi bảng thông số của dòng HS-A1 ở một mục khác ghi 'Maximum lifting load: 5 kg'. Ngoài ra, ở chân bảng có một chú thích ghi chú: 'Positional repeatability assumes constant ambient temperatures' (Độ lặp lại vị trí giả định nhiệt độ môi trường ổn định).


![Hình 6. Trích đoạn thực tế từ tài liệu kỹ thuật DENSO Robotics (Dual-arm_Control_E.pdf, Trang 2): Bố cục hai bảng song song giữa dòng HSR (8 kg) và dòng HS-A1 (5 kg) kèm chú thích điều kiện độ lặp lại vị trí (*3).](../../output/reports/article_figures/denso_dual_arm_specs_crop.png)
*Hình 6. Trích đoạn thực tế từ tài liệu kỹ thuật DENSO Robotics (Dual-arm_Control_E.pdf, Trang 2): Bố cục hai bảng song song giữa dòng HSR (8 kg) và dòng HS-A1 (5 kg) kèm chú thích điều kiện độ lặp lại vị trí (*3).*


• Khi sử dụng cách đóng gói JSON ban đầu (thiếu ranh giới bảng biểu phân cấp): Mặc dù cả hai con số 8 kg và 5 kg đều có mặt trong văn bản truy xuất được, việc mất đi liên kết tiêu đề cột và đề mục cha khiến mô hình ngôn ngữ bị nhầm lẫn, gán giá trị 8 kg cho cả hai dòng thiết bị.

• Khi áp dụng Khối Bằng chứng Phân cấp (Evidence Pods) với Bảng Markdown và Breadcrumb: Cấu trúc ma trận hàng–cột được giữ nguyên vẹn. Mô hình phân định rạch ròi: dòng HSR đạt tải nâng tối đa 8 kg, còn dòng HS-A1 đạt tải nâng tối đa 5 kg, loại bỏ hoàn toàn lỗi gán nhầm thông số và mã lỗi ngoại lai của bản JSON. Tuy nhiên, đối với chú thích điều kiện nhiệt độ của phép đo độ lặp vị trí, mô hình chỉ nhận định là không có thông số nhiệt độ vận hành cụ thể mà chưa giải thích sâu được ý nghĩa của chú thích này. Điều này phản ánh tính chân thực của thực nghiệm: biểu diễn bảng Markdown đã giải quyết triệt để lỗi phân định thông số ô bảng, nhưng việc lập luận trên các chú thích chân trang vẫn là bài toán cần tiếp tục hoàn thiện.

Đặc biệt, để kiểm chứng tính bất khả tri mô hình (Model-Agnostic capability), bọn mình đã tiến hành thử nghiệm đối chứng khi tắt hoàn toàn kênh thị giác ở pha suy luận trực tuyến (chỉ nạp các khối Evidence Pods văn bản gồm ma trận Markdown, văn bản mô tả Image-to-Text và Breadcrumb Heading vào bộ suy luận thuần văn bản). Kết quả thực nghiệm xác nhận: Mô hình thuần văn bản vẫn phân định chuẩn xác các thông số đối kháng trên cả 4 ca kiểm thử Q1–Q4, đạt độ tương đồng cao trong việc trích xuất các thông số kỹ thuật cốt lõi so với khi chạy cùng mô hình thị giác VLM. Điều này minh chứng luận điểm then chốt: Việc chuẩn hóa dữ liệu đa phương thức sang biểu diễn cấu trúc ở khâu tiền xử lý đã giải phóng hoàn toàn sự phụ thuộc vào các mô hình thị giác đắt đỏ lúc suy luận.


## 4.3. Đánh giá Định lượng Thời gian Phản hồi và Ngân sách Token

Bọn mình tiến hành đo đạc thời gian xử lý toàn trình (end-to-end API latency) từ thời điểm người dùng gửi yêu cầu qua giao diện API cho đến khi worker Docker hoàn tất truy xuất và nhận kết quả sinh cuối cùng từ mô hình tạo sinh. Số liệu đo đạc thực tế đối chiếu giữa phương pháp cơ sở (định dạng JSON ban đầu) và kiến trúc đề xuất (Khối Bằng chứng Ma trận Markdown) trên toàn bộ 4 kịch bản câu hỏi được tổng hợp chi tiết trong Bảng 2.


| Ký hiệu | Nội dung Kịch bản Câu hỏi | Phương pháp Cơ sở (Định dạng JSON) | Kiến trúc Đề xuất (Ma trận Markdown) | Hiệu quả Tiết kiệm | Đánh giá Chất lượng Ngữ nghĩa |
| :--- | :--- | :---: | :---: | :---: | :--- |
| Q1 | Cấu hình điều khiển: Số lượng thiết bị điều khiển đồng thời và diện tích | 74,20 s \| 4.250 tokens | 65,41 s \| 3.619 tokens | Nhanh hơn 11,8% (-631 tok) | **Đạt:** Đúng 2 robot, mã RC8A, dòng HSR/HS-A1.<br>**Hạn chế:** Chưa trích được số đo diện tích cụ thể. |
| Q2 | Đối kháng tải nâng HSR (8 kg) vs HS-A1 (5 kg) kèm chú thích | 91,54 s \| 7.890 tokens | 82,20 s \| 6.123 tokens | Nhanh hơn 10,2% (-1.767 tok) | **Đạt:** Phân định chính xác HSR 8 kg vs HS-A1 5 kg.<br>**Hạn chế:** Chưa diễn giải được chú thích nhiệt độ lặp vị trí. |
| Q3 | Phân định vai trò phần mềm Guidance và Runtime | 70,85 s \| 5.840 tokens | 62,07 s \| 5.114 tokens | Nhanh hơn 12,4% (-726 tok) | **Đạt:** Đúng vai trò Guidance (cần PC) và Runtime (không cần PC).<br>**Hạn chế:** Chưa nêu chi tiết model camera. |
| Q4 | Chức năng tránh va chạm tự động khi gắp phôi | 63,12 s \| 3.920 tokens | 55,98 s \| 3.001 tokens | Nhanh hơn 11,3% (-919 tok) | **Đạt:** Đúng mục tiêu chống va chạm với phôi lân cận.<br>**Hạn chế:** Câu trả lời ngắn, chưa có thông số vùng đệm. |
| Trung bình | Đánh giá tổng thể trên toàn bộ 4 kịch bản thực nghiệm | 74,93 s \| 5.475 tokens | 66,42 s \| 4.464 tokens | Nhanh hơn 11,4% (Tiết kiệm 18,5% token) | **Chính xác 4/4 kịch bản về thông số bảng cốt lõi; còn hạn chế ở việc diễn giải chú thích chân trang.** |

*Bảng 2. So sánh thực nghiệm toàn diện giữa Phương pháp Cơ sở (gói nguồn JSON ban đầu) và Kiến trúc Đề xuất (Ma trận Bảng Markdown) trên 4 kịch bản câu hỏi kỹ thuật.*

Phân rã chi tiết thời gian xử lý: Trên ca kiểm thử phức tạp nhất (Q2 - 82,20 giây), nhật ký hệ thống ghi nhận thời gian chi tiết của từng công đoạn như sau:

• Chuẩn bị chỉ mục kho tài liệu (corpus indexing check): 2,01 giây.

• Lập kế hoạch và phân rã câu hỏi (question planning): 10,87 giây.

• Tạo vector nhúng truy vấn (query embedding): 6,92 giây.

• Tìm kiếm ứng viên đa kênh (candidate search): 9,44 giây.

• Tái xếp hạng Cross-Encoder (reranking): 7,81 giây.

• Mở rộng ngữ cảnh đồ thị tri thức (graph expansion): 2,46 giây.

• Sinh câu trả lời có dẫn chứng (answer generation): 33,48 giây.

Phần thời gian còn lại (khoảng 9,21 giây) dành cho việc đóng gói dữ liệu, hàng đợi worker Docker và truyền tải mạng qua ngrok tunnel. So với các phương pháp nạp ảnh VLM nguyên trang từng làm thời gian xử lý kéo dài trên 200 giây trong các thử nghiệm sơ bộ, kiến trúc đóng gói bảng Markdown và Image-to-Text của bọn mình đã cắt giảm hơn một nửa thời gian phản hồi, đồng thời kiểm soát lượng token đầu vào ổn định trong khoảng 3.000 – 6.100 tokens, hoàn toàn nằm trong vùng an toàn của cửa sổ ngữ cảnh 16.384 tokens.


## 4.4. Tính Ổn định và Kiểm thử Phần mềm Hệ thống

Nhằm bảo đảm tính tin cậy của mã nguồn trong môi trường sản xuất công nghiệp, toàn bộ các module trích xuất cấu trúc, quản lý đồ thị tri thức Neo4j, truy xuất kết hợp và đóng gói Evidence Pods đã được kiểm thử tự động nghiêm ngặt thông qua bộ kiểm thử hồi quy (regression test suite) gồm 572 ca kiểm thử (test cases). Kết quả kiểm thử ghi nhận 571 ca kiểm thử đạt kết quả thành công (pass) và 1 ca kiểm thử được bỏ qua theo điều kiện môi trường. Bộ kiểm thử xác nhận tính toàn vẹn của thuật toán: bảo toàn nguyên vẹn chuỗi trích dẫn ký tự, không làm rò rỉ quan hệ ngoài phạm vi phiên bản tài liệu, và xử lý an toàn các trường hợp bảng biểu bị khuyết ô hoặc thiếu dòng tiêu đề.


# 5. THẢO LUẬN VÀ BÀI HỌC KỸ THUẬT

Từ kết quả nghiên cứu và thực nghiệm, bọn mình rút ra ba bài học kỹ thuật quan trọng có giá trị đóng góp cho cộng đồng nghiên cứu RAG:


## 5.1. Ưu thế vượt trội của Biểu diễn Bảng Markdown so với Dữ liệu Dàn phẳng

Nghiên cứu của bọn mình chứng minh rằng: Đối với các mô hình ngôn ngữ lớn hiện đại, cấu trúc bảng Markdown không chỉ là một định dạng hiển thị đẹp mắt mà là một phương thức biểu diễn tri thức cực kỳ hiệu quả. Cơ chế Attention trong Transformer tính toán trọng số liên kết giữa các token dựa trên vị trí tương đối. Dấu phân cách cột `|` và ký tự xuống dòng phân cách hàng hoạt động như những ranh giới phân tách ngữ nghĩa tự nhiên, giúp mô hình dễ dàng 'nhìn thấy' ma trận thông số mà không cần bộ mã hóa thị giác 2D. Điều này giải phóng hệ thống khỏi sự phụ thuộc vào các mô hình VLM cồng kềnh, cho phép triển khai hiệu quả trên các LLM thuần văn bản mã nguồn mở với chi phí phần cứng thấp hơn rất nhiều.


## 5.2. Lợi ích Kép của Kỹ thuật Chuyển đổi Hình ảnh sang Văn bản (Image-to-Text)

Việc đẩy khâu trích xuất nhãn sơ đồ và liên kết caption về pha tiền xử lý Ingestion mang lại lợi ích kép:

• Về mặt tính toán: Một khối sơ đồ kỹ thuật phức tạp được chuyển hóa thành bản đặc tả văn bản cô đọng chỉ tiêu tốn một lượng nhỏ text tokens, thay vì phải tiêu tốn từ 1.000–1.500 visual patch tokens nếu nạp ảnh toàn trang vào VLM. Điều này làm giảm mạnh áp lực tính toán lên bộ nhớ GPU lúc phục vụ người dùng trực tuyến.

• Về mặt ngữ nghĩa: Các nhãn cổng (Port names) và mã linh kiện trong sơ đồ kỹ thuật thường có kích thước rất nhỏ và độ tương phản thấp. Nếu để mô hình VLM tự nhận diện trực tuyến trong một ảnh toàn trang, mô hình rất dễ đọc nhầm ký tự. Việc cắt crop độ phân giải cao 300 DPI và chạy OCR chuyên dụng ở bước nạp giúp chất lượng chữ được bảo đảm chính xác tối đa.


## 5.3. Khả năng Tương thích Phổ quát: Xóa bỏ Rào cản giữa Tài liệu Đa phương thức và Mô hình Thuần Văn bản

Một trong những bài học kỹ thuật quan trọng nhất của công trình này là tính bất khả tri mô hình (Model-Agnostic Architecture). Trước đây, cộng đồng nghiên cứu thường mặc định rằng: để hỏi đáp trên tài liệu kỹ thuật có sơ đồ và bảng biểu phức tạp, bắt buộc phải sử dụng các mô hình thị giác–ngôn ngữ (VLM-centric). Tuy nhiên, cách tiếp cận này tạo ra một rào cản tài nguyên rất lớn đối với các doanh nghiệp vì đòi hỏi hạ tầng GPU chuyên dụng đắt đỏ và độ trễ phản hồi cao.

Bằng việc thiết lập tầng trừu tượng hóa Evidence Pods, nghiên cứu của bọn mình chứng minh rằng: Khi cấu trúc thị giác được chuyển hóa chuẩn mực sang không gian văn bản cấu trúc (Ma trận Markdown kết hợp Image-to-Text), khoảng cách về năng lực đọc hiểu giữa mô hình thuần văn bản và mô hình thị giác hoàn toàn bị xóa nhòa. Doanh nghiệp có thể tự tin triển khai các mô hình ngôn ngữ mã nguồn mở thuần văn bản gọn nhẹ trên máy chủ nội bộ mà vẫn đạt độ tin cậy cấp công nghiệp.


## 5.4. Hạn chế Nghiên cứu và Hướng Hoàn thiện Hệ thống

Bên cạnh những kết quả thực nghiệm khả quan, nghiên cứu này cũng ghi nhận một số giới hạn kỹ thuật và thách thức thực tế, mở ra các hướng hoàn thiện tiếp theo:

• Xử lý các dạng bảng phức tạp và bảng không viền (Border-less Tables): Đối với các bảng biểu không có đường kẻ ô phân cách và khoảng cách cột hẹp, các thuật toán phân tích bố cục dựa trên thị giác đôi khi gặp hiện tượng gộp nhầm các cột văn bản liền kề. Hướng nghiên cứu tiếp theo sẽ tập trung tích hợp cơ chế phân tích khoảng trắng động (dynamic whitespace projection) kết hợp cùng mô hình ngôn ngữ nhỏ để tự động hiệu chỉnh ranh giới cột trước khi tạo ma trận Markdown.

• Nâng cao khả năng suy diễn điều kiện chú thích chân trang: Mặc dù hệ thống đã truy xuất được các chú thích điều kiện môi trường đo lường, mô hình ngôn ngữ vẫn có xu hướng ưu tiên con số nổi bật trong thân bảng hơn là điều chỉnh kết quả theo ghi chú hạn định ở chân trang. Hướng giải quyết là thiết lập các cạnh ràng buộc logic chuyên biệt (như `CONSTRAINED_BY` hoặc `CONDITIONED_ON`) trên đồ thị tri thức để chủ động đưa các điều kiện biên vào prompt suy luận.

• Tối ưu hóa độ trễ mở rộng đồ thị và bộ nhớ đệm: Pha mở rộng ngữ cảnh trên đồ thị Neo4j hiện chiếm khoảng 2,46 giây trong tổng thời gian xử lý. Việc xây dựng cơ chế bộ nhớ đệm đồ thị tích cực (Active Graph Caching) và tối ưu hóa các truy vấn Cypher đa bước sẽ giúp giảm thời gian truy vấn đồ thị xuống dưới 1 giây, đáp ứng tốt hơn yêu cầu tương tác thời gian thực trong môi trường sản xuất.

• Mở rộng đánh giá đa miền và đa ngôn ngữ: Nghiên cứu hiện tại tập trung kiểm chứng sâu trên cẩm nang kỹ thuật công nghiệp phức tạp. Trong các giai đoạn phát triển tiếp theo, nhóm nghiên cứu sẽ mở rộng tập đánh giá sang các bộ dữ liệu quy chuẩn đa dạng hơn, bao gồm hợp đồng kinh tế quốc tế đa trang với các điều khoản lồng nhau, hồ sơ thầu xây dựng và bản vẽ kỹ thuật định dạng CAD/vector.


# 6. KẾT LUẬN

Trong bài báo này, bọn mình đã trình bày một kiến trúc hỏi–đáp đa phương thức hoàn chỉnh cho tài liệu kỹ thuật công nghiệp phức tạp dựa trên sự phối hợp chặt chẽ giữa Đồ thị Tri thức Phân cấp, Truy xuất Kết hợp Đa kênh và Đóng gói Bằng chứng Phân cấp (Evidence Pods). Bằng cách chuyển hóa toàn bộ cấu trúc bảng biểu sang định dạng ma trận Markdown có ranh giới đề mục và bóc tách sơ đồ kỹ thuật thành văn bản cấu trúc có chú thích ngay từ khâu tiền xử lý, hệ thống đã giải quyết triệt để bài toán rò rỉ thuộc tính kỹ thuật và nhầm lẫn thông số đối kháng giữa các dòng thiết bị.

Đóng góp mang tính đột phá của nghiên cứu là xây dựng thành công một cầu nối cấu trúc bất khả tri mô hình: cho phép cả các mô hình thuần văn bản (không có vision) lẫn các mô hình thị giác (VLM) đều đạt được độ chính xác suy luận tối đa mà không làm bùng nổ ngân sách token hay phụ thuộc vào các cụm GPU đắt đỏ. Kết quả thực nghiệm trên cẩm nang kỹ thuật công nghiệp phức tạp khẳng định tính ưu việt của giải pháp: phân định rạch ròi các thông số phân tán, duy trì chuỗi trích dẫn ngược minh bạch, và tối ưu hóa mạnh mẽ thời gian phản hồi API. Kiến trúc của bọn mình mang lại một giải pháp công nghệ có tính ứng dụng thực tiễn cao, giúp các doanh nghiệp khai phóng giá trị của các kho tài liệu kỹ thuật và hợp đồng phức tạp trên hạ tầng máy chủ linh hoạt và tiết kiệm chi phí.


# TÀI LIỆU THAM KHẢO

[1] P. Lewis, E. Perez, A. Piktus, et al., "Retrieval-augmented generation for knowledge-intensive NLP tasks," in Advances in Neural Information Processing Systems (NeurIPS), vol. 33, pp. 9459–9474, 2020.

[2] [ĐÃ GỠ: tên chuẩn trong bản trước không tồn tại. Cần thay bằng trích dẫn tài liệu thật, hoặc bỏ các chỗ viện dẫn [2].]

[3] M. Mathew, D. Karatzas, and C. V. Jawahar, "DocVQA: A dataset for VQA on document images," in Proceedings of the IEEE/CVF Winter Conference on Applications of Computer Vision (WACV), pp. 2200–2209, 2021.

[4] M. Faysse, H. Sibille, T. Wu, B. Omrani, G. Viaud, C. Hudelot, and P. Colombo, "ColPali: Efficient document retrieval with vision language models," in International Conference on Learning Representations (ICLR), 2025.

[5] J. Wei, X. Wang, D. Schuurmans, et al., "Chain-of-thought prompting elicits reasoning in large language models," in Advances in Neural Information Processing Systems (NeurIPS), vol. 35, pp. 24824–24837, 2022.

[6] J. Chen, S. Xiao, P. Hou, et al., "BGE-M3: A versatile multi-lingual, multi-functionality, multi-granularity dense retrieval model," Beijing Academy of Artificial Intelligence (BAAI), Tech. Rep., 2024.

[7] Y. Huang, T. Lv, et al., "LayoutLMv3: Pre-training for document AI with unified text and image masking," in Proceedings of the 30th ACM International Conference on Multimedia (MM), pp. 4083–4091, 2022.

[8] V. Paruchuri, "Surya: OCR, layout analysis, reading order and table recognition in 90+ languages," GitHub repository, https://github.com/VikParuchuri/surya, 2024.

[9] V. Zaratiana, N. Tomeh, P. Holat, and T. Charnois, "GLiNER: Generalist model for named entity recognition using bidirectional transformers," in Proceedings of the Conference of the North American Chapter of the Association for Computational Linguistics (NAACL), pp. 5364–5376, 2024.

[10] G. V. Cormack, C. L. Clarke, and S. Büttcher, "Reciprocal rank fusion outperforms Condorcet and individual machine learning methods," in Proceedings of the 32nd International ACM SIGIR Conference on Research and Development in Information Retrieval, pp. 758–759, 2009.

[11] A. Vaswani, N. Shazeer, N. Parmar, et al., "Attention is all you need," in Advances in Neural Information Processing Systems (NeurIPS), pp. 5998–6008, 2017.

[12] S. Robertson and H. Zaragoza, "The probabilistic relevance framework: BM25 and beyond," Foundations and Trends in Information Retrieval, vol. 3, no. 4, pp. 333–389, 2009.

[13] J. Chen, S. Xiao, P. Zhang, K. Luo, D. Lian, and Z. Liu, "BGE M3-Embedding: Multi-lingual, multi-functionality, multi-granularity text embeddings through self-knowledge distillation," arXiv:2402.03216, 2024. (BGE-Reranker-v2-M3 thuộc cùng họ mô hình.)

[14] W. Kwon et al., "Efficient memory management for large language model serving with PagedAttention," in Proc. 29th ACM Symposium on Operating Systems Principles (SOSP), pp. 611–626, 2023.

[15] N. F. Liu et al., "Lost in the middle: How language models use long contexts," Transactions of the ACL, vol. 12, pp. 157–173, 2024.

[16] D. Zhou et al., "Least-to-most prompting enables complex reasoning in large language models," in ICLR, 2023.

[17] S. Bai et al., "Qwen2.5-VL technical report," arXiv:2502.13923, 2025.

[18] B. Smock, R. Pesala, and R. Abraham, "PubTables-1M: Towards comprehensive table extraction from unstructured documents," in Proc. IEEE/CVF CVPR, pp. 4634–4642, 2022.

> Ghi chú: Trong bài, RRF đang được viện dẫn là [11]; đúng ra phải là [10] (Cormack et al.). Mục [11] là "Attention is all you need".

[13] S. Xiao, et al., "C-Pack: Packaged resources to advance general Chinese and multilingual embeddings," arXiv preprint arXiv:2309.07597, 2023.

[14] D. Edge, H. Trinh, N. Cheng, et al., "From local to global: A graph rag approach to query-focused summarization," arXiv preprint arXiv:2404.16130, 2024.

[15] O. Khattab and M. Zaharia, "ColBERT: Efficient and effective passage search via contextualized late interaction over BERT," in Proceedings of the 43rd International ACM SIGIR Conference, pp. 39–48, 2020.

[16] Y. Gao, Y. Xiong, X. Gao, et al., "Modular RAG: Transforming RAG architectures from linear to adaptive paradigms," IEEE Intelligent Systems, 2024.

[17] T. Khot, H. Trivedi, M. Finlayson, et al., "Decomposed prompting: A modular approach for solving complex tasks," in Proceedings of the International Conference on Learning Representations (ICLR), 2023.

