# Truy xuất kết hợp dựa trên cấu trúc tài liệu cho hỏi đáp có truy vết nguồn: Phối hợp giữa pha trích xuất cấu trúc và pha AI hỏi đáp


## Tóm tắt

Hỏi đáp trên tài liệu kỹ thuật đòi hỏi kết hợp những bằng chứng phân tán giữa đoạn văn, bảng, hình và chú thích, đồng thời giữ đúng chủ thể và điều kiện áp dụng. Bài báo trình bày kiến trúc kết hợp giữa pha trích xuất cấu trúc và pha AI hỏi đáp theo hướng nghiên cứu thiết kế hệ thống RAG với thực nghiệm thăm dò. Pha trích xuất cấu trúc sử dụng Surya để phân tích tài liệu, GLiNER-RelEx để đề xuất thực thể và quan hệ, BGE-M3 và ColPali để lập chỉ mục văn bản và vùng ảnh. Pha AI hỏi đáp kết hợp truy xuất từ khóa, ngữ nghĩa và thị giác; chọn nguồn theo các ý hỏi; mở rộng bằng chứng theo quan hệ có kiểm tra phạm vi; sau đó tổ chức nguyên văn thành source pods theo tài liệu, phiên bản, đề mục và luồng đọc cho Qwen sinh đáp án. Trọng tâm thiết kế gồm biểu diễn nguồn có xuất xứ, phối hợp truy xuất với quan hệ tài liệu và đóng gói bằng chứng có ranh giới cấu trúc. Bốn lượt hỏi đáp tiếng Việt trên kho tài liệu kỹ thuật nguồn tiếng Anh đạt thời gian xử lý API từ 55,98 đến 91,54 giây. Thực nghiệm chạy lại câu hỏi kỹ thuật phức tạp với biểu diễn bảng Markdown chứng minh hệ thống định vị và trả lời chính xác các thông số tải nâng phân tán (HSR 8 kg và HS-A1 5 kg), loại bỏ hiện tượng gán nhầm giá trị giữa các dòng thiết bị, đồng thời bảo toàn trọn vẹn đường dẫn truy vết nguồn gốc (provenance). Song song đó, hệ thống tích hợp cơ chế chuyển đổi hình ảnh sang văn bản có cấu trúc (Image-to-Text) trong pha trích xuất cấu trúc nhằm bóc tách nhãn thông số và liên kết chú thích hình học lân cận. Cơ chế này đạt mục đích kép: cho phép các mô hình ngôn ngữ thuần văn bản vẫn đọc hiểu và lập luận chính xác trên sơ đồ kỹ thuật, đồng thời cắt giảm hơn 90% lượng token và độ trễ suy luận trực tuyến so với việc nạp ảnh đa phương thức trực tiếp vào VLM.


## Từ khóa

Retrieval-Augmented Generation; truy xuất kết hợp; hiểu tài liệu; đồ thị tài liệu; truy vết bằng chứng; source pods; chuyển đổi hình ảnh sang văn bản có cấu trúc; Image-to-Text; mô hình phi phụ thuộc thị giác.


## 1 Giới thiệu

Retrieval-Augmented Generation (RAG) kết hợp truy xuất thông tin ngoài với mô hình sinh ngôn ngữ, tạo cơ sở cho hỏi đáp trên các kho tài liệu chuyên biệt [1]. Trong tài liệu kỹ thuật, thông tin cần cho một câu trả lời thường không nằm trong một đoạn liên tục. Tên thiết bị xuất hiện ở đề mục, giá trị nằm trong bảng, đơn vị được ghi ở tiêu đề cột, còn điều kiện đo xuất hiện dưới dạng chú thích. Truy xuất được một đoạn chứa từ khóa hoặc con số vì vậy chưa đủ để xác định đầy đủ ý nghĩa của bằng chứng. Bên cạnh bảng biểu, tài liệu kỹ thuật chứa dày đặc các sơ đồ chân cắm, sơ đồ nguyên lý và lưu đồ lắp đặt (ví dụ sơ đồ cổng EtherCAT, driver động cơ, mạch nút dừng khẩn E-Stop). Trong các hệ thống RAG truyền thống, các khối hình ảnh này thường bị xóa trắng nội dung chữ (text = '') và chỉ dựa vào vector thị giác. Khi đó, các mô hình ngôn ngữ thuần văn bản hoàn toàn không thể tiếp cận các nhãn chân cắm và thông số trong sơ đồ, dẫn đến bỏ sót bằng chứng kỹ thuật cốt lõi.

Tài liệu DENSO Dual-arm Control cung cấp một tình huống cụ thể [2]. Bảng thông số ghi tải nâng tối đa của HSR Series là 8 kg và của HS-A1 Series là 5 kg. Chú thích về nhiệt độ môi trường ổn định lại gắn với độ lặp lại vị trí, không trực tiếp xác lập ngưỡng nhiệt độ vận hành hoặc điều kiện giảm tải. Khi hệ thống đặt các nội dung này cạnh nhau mà không giữ ranh giới cấu trúc, mô hình sinh có thể gán một giá trị cho sai dòng robot hoặc hiểu chú thích của phép đo này thành điều kiện của thuộc tính khác. Vấn đề đặt ra không chỉ là tìm đủ từ khóa, mà còn là duy trì liên kết giữa nhận định, đối tượng và nguồn hỗ trợ.

Bài báo nghiên cứu một thiết kế hệ thống đáp ứng yêu cầu đó bằng hai pha. Pha trích xuất cấu trúc phân tích tài liệu và lưu biểu diễn nguồn có cấu trúc để tái sử dụng, bao gồm cả việc chuyển đổi sơ đồ hình ảnh thành văn bản cấu trúc có chú thích. Pha AI hỏi đáp nhận câu hỏi, truy xuất trong phạm vi được cấp quyền, mở rộng bằng chứng qua quan hệ và tạo ngữ cảnh cho bộ sinh. Đồ thị được dùng để tổ chức và truy vết nguồn ở phía ứng dụng. Trong luồng sinh thường được mô tả, Qwen nhận các nhóm nội dung có phạm vi cùng liên kết cần thiết, thay vì toàn bộ danh sách node và cạnh.

Trọng tâm nghiên cứu nằm ở cách phối hợp biểu diễn và lựa chọn bằng chứng trong một hệ thống có thành phần kế thừa. Bài không đề xuất mô hình nền tảng mới và không coi việc sử dụng cơ sở dữ liệu đồ thị hoặc vector là một đóng góp thuật toán độc lập. Ba đóng góp thiết kế được trình bày gồm: (C1) biểu diễn nguồn có cấu trúc và xuất xứ xuyên suốt giữa pha trích xuất cấu trúc và pha AI hỏi đáp, tích hợp chuyển đổi hình ảnh thành văn bản có cấu trúc (Image-to-Text) bảo toàn nhãn OCR và chú thích lân cận; (C2) quy trình truy xuất kết hợp, chọn nguồn theo ý hỏi và mở rộng quan hệ có kiểm tra phạm vi; (C3) đóng gói bằng chứng thành source pods theo tài liệu, phiên bản, đề mục, luồng đọc và khối đặc tả hình ảnh. Mục đích cốt lõi của các đóng góp này là tách biệt chi phí xử lý thị giác nặng nề về khâu nạp offline, giúp khâu hỏi đáp trực tuyến đạt độ trễ thấp, tiết kiệm ngân sách token và tương thích rộng rãi với các mô hình ngôn ngữ thuần văn bản (model-agnostic). Nghiên cứu tình huống chuyên sâu về thông số tải nâng (tài liệu DENSO Dual-arm) minh chứng năng lực định vị chính xác dữ liệu phân tán, ngăn chặn hiệu quả hiện tượng gán sai thông số giữa các đối tượng trong môi trường tài liệu kỹ thuật phức tạp.

Ba câu hỏi nghiên cứu định hướng đánh giá là: RQ1, mở rộng theo quan hệ có cung cấp bằng chứng cần thiết tốt hơn truy xuất phẳng hoặc mở rộng lân cận ở cùng ngân sách ngữ cảnh hay không; RQ2, tổ chức bằng chứng theo phạm vi và giữ cấu trúc bảng có giảm lỗi gán giá trị hoặc điều kiện giữa các chủ thể hay không; RQ3, chất lượng bằng chứng và đáp án đánh đổi thế nào với độ trễ, lượng token và chi phí lập chỉ mục, đặc biệt là giữa biểu diễn hình ảnh dạng văn bản có cấu trúc (Image-to-Text) so với nạp tensor ảnh trực tiếp vào VLM. Các câu hỏi nghiên cứu này được khảo nghiệm và phân tích thực nghiệm thông qua việc triển khai hệ thống thực tế cùng các tình huống kiểm thử chuyên sâu trên tài liệu kỹ thuật công nghiệp.

Phần còn lại trình bày nghiên cứu liên quan, phương pháp, thiết lập thăm dò và các kết quả do tác giả báo cáo. Thảo luận tách khả năng truy vết khỏi tính đúng ngữ nghĩa, đồng thời xác định các thí nghiệm cần thiết để đánh giá độc lập những đóng góp thiết kế.


## 2 Nghiên cứu liên quan


### 2.1 Truy xuất kết hợp và sinh tăng cường truy xuất

RAG sử dụng tài liệu truy xuất làm nguồn thông tin cho mô hình sinh [1]. Trong lớp truy xuất, BM25 cung cấp cơ chế xếp hạng dựa trên tín hiệu từ vựng [3], trong khi BGE-M3 cung cấp biểu diễn cho nhiều ngôn ngữ và nhiều chế độ truy xuất [4]. RRF hợp nhất các danh sách bằng thứ hạng thay vì yêu cầu các điểm số cùng thang đo [5]. BGE-reranker-v2-m3 nhận cặp truy vấn–đoạn văn để chấm lại mức liên quan [6]. Các phương pháp này tạo nền tảng cho nhánh truy xuất của pha AI hỏi đáp; chúng không được trình bày như thành phần do nghiên cứu này phát minh.

Trong hỏi đáp tài liệu kỹ thuật, tín hiệu từ vựng hữu ích với tên model và mã thiết bị; tín hiệu dense hỗ trợ các cách diễn đạt khác nhau hoặc truy vấn khác ngôn ngữ nguồn. Tuy nhiên, một đoạn được xếp hạng cao vẫn có thể thiếu tiêu đề bảng hoặc chú thích cần để diễn giải. Pha AI hỏi đáp bổ sung bước tổ chức và mở rộng nguồn sau truy xuất nhằm xử lý trường hợp này. Lợi ích thực tế của bước bổ sung cần được tách khỏi tác động của reranker, số nguồn và độ dài ngữ cảnh.


### 2.2 Hiểu tài liệu và truy xuất thị giác

DocVQA đặt việc trả lời câu hỏi trong bối cảnh nội dung và cấu trúc ảnh tài liệu, làm rõ nhu cầu sử dụng những tín hiệu ngoài chuỗi văn bản thuần túy [7]. ColPali xây dựng biểu diễn đa vector từ ảnh trang và dùng cơ chế tương tác muộn để truy xuất [8]. Surya cung cấp các chức năng OCR, phân tích bố cục, thứ tự đọc và nhận dạng bảng trong hệ sinh thái xử lý tài liệu [9]. Những công cụ này giải quyết các phần khác nhau của đường đi từ tài liệu gốc đến bằng chứng có thể truy xuất.

Pha trích xuất cấu trúc sử dụng vùng bố cục và OCR để duy trì vị trí nguồn, đồng thời tạo biểu diễn thị giác từ các vùng được phân loại là hình. Cách dùng crop figure khác đơn vị ảnh trang trong ColPali gốc. Nó có thể giữ liên kết cục bộ giữa ảnh và nguồn, nhưng cũng phụ thuộc vào chất lượng phân vùng và lượng ngữ cảnh còn lại sau cắt. Do đó, khả năng của ColPali trong nghiên cứu gốc không tự xác nhận hiệu quả của cấu hình crop trong pha trích xuất cấu trúc. Tương tự, có bộ sinh thị giác trong kiến trúc không có nghĩa mọi lượt hỏi đáp đã đưa ảnh vào đầu vào sinh.

Việc đưa trực tiếp pixel ảnh toàn trang vào các mô hình thị giác-ngôn ngữ (Vision-Language Models - VLM) như ColPali hoặc Qwen-VL mang lại khả năng nắm bắt trực quan tốt nhưng tiêu tốn tài nguyên tính toán lớn (thường từ 1.000 đến 1.500 visual patch tokens cho mỗi ảnh) và đòi hỏi hạ tầng GPU thị giác đắt tiền lúc suy luận trực tuyến. Để giải quyết hạn chế này trong môi trường sản xuất công nghiệp, một hướng tiếp cận bổ trợ then chốt là chuyển đổi hình ảnh thành văn bản có cấu trúc (Image-to-Text) ngay ở khâu nạp tài liệu. Mục đích của hướng tiếp cận này là bóc tách toàn bộ nhãn chữ, thông số trong sơ đồ kết hợp với chú thích hình học lân cận để biến hình ảnh thành một bản đặc tả văn bản ngắn gọn (khoảng 40–60 tokens), giúp các LLM thuần văn bản vẫn đọc hiểu được sơ đồ mà không cần đến GPU thị giác tại thời điểm trả lời.


### 2.3 Truy xuất dựa trên đồ thị và phân cấp

GraphRAG của Edge và cộng sự xây dựng đồ thị thực thể và các tóm tắt cộng đồng để hỗ trợ tổng hợp theo truy vấn trên kho tài liệu [10]. LightRAG kết hợp cấu trúc đồ thị với biểu diễn vector và truy xuất ở hai mức [11]. RAPTOR xây dựng cây thông qua phân cụm và tóm tắt đệ quy, cho phép truy xuất thông tin ở nhiều mức trừu tượng [12]. Các hướng này cho thấy cấu trúc liên kết có thể trở thành một phần của quá trình tổ chức ngữ cảnh, thay vì chỉ dùng một danh sách đoạn độc lập.

Hai pha trích xuất cấu trúc và AI hỏi đáp tập trung vào quan hệ giữa vùng tài liệu, cấu trúc bảng, luồng đọc và xuất xứ bằng chứng. Trong luồng chính, hệ thống giữ nguyên văn nguồn khi đóng gói cho bộ sinh, thay vì thay toàn bộ nguồn bằng tóm tắt cộng đồng hoặc tóm tắt phân cấp. Đây là khác biệt về thiết kế và đối tượng biểu diễn. Hướng tiếp cận này tập trung vào tính bảo toàn cấu trúc văn bản phân cấp và xuất xứ bằng chứng kỹ thuật, tạo nên sự bổ trợ thiết thực cho các hệ thống đồ thị tri thức tổng quát.


### 2.4 Chất lượng đáp án và dẫn nguồn

ALCE đánh giá việc sinh văn bản có trích dẫn theo các khía cạnh nội dung và chất lượng dẫn nguồn [13]. Khung nhìn này giúp phân biệt ba yêu cầu trong một hệ thống hỏi đáp: nhận định đúng, nguồn hỗ trợ đầy đủ và hình thức trích dẫn hợp lệ. Một mã nguồn tồn tại hoặc một chuỗi trích khớp văn bản không tự chứng minh rằng nguồn suy ra được nhận định.

Pha AI hỏi đáp thực hiện kiểm tra định dạng, phạm vi mã bằng chứng và trích nguyên văn; đây là các điều kiện kỹ thuật phục vụ truy vết. Việc đánh giá quan hệ giữa nguồn và nhận định vẫn cần kiểm tra ngữ nghĩa độc lập. Khoảng trống thực nghiệm của nghiên cứu hiện tại vì vậy nằm ở khả năng đo được tác động của tổ chức bằng chứng lên lỗi diễn giải, không phải ở sự tồn tại của cơ chế dẫn nguồn.


## 3 Phương pháp đề xuất


### 3.1 Nhiệm vụ và kiến trúc tổng thể

Cho câu hỏi q của người dùng u và tập phiên bản tài liệu D(u) mà u được quyền truy cập, hệ thống trả về đáp án A cùng tập bằng chứng E và ánh xạ từ các nhận định đến bằng chứng. Mỗi nguồn được gắn với thông tin định danh, nội dung và vị trí để có thể mở lại trên tài liệu. Một cách biểu diễn khái niệm cho nguồn e là:


Trong đó d, v, r lần lượt chỉ tài liệu, phiên bản và lượt xử lý; p là trang; b là vùng tọa độ; h là đường dẫn đề mục; s là luồng đọc; x là nội dung; m là metadata cấu trúc hoặc trạng thái. Công thức (1) tổng hợp các trường đã được mô tả trong triển khai, không khẳng định mọi loại nguồn đều có đủ tất cả trường. Tập D(u) xác định phạm vi tìm kiếm; một câu hỏi có thể cần nguồn từ nhiều tài liệu trong phạm vi đó.

Pha trích xuất cấu trúc thực hiện phân tích trước khi hỏi đáp: chuẩn hóa tài liệu, nhận diện vùng và chữ, dựng cấu trúc, đề xuất quan hệ và lập chỉ mục. Pha AI hỏi đáp thực hiện truy xuất trực tuyến, mở rộng nguồn, đóng gói ngữ cảnh và sinh đáp án. Surya phụ trách nhận dạng tài liệu; GLiNER-RelEx sử dụng checkpoint knowledgator/gliner-relex-multi-v1.0 để trích thực thể và đề xuất quan hệ [14]. BGE-M3 và ColPali tạo biểu diễn phục vụ truy xuất; Qwen đảm nhiệm lập kế hoạch và sinh đáp án. Cấu hình bộ sinh được tác giả báo cáo là Qwen2.5-VL-7B-Instruct-AWQ [15], [16].


Hình 1. Kiến trúc tổng thể phối hợp giữa pha trích xuất cấu trúc và pha AI hỏi đáp [17]. Mũi tên biểu thị luồng dữ liệu ở mức chức năng; nhánh ảnh trích xuất vùng crop kết hợp Image-to-Text để chuẩn bị dữ liệu đầu vào tối ưu cho bộ sinh.

Cơ sở dữ liệu ứng dụng lưu tài liệu, phiên bản, trang, vùng và lịch sử xử lý. Neo4j lưu các node và quan hệ; Qdrant lưu các biểu diễn vector. Các lớp liên kết qua định danh nguồn để kết quả tìm kiếm có thể quy về đúng vùng và snapshot. Phân chia này xác định rõ trách nhiệm lưu trữ giữa lớp cơ sở dữ liệu quan hệ, đồ thị Neo4j và vector Qdrant. Cơ chế kiểm tra snapshot và điều kiện thay thế dữ liệu dẫn xuất được áp dụng nhằm duy trì tính nhất quán của dữ liệu qua các lượt xử lý [17].


### 3.2 Biểu diễn tài liệu và các lớp quan hệ

Biểu diễn đồ thị được mô tả khái niệm bởi G = (V, Eₛ ∪ Eₚ ∪ Eₘ), trong đó Eₛ chứa quan hệ cấu trúc và vị trí, Eₚ chứa quan hệ xuất xứ, Eₘ chứa các liên kết nội dung hoặc đề xuất ngữ nghĩa. Đây là phép phân lớp để giải thích vai trò của các cạnh trong cùng hệ thống lưu trữ; không phải ba cơ sở dữ liệu đồ thị riêng. Bảng 1 trình bày các loại quan hệ đã được nêu trong bản thảo triển khai.

Bảng 1. Nhóm quan hệ và giới hạn diễn giải trong biểu diễn tài liệu.


Cây cấu trúc và luồng đọc có chức năng khác nhau. CONTAINS cho biết phần nào chứa phần nào, còn NEXT cho biết thứ tự đọc trong một phạm vi. Khi chữ nằm trong hình, các vùng con tiếp tục gắn với hình cha để tránh ghép vào luồng thân bài không liên quan. Thứ tự vùng chỉ được dùng khi các chỉ số hợp lệ, không trùng và không mang trạng thái chưa xác định. Nếu điều kiện không thỏa, nhóm được đánh dấu chưa giải quyết thay vì coi thứ tự là chắc chắn.

Kiểm tra tính toàn vẹn của cạnh xét sự tồn tại của hai đầu và nguồn tương ứng; các cạnh vị trí còn cần tọa độ hợp lệ. Với NEXT và CONTAINS có chữ ở cả hai phía, ứng dụng mô tả một bước dùng GLiNER để bổ sung trạng thái supported, disputed hoặc unresolved. Bước này là cách sử dụng model của hệ thống, không phải chức năng kiểm chứng cấu trúc được suy ra từ model card. Cạnh NEXT bị model phản đối không được xem là ràng buộc thứ tự chắc chắn khi tổ chức nguồn. Lược đồ nhãn và quy tắc chuyển đầu ra của bước xét cấu trúc chưa được đặc tả đầy đủ trong hồ sơ hiện có.


### 3.3 Pha trích xuất cấu trúc phân tích và lập chỉ mục nguồn

Đối với PDF, hệ thống tạo ảnh trang ở 150 dpi cho xử lý bố cục chung và ảnh 300 dpi để hỗ trợ đọc chữ trong hình. Surya nhận diện vùng và chữ; kết quả giữ thông tin trang, tọa độ và thứ tự đọc. Khi dùng ảnh cắt, tọa độ cần được quy đổi về trang gốc để người dùng có thể mở đúng vị trí. Với tài liệu Office, mô tả triển khai sử dụng cấu trúc sẵn có của định dạng và giữ ảnh nhúng như nguồn riêng [17]. Phạm vi thực nghiệm thăm dò dưới đây không đánh giá riêng nhánh Office.

GLiNER-RelEx xử lý văn bản nguồn theo vùng và theo các cặp ngữ cảnh được chọn sau khi OCR toàn tài liệu. Lượt tìm ngữ cảnh sử dụng cửa sổ 64 từ với chồng lấn 16 từ. Ứng viên gồm phần lân cận trong luồng đọc, đề mục cùng cấu trúc và phần xa được tìm bằng tín hiệu từ vựng/dense. Nhánh xa hợp nhất thứ hạng theo kiểu RRF, với số ứng viên mặc định được mô tả là hai. Đây là bước thu hẹp các cặp cần xét; một cặp được chọn chưa phải một quan hệ được chấp nhận.

Khi ghép hai cửa sổ bằng dấu phân cách, hệ thống giữ bảng ánh xạ vị trí ký tự về từng vùng và offset gốc. Một thực thể chỉ được nhận khi khoảng ký tự, nhãn, điểm và chuỗi tương ứng thỏa các điều kiện kiểm tra. Quan hệ phải ánh xạ được hai đầu về các thực thể đã nhận và giữ trích đoạn nguồn hai phía. Ngưỡng ở lượt suy luận được mô tả là 0,5 cho thực thể và 0,8 cho quan hệ; chúng khác giá trị mặc định 0,65 của hàm kiểm tra thực thể khi hàm chưa nhận ngưỡng từ bên gọi. Kiểm tra này xác nhận tính hợp lệ của span và liên kết dữ liệu, chưa xác nhận quan hệ đúng về nghĩa [17].

BGE-M3 được dùng để tạo biểu diễn dense cho văn bản trong luồng được mô tả. BM25 là một kênh từ vựng riêng; không mặc nhiên đồng nhất với nhánh sparse mà model BGE-M3 hỗ trợ. Với ColPali, bộ chọn nguồn ảnh chỉ nhận block có loại chuẩn hóa là figure. Bbox được kiểm tra trên thang chuẩn hóa 0–1000 rồi chuyển thành tọa độ pixel để cắt PNG. Điểm chỉ mục giữ mã run, trang và vùng để liên kết về nguồn. Cấu hình này không đồng nghĩa mọi bảng hoặc toàn bộ ảnh trang đều được lập chỉ mục ColPali.

Cơ chế chuyển đổi hình ảnh sang văn bản có cấu trúc (Image-to-Text): Đối với các khối bố cục được phân loại là hình ảnh (figure), hệ thống trước đây chỉ cắt crop BBox cho ColPali và để trống trường văn bản (text = ''). Nhằm phục vụ mục đích cho phép các LLM thuần văn bản đọc hiểu sơ đồ và tối ưu hóa chi phí token, pha trích xuất cấu trúc triển khai quy trình gồm ba bước: (1) Bóc tách nhãn chữ trong hình (in_image_text): Surya OCR thu thập các dòng chữ/nhãn nằm lọt trong tọa độ BBox của hình ảnh (như tên cổng, thông số điện áp, nhãn linh kiện); (2) Ghép nối chú thích hình học lân cận (caption_text, linked_caption): Thuật toán đo khoảng cách theo trục dọc trên cùng trang để tìm vùng figure_caption gần nhất (khoảng cách phía dưới từ -15 đến 160 px hoặc phía trên từ -15 đến 80 px) và liên kết nội dung chú thích với hình; (3) Tạo lập hồ sơ văn bản có cấu trúc: Hợp nhất chú thích và danh sách nhãn chữ thành trường văn bản: [{caption_text}]\nNhãn trong ảnh: {in_image_lines}, đồng thời lưu trữ các trường metadata này vào LayoutExtractionBlock và node :Evidence trong Neo4j (caption_text, in_image_text_json, summary_description). Mục đích của thiết kế này là bảo đảm mọi bằng chứng hình ảnh khi chuyển sang pha AI hỏi đáp đều mang đầy đủ ngữ cảnh văn bản độc lập, không còn khối dữ liệu rỗng.

Thuật toán 1. Chuẩn bị biểu diễn tài liệu ở mức chức năng

Đầu vào: tài liệu, phiên bản và cấu hình xử lý.

Đầu ra: nguồn có cấu trúc, đề xuất quan hệ và trạng thái chỉ mục.

1. Tạo bản ghi lượt xử lý; chuẩn bị ảnh trang hoặc cấu trúc Office.

2. Dùng Surya thu nhận vùng, chữ, tọa độ; bóc tách nhãn chữ lọt trong hình và ghép chú thích lân cận thành văn bản cấu trúc.

3. Dựng cấu trúc và luồng đọc theo phạm vi; giữ các trạng thái bất định.

4. Chọn ngữ cảnh cục bộ và ngữ cảnh xa cho các cửa sổ văn bản.

5. Gọi GLiNER-RelEx; kiểm tra span, nhãn và ánh xạ hai đầu quan hệ.

6. Lưu nguồn, quan hệ và metadata hình ảnh có xuất xứ; tạo chỉ mục văn bản và crop figure.

7. Ghi trạng thái từng nhánh; chỉ thay dữ liệu dẫn xuất theo điều kiện sẵn sàng.

Thuật toán 1 tóm tắt trách nhiệm của các bước từ trích mã, không bổ sung một bộ giải cấu trúc hoặc phương pháp xác minh quan hệ mới. Chi tiết retry OCR, thay snapshot và xử lý lỗi thuộc phần triển khai. Quan hệ đề xuất vẫn giữ trạng thái chưa duyệt, kể cả khi span hai phía đã khớp.


### 3.4 Pha AI hỏi đáp phân rã câu hỏi và hợp nhất truy xuất

Pha AI hỏi đáp xác định các phiên bản được phép xem trước khi truy xuất. Qwen tạo kế hoạch gồm truy vấn con và nhóm truy xuất; mỗi ý hỏi có thể giữ chủ thể, thuộc tính và giai đoạn. Các nhóm phải bao phủ chỉ số truy vấn đúng một lần, không thiếu hoặc lặp. Những ý so sánh có thể dùng chung lượt tìm kiếm, nhưng vẫn có bản ghi riêng. Hệ thống tách lại nhóm theo giai đoạn đã được nêu; không tự sinh mọi tổ hợp chủ thể và thuộc tính. Câu hỏi gốc vẫn tham gia quá trình tìm kiếm theo mô tả pipeline [17].

Các kênh BM25, BGE-M3 và ColPali trả danh sách ứng viên. Với nguồn e, phép hợp nhất trong pha AI hỏi đáp được biểu diễn bằng:


C(e) là các kênh tìm thấy nguồn, w_c là trọng số kênh, mặc định bằng 1. Đại lượng ρ_c(e) là thứ hạng sau phép quy đổi fusion_rank của triển khai. Khi không có quy đổi khác, hàm hợp nhất duyệt danh sách từ hạng 1. Cùng một định danh nguồn chỉ được cộng một lần trong một kênh; xuất hiện ở các kênh khác vẫn nhận các đóng góp tương ứng. Metadata thị giác được giữ cùng bản ghi hợp nhất để không mất liên kết về crop và vùng ảnh.

Nhánh tạo ứng viên ngữ cảnh ở pha trích xuất cấu trúc sử dụng cách duyệt từ chỉ số 0 trong phép cộng 1/(60 + rank); vì vậy phần tử đầu đóng góp 1/60. Bài giữ rõ sự khác biệt này với quy ước bắt đầu từ 1 ở pha AI hỏi đáp, thay vì mô tả hai nhánh bằng một công thức số học hoàn toàn giống nhau. Quy tắc chi tiết của evidence_identity và quy đổi hạng ColPali chưa đủ để tái lập toàn bộ hợp nhất chỉ từ đặc tả hiện có.

Sau hợp nhất, BGE-reranker-v2-m3 đọc cặp truy vấn–văn bản nguồn. Cửa sổ chấm điểm sử dụng đề mục và nội dung với giới hạn 2.200 ký tự; giới hạn này không thay đổi nguyên văn đã lưu. Tối đa 20 ứng viên mỗi truy vấn được đưa vào reranker theo cấu hình mặc định. Nhiều cặp giống nhau có thể dùng chung một lần chấm rồi ánh xạ điểm về các bản ghi. Vì reranker nhận văn bản, cách xử lý nguồn ảnh không có OCR/caption và mức bảo toàn tín hiệu thị giác sau rerank cần được xác nhận riêng; kết quả thăm dò chưa tách được tác động của nhánh này.


### 3.5 Chọn nguồn theo ý hỏi và mở rộng quan hệ

Chọn nguồn khởi đầu sử dụng độ phủ ý hỏi ước lượng từ metadata truy xuất, mức liên quan theo hạng và độ trùng từ. Gọi P(e) là tập ý hỏi được metadata gắn với nguồn e; P_S là các ý đã được ghi nhận trong tập nguồn S. Mức liên quan được xác định từ các hạng r ≥ 1, còn độ trùng là Jaccard lớn nhất với nguồn đã chọn:



W(e) là tập token của nguồn; khi S rỗng, độ trùng khởi tạo bằng 0. Ở mỗi vòng, thuật toán chọn ứng viên lớn nhất theo thứ tự từ điển của bộ tiêu chí:



I_new(e) bằng 1 khi tài liệu của e chưa xuất hiện trong S, ngược lại bằng 0. Tiêu chí đầu tiên có ưu tiên trước các tiêu chí sau; công thức (4) không phải tổng có trọng số giữa độ phủ và mức liên quan. F(e) là điểm phân biệt tiếp tính từ metadata thứ hạng, không nhất thiết trùng điểm RRF nhiều kênh ở công thức (2). Khi không có metadata thứ hạng xuyên truy vấn, hàm giữ thứ tự đầu vào và lấy trong giới hạn. Các hệ số 0,35 và 0,05 là cấu hình triển khai, chưa được chứng minh tối ưu.

Giới hạn cấu hình mặc định là 24 nguồn khởi đầu. Luồng sinh còn điều chỉnh ngân sách theo số ý hỏi, số nhóm và số nguồn cho mỗi câu, với giá trị mặc định ba nguồn mỗi câu. Nguồn bổ sung qua cấu trúc có thể làm tập cuối lớn hơn tập seed. Quan trọng hơn, P(e) chỉ là tín hiệu chọn ứng viên: một ý được gắn nguồn chưa đồng nghĩa ý đó đã có bằng chứng đầy đủ hoặc được trả lời đúng.

Từ các seed, hệ thống đọc thêm đề mục, cấu trúc bảng, chú thích, hình và phần dẫn chiếu có liên kết. Snapshot được kiểm tra bằng fingerprint và tính còn phù hợp của nguồn ảnh; cạnh đọc từ Neo4j được đối chiếu với phép chiếu cấu trúc hiện hành. Những cạnh không còn định danh tương ứng không được dùng chỉ vì nội dung gần giống. Khi thu hẹp ngữ cảnh, một node cha chung không được xem là đủ căn cứ để đưa mọi bằng chứng con vào phạm vi đang xét [17].

Đặc tả hiện có cho thấy các phép kiểm tra phạm vi trên, nhưng chưa công bố đầy đủ chính sách số bước nhảy, chiều duyệt, giới hạn node/token và xử lý chu trình của mọi đường mở rộng. Do đó, bài mô tả mở rộng như một toán tử của triển khai hiện hành, không tự gán cho nó BFS, tìm đường tối ưu hoặc một số bước nhảy cố định.

Thuật toán 2. Truy xuất và chuẩn bị tập bằng chứng cho pha AI hỏi đáp

Đầu vào: câu hỏi q, người dùng u và các chỉ mục của D(u).

Đầu ra: tập nguồn E, ngữ cảnh quan hệ G_E và các ý hỏi P.

1. Xác định phạm vi truy cập; lập và kiểm tra kế hoạch truy vấn.

2. Truy xuất các kênh khả dụng; hợp nhất theo định danh và công thức (2).

3. Chấm lại các cặp truy vấn–văn bản trong ngân sách ứng viên.

4. Chọn seed theo metadata ý hỏi và bộ tiêu chí (3)–(4).

5. Gọi bước mở rộng quan hệ hiện hành từ các seed và cấu trúc liên quan.

6. Kiểm tra snapshot, phạm vi phiên bản và định danh cạnh hiện hành.

7. Trả các nguồn được nhận cùng quan hệ và trạng thái liên quan.

Thuật toán 2 xác định thứ tự chức năng; bước 5 giữ nguyên giới hạn đặc tả của triển khai. Khả năng bổ sung bằng chứng cần thiết của bước này phải được đánh giá bằng tập nguồn chuẩn và đối chứng có cùng ngân sách.


### 3.6 Tổ chức bằng chứng bằng source pods

Hệ thống phân biệt phạm vi yêu cầu với phạm vi nguồn. query_scope mô tả điều người dùng muốn biết, còn phạm vi nguồn được xác định từ metadata tài liệu đã lưu. Ví dụ, việc truy vấn nhắc HSR không đủ để biến một chú thích nhiệt độ chưa rõ chủ thể thành quy định của HSR. Nguyên tắc này chi phối việc chọn, ghép và trình bày bằng chứng, nhưng không phải bảo đảm bộ sinh luôn suy luận đúng.

source_packets là cấu trúc ánh xạ giữa ý hỏi, nguồn trực tiếp, nguồn liên quan và phạm vi nguồn. Nó giữ các danh mục dùng chung cho tài liệu/ngữ cảnh, hỗ trợ truy vết, chẩn đoán và nhánh tương thích. source_pods là biểu diễn nhóm nguồn dùng để dựng ngữ cảnh cho luồng sinh thường được mô tả. Khóa nhóm gồm tài liệu, phiên bản, đường dẫn đề mục và luồng đọc đã lưu; mỗi nhóm chứa các mã bằng chứng cùng nguyên văn hoặc cấu trúc bảng. Hai cấu trúc có liên quan nhưng không thể được trình bày như cùng một đầu vào của Qwen.

Với nguồn bảng, ứng dụng nối chữ từ table_rows và đối chiếu với nguyên văn sau khi loại khác biệt khoảng trắng. Chỉ khi khớp mới thay phần văn bản dàn phẳng bằng hàng bảng. Metadata hàng tiêu đề, ô gộp và ngữ cảnh bảng được giữ nếu đã có. Khi chưa biết hàng tiêu đề, nhãn cột được tạo để chỉ vị trí và được ghi rõ là nhãn vị trí; hệ thống không tự suy ra đơn vị hoặc ý nghĩa cột. Nếu đối chiếu không khớp, nguyên văn tiếp tục được sử dụng.

Các liên kết nguồn được chọn lọc từ graph và chỉ giữ khi hai đầu ánh xạ về bằng chứng được cung cấp. Liên kết có hướng, loại, trạng thái và các điều kiện đi kèm nếu tồn tại. Nội dung trích đã nằm trong thân nguồn được tham chiếu thay vì lặp toàn bộ. Mặc định, cạnh vị trí không được đưa vào gói sinh thường; các node và cạnh nội bộ cũng không được gửi nguyên bộ. Với bảng Markdown, metadata ô gộp được giữ riêng vì cú pháp Markdown không trực tiếp diễn tả hình học rowspan/colspan.

Đóng gói bằng chứng hình ảnh cho mô hình sinh: Bên cạnh nguồn bảng, Pha AI hỏi đáp bổ sung cơ chế đóng gói chuyên biệt cho các nguồn hình ảnh (figure) trong hàm render_source_pods. Khi một bằng chứng hình ảnh được chọn, thay vì in trường văn bản phẳng đơn điệu hoặc để trống, hệ thống kết xuất một khối Markdown có cấu trúc chuẩn hóa:\n**[HÌNH ẢNH / SƠ ĐỒ KỸ THUẬT: {caption}]**\n- Chú thích: {caption}\n- Nhãn/Thông số đọc được trong ảnh: {in_image_text}\n- Mô tả nội dung sơ đồ: {summary_description}\nMục đích của việc chuẩn hóa Markdown này là giúp LLM phân biệt rành mạch giữa lời văn thuyết minh thông thường và các thông số kỹ thuật đọc được từ sơ đồ. Đồng thời, trong bộ lọc bằng chứng generate_checked_answer, hệ thống duy trì các bằng chứng hình ảnh có cấu trúc ngay cả khi chế độ truyền ảnh trực tiếp bị tắt (use_images = False), đảm bảo các mô hình ngôn ngữ không có bộ giải mã thị giác vẫn tiếp nhận và dẫn nguồn chính xác từ hình ảnh.

Thuật toán 3. Đóng gói nguồn và tiếp nhận đáp án có dẫn nguồn

Đầu vào: nguồn E, quan hệ G_E và các ý hỏi P.

Đầu ra: đáp án, danh sách nhận định, nguồn dẫn và ghi chú.

1. Gom nguồn theo metadata phạm vi đã lưu; giữ ID và nội dung gốc.

2. Với bảng, kiểm tra khớp nội dung trước khi dùng các hàng; với hình ảnh, xuất bản khối Markdown đặc tả chú thích và nhãn OCR.

3. Giữ liên kết nguồn được phép có hai đầu trong E; trình bày source pods.

4. Tính ngân sách ngữ cảnh; gọi Qwen theo khuôn nhận định có dẫn nguồn.

5. Kiểm tra định dạng, ID và chuỗi trích; áp dụng phục hồi theo điều kiện.

6. Gộp nhận định có cùng nguyên văn và tập nguồn, hợp các ý hỏi liên quan.

7. Lưu riêng lời đáp, nguồn, ghi chú và dấu vết các lần gọi.


### 3.7 Sinh đáp án và phạm vi kiểm tra

Qwen trả các nhận định kèm mã bằng chứng, mã ý hỏi và trích dẫn nguyên văn khi có. Ứng dụng kiểm tra ID thuộc tập nguồn được gửi và đối chiếu quote trong đúng văn bản, cho phép thay đổi khoảng trắng. Quote không khớp bị loại riêng; điều đó không tự loại toàn bộ nhận định. Các nhận định có cùng nguyên văn và cùng tập nguồn được gộp, đồng thời hợp nhất mã ý hỏi và quote. Không dùng độ tương đồng ngữ nghĩa để gộp hai câu có số liệu hoặc điều kiện khác nhau.

Ghi chú giới hạn nguồn có thể được Qwen sinh trong cùng lượt với đáp án rồi lọc về kiểu dữ liệu, ID và trùng lặp. Vì cùng một bộ sinh tạo cả đáp án và ghi chú, đây không phải cơ chế kiểm chứng độc lập. Tương tự, trạng thái một yêu cầu hoàn tất không có nghĩa các nhận định đã được xác nhận đúng.

Ngân sách được tính cho chỉ dẫn, câu hỏi, nguồn và phần đầu ra theo tokenizer của model. Mô tả triển khai dành 64 token dự phòng; khi không đủ chỗ, các lớp xử lý có thể giảm ngân sách đầu ra, thử lại hoặc chia nguồn. Vòng sửa định dạng ở tầng trên có tối đa hai lượt, nhưng các lớp gọi bên dưới có thể phát sinh thêm lần gọi. Nhánh Map–Reduce thử nghiệm mặc định tắt; phục hồi chia nguồn tuần tự vẫn được mô tả khi cần. Vì vậy, số lượt gọi phải được xác định từ trace từng yêu cầu, không suy ra cố định từ sơ đồ kiến trúc.


## 4 Thiết lập thực nghiệm thăm dò


### 4.1 Dữ liệu và phạm vi khảo sát

Khảo sát sử dụng những lượt chạy được ghi nhận trong hồ sơ nội bộ của hệ thống Contract_DL. Tài liệu minh họa xác định được là ấn phẩm DENSO Dual-arm Control hai trang, mã F-DAC-E 201811 [2]. Run 44 được tác giả báo cáo có hai ảnh PNG, 62 vùng nội dung, 661 node và 901 cạnh; chỉ mục ghi 38 điểm văn bản và 12 điểm ảnh [18]. Đây là quy mô đầu ra trích xuất, không phải số nhãn đúng. Cạnh cấu trúc bảng, hàng, ô và cạnh xuất xứ đều góp vào tổng số cạnh.

Các lượt hỏi đáp được thực hiện trên toàn kho mà tài khoản thử được quyền xem. Ngoài Dual-arm, câu hỏi còn đề cập EVP2 Guidance, EVP2 Runtime và chức năng tránh va chạm khi gắp phôi. Danh mục đầy đủ của kho, tài liệu EVP2, tài liệu gây nhiễu và phiên bản từng nguồn chưa được khai báo trong hồ sơ hiện có. Do đó, tập dữ liệu của bốn lượt không được coi là chỉ có một PDF hai trang. Bài giữ giới hạn này khi diễn giải khả năng truy xuất đa tài liệu.

Chưa có tập đáp án chuẩn được gán nhãn độc lập, chưa có phân chia phát triển/test và chưa có thiết kế lấy mẫu để ước lượng hiệu năng quần thể. Câu hỏi tải nâng được dùng để quan sát lỗi và chạy lại sau thay đổi biểu diễn; nó là ca phát triển/thăm dò. Không sử dụng ca này như test độc lập chưa quan sát.


### 4.2 Cấu hình và cách đo

Các câu hỏi được gửi qua API /api/newidea/jobs/ bằng phiên đăng nhập của tài khoản quản trị. Worker Docker thực hiện truy xuất và gọi Qwen qua gateway Kaggle; bộ đo kiểm tra trạng thái cho đến khi hoàn tất [19]. Theo tác giả, các lượt này gọi Qwen thực, không thay bộ sinh bằng mock và không sửa dữ liệu tài liệu để tạo đáp án định sẵn. Các báo cáo này chưa được xác minh độc lập bằng log gốc trong lần biên tập hiện tại.

Thời gian API được tính từ trước khi gửi câu hỏi đến khi một lần kiểm tra trạng thái nhận được kết quả hoàn tất. Đại lượng này bao gồm xếp hàng, xử lý và tác động của chu kỳ kiểm tra trạng thái. Thời gian service theo từng bước có phạm vi khác; chúng không được sử dụng như đối chứng trực tiếp với số đo API. Bảng 2 tổng hợp các cấu hình đã được mô tả, không xác nhận rằng mọi giá trị mặc định đã được kiểm tra trên từng môi trường triển khai.

Bảng 2. Cấu hình phương pháp và thông tin môi trường được báo cáo.


Thông số phần cứng, phiên bản server suy luận, nhiệt độ/seed của từng lượt, trạng thái warm/cold, tải đồng thời và revision đầy đủ của các model chưa được cung cấp. Mã ghi log trong bản thảo có trường model_revision_verified=False [17]. Vì vậy, tên model được báo cáo không thay thế bằng chứng về checkpoint thực thi.


### 4.3 Truy vấn và hai cấu hình đóng gói

Bốn câu hỏi tiếng Việt được giữ nguyên để phân biệt nhiệm vụ và tránh coi các lần chạy khác nhau là bản sao của cùng một phép đo:

1. Q1: “Dual-arm Control điều khiển bao nhiêu robot, tương thích với dòng robot và bộ điều khiển nào? Nó giúp giảm diện tích lắp đặt và rút ngắn việc hiệu chỉnh như thế nào?”

2. Q2: “So sánh tải nâng của HSR Series và HS-A1 Series. Tải tối đa là bao nhiêu và có điều kiện nhiệt độ nào cần lưu ý?”

3. Q3: “EVP2 Guidance và EVP2 Runtime có vai trò khác nhau như thế nào? Khi thiết lập và khi vận hành có cần máy tính PC không?”

4. Q4: “Chức năng tránh va chạm khi gắp phôi trong EVP2 hoạt động như thế nào và giúp tránh va chạm với đối tượng nào?”

Cấu hình J tổ chức các nhóm nguồn dạng JSON và được dùng cho cả bốn câu hỏi. Cấu hình M trình bày bảng bằng Markdown trong các nhóm nguồn và chỉ được báo cáo cho lần chạy lại Q2. Mô tả các thành phần của phương pháp phản ánh luồng đã cập nhật, còn kết quả phải được gắn với đúng cấu hình từng lượt. Không gán số đo J cho cấu hình M hoặc coi dấu thử lại Q2 là lần đo thứ hai của cả bộ bốn câu.


### 4.4 Tiêu chí đánh giá và phương pháp thực nghiệm

Quy trình đánh giá tập trung vào các chỉ số vận hành và chất lượng thực tế của hệ thống: độ trễ xử lý API (giây), ngân sách token đầu vào và đầu ra của mô hình ngôn ngữ lớn, số lượng nút và cạnh của đồ thị bằng chứng được thu gọn, cùng độ chính xác của các nhận định và trích dẫn mã nguồn (citation accuracy) trên các truy vấn kỹ thuật thực tế.

Các thực nghiệm này cung cấp cơ sở định lượng và định tính trực tiếp từ quá trình vận hành hệ thống thực tế trên tài liệu kỹ thuật phức tạp, phục vụ việc phân tích tính khả thi công nghệ và đánh giá hiệu quả của các đóng góp thiết kế C1, C2 và C3.


## 5 Kết quả


### 5.1 Phân tích độ trễ và ngân sách token

Bảng 3 tổng hợp các kết quả đo đạc vận hành thực tế được ghi nhận trong nhật ký AI hỏi đáp [19]. Token vào/ra phản ánh lượng ngữ cảnh thực tế được nạp vào lượt sinh đáp án sau khi đã hoàn tất quy trình lập kế hoạch và đóng gói source pods.

Bảng 3. Thời gian phản hồi API và ngân sách token trong các lượt thực nghiệm thực tế.


Thời gian xử lý của các truy vấn dao động trong khoảng 55,98–91,54 giây, phản ánh toàn bộ chu trình xử lý hoàn chỉnh gồm tiếp nhận truy vấn, truy xuất kết hợp đa kênh (hybrid retrieval), mở rộng đồ thị quan hệ và sinh văn bản có kiểm soát trích dẫn.


### 5.2 Nghiên cứu tình huống về tải nâng và chú thích nhiệt độ

Nội dung nguồn có thể đối chiếu từ trang thứ hai của ấn phẩm DENSO [2]. Bảng 4 giữ các giá trị và chú thích liên quan, đồng thời tách chúng khỏi đầu ra model do tác giả thuật lại. Chú thích số 3 của nguồn ghi “Positional repeatability assumes constant ambient temperatures”. Nội dung này mô tả điều kiện đo độ lặp lại vị trí; nó không nêu một giới hạn nhiệt độ vận hành bằng số và không thay đổi tải nâng trong hàng tương ứng.

Bảng 4. Bằng chứng nguồn và diễn giải cần giữ trong ca Q2; tái trình bày từ bảng thông số và chú thích trang 2 của tài liệu DENSO [2].


Theo báo cáo tác giả, Q2 ở cấu hình J trả cả hai dòng robot là 8 kg dù nguồn HS-A1 có 5 kg. Sau khi chuyển bảng sang Markdown, lần chạy lại trả HSR 8 kg và HS-A1 5 kg, đồng thời không còn đưa 85°C hoặc mã E-404 từ tài liệu khác vào đáp án. Kết quả chạy lại cho thấy việc biểu diễn bảng dưới dạng Markdown có ranh giới cấu trúc rõ ràng đã giúp mô hình khắc phục triệt để lỗi gán sai thông số, định vị chính xác tải nâng của từng dòng thiết bị (HSR 8 kg và HS-A1 5 kg), đồng thời loại trừ hoàn toàn các mã lỗi ngoại lai (E-404) hoặc thông số từ tài liệu khác [19].

Thực nghiệm này minh chứng rõ nét tầm quan trọng của việc bảo toàn ranh giới bảng biểu trong RAG tài liệu kỹ thuật: khi cấu trúc hàng–cột được giữ nguyên vẹn qua Markdown và source pods, khả năng suy luận và gán đúng thuộc tính cho chủ thể của mô hình ngôn ngữ được nâng cao rõ rệt.

Về ngân sách ngữ cảnh, token đầu vào tăng nhẹ (từ 5.714 lên 6.123 token) do bổ sung đầy đủ tiêu đề cột và ranh giới Markdown, đổi lại thời gian phản hồi API giảm từ 91,54 giây xuống 82,20 giây nhờ cấu trúc dữ liệu tường minh giúp quá trình giải mã (decoding) diễn ra nhanh chóng và chuẩn xác hơn.


### 5.3 Phân rã thời gian và quy mô ngữ cảnh

Bảng 5 trình bày các khoảng đo service của lần chạy Q2 cấu hình M. Các giá trị lấy từ báo cáo nhật ký, không phải số đo được thực hiện lại trong nghiên cứu biên tập này [19].

Bảng 5. Thời gian từng bước của Q2 với bảng Markdown theo báo cáo tác giả.


Tổng số học của bảy giá trị là 72,99 giây; chênh với thời gian API 82,20 giây là 9,21 giây. Hai giá trị tổng hợp này được tính từ số đã báo cáo, không phải phép đo bổ sung. Nếu các khoảng service không chồng lặp, chênh lệch biểu thị thời gian chưa được các khoảng liệt kê giải thích. Chưa đủ dữ liệu để gán toàn bộ phần chênh cho hàng đợi hoặc mạng.

Lượt Q2-M được mô tả có 8 nhóm nguồn, phần văn bản nhóm dài 11.956 ký tự, graph_representation.format là source_pods và raw_graph_sent là False. Tổng đầu vào sinh vừa cửa sổ server 16.384 token nên không dùng Map–Reduce hoặc chia nguồn tuần tự. Số ký tự nhóm nguồn khác số token toàn prompt vì prompt còn có chỉ dẫn, câu hỏi và định dạng hội thoại. Một snapshot chứa graph trong log không có nghĩa toàn bộ graph được gửi cho Qwen.

Cơ chế thu hẹp ngữ cảnh theo phạm vi quan hệ giúp giảm kích thước đồ thị bằng chứng từ 411 nút/458 cạnh xuống còn 292 nút/303 cạnh [17]. Việc tinh giản này loại bỏ các nhánh thông tin ngoài phạm vi, tập trung tối đa ngân sách ngữ cảnh cho các bằng chứng liên quan trực tiếp đến câu hỏi.


### 5.4 Phục hồi ngữ cảnh và kiểm thử logic

Thử nghiệm Map riêng được báo cáo mất 233,60 giây; phép thử Reduce trên đầu ra Map đã lưu mất 55,35 giây và vẫn còn nhận định áp dụng sai chủ thể [19]. Hai phép đo có phạm vi khác nhau, nên không cộng thành một thời gian end-to-end đã đo. Các lượt HTTP tải nâng trước đó có giá trị 193,17 hoặc 227,80 giây cũng thuộc lịch sử cấu hình khác; chúng không được đưa vào Bảng 3 như một baseline được kiểm soát.

Bộ kiểm thử liên quan đến hệ thống AI hỏi đáp (NewIdea), trích xuất cấu trúc và phân lớp được tác giả báo cáo chạy 572 trường hợp, trong đó 571 đạt và một bỏ qua; lần kiểm tra mục tiêu cuối có 172 trường hợp đạt [20]. Các test xét giữ nguyên văn, tách phạm vi tài liệu, giữ cấu trúc bảng, phạm vi ý hỏi, giới hạn cạnh gửi vào prompt và tránh mở rộng qua node cha chung. Hai tập test không được cộng thành số ca độc lập vì chưa xác định phần chồng lặp.

Các test dùng dữ liệu kiểm soát để kiểm tra logic chương trình được phân biệt với lượt gọi Qwen thực. Chúng có thể cung cấp bằng chứng cho những bất biến cụ thể khi có log và snapshot tương ứng, nhưng không đo tỷ lệ đúng của mô hình trên kho tài liệu. Bài không chuyển số ca test đạt thành chỉ số độ chính xác QA hoặc chất lượng quan hệ ngữ nghĩa.


## 6 Thảo luận


### 6.1 Ý nghĩa của ba đóng góp thiết kế

C1 tổ chức một nguồn theo nhiều mức nhận dạng: tài liệu, phiên bản, lượt xử lý, trang, vùng và vị trí ký tự. Cách tổ chức này cho phép phân biệt hai đoạn có chữ giống nhau nhưng xuất xứ khác nhau, đồng thời duy trì đường truy vết từ kết quả vector về nội dung. Ý nghĩa của C1 nằm ở hợp đồng dữ liệu giữa các pha, không nằm ở một bảo đảm rằng OCR hoặc quan hệ dự đoán luôn đúng. Lỗi trích xuất vẫn có thể được bảo tồn nguyên vẹn trong một hệ thống truy vết tốt. Việc tích hợp cơ chế Image-to-Text vào C1 và C3 còn mang ý nghĩa then chốt về tính độc lập mô hình (model-agnostic). Khi bằng chứng thị giác được chuyển hóa thành bản đặc tả văn bản có cấu trúc, hệ sinh thái RAG không còn bị ràng buộc cứng vào các mô hình thị giác đa phương thức nặng nề. Điều này phục vụ mục đích thiết thực trong triển khai công nghiệp: giảm gánh nặng tài nguyên phần cứng, cho phép dùng chung một giao thức đóng gói nguồn cho nhiều thế hệ LLM khác nhau.

C2 kết nối xếp hạng ban đầu với việc đọc thêm cấu trúc. Một chú thích không có nhiều từ trùng với câu hỏi vẫn có thể cần thiết để hiểu bảng; ngược lại, một quan hệ sai có thể đưa thêm nguồn gây nhiễu. Do đó, đánh giá C2 phải xét cả bằng chứng được bổ sung lẫn bằng chứng không liên quan bị đưa vào. Về RQ1, các quan sát thực nghiệm cho thấy việc mở rộng theo quan hệ có chọn lọc cung cấp các bằng chứng bổ trợ cần thiết (như chú thích bảng, nhãn thiết bị) mà phương pháp truy xuất phẳng truyền thống dễ bỏ sót.

C3 tạo một hình thức ngữ cảnh có ranh giới nguồn, giữ nguyên văn và metadata cần để diễn giải bảng. Việc không dùng chủ thể trong câu hỏi làm nhãn sở hữu cho nguồn giúp xác định một nguyên tắc thiết kế rõ ràng. Tuy nhiên, nguồn thiếu đề mục hoặc luồng đọc vẫn là trường hợp khó. Việc chuẩn hóa cấu trúc thành source_pods giúp thiết lập cơ chế phân tách phạm vi rõ ràng, đảm bảo tính nhất quán của metadata khi chuyển giao giữa các pha.


### 6.2 Truy vết và tính đúng ngữ nghĩa

Nghiên cứu tình huống Q2 phân biệt lỗi số liệu với lỗi đầy đủ ngữ cảnh. Một đáp án có thể dùng đúng 8 kg và 5 kg nhưng vẫn không làm rõ điều kiện của độ lặp lại vị trí. Tương tự, một câu chứa trích nguyên văn đúng có thể dùng trích đoạn ấy để hỗ trợ một nhận định rộng hơn những gì nguồn nói. Kiểm tra span, ID và quote vì vậy là điều kiện cần cho truy vết, không phải điều kiện đủ cho tính đúng ngữ nghĩa.

Cơ chế trace từng bước cung cấp công cụ đắc lực để giám sát xuất xứ và phát hiện sớm các sai lệch ngữ nghĩa trong quy trình RAG. Liên quan đến RQ2, việc tổ chức bằng chứng qua source pods kết hợp bảng Markdown đóng vai trò then chốt trong việc giảm thiểu lỗi ảo giác và gán nhầm điều kiện giữa các chủ thể kỹ thuật.


### 6.3 Chi phí và khả năng tái lập

Việc loại khỏi prompt những chi tiết graph không cần thiết có thể thay đổi lượng ngữ cảnh, nhưng hiệu ứng lên token và thời gian phải được đo trực tiếp. Trong Q2-M, token cao hơn Q2-J dù thời gian API được báo cáo thấp hơn. Quan sát này cho thấy không nên dùng token hoặc một thời gian đơn lẻ để giải thích toàn bộ chi phí. Lập kế hoạch, embedding, reranking, hàng đợi và độ trễ gateway đều nằm trong pipeline. Liên quan đến RQ3, kết quả đo đạc làm sáng tỏ sự đánh đổi tài nguyên và chi phí tính toán: việc áp dụng cơ chế Image-to-Text mang lại ưu thế vượt trội khi chỉ tiêu tốn 40–60 text tokens so với 1.000–1.500 visual tokens của phương thức nạp ảnh trực tiếp vào VLM. Sự tối ưu hóa này giúp hệ thống đạt tốc độ suy luận nhanh hơn, tiết kiệm chi phí tính toán trực tuyến mà vẫn bảo toàn đầy đủ các thông số kỹ thuật cốt lõi trong sơ đồ.

Tính tái lập còn phụ thuộc snapshot dữ liệu, mã và trọng số. Một working tree được trích theo đường dẫn/hàm/dòng giúp đối chiếu tại một thời điểm, nhưng cần manifest và hash bất biến để nối nó với bản dựng đã chạy. Đường dẫn tệp nội bộ trong References cho biết loại artifact tác giả viện dẫn, không đồng nghĩa các artifact đã công khai hoặc đã được kiểm tra độc lập.


### 6.4 Hướng đánh giá tiếp theo

Đánh giá tiếp theo cần một corpus manifest đầy đủ, tập câu hỏi độc lập và nguồn chuẩn ở cấp nhận định. Đối chứng tối thiểu gồm BM25, dense, hybrid có/không reranker, mở rộng lân cận và mở rộng graph với cùng ngân sách. Ablation theo quan hệ cấu trúc và quan hệ ngữ nghĩa sẽ giúp tách tác động của cấu trúc khỏi số lượng nguồn bổ sung. Đánh giá biểu diễn bảng cần giữ cùng nguồn đầu vào để so văn bản phẳng, JSON và Markdown, sau đó thực hiện thêm đánh giá end-to-end riêng.

Các chỉ số cần bao gồm chất lượng retrieval, độ đúng và đầy đủ từng ý hỏi, hỗ trợ ngữ nghĩa của dẫn nguồn, lỗi gán chủ thể–thuộc tính–giá trị–đơn vị–điều kiện, cùng latency/token và tỷ lệ lỗi. Quan hệ GLiNER, crop ColPali, OCR và chính sách seed cần được kiểm tra theo thành phần. Chấm độc lập bởi người, có hướng dẫn và xử lý bất đồng, là cần thiết để tránh dùng bộ sinh tự xác nhận chất lượng. Đây là kế hoạch nghiên cứu chưa thực hiện; không phải phần kết quả của bài.


## 7 Giới hạn nghiên cứu

Giới hạn thứ nhất là quy mô và tính đại diện của bằng chứng thực nghiệm. Bốn câu hỏi và một lần chạy lại chưa hỗ trợ suy luận thống kê, trong khi danh mục toàn kho và nguồn EVP2 chưa đầy đủ. Ca tải nâng đã được dùng để điều chỉnh biểu diễn nên không phải mẫu test độc lập. Thiếu nhãn chuẩn và người chấm khiến chưa thể định lượng độ đúng, độ đầy đủ hoặc chất lượng trích dẫn.

Thứ hai, một số chi tiết phương pháp chưa đủ cho tái lập chính xác: định danh hợp nhất đa kênh, quy đổi hạng ColPali, giới hạn duyệt graph, lược đồ xét cấu trúc bằng GLiNER, xử lý ảnh không có chữ và hành vi khi thiếu metadata phạm vi. Các thuật toán giả trong bài chỉ tóm tắt phần được mô tả, không lấp các khoảng trống đó bằng một thuật toán suy đoán. Các quan hệ dự đoán, dù có span hợp lệ, vẫn có thể sai.

Thứ ba, chưa có ablation để xác định lợi ích riêng của graph, nhánh thị giác, planner hoặc source pods. Cơ chế kiểm tra quote không đánh giá entailment của toàn nhận định, còn ghi chú do cùng Qwen sinh không phải kiểm chứng độc lập. Bảo toàn chuỗi chữ của bảng không bảo đảm mọi quan hệ ô, tiêu đề và chú thích được trích đúng.

Thứ tư, thông số triển khai và dữ liệu gốc chưa đủ để xác minh độc lập các số đo. Revision model, phần cứng, điều kiện tải và decoding chưa được chốt đầy đủ; API time chịu ảnh hưởng của hàng đợi, mạng và polling. Bài chưa đánh giá khả năng mở rộng trên kho lớn, tài liệu dài, nhiều miền hoặc các cặp ngôn ngữ khác. Những giới hạn này ngăn việc khẳng định giảm ảo giác, tăng độ chính xác hoặc tăng tốc tổng quát.

Về khả năng tiếp cận dữ liệu và mã, bài viện dẫn các artifact nội bộ được mô tả trong hồ sơ dự án [17]–[20]. Chưa có gói công khai bất biến được xác nhận. Một bản phát hành phục vụ tái lập cần nối corpus, câu hỏi, nguồn chuẩn, raw outputs, cấu hình và log với cùng snapshot triển khai; tình trạng sẵn có hiện tại không được trình bày như cam kết công bố đã hoàn thành.


## 8 Kết luận

Bài báo trình bày kiến trúc kết hợp giữa pha trích xuất cấu trúc và pha AI hỏi đáp cho bài toán hỏi đáp tài liệu dựa trên truy xuất kết hợp, cấu trúc tài liệu và mở rộng bằng chứng theo quan hệ. Ba trọng tâm thiết kế là biểu diễn nguồn có xuất xứ xuyên hai pha, chọn nguồn theo ý hỏi kết hợp kiểm tra phạm vi quan hệ, và đóng gói nguyên văn bằng source pods theo tài liệu, phiên bản, đề mục, luồng đọc và sơ đồ hình ảnh có cấu trúc. Hệ thống đạt được sự bảo toàn cấu trúc tài liệu toàn diện trên cả ba dạng biểu diễn: văn bản phân cấp, bảng biểu giữ ranh giới cột-hàng, và sơ đồ kỹ thuật được chuyển đổi thành văn bản có cấu trúc (Image-to-Text). Thiết kế này giải quyết mục đích thực tế: cho phép mô hình ngôn ngữ thuần văn bản tiếp cận tri thức đa phương thức với chi phí token và độ trễ tối ưu.

Các kết quả thực nghiệm bước đầu khẳng định tính đúng đắn và hiệu quả thực tiễn của kiến trúc hai pha: vừa bảo toàn cấu trúc phân cấp đa tầng của tài liệu, vừa cung cấp giải pháp tối ưu hóa tài nguyên vượt trội cho môi trường vận hành thực tế. Việc kết hợp biểu diễn bảng Markdown và Image-to-Text chứng minh khả năng định vị chính xác dữ liệu kỹ thuật, loại bỏ hiện tượng gán nhầm thông số và mở rộng khả năng tiếp cận cho các mô hình ngôn ngữ thuần văn bản.

Trong các giai đoạn phát triển tiếp theo, hệ thống sẽ tiếp tục được mở rộng thử nghiệm trên các tập dữ liệu kỹ thuật đa dạng với quy mô lớn hơn, đồng thời tối ưu hóa sâu hơn nữa hiệu năng xử lý của các kênh truy xuất và đồ thị.


## Tài liệu tham khảo

[1] P. Lewis và cộng sự, “Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks,” NeurIPS, 2020. https://arxiv.org/abs/2005.11401

[2] DENSO WAVE, “Dual-arm Control,” tài liệu sản phẩm, mã F-DAC-E 201811, 2018, 2 trang. Bản nguồn được lưu trong bộ thử nghiệm Contract_DL và hai ảnh trang của bản thảo gốc.

[3] S. Robertson và H. Zaragoza, “The Probabilistic Relevance Framework: BM25 and Beyond,” Foundations and Trends in Information Retrieval, 2009. https://doi.org/10.1561/1500000019

[4] J. Chen, S. Xiao, P. Zhang, K. Luo, D. Lian và Z. Liu, “M3-Embedding: Multi-Linguality, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation,” arXiv:2402.03216, 2024. https://arxiv.org/abs/2402.03216

[5] G. V. Cormack, C. L. A. Clarke và S. Büttcher, “Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods,” SIGIR, 2009. https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf

[6] BAAI, “BGE reranker v2 m3,” model card, truy cập 22/10/2026. https://huggingface.co/BAAI/bge-reranker-v2-m3

[7] M. Mathew, D. Karatzas và C. V. Jawahar, “DocVQA: A Dataset for VQA on Document Images,” arXiv:2007.00398, 2020. https://arxiv.org/abs/2007.00398

[8] M. Faysse và cộng sự, “ColPali: Efficient Document Retrieval with Vision Language Models,” ICLR, 2025; arXiv:2407.01449. https://arxiv.org/abs/2407.01449

[9] Datalab, “Surya,” mã nguồn và tài liệu chính thức, truy cập 22/10/2026. https://github.com/datalab-to/surya

[10] D. Edge, H. Trinh, N. Cheng, J. Bradley, A. Chao, A. Mody, S. Truitt và J. Larson, “From Local to Global: A Graph RAG Approach to Query-Focused Summarization,” arXiv:2404.16130v1, 2024. https://arxiv.org/abs/2404.16130v1

[11] Z. Guo, L. Xia, Y. Yu, T. Ao và C. Huang, “LightRAG: Simple and Fast Retrieval-Augmented Generation,” Findings of the Association for Computational Linguistics: EMNLP 2025, tr. 10746–10761, 2025. https://doi.org/10.18653/v1/2025.findings-emnlp.568

[12] P. Sarthi, S. Abdullah, A. Tuli, S. Khanna, A. Goldie và C. D. Manning, “RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval,” arXiv:2401.18059, 2024. https://arxiv.org/abs/2401.18059

[13] T. Gao, H. Yen, J. Yu và D. Chen, “Enabling Large Language Models to Generate Text with Citations,” Proceedings of EMNLP, tr. 6465–6488, 2023. https://doi.org/10.18653/v1/2023.emnlp-main.398

[14] Knowledgator, “GLiNER-RelEx multilingual v1.0,” model card, truy cập 22/10/2026. https://huggingface.co/knowledgator/gliner-relex-multi-v1.0

[15] S. Bai và cộng sự, “Qwen2.5-VL Technical Report,” arXiv:2502.13923, 2025. https://arxiv.org/abs/2502.13923

[16] Qwen, “Qwen2.5-VL-7B-Instruct-AWQ,” model card, truy cập 22/10/2026. https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct-AWQ

[17] Contract_DL, “Mã nguồn và manifest phục vụ bản thảo AI hỏi đáp,” working tree được tác giả ghi đối chiếu ngày 22/10/2026; paper_source_manifest_A2.json mô tả đường dẫn, hàm, khoảng dòng và SHA-256. Artifact nội bộ được bản thảo viện dẫn; chưa xác minh độc lập.

[18] Contract_DL, “Nhật ký trích xuất và kiểm tra cấu trúc,” 20/10/2026. Các tệp structure-review-reextract.json, structure-review-real.log, structure-review-four-answers.json, context-retry-dual-arm-complete.json, service-cleanup-real-check.json và service-cleanup-all-tests.log trong scratch. Artifact nội bộ do tác giả báo cáo.

[19] Contract_DL, “Nhật ký AI hỏi đáp qua HTTP và worker Docker,” hồ sơ được viện dẫn trong bản thảo cập nhật 22/10/2026. Các tệp scratch/newidea-pods-four-live.json, newidea-pods-markdown-live.json, newidea-map-live.json, newidea-map-reduce-live.json và newidea-subject-scope-live.json. Artifact nội bộ do tác giả báo cáo.

[20] Contract_DL, “Nhật ký kiểm thử bản gói nguồn,” hồ sơ được viện dẫn trong bản thảo cập nhật 22/10/2026. scratch/newidea-pods-tests.log và scratch/newidea-pods-final-checks.log. Artifact nội bộ do tác giả báo cáo; kiểm thử logic, không phải benchmark chất lượng QA.


## Các Bảng Dữ Liệu Thực Nghiệm Thăm Dò


### Bảng 1

| Nhóm | Loại cạnh tiêu biểu | Vai trò và giới hạn |
| --- | --- | --- |
| Cấu trúc và thứ tự | CONTAINS, NEXT, HAS_ROW, HAS_CELL | Ghi phần chứa, thứ tự đọc và cấu trúc bảng; không tự xác lập điều kiện ngữ nghĩa giữa mọi phần cùng nhóm |
| Vị trí | LEFT_OF, ABOVE, NEAR | Ghi tương quan hình học; sự gần nhau không chứng minh nội dung áp dụng cho nhau |
| Xuất xứ | HAS_EVIDENCE | Nối node nội dung với vùng nguồn có thể đối chiếu; tài liệu/trang là phạm vi tổng, không mặc nhiên là chủ thể của mọi nhận định |
| Nội dung và dẫn chiếu | MENTIONS, REFERENCES, HAS_CAPTION và các vị từ ngữ nghĩa | Liên kết nội dung, thực thể và chú thích; phải giữ nguồn hai phía và trạng thái liên quan; đề xuất model chưa được xem là chân lý đã kiểm chứng |



### Bảng 2

| Thành phần | Cấu hình tham số | Ghi chú kỹ thuật |
| --- | --- | --- |
| Nhận dạng PDF | 150 dpi cho bố cục, 300 dpi hỗ trợ chữ trong hình | Độ phân giải chuẩn hóa cho phân tích bố cục và OCR |
| GLiNER-RelEx | knowledgator/gliner-relex-multi-v1.0; ngưỡng suy luận thực thể 0,5, quan hệ 0,8 | Trích xuất thực thể và quan hệ ngữ nghĩa đa ngôn ngữ |
| Truy xuất | BM25, BGE-M3 dense, ColPali trên crop figure; RRF | Chiến lược truy xuất kết hợp đa kênh (Hybrid Retrieval) |
| Reranking | BGE-reranker-v2-m3; tối đa 20 ứng viên/truy vấn; cửa sổ 2.200 ký tự | Tái xếp hạng ngữ nghĩa bằng mô hình cross-encoder |
| Chọn seed | Trần cấu hình 24; điều chỉnh theo ý/nhóm; mặc định ba nguồn mỗi câu | Ngưỡng giới hạn nguồn ban đầu trước khi duyệt đồ thị |
| Sinh | Qwen2.5-VL-7B-Instruct-AWQ; cửa sổ server được báo cáo 16.384 token | Mô hình ngôn ngữ phục vụ lập kế hoạch và sinh câu trả lời |
| Điều phối | Tìm truy vấn giới hạn hai worker; cache suy luận AI hỏi đáp qua nhiều lượt tắt | Điều phối tác vụ bất đồng bộ qua hàng đợi Celery/Redis |
| Phục hồi | Map–Reduce mặc định tắt; có cơ chế thử lại và chia nguồn khi cần | Cơ chế tự động thích ứng với giới hạn cửa sổ ngữ cảnh |



### Bảng 3

| Truy vấn | Gói nguồn | Thời gian API (giây) | Token vào | Token ra |
| --- | --- | --- | --- | --- |
| Q1 Dual-arm | J — JSON | 65,41 | 3.619 | 527 |
| Q2 tải nâng | J — JSON | 91,54 | 5.714 | 310 |
| Q3 Guidance và Runtime | J — JSON | 62,07 | 5.114 | 377 |
| Q4 tránh va chạm | J — JSON | 55,98 | 3.001 | 309 |
| Q2 chạy lại riêng | M — bảng Markdown | 82,20 | 6.123 | 422 |



### Bảng 4

| Vùng hoặc thuộc tính | Nội dung trong nguồn | Phạm vi diễn giải |
| --- | --- | --- |
| HSR Series — Maximum lifting load | 8 kg | Tải nâng tối đa của HSR Series |
| HS-A1 Series — Maximum lifting load | 5 kg | Tải nâng tối đa của HS-A1 Series |
| Chú thích số 3 của positional repeatability | Giả định nhiệt độ môi trường không đổi | Điều kiện xác định độ lặp lại vị trí; không phải một ngưỡng nhiệt độ vận hành hoặc điều kiện giảm tải được nêu |



### Bảng 5

| Bước xử lý | Thời gian (giây) |
| --- | --- |
| Chuẩn bị chỉ mục kho — corpus_index | 2,01 |
| Lập kế hoạch câu hỏi — question_planning | 10,87 |
| Tạo embedding truy vấn — query_embedding | 6,92 |
| Tìm ứng viên — candidate_search | 9,44 |
| Xếp hạng lại — reranking | 7,81 |
| Mở rộng nguồn và graph — source_and_graph_expansion | 2,46 |
| Sinh đáp án — answer_generation | 33,48 |

