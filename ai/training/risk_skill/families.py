"""Clause/provision pairs that teach the risk-reading skill, not the law.

Every sample puts the provision in the brief, and the label follows from what that provision says: the same clause is
a conflict under one limit and compliant under another, and fine where the law lets the parties agree otherwise. A model
trained on such pairs has to read the supplied law; one that memorised "20%/năm" fails the changed-law twins.

Labels are computed from the generated values, so they are right by construction. This is data preparation; at run
time the model still decides.

Topic groups:
  max / min     a numeric ceiling or floor; the clause's value is on either side of it or on it
  default       the law sets a value "unless agreed otherwise": any agreed value is not a conflict
  form          a mandatory form (written, notarised); the clause keeps or drops it
  ban           a prohibited act; the clause allows or forbids it
  unclear       a vague clause (no determinable time, price, quality): a drafting suggestion, not a conflict
HOLDOUT topics appear only in the evaluation set, so it measures the skill on subjects never trained on.
"""
import random
import re

# A provision's status exactly as the run time writes it (knowledge_repository.legal_note, else the status itself).
# A repealed text ("Hết hiệu lực") never reaches a brief: the search reads only texts in force and uploads.
IN_FORCE = 'Còn hiệu lực'
PARTLY_REPEALED = 'Tình trạng: Hết hiệu lực một phần. Các điều của văn bản này có thể không còn áp dụng nguyên văn.'
UPLOADED_NOTE = 'Tài liệu do người dùng tải lên; hiệu lực chưa được xác minh.'
STATUSES = [IN_FORCE] * 8 + [PARTLY_REPEALED] * 2 + [UPLOADED_NOTE]
DOC_NAMES = ['Dân sự', 'Thương mại', 'Nhà ở', 'Lao động', 'Kinh doanh bất động sản', 'Xây dựng', 'Bảo vệ quyền lợi người tiêu dùng',
             'Đầu tư', 'Các tổ chức tín dụng', 'Đấu thầu']
TITLES = ['Hợp đồng vay tiền', 'Hợp đồng mua bán hàng hóa', 'Hợp đồng thuê nhà', 'Hợp đồng lao động', 'Hợp đồng thi công xây dựng',
          'Hợp đồng cung cấp dịch vụ', 'Hợp đồng đại lý', 'Hợp đồng mua bán căn hộ']
COMPANIES = ['Công ty TNHH An Phát', 'Công ty Cổ phần Minh Long', 'Công ty TNHH Thương mại Hà Thành', 'Ông Nguyễn Văn Bình',
             'Bà Trần Thị Mai', 'Công ty Cổ phần Xây dựng Sông Hồng', 'Công ty TNHH Dịch vụ Sao Việt', 'Ông Lê Hoàng Nam']
FILLERS = ['Các bên cam kết thực hiện đúng nội dung điều này.', 'Mọi thay đổi phải được hai bên thống nhất bằng văn bản.',
           'Điều khoản này có hiệu lực kể từ ngày ký hợp đồng.', '']

# Numeric ceilings (max) and floors (min). law: the provision sentence; clause: the contract sentence; value(rng, limit,
# side): a value below, on or above the limit; text(v): how the clause writes it; amount(v): what is compared.
NUMERIC = {
    'interest': dict(kind='max', law_title='Lãi suất', limits=(10, 15, 20, 24),
        law='Trường hợp các bên có thỏa thuận về lãi suất thì lãi suất theo thỏa thuận không được vượt quá {limit}%/năm của khoản tiền vay.',
        clause_title='Lãi suất', clause='Lãi suất cho vay là {value} tính trên dư nợ gốc.', subject='lãi suất', unit='%/năm',
        category='Lãi suất vượt mức tối đa', party='Bên vay', level='HIGH'),
    'penalty': dict(kind='max', law_title='Mức phạt vi phạm', limits=(5, 8, 10, 12),
        law='Mức phạt đối với vi phạm nghĩa vụ hợp đồng do các bên thoả thuận trong hợp đồng, nhưng không quá {limit}% giá trị phần nghĩa vụ hợp đồng bị vi phạm.',
        clause_title='Phạt vi phạm', clause='Bên vi phạm phải chịu phạt {value} giá trị phần nghĩa vụ hợp đồng bị vi phạm.',
        subject='mức phạt', unit='%', category='Mức phạt vượt mức tối đa', party='Bên vi phạm', level='HIGH'),
    'advance': dict(kind='max', law_title='Tạm ứng hợp đồng', limits=(15, 20, 30, 50),
        law='Mức tạm ứng hợp đồng không vượt quá {limit}% giá trị hợp đồng tại thời điểm ký kết.',
        clause_title='Tạm ứng', clause='Bên giao thầu tạm ứng cho Bên nhận thầu {value} giá trị hợp đồng ngay sau khi ký.',
        subject='mức tạm ứng', unit='%', category='Mức tạm ứng vượt mức cho phép', party='Bên giao thầu', level='MEDIUM'),
    'probation': dict(kind='max', law_title='Thời gian thử việc', limits=(6, 30, 60, 180),
        law='Thời gian thử việc do hai bên thỏa thuận căn cứ vào tính chất và mức độ phức tạp của công việc nhưng chỉ được thử việc một lần và không quá {limit} ngày.',
        clause_title='Thử việc', clause='Thời gian thử việc của người lao động là {value} kể từ ngày bắt đầu làm việc.',
        subject='thời gian thử việc', unit=' ngày', category='Thời gian thử việc vượt mức tối đa', party='Người lao động', level='HIGH'),
    'refund': dict(kind='max', law_title='Hoàn trả tiền cho người tiêu dùng', limits=(7, 15, 30, 45),
        law='Tổ chức, cá nhân kinh doanh phải hoàn trả tiền cho người tiêu dùng trong thời hạn không quá {limit} ngày kể từ ngày nhận được yêu cầu.',
        clause_title='Hoàn tiền', clause='Bên bán hoàn trả tiền cho Bên mua trong vòng {value} kể từ ngày nhận được yêu cầu.',
        subject='thời hạn hoàn tiền', unit=' ngày', category='Thời hạn hoàn tiền vượt mức cho phép', party='Bên mua', level='MEDIUM'),
    'notice': dict(kind='min', law_title='Đơn phương chấm dứt hợp đồng', limits=(15, 30, 45, 60),
        law='Bên đơn phương chấm dứt thực hiện hợp đồng phải thông báo bằng văn bản cho bên kia trước ít nhất {limit} ngày.',
        clause_title='Chấm dứt hợp đồng', clause='Mỗi bên có quyền đơn phương chấm dứt hợp đồng với điều kiện thông báo bằng văn bản trước {value}.',
        subject='thời hạn báo trước', unit=' ngày', category='Thời hạn báo trước ngắn hơn mức tối thiểu', party='Bên bị chấm dứt hợp đồng', level='HIGH'),
    'warranty': dict(kind='min', law_title='Thời hạn bảo hành', limits=(12, 24, 36, 60),
        law='Thời hạn bảo hành công trình không ít hơn {limit} tháng kể từ ngày nghiệm thu đưa công trình vào sử dụng.',
        clause_title='Bảo hành', clause='Bên nhận thầu bảo hành công trình trong thời hạn {value} kể từ ngày nghiệm thu.',
        subject='thời hạn bảo hành', unit=' tháng', category='Thời hạn bảo hành ngắn hơn mức tối thiểu', party='Bên giao thầu', level='HIGH'),
    'complaint': dict(kind='min', law_title='Thời hạn khiếu nại', limits=(10, 30, 60, 90),
        law='Thời hạn khiếu nại về số lượng hàng hóa không ít hơn {limit} ngày kể từ ngày giao hàng.',
        clause_title='Khiếu nại', clause='Bên mua chỉ được khiếu nại về số lượng hàng hóa trong vòng {value} kể từ ngày giao hàng.',
        subject='thời hạn khiếu nại', unit=' ngày', category='Thời hạn khiếu nại ngắn hơn mức tối thiểu', party='Bên mua', level='MEDIUM'),
    # Also on real law (Luật Thương mại Điều 222, Bộ luật Dân sự Điều 260), see build.REAL_LAW.
    'bid_security': dict(kind='max', law_title='Bảo đảm dự thầu', limits=(1, 2, 3, 5),
        law='Tỷ lệ tiền đặt cọc, ký quỹ dự thầu do bên mời thầu quy định, nhưng không quá {limit}% tổng giá trị ước tính của hàng hoá, dịch vụ đấu thầu.',
        clause_title='Bảo đảm dự thầu', clause='Bên dự thầu nộp tiền đặt cọc dự thầu bằng {value} tổng giá trị ước tính của gói thầu.',
        subject='tiền bảo đảm dự thầu', unit='%', category='Bảo đảm dự thầu vượt mức tối đa', party='Bên dự thầu', level='MEDIUM'),
    'usufruct': dict(kind='max', law_title='Thời hạn của quyền hưởng dụng', limits=(10, 20, 30, 50),
        law='Thời hạn của quyền hưởng dụng do các bên thỏa thuận nhưng tối đa {limit} năm nếu người hưởng dụng là pháp nhân.',
        clause_title='Thời hạn hưởng dụng', clause='Bên hưởng dụng là pháp nhân được hưởng dụng tài sản trong thời hạn {value} kể từ ngày ký hợp đồng.',
        subject='thời hạn hưởng dụng', unit=' năm', category='Thời hạn hưởng dụng vượt mức tối đa', party='Bên có tài sản', level='MEDIUM'),
    # Evaluation only.
    'performance_security': dict(kind='max', law_title='Bảo đảm thực hiện hợp đồng', limits=(5, 10, 15),
        law='Số tiền đặt cọc, ký quỹ bảo đảm thực hiện hợp đồng do bên mời thầu quy định, nhưng không quá {limit}% giá trị hợp đồng.',
        clause_title='Bảo đảm thực hiện hợp đồng', clause='Bên trúng thầu nộp tiền ký quỹ bảo đảm thực hiện hợp đồng bằng {value} giá trị hợp đồng.',
        subject='tiền bảo đảm thực hiện hợp đồng', unit='%', category='Bảo đảm thực hiện hợp đồng vượt mức tối đa', party='Bên trúng thầu', level='MEDIUM'),
    'auction_deposit': dict(kind='max', law_title='Đăng ký tham gia đấu giá', limits=(1, 2, 5),
        law='Người tổ chức đấu giá có thể yêu cầu người tham gia đấu giá nộp một khoản tiền đặt trước, nhưng không quá {limit}% giá khởi điểm của hàng hoá được đấu giá.',
        clause_title='Tiền đặt trước', clause='Người tham gia đấu giá nộp khoản tiền đặt trước bằng {value} giá khởi điểm của hàng hóa.',
        subject='tiền đặt trước', unit='%', category='Tiền đặt trước đấu giá vượt mức tối đa', party='Người tham gia đấu giá', level='MEDIUM'),
    'deposit': dict(kind='max', law_title='Tiền đặt cọc thuê nhà', limits=(1, 2, 3, 6),
        law='Tiền đặt cọc để bảo đảm thực hiện hợp đồng thuê nhà ở không được vượt quá {limit} tháng tiền thuê.',
        clause_title='Đặt cọc', clause='Bên thuê đặt cọc cho Bên cho thuê số tiền tương đương {value} tiền thuê.',
        subject='tiền đặt cọc', unit=' tháng', category='Tiền đặt cọc vượt mức tối đa', party='Bên thuê', level='MEDIUM'),
    'overtime': dict(kind='max', law_title='Làm thêm giờ', limits=(20, 40, 60),
        law='Số giờ làm thêm của người lao động không quá {limit} giờ trong 01 tháng.',
        clause_title='Làm thêm giờ', clause='Người lao động làm thêm theo yêu cầu của Bên A tối đa {value} mỗi tháng.',
        subject='số giờ làm thêm', unit=' giờ', category='Số giờ làm thêm vượt mức tối đa', party='Người lao động', level='HIGH'),
    'rent_notice': dict(kind='min', law_title='Điều chỉnh giá thuê', limits=(30, 60, 90),
        law='Bên cho thuê phải thông báo cho bên thuê trước ít nhất {limit} ngày trước khi điều chỉnh giá thuê.',
        clause_title='Giá thuê', clause='Bên cho thuê được điều chỉnh giá thuê sau khi thông báo cho Bên thuê trước {value}.',
        subject='thời hạn thông báo', unit=' ngày', category='Thời hạn thông báo ngắn hơn mức tối thiểu', party='Bên thuê', level='MEDIUM'),
}
# The parties may agree otherwise: no clause value conflicts with these.
DEFAULT = {
    'pay_term': dict(law_title='Thời hạn thanh toán',
        law='Bên mua phải thanh toán tiền mua theo thời hạn thỏa thuận; trường hợp không có thỏa thuận thì bên mua phải thanh toán tại thời điểm nhận hàng.',
        clause_title='Thanh toán', clause='Bên mua thanh toán toàn bộ giá trị hợp đồng trong vòng {n} ngày kể từ ngày nhận hàng.'),
    'penalty_free': dict(law_title='Thỏa thuận phạt vi phạm',
        law='Mức phạt vi phạm do các bên thỏa thuận, trừ trường hợp luật liên quan có quy định khác.',
        clause_title='Phạt vi phạm', clause='Bên vi phạm phải chịu phạt {n}% giá trị hợp đồng.'),
    'warranty_default': dict(law_title='Thời hạn bảo hành',
        law='Trường hợp các bên không có thỏa thuận khác, thời hạn bảo hành hàng hóa là {d} tháng kể từ ngày giao hàng.',
        clause_title='Bảo hành', clause='Bên bán bảo hành hàng hóa trong thời hạn {n} tháng kể từ ngày giao hàng.'),
    'place': dict(law_title='Địa điểm giao hàng',
        law='Địa điểm giao hàng do các bên thỏa thuận; trường hợp không có thỏa thuận thì địa điểm giao hàng là nơi cư trú hoặc trụ sở của bên mua.',
        clause_title='Giao hàng', clause='Bên bán giao hàng tại kho của Bên bán ở Khu công nghiệp số {n}.'),
    # Provisions that leave the matter to the parties: a clause that settles it is fine, one that leaves it open is a
    # drafting point (see UNCLEAR), never a conflict. The skill is telling the two apart, not knowing the law.
    'acceptance': dict(law_title='Nghiệm thu',
        law='Việc nghiệm thu được thực hiện theo thỏa thuận của các bên về thời điểm, nội dung và tiêu chí nghiệm thu.',
        clause_title='Nghiệm thu', clause='Hai bên tiến hành nghiệm thu trong vòng {n} ngày kể từ ngày bàn giao, theo tiêu chí kỹ thuật tại Phụ lục 01.'),
    'compensation': dict(law_title='Bồi thường thiệt hại',
        law='Bên vi phạm phải bồi thường thiệt hại do hành vi vi phạm gây ra; mức và cách tính bồi thường do các bên thỏa thuận.',
        clause_title='Bồi thường thiệt hại', clause='Bên vi phạm bồi thường toàn bộ thiệt hại thực tế, được tính theo hóa đơn và chứng từ hợp lệ, trong vòng {n} ngày kể từ ngày nhận yêu cầu.'),
    'price_change': dict(law_title='Điều chỉnh giá hợp đồng',
        law='Giá hợp đồng chỉ được điều chỉnh trong các trường hợp và theo phương pháp các bên đã thỏa thuận trong hợp đồng.',
        clause_title='Điều chỉnh giá', clause='Giá hợp đồng được điều chỉnh khi chỉ số giá vật liệu do cơ quan thống kê công bố tăng quá {n}% so với ngày ký.'),
    # Also on real law (Bộ luật Dân sự Điều 454). d: the fallback value the provision names.
    'redemption': dict(law_title='Chuộc lại tài sản đã bán', d=(1, 2, 3),
        law='Thời hạn chuộc lại tài sản do các bên thoả thuận; trường hợp không có thỏa thuận thì thời hạn chuộc lại không quá {d} năm đối với động sản kể từ thời điểm giao tài sản.',
        clause_title='Chuộc lại tài sản', clause='Bên bán được quyền chuộc lại tài sản đã bán trong thời hạn {n} tháng kể từ ngày giao tài sản.'),
    # Evaluation only (also on real law: Luật Thương mại Điều 318).
    'complaint_terms': dict(law_title='Thời hạn khiếu nại', d=(1, 3, 6),
        law='Thời hạn khiếu nại do các bên thỏa thuận, nếu các bên không có thoả thuận thì thời hạn khiếu nại về số lượng hàng hoá là {d} tháng kể từ ngày giao hàng.',
        clause_title='Khiếu nại', clause='Bên mua được khiếu nại về số lượng hàng hóa trong vòng {n} ngày kể từ ngày giao hàng.'),
}
# A mandatory form or a ban: a breaking and a keeping wording of the same clause.
RULED = {
    'notarise': dict(group='form', law_title='Hình thức hợp đồng mua bán nhà ở',
        law='Hợp đồng mua bán nhà ở phải được công chứng hoặc chứng thực.', clause_title='Hiệu lực hợp đồng',
        breaks='Hai bên thống nhất hợp đồng có hiệu lực ngay khi ký mà không cần công chứng hoặc chứng thực.',
        keeps='Hợp đồng được công chứng tại tổ chức hành nghề công chứng và có hiệu lực từ ngày công chứng.',
        category='Hợp đồng không tuân thủ hình thức bắt buộc', party='Cả hai bên', level='HIGH',
        why='bỏ yêu cầu công chứng hoặc chứng thực', rule='hợp đồng mua bán nhà ở phải được công chứng hoặc chứng thực'),
    'written_labour': dict(group='form', law_title='Hình thức hợp đồng lao động',
        law='Hợp đồng lao động phải được giao kết bằng văn bản và được làm thành 02 bản, người lao động giữ 01 bản.',
        clause_title='Giao kết hợp đồng', breaks='Hai bên giao kết hợp đồng lao động bằng lời nói và không lập văn bản.',
        keeps='Hợp đồng lao động được lập thành 02 bản bằng văn bản, mỗi bên giữ 01 bản.',
        category='Hợp đồng không được lập bằng văn bản', party='Người lao động', level='HIGH',
        why='cho phép giao kết bằng lời nói', rule='hợp đồng lao động phải được giao kết bằng văn bản'),
    'arbitration_form': dict(group='form', law_title='Hình thức thỏa thuận trọng tài',
        law='Thỏa thuận trọng tài phải được xác lập dưới dạng văn bản.', clause_title='Giải quyết tranh chấp',
        breaks='Các bên thỏa thuận bằng miệng về việc đưa tranh chấp ra giải quyết tại trọng tài.',
        keeps='Thỏa thuận đưa tranh chấp ra giải quyết tại trọng tài được lập thành văn bản là phụ lục của hợp đồng này.',
        category='Thỏa thuận trọng tài không có hình thức văn bản', party='Cả hai bên', level='HIGH',
        why='chỉ thỏa thuận trọng tài bằng miệng', rule='thỏa thuận trọng tài phải được xác lập dưới dạng văn bản'),
    'pledge': dict(group='ban', law_title='Xử lý tài sản cầm cố',
        law='Trường hợp giá trị của tài sản bảo đảm lớn hơn giá trị của nghĩa vụ được bảo đảm thì bên nhận bảo đảm phải thanh toán số tiền chênh lệch cho bên bảo đảm.',
        clause_title='Tài sản bảo đảm', breaks='Khi Bên vay chậm trả, Bên cho vay được sở hữu tài sản cầm cố mà không phải thanh toán phần chênh lệch.',
        keeps='Khi xử lý tài sản cầm cố, Bên cho vay phải thanh toán cho Bên vay phần chênh lệch giữa giá trị tài sản và số tiền còn nợ.',
        category='Không thanh toán phần chênh lệch khi xử lý tài sản bảo đảm', party='Bên vay', level='HIGH',
        why='cho bên nhận bảo đảm giữ tài sản mà không trả phần chênh lệch', rule='bên nhận bảo đảm phải thanh toán số tiền chênh lệch'),
    'early_demand': dict(group='ban', law_title='Thực hiện hợp đồng vay có kỳ hạn',
        law='Đối với hợp đồng vay có kỳ hạn và có lãi thì bên cho vay chỉ được đòi lại tài sản trước kỳ hạn nếu được bên vay đồng ý.',
        clause_title='Trả nợ trước hạn', breaks='Bên cho vay có quyền yêu cầu Bên vay trả toàn bộ khoản vay bất kỳ lúc nào mà không cần sự đồng ý của Bên vay.',
        keeps='Bên cho vay chỉ được yêu cầu trả nợ trước hạn khi Bên vay đồng ý bằng văn bản.',
        category='Đòi nợ trước hạn trái quy định', party='Bên vay', level='HIGH',
        why='cho bên cho vay đòi nợ trước hạn không cần bên vay đồng ý', rule='bên cho vay chỉ được đòi trước kỳ hạn nếu bên vay đồng ý'),
    'id_papers': dict(group='ban', law_title='Hành vi người sử dụng lao động không được làm',
        law='Người sử dụng lao động không được giữ bản chính giấy tờ tùy thân, văn bằng, chứng chỉ của người lao động.',
        clause_title='Giấy tờ của người lao động', breaks='Bên A giữ bản chính căn cước công dân và văn bằng của người lao động trong suốt thời hạn hợp đồng.',
        keeps='Bên A chỉ lưu bản sao căn cước công dân và văn bằng của người lao động.',
        category='Giữ bản chính giấy tờ của người lao động', party='Người lao động', level='HIGH',
        why='cho người sử dụng lao động giữ bản chính giấy tờ tùy thân', rule='người sử dụng lao động không được giữ bản chính giấy tờ tùy thân'),
    # Evaluation only.
    'entry': dict(group='ban', law_title='Quyền của bên thuê nhà',
        law='Bên cho thuê không được vào nhà ở đang cho thuê khi chưa được bên thuê đồng ý, trừ trường hợp khẩn cấp.',
        clause_title='Kiểm tra nhà', breaks='Bên cho thuê được vào nhà bất kỳ lúc nào để kiểm tra mà không cần báo trước cho Bên thuê.',
        keeps='Bên cho thuê chỉ vào nhà để kiểm tra khi Bên thuê đồng ý, trừ trường hợp khẩn cấp.',
        category='Vào nhà cho thuê khi chưa được đồng ý', party='Bên thuê', level='MEDIUM',
        why='cho bên cho thuê vào nhà bất kỳ lúc nào', rule='bên cho thuê không được vào nhà khi chưa được bên thuê đồng ý'),
}
# Vague clauses next to a provision on the same subject: a drafting suggestion.
UNCLEAR = {
    'pay_vague': dict(law='pay_term', clause_title='Thanh toán', clause='Bên mua thanh toán cho Bên bán trong thời gian hợp lý sau khi nhận hàng.',
        category='Thời hạn thanh toán không xác định', why='không xác định được thời hạn thanh toán cụ thể', party='Bên bán'),
    'price_vague': dict(law='pay_term', clause_title='Giá', clause='Giá hàng hóa được xác định theo giá thị trường tại thời điểm giao hàng.',
        category='Giá chưa được xác định', why='giá chưa được xác định và có thể hiểu khác nhau giữa các bên', party='Bên mua'),
    'delivery_vague': dict(law='place', clause_title='Giao hàng', clause='Bên bán giao hàng cho Bên mua khi có điều kiện.',
        category='Thời điểm giao hàng không xác định', why='không xác định được thời điểm giao hàng', party='Bên mua'),
    'quality_vague': dict(law='warranty_default', clause_title='Chất lượng', clause='Hàng hóa phải đạt chất lượng tốt theo đánh giá của Bên bán.',
        category='Tiêu chuẩn chất lượng không rõ ràng', why='tiêu chuẩn chất lượng phụ thuộc đánh giá của một bên', party='Bên mua'),
    'accept_vague': dict(law='acceptance', clause_title='Nghiệm thu', clause='Công trình được nghiệm thu khi đạt yêu cầu của Bên giao thầu.',
        category='Tiêu chí nghiệm thu không xác định', why='không nêu yêu cầu cụ thể để nghiệm thu, việc nghiệm thu phụ thuộc ý chí của một bên',
        party='Bên nhận thầu'),
    'comp_vague': dict(law='compensation', clause_title='Bồi thường thiệt hại', clause='Bên vi phạm bồi thường cho bên kia một khoản phù hợp với mức độ vi phạm.',
        category='Mức bồi thường không xác định', why='không xác định được mức hoặc cách tính khoản bồi thường', party='Bên bị vi phạm'),
    'adjust_vague': dict(law='price_change', clause_title='Điều chỉnh giá', clause='Bên bán có quyền điều chỉnh giá khi cần thiết và thông báo cho Bên mua.',
        category='Điều kiện điều chỉnh giá không rõ ràng', why='không nêu trường hợp và cách điều chỉnh giá, để một bên tự quyết định',
        party='Bên mua'),
    'later_vague': dict(law='pay_term', clause_title='Thanh toán', clause='Các nội dung khác về thanh toán sẽ do hai bên thỏa thuận sau.',
        category='Nội dung thanh toán để ngỏ', why='để lại nội dung thanh toán cho một thỏa thuận sau mà không nêu thời hạn hay cách xác định',
        party='Bên bán'),
    # Evaluation only.
    'rent_vague': dict(law='pay_term', clause_title='Tiền thuê', clause='Bên thuê trả tiền thuê theo định kỳ phù hợp với khả năng của Bên thuê.',
        category='Kỳ thanh toán tiền thuê không xác định', why='không xác định được kỳ và thời hạn trả tiền thuê', party='Bên cho thuê'),
    'scope_vague': dict(law='acceptance', clause_title='Phạm vi công việc', clause='Bên B thực hiện các công việc khác theo yêu cầu của Bên A.',
        category='Phạm vi công việc không xác định', why='không xác định được phạm vi công việc Bên B phải thực hiện', party='Bên B'),
}
# Evaluation-only topics of every kind (ceiling, ban, agreed-otherwise, vague, cross-clause), so the evaluation
# measures the skill on subjects never trained on.
HOLDOUT = {'deposit', 'overtime', 'rent_notice', 'entry', 'rent_vague', 'performance_security', 'auction_deposit',
           'complaint_terms', 'scope_vague', 'rent_price_twice'}


def number(v):
    """Vietnamese decimal comma: 2.5 -> '2,5'."""
    return (f'{v:.2f}'.rstrip('0').rstrip('.') if v != int(v) else str(int(v))).replace('.', ',')


class Maker:
    def __init__(self, rng, split='train'):
        self.rng = rng
        self.split = split

    def pick(self, options, key=None):
        """One wording. Each list of wordings is cut in three: most for training, a part only the validation set
        uses and a part only the evaluation set uses, so both measure wordings never trained on. Holdout topics
        appear only in evaluation and use every wording."""
        if len(options) < 5 or key in HOLDOUT:
            return self.rng.choice(options)
        k = len(options) // 5
        return self.rng.choice({'train': options[:-2 * k], 'valid': options[-2 * k:-k], 'eval': options[-k:]}[self.split])

    def law_template(self, key, t):
        return self.pick([t['law'], *LAW_VARIANTS.get(key, [])], key)

    def sentence(self, key, base, variants):
        """A clause sentence: one of its wordings, now and then after an opening phrase."""
        core = self.pick([base, *variants.get(key, [])], key)
        lead = self.rng.choice(LEADS)
        return lead + core[0].lower() + core[1:] if lead else core

    def document(self):
        kind, suffix = self.rng.choice([('Luật', 'QH'), ('Bộ luật', 'QH'), ('Nghị định', 'NĐ-CP')])
        year = self.rng.randint(2005, 2034)
        tail = f'QH{self.rng.randint(11, 16)}' if suffix == 'QH' else suffix
        name = f'{kind} {self.rng.choice(DOC_NAMES)} số {self.rng.randint(10, 160)}/{year}/{tail}'
        return f'LAW-{self.rng.randint(10000, 99999)} — {name}', name

    def law(self, title, text):
        """A provision as retrieve_batch hands it to the brief."""
        stored, name = self.document()
        article = self.rng.randint(5, 480)
        heading = f'Chương {self.rng.choice(["II", "III", "IV", "V", "VI", "VII"])} {self.rng.choice(["QUY ĐỊNH CHUNG", "HỢP ĐỒNG", "NGHĨA VỤ CỦA CÁC BÊN", "BẢO ĐẢM THỰC HIỆN NGHĨA VỤ"])}'
        return dict(source_id=f'S{self.rng.randint(1, 10**6)}', document=stored, status=self.rng.choice(STATUSES), heading=heading,
                    clause_title=f'Điều {article}. {title}', text=f'Điều {article}. {title}\n{text}', name=name, article=article)

    def article_body(self, key, rule):
        """Now and then the rule is one paragraph of a long article (several numbered paragraphs, up to the 2,400
        characters the run time keeps per provision), so the answer has to quote that paragraph, not the article."""
        if self.rng.random() >= LONG_ARTICLE_SHARE:
            return rule
        own = [text for _, text in HARD.get(key, [])]
        # 4-14 sentences grouped 1-3 per paragraph: about 600 to 2,300 characters around the rule.
        sentences = self.rng.sample(ARTICLE_PARAGRAPHS, self.rng.randint(4, 14))
        others = []
        while sentences:
            size = self.rng.randint(1, 3)
            others.append(' '.join(sentences[:size]))
            sentences = sentences[size:]
        paragraphs = own + others
        self.rng.shuffle(paragraphs)
        paragraphs.insert(self.rng.randint(0, len(paragraphs)), rule)
        while len('\n'.join(paragraphs)) > 2300 and len(paragraphs) > 2:
            paragraphs.remove(next(p for p in paragraphs if p != rule))
        return '\n'.join(f'{i}. {p}' for i, p in enumerate(paragraphs, 1))

    def clause(self, title, sentence):
        filler = self.rng.choice(FILLERS)
        number_ = self.rng.randint(2, 15)
        content = f'Điều {number_}. {title}\n{sentence}' + (f' {filler}' if filler else '')
        return dict(id=number_, title=f'Điều {number_}. {title}', content=content)

    # --- one clause with its provision and the expected answer -------------------------------------------------
    def numeric(self, key, side=None, limit=None):
        t = NUMERIC[key]
        limit = limit if limit is not None else self.rng.choice(t['limits'])
        side = side or self.rng.choice(['over', 'over', 'on', 'under'])
        value, shown = self.numeric_value(key, t, limit, side)
        template = self.law_template(key, t)
        rule = template.format(limit=number(limit))
        law = self.law(t['law_title'], self.article_body(key, rule))
        sentence = self.sentence(key, t['clause'], CLAUSE_VARIANTS).format(value=shown)
        clause = self.clause(t['clause_title'], sentence)
        breaks = value > limit if t['kind'] == 'max' else value < limit
        extra = f' (tương đương {number(value)}%/năm)' if key == 'interest' and '/tháng' in shown else ''
        expect = dict(group=t['kind'], topic=key, conflict=breaks, unclear=False, limit=limit, value=value, law_template=template,
                      shown=f'{shown}{extra}', law_rule=rule)
        if not breaks:
            return clause, law, None, expect
        ref = f'Điều {law["article"]} {law["name"]}'
        explanation = numeric_explanation(self.rng, t, clause['title'], f'{shown}{extra}', limit, ref)
        risk = dict(category=t['category'], risk_level=numeric_level(t, value, limit), explanation=explanation,
                    recommendation=numeric_fix(self.rng, t, value, limit, clause['title'], ref),
                    disadvantaged_party=t['party'], contract_quote=sentence, law_quote=rule, kind='conflict')
        return clause, law, risk, expect

    def numeric_value(self, key, t, limit, side):
        if key == 'interest':
            monthly = self.rng.random() < .6
            annual = {'over': limit + self.rng.choice([4, 6, 12, 36, 40]), 'on': limit, 'under': max(1, limit - self.rng.choice([2, 4, 6]))}[side]
            if monthly and (annual / 12) * 100 == int((annual / 12) * 100):
                return annual, f'{number(annual / 12)}%/tháng'
            return annual, f'{number(annual)}%/năm'
        step = max(1, round(limit * self.rng.choice([.25, .5, 1])))
        value = {'over': limit + step, 'on': limit, 'under': max(1, limit - step)}[side]
        if t['kind'] == 'min':
            value = {'over': max(1, limit - step), 'on': limit, 'under': limit + step}[side]  # 'over' = breaks
        return value, f'{number(value)}{t["unit"]}'

    def default(self, key):
        t = DEFAULT[key]
        n = self.rng.choice([1, 3, 5, 7, 10, 15, 20, 30, 45, 60])
        law = self.law(t['law_title'], t['law'].format(d=number(self.rng.choice(t.get('d', (6, 12, 24))))))
        clause = self.clause(t['clause_title'], self.sentence(key, t['clause'], DEFAULT_VARIANTS).format(n=n))
        return clause, law, None, dict(group='default', topic=key, conflict=False, unclear=False)

    def ruled(self, key, breaks=None):
        t = RULED[key]
        breaks = self.rng.random() < .6 if breaks is None else breaks
        law = self.law(t['law_title'], self.article_body(key, t['law']))
        wordings = RULED_VARIANTS.get(key, {})
        sentence = (self.pick([t['breaks'], *wordings.get('breaks', [])], key) if breaks
                    else self.pick([t['keeps'], *wordings.get('keeps', [])], key))
        clause = self.clause(t['clause_title'], sentence)
        expect = dict(group=t['group'], topic=key, conflict=breaks, unclear=False)
        if not breaks:
            return clause, law, None, expect
        ref = f'Điều {law["article"]} {law["name"]}'
        risk = dict(category=t['category'], risk_level=t['level'],
                    explanation=f'{clause["title"]} {t["why"]}, trái với {ref}: {t["rule"]}.',
                    recommendation=ruled_fix(self.rng, t), disadvantaged_party=t['party'],
                    contract_quote=sentence, law_quote=t['law'], kind='conflict')
        return clause, law, risk, expect

    def unclear(self, key):
        t = UNCLEAR[key]
        law = self.default(t['law'])[1]
        sentence = self.pick([t['clause'], *UNCLEAR_VARIANTS.get(key, [])], key)
        clause = self.clause(t['clause_title'], sentence)
        # A fix that quotes words of the clause only fits the wording that has those words.
        fixes = [f for f in UNCLEAR_FIX.get(key, []) + UNCLEAR_GENERIC_FIX
                 if all(q in sentence for q in re.findall(r'"([^"]+)"', f))]
        risk = dict(category=t['category'], risk_level='LOW', explanation=self.rng.choice(UNCLEAR_EXPLANATIONS).format(
                        title=clause['title'], why=t['why']),
                    recommendation=self.rng.choice(fixes), disadvantaged_party=t['party'],
                    contract_quote=sentence, law_quote='', kind='unclear')
        return clause, law, risk, dict(group='unclear', topic=key, conflict=False, unclear=True)

    def distractors(self, exclude, holdout):
        """Provisions on other subjects, as retrieval also returns."""
        pool = [k for k in (*NUMERIC, *RULED, *DEFAULT) if k != exclude and (holdout or k not in HOLDOUT)]
        out = []
        for key in self.rng.sample(pool, self.rng.choice([0, 1, 1, 2])):
            if key in NUMERIC:
                t = NUMERIC[key]
                out.append(self.law(t['law_title'], self.article_body(key, self.law_template(key, t).format(limit=number(self.rng.choice(t['limits']))))))
            elif key in RULED:
                out.append(self.law(RULED[key]['law_title'], self.article_body(key, RULED[key]['law'])))
            else:
                out.append(self.default(key)[1])
        return out

    def hard(self, topic):
        """Provisions on the clause's own subject that set no rule the clause can break."""
        return [self.law(title, text) for title, text in HARD.get(topic, [])]


# --------------------------------------------------------------------------- risk rule catalog
# The kinds of risk the administrator's catalog names (contracts.RiskRule). A brief lists some of them; a risk is
# filed under the rule that describes it, or OTHER when the listed rules do not. alt: the same kind written with another
# name and description, listed under a made-up code, so the model matches a rule by what it says, not by its code.
CONCEPTS = {
    'interest_cap': dict(code='INTEREST_CAP', name='Lãi suất vượt mức luật cho phép', severity='HIGH',
        description='Lãi suất thỏa thuận (kể cả lãi chậm trả, lãi trên lãi) cao hơn mức tối đa mà điều luật được dẫn cho phép.',
        alt=('Lãi vay vượt trần', 'Mức lãi các bên thỏa thuận cao hơn trần lãi suất luật định.')),
    'penalty_cap': dict(code='PENALTY_CAP', name='Mức phạt vi phạm vượt trần', severity='HIGH',
        description='Mức phạt vi phạm cao hơn mức tối đa luật quy định cho loại hợp đồng này.',
        alt=('Phạt hợp đồng quá mức', 'Khoản phạt do vi phạm nghĩa vụ vượt tỷ lệ tối đa luật cho phép.')),
    'deadline': dict(code='DEADLINE', name='Thời hạn trái luật', severity='MEDIUM',
        description='Thời hạn báo trước, khiếu nại, bảo hành, hoàn tiền, thanh toán ngắn hoặc dài hơn mức luật quy định.',
        alt=('Thời hạn không đúng luật', 'Một thời hạn trong hợp đồng ngắn hơn mức tối thiểu hoặc dài hơn mức tối đa luật đặt ra.')),
    'form': dict(code='MANDATORY_FORM', name='Không đúng hình thức bắt buộc', severity='HIGH',
        description='Hợp đồng hoặc thỏa thuận không theo hình thức luật bắt buộc (văn bản, công chứng, chứng thực).',
        alt=('Sai hình thức giao kết', 'Thiếu văn bản, công chứng hoặc chứng thực mà luật bắt buộc.')),
    'dispute': dict(code='DISPUTE_RESOLUTION', name='Điều khoản giải quyết tranh chấp không hợp lệ', severity='MEDIUM',
        description='Cơ quan, thủ tục hoặc thỏa thuận trọng tài không đáp ứng điều kiện luật quy định.',
        alt=('Giải quyết tranh chấp sai luật', 'Thỏa thuận trọng tài hoặc cơ quan giải quyết tranh chấp không đủ điều kiện luật định.')),
    'collateral': dict(code='COLLATERAL', name='Xử lý tài sản bảo đảm trái luật', severity='HIGH',
        description='Cách xử lý tài sản cầm cố, thế chấp, đặt cọc trái quy định (ví dụ giữ tài sản không thanh toán chênh lệch).',
        alt=('Tài sản bảo đảm, đặt cọc trái luật', 'Điều khoản về cầm cố, thế chấp hoặc đặt cọc vượt giới hạn hoặc trái cách xử lý luật quy định.')),
    'unilateral': dict(code='UNILATERAL_RIGHT', name='Quyền một phía trái luật', severity='HIGH',
        description='Một bên được đơn phương chấm dứt, đòi trước hạn hoặc thay đổi nghĩa vụ trái điều kiện luật cho phép.',
        alt=('Quyền đơn phương trái luật', 'Một bên tự ý đòi trước hạn, chấm dứt hoặc đổi nghĩa vụ mà luật không cho.')),
    'prohibited': dict(code='PROHIBITED_TERM', name='Điều khoản trái điều cấm của luật', severity='HIGH',
        description='Điều khoản cho phép làm điều luật cấm hoặc loại bỏ quyền mà luật không cho thỏa thuận khác.',
        alt=('Vi phạm điều cấm', 'Cho phép hành vi luật cấm hoặc tước quyền luật bảo vệ.')),
    'cross': dict(code='CROSS_CLAUSE', name='Mâu thuẫn hoặc mất cân bằng giữa các điều', severity='MEDIUM',
        description='Hai hay nhiều điều mâu thuẫn nhau, hoặc gộp lại khiến một bên chịu phần lớn rủi ro.',
        alt=('Các điều khoản mâu thuẫn', 'Hai điều trong cùng hợp đồng quy định khác nhau về cùng một nội dung.')),
    'labour': dict(code='LABOUR_TERM', name='Điều khoản lao động trái luật', severity='HIGH',
        description='Thời gian thử việc, giờ làm thêm hoặc điều kiện làm việc vượt giới hạn luật lao động cho phép.',
        alt=('Vi phạm quy định lao động', 'Thử việc, làm thêm giờ hoặc điều kiện lao động vượt mức luật cho phép.')),
    'advance': dict(code='ADVANCE_CAP', name='Tạm ứng vượt mức cho phép', severity='MEDIUM',
        description='Khoản tạm ứng hoặc trả trước cao hơn tỷ lệ tối đa luật quy định trên giá trị hợp đồng.',
        alt=('Trả trước quá mức', 'Tỷ lệ tạm ứng, trả trước vượt giới hạn luật đặt ra.')),
    'vague': dict(code='VAGUE_TERM', name='Điều khoản không rõ ràng', severity='LOW',
        description='Thời hạn, giá, chất lượng, tiêu chí hoặc mức bồi thường không xác định được, dễ dẫn đến tranh chấp.',
        alt=('Nội dung chưa xác định', 'Điều khoản để ngỏ hoặc mơ hồ, không đo được nghĩa vụ của các bên.')),
}
# The kind of risk each topic is; None: no catalog rule describes it, so the answer files it under OTHER.
CONCEPT_OF = dict(interest='interest_cap', penalty='penalty_cap', advance='advance', probation='labour', refund='deadline',
                  notice='deadline', warranty='deadline', complaint='deadline', notarise='form', written_labour='form',
                  arbitration_form='dispute', pledge='collateral', early_demand='unilateral', id_papers='prohibited',
                  deposit='collateral', overtime='labour', rent_notice='deadline', entry='prohibited',
                  bid_security='collateral', performance_security='collateral', auction_deposit='collateral', usufruct='deadline',
                  pay_vague='vague', price_vague='vague', delivery_vague='vague', quality_vague='vague', rent_vague='vague',
                  accept_vague='vague', comp_vague='vague', adjust_vague='vague', later_vague='vague', scope_vague='vague')

# The kind of contract a clause on each topic sits in (a random title is still used now and then).
TOPIC_TITLES = dict(
    interest=['Hợp đồng vay tiền'], pledge=['Hợp đồng vay tiền'], early_demand=['Hợp đồng vay tiền'],
    penalty=['Hợp đồng mua bán hàng hóa', 'Hợp đồng cung cấp dịch vụ', 'Hợp đồng đại lý'],
    advance=['Hợp đồng thi công xây dựng'], warranty=['Hợp đồng thi công xây dựng'],
    probation=['Hợp đồng lao động'], written_labour=['Hợp đồng lao động'], id_papers=['Hợp đồng lao động'], overtime=['Hợp đồng lao động'],
    refund=['Hợp đồng mua bán hàng hóa', 'Hợp đồng cung cấp dịch vụ'], complaint=['Hợp đồng mua bán hàng hóa'],
    notice=['Hợp đồng cung cấp dịch vụ', 'Hợp đồng đại lý', 'Hợp đồng thuê nhà'], notarise=['Hợp đồng mua bán căn hộ'],
    arbitration_form=['Hợp đồng mua bán hàng hóa', 'Hợp đồng cung cấp dịch vụ', 'Hợp đồng thi công xây dựng'],
    deposit=['Hợp đồng thuê nhà'], rent_notice=['Hợp đồng thuê nhà'], entry=['Hợp đồng thuê nhà'], rent_vague=['Hợp đồng thuê nhà'],
    pay_term=['Hợp đồng mua bán hàng hóa'], penalty_free=['Hợp đồng mua bán hàng hóa', 'Hợp đồng cung cấp dịch vụ'],
    warranty_default=['Hợp đồng mua bán hàng hóa'], place=['Hợp đồng mua bán hàng hóa'],
    pay_vague=['Hợp đồng mua bán hàng hóa'], price_vague=['Hợp đồng mua bán hàng hóa'], delivery_vague=['Hợp đồng mua bán hàng hóa'],
    quality_vague=['Hợp đồng mua bán hàng hóa'],
    acceptance=['Hợp đồng thi công xây dựng', 'Hợp đồng cung cấp dịch vụ'], accept_vague=['Hợp đồng thi công xây dựng', 'Hợp đồng cung cấp dịch vụ'],
    compensation=['Hợp đồng mua bán hàng hóa', 'Hợp đồng cung cấp dịch vụ', 'Hợp đồng thi công xây dựng'],
    comp_vague=['Hợp đồng mua bán hàng hóa', 'Hợp đồng cung cấp dịch vụ', 'Hợp đồng thi công xây dựng'],
    price_change=['Hợp đồng thi công xây dựng', 'Hợp đồng mua bán hàng hóa'], adjust_vague=['Hợp đồng mua bán hàng hóa', 'Hợp đồng cung cấp dịch vụ'],
    later_vague=['Hợp đồng mua bán hàng hóa', 'Hợp đồng cung cấp dịch vụ'],
    bid_security=['Hợp đồng mua bán hàng hóa qua đấu thầu'], performance_security=['Hợp đồng mua bán hàng hóa qua đấu thầu'],
    auction_deposit=['Quy chế đấu giá hàng hóa'], usufruct=['Hợp đồng xác lập quyền hưởng dụng'],
    redemption=['Hợp đồng mua bán tài sản có thỏa thuận chuộc lại'], complaint_terms=['Hợp đồng mua bán hàng hóa'],
    scope_vague=['Hợp đồng cung cấp dịch vụ', 'Hợp đồng thi công xây dựng'])

# Provisions on the clause's own subject that set no rule the clause can break: retrieval returns such provisions next
# to the governing one, so choosing the right provision takes reading it, not matching its subject.
HARD = {
    'interest': [('Nghĩa vụ trả nợ của bên vay', 'Bên vay phải trả đủ tiền khi đến hạn; nếu tài sản là tiền thì phải trả bằng tiền, trừ trường hợp có thỏa thuận khác.'),
                 ('Lãi chậm trả', 'Trường hợp chậm trả tiền thì bên chậm trả phải trả lãi đối với số tiền chậm trả theo mức các bên thỏa thuận.')],
    'penalty': [('Phạt vi phạm', 'Phạt vi phạm là sự thỏa thuận giữa các bên trong hợp đồng, theo đó bên vi phạm nghĩa vụ phải nộp một khoản tiền cho bên bị vi phạm.')],
    'advance': [('Sử dụng tiền tạm ứng', 'Bên nhận tạm ứng phải sử dụng tiền tạm ứng đúng mục đích và đúng đối tượng của hợp đồng.')],
    'probation': [('Nội dung thử việc', 'Người sử dụng lao động và người lao động có thể thỏa thuận nội dung thử việc ghi trong hợp đồng lao động hoặc thỏa thuận về thử việc bằng việc giao kết hợp đồng thử việc.')],
    'refund': [('Cung cấp chứng từ', 'Tổ chức, cá nhân kinh doanh có trách nhiệm cung cấp hóa đơn, chứng từ liên quan đến giao dịch cho người tiêu dùng.')],
    'notice': [('Hậu quả đơn phương chấm dứt', 'Khi hợp đồng bị đơn phương chấm dứt thì hợp đồng chấm dứt kể từ thời điểm bên kia nhận được thông báo chấm dứt.')],
    'warranty': [('Trách nhiệm bảo hành', 'Nhà thầu có trách nhiệm thực hiện bảo hành sau khi nhận được thông báo yêu cầu bảo hành của chủ đầu tư.')],
    'complaint': [('Quyền khiếu nại', 'Bên mua có quyền khiếu nại về chất lượng hàng hóa theo thỏa thuận trong hợp đồng.')],
    'notarise': [('Nghĩa vụ giao nhà', 'Bên bán có nghĩa vụ giao nhà ở kèm theo hồ sơ về nhà ở cho bên mua theo thời hạn đã thỏa thuận.')],
    'written_labour': [('Hiệu lực hợp đồng lao động', 'Hợp đồng lao động có hiệu lực kể từ ngày hai bên giao kết, trừ trường hợp hai bên có thỏa thuận khác.')],
    'arbitration_form': [('Hình thức giải quyết tranh chấp', 'Tranh chấp được giải quyết bằng Trọng tài nếu các bên có thỏa thuận trọng tài.')],
    'pledge': [('Nghĩa vụ của bên nhận cầm cố', 'Bên nhận cầm cố có nghĩa vụ bảo quản, giữ gìn tài sản cầm cố.')],
    'early_demand': [('Trả nợ trước hạn của bên vay', 'Bên vay có thể trả nợ trước kỳ hạn nhưng phải trả toàn bộ lãi theo kỳ hạn, trừ trường hợp có thỏa thuận khác.')],
    'id_papers': [('Thông tin khi giao kết', 'Người sử dụng lao động có quyền yêu cầu người lao động cung cấp thông tin về họ tên, ngày tháng năm sinh, nơi cư trú và trình độ học vấn.')],
    'pay_term': [('Nghĩa vụ nhận hàng', 'Bên mua có nghĩa vụ nhận hàng theo thỏa thuận và thực hiện những công việc hợp lý để bên bán giao hàng.')],
    'penalty_free': [('Phạt vi phạm', 'Phạt vi phạm là sự thỏa thuận giữa các bên trong hợp đồng, theo đó bên vi phạm nghĩa vụ phải nộp một khoản tiền cho bên bị vi phạm.')],
    'warranty_default': [('Nghĩa vụ bảo hành', 'Bên bán phải sửa chữa hoặc thay thế hàng hóa có khuyết tật trong thời hạn bảo hành.')],
    'place': [('Nghĩa vụ giao hàng', 'Bên bán phải giao hàng đúng số lượng, chất lượng và kèm theo chứng từ liên quan.')],
    'acceptance': [('Hồ sơ nghiệm thu', 'Kết quả nghiệm thu được lập thành biên bản có chữ ký của đại diện các bên.')],
    'compensation': [('Hạn chế tổn thất', 'Bên có quyền lợi bị vi phạm phải áp dụng các biện pháp hợp lý để hạn chế tổn thất.')],
    'price_change': [('Giá hợp đồng', 'Giá hợp đồng là khoản kinh phí bên giao thầu cam kết trả cho bên nhận thầu để thực hiện công việc theo hợp đồng.')],
    # Evaluation only.
    'deposit': [('Tiền thuê nhà', 'Bên thuê phải trả tiền thuê nhà theo thỏa thuận.')],
    'overtime': [('Tiền lương làm thêm giờ', 'Người lao động làm thêm giờ được trả lương theo đơn giá tiền lương của công việc đang làm.')],
    'rent_notice': [('Giá thuê nhà ở', 'Giá thuê nhà ở do các bên thỏa thuận.')],
    'entry': [('Bảo trì nhà cho thuê', 'Bên cho thuê có nghĩa vụ bảo trì, sửa chữa nhà ở theo định kỳ.')],
    'bid_security': [('Hình thức bảo đảm dự thầu', 'Bảo đảm dự thầu được thực hiện dưới hình thức đặt cọc, ký quỹ hoặc bảo lãnh dự thầu.')],
    'usufruct': [('Quyền cho thuê quyền hưởng dụng', 'Người hưởng dụng có quyền cho thuê quyền hưởng dụng trong thời hạn của quyền hưởng dụng.')],
    'redemption': [('Nghĩa vụ của bên mua trong thời hạn chuộc lại', 'Trong thời hạn chuộc lại, bên mua không được xác lập giao dịch chuyển quyền sở hữu tài sản cho chủ thể khác.')],
    'performance_security': [('Hiệu lực bảo đảm thực hiện hợp đồng', 'Biện pháp bảo đảm thực hiện hợp đồng có hiệu lực cho đến thời điểm bên trúng thầu hoàn thành nghĩa vụ hợp đồng.')],
    'auction_deposit': [('Trả lại tiền đặt trước', 'Trường hợp người tham gia đấu giá không mua được hàng hoá thì khoản tiền đặt trước được trả lại ngay sau khi cuộc đấu giá kết thúc.')],
    'complaint_terms': [('Quyền khiếu nại', 'Bên mua có quyền khiếu nại về chất lượng hàng hóa theo thỏa thuận trong hợp đồng.')],
}

# Two clauses of one contract that disagree on one amount or deadline: a drafting risk (no law is broken) the model can
# only see with the other clause in the brief. With equal values the pair is consistent and nothing is wrong.
CROSS = {
    'pay_days': dict(title_a='Thanh toán', a='Bên mua thanh toán toàn bộ giá trị hợp đồng trong vòng {a} ngày kể từ ngày nhận hàng.',
        title_b='Chứng từ thanh toán', b='Bên mua thanh toán cho Bên bán trong vòng {b} ngày kể từ ngày nhận hàng và hóa đơn hợp lệ.',
        subject='thời hạn thanh toán', unit=' ngày', values=(10, 15, 30, 45, 60), party='Bên bán', contracts=['Hợp đồng mua bán hàng hóa']),
    'delivery_days': dict(title_a='Giao hàng', a='Bên bán giao hàng trong vòng {a} ngày kể từ ngày ký hợp đồng.',
        title_b='Tiến độ thực hiện', b='Toàn bộ hàng hóa được giao chậm nhất {b} ngày kể từ ngày ký hợp đồng.',
        subject='thời hạn giao hàng', unit=' ngày', values=(7, 15, 20, 30), party='Bên mua', contracts=['Hợp đồng mua bán hàng hóa']),
    'penalty_twice': dict(title_a='Phạt vi phạm', a='Bên chậm giao hàng chịu phạt {a}% giá trị phần hàng giao chậm.',
        title_b='Trách nhiệm do vi phạm', b='Trường hợp chậm giao hàng, Bên bán chịu phạt {b}% giá trị phần hàng giao chậm.',
        subject='mức phạt chậm giao hàng', unit='%', values=(2, 3, 5, 8), party='Bên bán', contracts=['Hợp đồng mua bán hàng hóa']),
    'warranty_twice': dict(title_a='Bảo hành', a='Bên bán bảo hành hàng hóa trong {a} tháng kể từ ngày giao hàng.',
        title_b='Cam kết chất lượng', b='Thời hạn bảo hành hàng hóa là {b} tháng kể từ ngày giao hàng.',
        subject='thời hạn bảo hành', unit=' tháng', values=(6, 12, 18, 24), party='Bên mua', contracts=['Hợp đồng mua bán hàng hóa']),
    'notice_twice': dict(title_a='Chấm dứt hợp đồng', a='Mỗi bên được chấm dứt hợp đồng sau khi báo trước {a} ngày bằng văn bản.',
        title_b='Thời hạn hợp đồng', b='Bên muốn chấm dứt hợp đồng trước thời hạn phải báo trước cho bên kia {b} ngày.',
        subject='thời hạn báo trước', unit=' ngày', values=(15, 30, 45, 60), party='Cả hai bên',
        contracts=['Hợp đồng cung cấp dịch vụ', 'Hợp đồng đại lý']),
    'acceptance_days': dict(title_a='Nghiệm thu', a='Hai bên tiến hành nghiệm thu trong vòng {a} ngày kể từ ngày bàn giao.',
        title_b='Hồ sơ nghiệm thu', b='Biên bản nghiệm thu được lập chậm nhất {b} ngày sau ngày bàn giao.',
        subject='thời hạn nghiệm thu', unit=' ngày', values=(5, 7, 10, 15), party='Bên nhận thầu',
        contracts=['Hợp đồng thi công xây dựng', 'Hợp đồng cung cấp dịch vụ']),
    'advance_twice': dict(title_a='Tạm ứng', a='Bên giao thầu tạm ứng {a}% giá trị hợp đồng sau khi ký.',
        title_b='Thanh toán', b='Khoản tạm ứng của hợp đồng là {b}% giá trị hợp đồng, được thu hồi qua các đợt thanh toán.',
        subject='mức tạm ứng', unit='%', values=(5, 8, 10, 12), party='Bên nhận thầu', contracts=['Hợp đồng thi công xây dựng']),
    # Evaluation only.
    'rent_price_twice': dict(title_a='Giá thuê', a='Giá thuê nhà là {a} triệu đồng mỗi tháng.',
        title_b='Thanh toán tiền thuê', b='Bên thuê thanh toán tiền thuê {b} triệu đồng mỗi tháng vào ngày 05 hằng tháng.',
        subject='giá thuê', unit=' triệu đồng', values=(8, 10, 12, 15), party='Bên thuê', contracts=['Hợp đồng thuê nhà']),
}
# Clauses that sit next to the one under review and change nothing about it.
NEUTRAL = [('Thông báo', 'Mọi thông báo giữa các bên được gửi bằng văn bản đến địa chỉ ghi tại phần đầu hợp đồng.'),
           ('Điều khoản chung', 'Hợp đồng được lập thành 02 bản có giá trị pháp lý như nhau, mỗi bên giữ 01 bản.'),
           ('Luật áp dụng', 'Hợp đồng này được điều chỉnh bởi pháp luật Việt Nam.'),
           ('Bảo mật', 'Các bên giữ bí mật thông tin của hợp đồng, trừ trường hợp pháp luật yêu cầu cung cấp.'),
           ('Sửa đổi hợp đồng', 'Mọi sửa đổi, bổ sung hợp đồng phải được lập thành văn bản và có chữ ký của hai bên.')]
# Two risks in one clause: topics that sit in the same kind of contract.
COMBOS = [('interest', 'early_demand'), ('interest', 'pledge'), ('probation', 'id_papers'), ('probation', 'written_labour'),
          ('advance', 'warranty'), ('complaint', 'refund'), ('penalty', 'delivery_vague'), ('complaint', 'quality_vague'),
          ('warranty', 'accept_vague'), ('advance', 'accept_vague'), ('refund', 'adjust_vague'), ('notice', 'comp_vague')]

# Ways to recommend a fix, so answers are not one sentence learned by heart.
UNCLEAR_FIX = dict(
    pay_vague=['Ghi rõ thời hạn thanh toán bằng số ngày cụ thể, ví dụ trong vòng 15 ngày kể từ ngày nhận hàng.',
               'Thay "thời gian hợp lý" bằng một thời hạn thanh toán xác định và mốc tính thời hạn.'],
    price_vague=['Ghi rõ đơn giá hoặc công thức tính giá và nguồn giá thị trường được dùng để đối chiếu.',
                 'Xác định giá cố định trong hợp đồng hoặc nêu cách tính giá có số liệu cụ thể.'],
    delivery_vague=['Ghi rõ ngày giao hàng hoặc thời hạn giao hàng tính từ ngày ký hợp đồng.',
                    'Thay "khi có điều kiện" bằng thời hạn giao hàng cụ thể và hậu quả khi giao chậm.'],
    quality_vague=['Nêu tiêu chuẩn chất lượng cụ thể (tiêu chuẩn kỹ thuật, mẫu đối chứng) thay cho đánh giá của một bên.',
                   'Quy định chất lượng theo tiêu chuẩn khách quan và cách kiểm định khi có tranh chấp.'],
    rent_vague=['Ghi rõ kỳ trả tiền thuê (hằng tháng, hằng quý) và hạn trả trong mỗi kỳ.',
                'Thay "phù hợp với khả năng của Bên thuê" bằng kỳ thanh toán và ngày đến hạn cụ thể.'],
    accept_vague=['Liệt kê tiêu chí nghiệm thu cụ thể (tiêu chuẩn kỹ thuật, bản vẽ, phụ lục) và thời hạn nghiệm thu.',
                  'Thay "đạt yêu cầu của Bên giao thầu" bằng tiêu chí khách quan mà hai bên cùng đối chiếu được.'],
    comp_vague=['Ghi rõ cách tính bồi thường (thiệt hại thực tế có chứng từ) và thời hạn thanh toán khoản bồi thường.',
                'Thay "khoản phù hợp với mức độ vi phạm" bằng mức hoặc công thức tính bồi thường cụ thể.'],
    adjust_vague=['Nêu rõ các trường hợp được điều chỉnh giá, cách tính giá mới và thời hạn báo trước.',
                  'Thay "khi cần thiết" bằng điều kiện điều chỉnh giá đo được, ví dụ chỉ số giá tăng quá một mức nhất định.'],
    later_vague=['Ghi ngay trong hợp đồng phương thức, thời hạn và chứng từ thanh toán thay vì để thỏa thuận sau.',
                 'Nếu cần thỏa thuận sau, nêu thời hạn ký phụ lục và cách xử lý khi hai bên chưa thống nhất.'])


def numeric_level(t, value, limit):
    """How far the value is off the limit sets the level: half again past it (or a floor missed by a third) is HIGH."""
    far = value >= limit * 1.5 if t['kind'] == 'max' else value <= limit * 2 / 3
    return 'HIGH' if far else 'MEDIUM'


def numeric_explanation(rng, t, clause_title, shown, limit, ref):
    """One of several ways to say that a value is on the wrong side of a limit."""
    is_max = t['kind'] == 'max'
    return rng.choice(NUMERIC_EXPLANATIONS).format(
        title=clause_title, subject=t['subject'], subject_cap=t['subject'][0].upper() + t['subject'][1:], shown=shown,
        side='vượt mức tối đa' if is_max else 'thấp hơn mức tối thiểu', bound='không vượt quá' if is_max else 'không thấp hơn',
        limit=f'{number(limit)}{t["unit"]}', ref=ref)


def numeric_fix(rng, t, value, limit, clause_title, ref):
    """One of several ways to word the fix of a value on the wrong side of a limit."""
    is_max = t['kind'] == 'max'
    cmp_ = 'không vượt quá' if is_max else 'không thấp hơn'
    lim, val = f'{number(limit)}{t["unit"]}', f'{number(value)}{t["unit"]}'
    move = (f'Giảm {t["subject"]} từ {val} xuống tối đa {lim}.' if is_max else f'Tăng {t["subject"]} từ {val} lên ít nhất {lim}.')
    return rng.choice([
        f'Điều chỉnh {t["subject"]} {cmp_} {lim}.',
        f'Sửa {clause_title} để {t["subject"]} {cmp_} {lim} theo {ref}.',
        move,
        f'Thỏa thuận lại {t["subject"]} ở mức {cmp_} {lim} và ghi rõ trong {clause_title}.',
        f'Đưa {t["subject"]} về mức {"tối đa" if is_max else "tối thiểu"} {lim} như {ref} cho phép.',
        f'Ghi lại {t["subject"]} trong {clause_title} là {lim} hoặc một mức {"thấp" if is_max else "cao"} hơn.',
        f'{t["party"]} nên đề nghị sửa {t["subject"]} thành mức {cmp_} {lim} trước khi ký.',
        f'Thay con số {val} bằng một mức {cmp_} {lim} để phù hợp với {ref}.',
        f'Bổ sung câu: "{t["subject"][0].upper() + t["subject"][1:]} {cmp_} {lim}" vào {clause_title}.',
        f'Rà soát và sửa {t["subject"]}; mức hiện tại {val} cần {"giảm xuống" if is_max else "tăng lên"} {lim}.'])


def ruled_fix(rng, t):
    return rng.choice([f'Sửa điều khoản để bảo đảm {t["rule"]}.',
                       f'Thay nội dung điều khoản bằng: "{t["keeps"]}"',
                       f'Bỏ nội dung {t["why"]} và quy định rõ rằng {t["rule"]}.',
                       f'Xóa phần {t["why"]}; điều khoản phải tuân thủ quy định: {t["rule"]}.',
                       f'Viết lại điều khoản theo đúng yêu cầu của luật: {t["rule"]}.',
                       f'{t["party"]} nên yêu cầu sửa điều khoản để {t["rule"]}.',
                       f'Không ký điều khoản ở dạng hiện tại; sửa lại để {t["rule"]}.'])


# --------------------------------------------------------------------------- wordings
# More ways to write the same clause and the same provision, so the model learns the skill and not a sentence. Each
# list is cut by Maker.pick: most wordings train, the last ones are kept for the validation and evaluation sets only.
# Opening phrases a clause sentence may start with (shared by all splits; the wording itself is what is held out).
LEADS = ['', '', '', '', 'Hai bên thống nhất: ', 'Theo thỏa thuận của các bên, ', 'Các bên cam kết: ',
         'Kể từ ngày hợp đồng có hiệu lực, ', 'Trong suốt thời hạn hợp đồng, ', 'Bằng hợp đồng này, ']

CLAUSE_VARIANTS = {
    'interest': [
        'Bên vay trả lãi cho Bên cho vay theo mức {value} trên số tiền vay.',
        'Khoản vay chịu lãi suất cố định {value} trong suốt thời hạn vay.',
        'Mức lãi áp dụng cho khoản vay là {value}, tiền lãi trả vào ngày cuối mỗi tháng.',
        'Bên A cho Bên B vay với lãi suất {value} tính trên số dư nợ thực tế.',
        'Tiền lãi được tính theo lãi suất {value} kể từ ngày giải ngân.',
        'Lãi suất trong hạn của khoản vay được hai bên thỏa thuận ở mức {value}.',
        'Số tiền vay được tính lãi {value} và trả cùng kỳ trả gốc.',
        'Bên vay chịu lãi {value} đối với toàn bộ số tiền đã nhận.',
        'Lãi vay được ấn định là {value}, không thay đổi trong thời hạn hợp đồng.'],
    'penalty': [
        'Trường hợp vi phạm nghĩa vụ, bên vi phạm nộp phạt {value} giá trị phần nghĩa vụ bị vi phạm.',
        'Mức phạt vi phạm hợp đồng là {value} giá trị phần nghĩa vụ bị vi phạm.',
        'Bên nào vi phạm nghĩa vụ thì bị phạt {value} giá trị phần hợp đồng bị vi phạm.',
        'Khi giao hàng chậm, Bên bán chịu phạt {value} giá trị lô hàng giao chậm.',
        'Bên vi phạm phải trả cho bên bị vi phạm khoản tiền phạt bằng {value} giá trị nghĩa vụ không thực hiện.',
        'Mỗi lần vi phạm, bên vi phạm chịu phạt {value} giá trị phần nghĩa vụ liên quan.',
        'Hai bên thỏa thuận mức phạt {value} giá trị phần nghĩa vụ hợp đồng bị vi phạm.',
        'Nếu chậm thanh toán, Bên mua bị phạt {value} số tiền chậm thanh toán.',
        'Tổng mức phạt cho các vi phạm của một bên là {value} giá trị phần nghĩa vụ bị vi phạm.'],
    'advance': [
        'Mức tạm ứng hợp đồng là {value} giá trị hợp đồng.',
        'Trong vòng 07 ngày kể từ ngày ký, Bên A tạm ứng cho Bên B {value} giá trị hợp đồng.',
        'Bên nhận thầu được nhận tiền tạm ứng bằng {value} giá trị hợp đồng sau khi nộp bảo lãnh tạm ứng.',
        'Khoản tạm ứng lần đầu bằng {value} giá trị hợp đồng đã ký.',
        'Chủ đầu tư tạm ứng {value} giá trị hợp đồng để nhà thầu chuẩn bị vật tư.',
        'Giá trị tạm ứng được hai bên thống nhất là {value} tổng giá trị hợp đồng.',
        'Bên giao thầu thanh toán trước {value} giá trị hợp đồng dưới hình thức tạm ứng.',
        'Tiền tạm ứng tương đương {value} giá trị hợp đồng và được thu hồi dần qua các đợt thanh toán.',
        'Ngay khi hợp đồng có hiệu lực, Bên nhận thầu được tạm ứng {value} giá trị hợp đồng.'],
    'probation': [
        'Người lao động thử việc trong thời gian {value}.',
        'Hai bên thỏa thuận thời gian thử việc là {value} trước khi ký hợp đồng chính thức.',
        'Bên B làm việc theo chế độ thử việc {value} kể từ ngày nhận việc.',
        'Thời hạn thử việc đối với vị trí này là {value}.',
        'Người lao động phải trải qua {value} thử việc tại công ty.',
        'Giai đoạn thử việc kéo dài {value}, người lao động hưởng 85% mức lương chính thức.',
        'Bên A tuyển dụng Bên B với thời gian thử việc {value}.',
        'Sau {value} thử việc, Bên A đánh giá và quyết định ký hợp đồng lao động.',
        'Thời gian thử việc được tính là {value} kể từ ngày người lao động bắt đầu làm việc.'],
    'refund': [
        'Khoản tiền hoàn lại được chuyển cho khách hàng trong thời hạn {value} kể từ ngày nhận yêu cầu.',
        'Bên cung cấp dịch vụ hoàn tiền cho Bên sử dụng dịch vụ chậm nhất {value} sau khi nhận được yêu cầu hoàn tiền.',
        'Thời hạn hoàn trả tiền cho người mua là {value} kể từ ngày tiếp nhận yêu cầu.',
        'Trường hợp trả lại hàng, Bên bán hoàn tiền trong {value} kể từ ngày nhận được yêu cầu.',
        'Bên bán có {value} kể từ ngày nhận yêu cầu để hoàn trả tiền cho Bên mua.',
        'Tiền được hoàn trả cho khách hàng trong vòng {value} tính từ ngày nhận được yêu cầu hợp lệ.',
        'Việc hoàn tiền cho Bên mua được thực hiện trong thời hạn {value} kể từ khi Bên bán nhận được yêu cầu.',
        'Bên A hoàn lại số tiền đã thanh toán cho Bên B trong vòng {value} kể từ ngày nhận yêu cầu.',
        'Khi chấp nhận yêu cầu hoàn tiền, Bên bán thanh toán lại cho Bên mua trong {value} kể từ ngày nhận yêu cầu.'],
    'notice': [
        'Bên muốn đơn phương chấm dứt hợp đồng phải báo trước cho bên kia {value} bằng văn bản.',
        'Hợp đồng có thể bị một bên đơn phương chấm dứt sau khi thông báo trước {value}.',
        'Bên A được đơn phương chấm dứt hợp đồng nếu gửi thông báo bằng văn bản trước {value}.',
        'Thời hạn báo trước khi đơn phương chấm dứt hợp đồng là {value}.',
        'Trước khi đơn phương chấm dứt hợp đồng, bên chấm dứt thông báo cho bên kia trước {value}.',
        'Mỗi bên được chấm dứt hợp đồng trước hạn với điều kiện báo trước {value}.',
        'Việc đơn phương chấm dứt hợp đồng có hiệu lực sau {value} kể từ ngày bên kia nhận được thông báo.',
        'Bên cho thuê có quyền đơn phương chấm dứt hợp đồng khi thông báo trước cho Bên thuê {value}.',
        'Thông báo đơn phương chấm dứt hợp đồng phải được gửi bằng văn bản trước {value}.'],
    'warranty': [
        'Thời hạn bảo hành công trình là {value} tính từ ngày nghiệm thu đưa vào sử dụng.',
        'Nhà thầu chịu trách nhiệm bảo hành hạng mục công trình trong {value} sau khi nghiệm thu.',
        'Công trình được bảo hành {value} kể từ ngày hai bên ký biên bản nghiệm thu.',
        'Bên B bảo hành phần việc đã thi công trong thời gian {value} kể từ ngày nghiệm thu.',
        'Thời gian bảo hành đối với công trình là {value}.',
        'Sau khi nghiệm thu, nhà thầu bảo hành công trình trong vòng {value}.',
        'Bên nhận thầu cam kết bảo hành chất lượng công trình {value} kể từ ngày bàn giao.',
        'Hai bên thống nhất thời hạn bảo hành công trình là {value} kể từ ngày nghiệm thu.',
        'Nghĩa vụ bảo hành công trình của Bên nhận thầu kéo dài {value} kể từ ngày nghiệm thu.'],
    'complaint': [
        'Mọi khiếu nại về số lượng hàng hóa phải được gửi trong {value} kể từ ngày giao hàng.',
        'Thời hạn khiếu nại về số lượng hàng hóa là {value} kể từ ngày giao hàng.',
        'Sau {value} kể từ ngày giao hàng, Bên bán không giải quyết khiếu nại về số lượng hàng hóa.',
        'Bên mua có {value} kể từ ngày nhận hàng để khiếu nại về số lượng.',
        'Khiếu nại về thiếu hụt số lượng hàng hóa chỉ được chấp nhận trong thời hạn {value} kể từ ngày giao hàng.',
        'Bên mua phải thông báo khiếu nại về số lượng hàng hóa cho Bên bán trong vòng {value} sau khi giao hàng.',
        'Quyền khiếu nại về số lượng hàng hóa của Bên mua chấm dứt sau {value} kể từ ngày giao hàng.',
        'Hai bên thống nhất thời hạn khiếu nại về số lượng hàng hóa là {value} tính từ ngày giao hàng.',
        'Bên mua được khiếu nại về số lượng hàng hóa trong thời gian {value} kể từ ngày giao hàng.'],
    'bid_security': [
        'Mức bảo đảm dự thầu là {value} tổng giá trị ước tính của hàng hóa đấu thầu.',
        'Khi nộp hồ sơ dự thầu, bên dự thầu ký quỹ {value} giá trị ước tính của gói thầu.',
        'Bên mời thầu yêu cầu bên dự thầu đặt cọc {value} tổng giá trị ước tính của dịch vụ đấu thầu.',
        'Tiền đặt cọc dự thầu được quy định bằng {value} giá trị ước tính của gói thầu.',
        'Bên dự thầu phải nộp bảo lãnh dự thầu với giá trị {value} tổng giá trị ước tính của hàng hóa.',
        'Mỗi bên dự thầu nộp khoản ký quỹ dự thầu tương đương {value} giá trị ước tính của gói thầu.',
        'Hồ sơ dự thầu chỉ hợp lệ khi kèm tiền đặt cọc bằng {value} tổng giá trị ước tính của hàng hóa, dịch vụ đấu thầu.',
        'Tỷ lệ ký quỹ dự thầu áp dụng cho gói thầu này là {value} tổng giá trị ước tính.',
        'Bên dự thầu nộp {value} tổng giá trị ước tính của hàng hóa đấu thầu làm tiền bảo đảm dự thầu.'],
    'usufruct': [
        'Quyền hưởng dụng của Công ty TNHH An Phát đối với tài sản kéo dài {value}.',
        'Thời hạn hưởng dụng tài sản của Bên B là pháp nhân là {value} kể từ ngày bàn giao.',
        'Bên A xác lập cho Bên B là doanh nghiệp quyền hưởng dụng thửa đất trong {value}.',
        'Công ty Cổ phần Minh Long được khai thác, hưởng hoa lợi từ tài sản trong thời hạn {value}.',
        'Quyền hưởng dụng của bên hưởng dụng là tổ chức có thời hạn {value} tính từ ngày đăng ký.',
        'Hai bên thỏa thuận thời hạn hưởng dụng là {value} đối với Bên B là pháp nhân.',
        'Bên B là pháp nhân được sử dụng và hưởng hoa lợi từ tài sản trong vòng {value}.',
        'Thời hạn của quyền hưởng dụng dành cho Công ty TNHH Dịch vụ Sao Việt là {value}.',
        'Quyền hưởng dụng được xác lập cho pháp nhân hưởng dụng trong thời gian {value} kể từ ngày ký.'],
    # Evaluation-only topics: every wording is used there.
    'deposit': ['Khi ký hợp đồng, Bên thuê giao cho Bên cho thuê tiền đặt cọc bằng {value} tiền thuê.',
                'Tiền cọc thuê nhà là {value} tiền thuê và được hoàn trả khi kết thúc hợp đồng.'],
    'overtime': ['Bên A được yêu cầu người lao động làm thêm đến {value} trong một tháng.',
                 'Số giờ làm thêm tối đa của người lao động là {value} mỗi tháng.'],
    'rent_notice': ['Trước khi tăng giá thuê, Bên cho thuê báo cho Bên thuê biết trước {value}.',
                    'Giá thuê có thể được điều chỉnh với điều kiện Bên cho thuê thông báo trước {value}.'],
    'performance_security': ['Bảo đảm thực hiện hợp đồng có giá trị bằng {value} giá trị hợp đồng.',
                             'Trước khi ký hợp đồng, bên trúng thầu đặt cọc {value} giá trị hợp đồng để bảo đảm thực hiện.'],
    'auction_deposit': ['Khoản tiền đặt trước để tham gia đấu giá là {value} giá khởi điểm.',
                        'Mỗi người đăng ký tham gia đấu giá nộp tiền đặt trước bằng {value} giá khởi điểm của lô hàng.'],
}

LAW_VARIANTS = {
    'interest': [
        'Lãi suất vay do các bên thỏa thuận nhưng không được vượt quá {limit}%/năm của khoản tiền vay.',
        'Mức lãi suất thỏa thuận trong hợp đồng vay tài sản không được cao hơn {limit}%/năm tính trên khoản tiền vay.',
        'Các bên được thỏa thuận lãi suất vay; mức lãi suất tối đa là {limit}%/năm của khoản tiền vay, phần vượt quá không có hiệu lực.',
        'Lãi suất theo thỏa thuận của hợp đồng vay không vượt quá {limit}%/năm của số tiền vay.',
        'Trường hợp hợp đồng vay có lãi, lãi suất do các bên thỏa thuận nhưng tối đa là {limit}%/năm của khoản vay.'],
    'penalty': [
        'Mức phạt vi phạm do các bên thỏa thuận nhưng không vượt quá {limit}% giá trị phần nghĩa vụ hợp đồng bị vi phạm.',
        'Tổng mức phạt đối với nhiều vi phạm do các bên thỏa thuận, nhưng không quá {limit}% giá trị phần nghĩa vụ hợp đồng bị vi phạm.',
        'Các bên có thể thỏa thuận về phạt vi phạm; mức phạt tối đa là {limit}% giá trị phần nghĩa vụ bị vi phạm.',
        'Mức phạt vi phạm hợp đồng không được cao hơn {limit}% giá trị phần nghĩa vụ hợp đồng bị vi phạm.',
        'Bên vi phạm chịu phạt theo thỏa thuận, nhưng mức phạt không vượt quá {limit}% giá trị phần nghĩa vụ không được thực hiện.'],
    'advance': [
        'Giá trị tạm ứng hợp đồng tối đa là {limit}% giá trị hợp đồng tại thời điểm ký kết.',
        'Bên giao thầu chỉ được tạm ứng cho bên nhận thầu không quá {limit}% giá trị hợp đồng.',
        'Mức tạm ứng do các bên thỏa thuận nhưng không được vượt quá {limit}% giá trị hợp đồng đã ký.',
        'Tiền tạm ứng hợp đồng không quá {limit}% giá trị hợp đồng tại thời điểm hợp đồng có hiệu lực.',
        'Tổng mức tạm ứng của hợp đồng không được lớn hơn {limit}% giá trị hợp đồng.'],
    'probation': [
        'Thời gian thử việc không quá {limit} ngày và chỉ được thử việc một lần đối với một công việc.',
        'Người sử dụng lao động và người lao động chỉ được thỏa thuận thử việc một lần, thời gian thử việc không vượt quá {limit} ngày.',
        'Thời gian thử việc tối đa là {limit} ngày tùy theo tính chất công việc.',
        'Thời gian thử việc do hai bên thỏa thuận nhưng không được kéo dài quá {limit} ngày.',
        'Mỗi công việc chỉ được thử việc một lần với thời gian thử việc không quá {limit} ngày.'],
    'refund': [
        'Thời hạn hoàn trả tiền cho người tiêu dùng không quá {limit} ngày kể từ ngày tổ chức, cá nhân kinh doanh nhận được yêu cầu.',
        'Tổ chức, cá nhân kinh doanh hoàn trả tiền cho người tiêu dùng chậm nhất {limit} ngày kể từ ngày nhận được yêu cầu hoàn tiền.',
        'Khi người tiêu dùng yêu cầu hoàn tiền hợp lệ, tiền phải được hoàn trả trong vòng {limit} ngày kể từ ngày nhận được yêu cầu.',
        'Việc hoàn trả tiền cho người tiêu dùng phải được thực hiện trong thời hạn tối đa {limit} ngày kể từ ngày nhận yêu cầu.',
        'Tổ chức, cá nhân kinh doanh không được hoàn trả tiền cho người tiêu dùng chậm hơn {limit} ngày kể từ ngày nhận được yêu cầu.'],
    'notice': [
        'Bên đơn phương chấm dứt hợp đồng phải báo trước cho bên kia ít nhất {limit} ngày bằng văn bản.',
        'Thời hạn báo trước khi đơn phương chấm dứt thực hiện hợp đồng không được ít hơn {limit} ngày.',
        'Trường hợp đơn phương chấm dứt hợp đồng, bên chấm dứt phải thông báo bằng văn bản trước tối thiểu {limit} ngày.',
        'Việc đơn phương chấm dứt hợp đồng chỉ có hiệu lực khi bên kia được báo trước bằng văn bản từ {limit} ngày trở lên.',
        'Mỗi bên được đơn phương chấm dứt hợp đồng nếu thông báo bằng văn bản cho bên kia trước ít nhất {limit} ngày.'],
    'warranty': [
        'Thời hạn bảo hành công trình tối thiểu là {limit} tháng kể từ ngày nghiệm thu đưa công trình vào sử dụng.',
        'Nhà thầu phải bảo hành công trình trong thời hạn không ngắn hơn {limit} tháng kể từ ngày nghiệm thu.',
        'Công trình được bảo hành ít nhất {limit} tháng tính từ ngày nghiệm thu hoàn thành.',
        'Thời gian bảo hành công trình do các bên thỏa thuận nhưng không ít hơn {limit} tháng kể từ ngày nghiệm thu.',
        'Bên nhận thầu có nghĩa vụ bảo hành công trình tối thiểu {limit} tháng sau khi công trình được nghiệm thu.'],
    'complaint': [
        'Bên mua được khiếu nại về số lượng hàng hóa trong thời hạn tối thiểu {limit} ngày kể từ ngày giao hàng.',
        'Thời hạn khiếu nại về số lượng hàng hóa do các bên thỏa thuận nhưng không được ngắn hơn {limit} ngày kể từ ngày giao hàng.',
        'Các bên không được thỏa thuận thời hạn khiếu nại về số lượng hàng hóa ít hơn {limit} ngày kể từ ngày giao hàng.',
        'Quyền khiếu nại về số lượng hàng hóa được bảo đảm trong ít nhất {limit} ngày kể từ ngày giao hàng.',
        'Khiếu nại về số lượng hàng hóa được gửi trong thời hạn không dưới {limit} ngày kể từ ngày giao hàng.'],
    'bid_security': [
        'Bên mời thầu có thể yêu cầu bên dự thầu nộp tiền đặt cọc dự thầu không vượt quá {limit}% tổng giá trị ước tính của gói thầu.',
        'Mức bảo đảm dự thầu tối đa là {limit}% tổng giá trị ước tính của hàng hóa, dịch vụ đấu thầu.',
        'Tiền ký quỹ dự thầu không được lớn hơn {limit}% tổng giá trị ước tính của hàng hóa đấu thầu.',
        'Bảo đảm dự thầu do bên mời thầu quy định với tỷ lệ không quá {limit}% giá trị ước tính của gói thầu.',
        'Bên dự thầu nộp bảo đảm dự thầu theo yêu cầu của bên mời thầu, nhưng không quá {limit}% tổng giá trị ước tính.'],
    'usufruct': [
        'Quyền hưởng dụng của pháp nhân có thời hạn tối đa {limit} năm.',
        'Trường hợp người hưởng dụng đầu tiên là pháp nhân, thời hạn của quyền hưởng dụng không quá {limit} năm.',
        'Thời hạn hưởng dụng do các bên thỏa thuận hoặc do luật quy định nhưng không vượt quá {limit} năm đối với pháp nhân.',
        'Pháp nhân chỉ được hưởng dụng tài sản trong thời hạn không quá {limit} năm.',
        'Quyền hưởng dụng xác lập cho pháp nhân chấm dứt chậm nhất sau {limit} năm.'],
    'deposit': ['Bên cho thuê không được thu tiền đặt cọc thuê nhà ở vượt quá {limit} tháng tiền thuê.'],
    'overtime': ['Tổng số giờ làm thêm của người lao động không được vượt quá {limit} giờ trong một tháng.'],
    'rent_notice': ['Việc điều chỉnh giá thuê nhà ở phải được bên cho thuê thông báo cho bên thuê trước tối thiểu {limit} ngày.'],
    'performance_security': ['Bảo đảm thực hiện hợp đồng do bên mời thầu yêu cầu không được vượt quá {limit}% giá trị hợp đồng.'],
    'auction_deposit': ['Khoản tiền đặt trước khi tham gia đấu giá không được lớn hơn {limit}% giá khởi điểm của hàng hoá đấu giá.'],
}

RULED_VARIANTS = {
    'notarise': dict(
        breaks=['Hợp đồng mua bán căn hộ có hiệu lực từ ngày hai bên ký, các bên không thực hiện công chứng hay chứng thực.',
                'Hai bên chỉ ký hợp đồng mua bán nhà ở dưới hình thức giấy viết tay, không công chứng.',
                'Để tiết kiệm chi phí, hợp đồng mua bán nhà này không phải công chứng hoặc chứng thực.',
                'Việc mua bán nhà ở hoàn tất khi Bên mua thanh toán đủ tiền, không cần công chứng hợp đồng.'],
        keeps=['Hai bên có trách nhiệm công chứng hợp đồng mua bán nhà ở này trước khi bàn giao.',
               'Hợp đồng mua bán căn hộ được chứng thực tại Ủy ban nhân dân cấp xã nơi có nhà.',
               'Hợp đồng chỉ có hiệu lực sau khi được công chứng theo quy định.']),
    'written_labour': dict(
        breaks=['Bên A và Bên B làm việc theo thỏa thuận miệng, không ký hợp đồng lao động bằng văn bản.',
                'Hợp đồng lao động giữa hai bên được xác lập qua trao đổi bằng lời và không lập thành văn bản.',
                'Người lao động bắt đầu làm việc ngay mà không ký kết hợp đồng lao động bằng văn bản.',
                'Hai bên không lập văn bản hợp đồng lao động, mọi nội dung do người sử dụng lao động thông báo bằng lời.'],
        keeps=['Hai bên ký kết hợp đồng lao động bằng văn bản trước khi người lao động bắt đầu làm việc.',
               'Hợp đồng lao động được lập thành văn bản, người lao động giữ một bản.',
               'Mọi thỏa thuận lao động giữa hai bên được ghi nhận bằng hợp đồng văn bản có chữ ký của hai bên.']),
    'arbitration_form': dict(
        breaks=['Tranh chấp được giải quyết tại trọng tài theo thỏa thuận miệng của hai bên khi phát sinh tranh chấp.',
                'Hai bên đồng ý bằng lời nói rằng tranh chấp sẽ do trọng tài giải quyết, không cần lập văn bản.',
                'Việc lựa chọn trọng tài được các bên thống nhất qua điện thoại và không lập thành văn bản.',
                'Thỏa thuận giải quyết tranh chấp bằng trọng tài được xác lập bằng lời nói giữa đại diện hai bên.'],
        keeps=['Tranh chấp phát sinh từ hợp đồng này được giải quyết tại trọng tài theo thỏa thuận trọng tài bằng văn bản tại điều này.',
               'Hai bên lập văn bản thỏa thuận trọng tài kèm theo hợp đồng.',
               'Thỏa thuận trọng tài được ghi bằng văn bản trong hợp đồng này.']),
    'pledge': dict(
        breaks=['Nếu Bên vay không trả nợ đúng hạn, tài sản cầm cố đương nhiên thuộc sở hữu của Bên cho vay mà không thanh toán chênh lệch.',
                'Bên cho vay được giữ toàn bộ tài sản cầm cố mà không hoàn lại phần giá trị vượt quá khoản nợ.',
                'Khi xử lý tài sản cầm cố, mọi khoản chênh lệch thuộc về Bên cho vay.',
                'Trường hợp vi phạm nghĩa vụ trả nợ, Bên cho vay nhận tài sản cầm cố thay cho khoản nợ mà không thanh toán chênh lệch.'],
        keeps=['Sau khi xử lý tài sản cầm cố, số tiền vượt quá khoản nợ được trả lại cho Bên vay.',
               'Phần giá trị tài sản bảo đảm lớn hơn nghĩa vụ được bảo đảm được Bên cho vay thanh toán cho Bên vay.',
               'Bên cho vay hoàn trả Bên vay khoản chênh lệch khi giá trị tài sản cầm cố lớn hơn số tiền còn nợ.']),
    'early_demand': dict(
        breaks=['Bên cho vay được thu hồi khoản vay trước hạn bất cứ lúc nào bằng thông báo đơn phương.',
                'Bên cho vay có quyền yêu cầu trả nợ trước kỳ hạn mà không cần Bên vay chấp thuận.',
                'Trong thời hạn vay, Bên cho vay được đòi lại toàn bộ tiền vay khi có nhu cầu mà không cần sự đồng ý của Bên vay.',
                'Bên A có quyền chấm dứt khoản vay và đòi nợ trước hạn theo ý mình.'],
        keeps=['Việc đòi nợ trước kỳ hạn chỉ thực hiện khi có sự đồng ý của Bên vay.',
               'Bên cho vay không được đòi lại tiền vay trước hạn nếu Bên vay không đồng ý.',
               'Bên cho vay có thể đề nghị trả nợ trước hạn và chỉ áp dụng khi Bên vay chấp thuận bằng văn bản.']),
    'id_papers': dict(
        breaks=['Người lao động nộp bản chính văn bằng, chứng chỉ cho Bên A giữ đến khi chấm dứt hợp đồng.',
                'Bên A giữ bản gốc căn cước công dân của người lao động để bảo đảm thực hiện hợp đồng.',
                'Khi nhận việc, người lao động giao bản chính giấy tờ tùy thân cho công ty quản lý.',
                'Công ty lưu giữ bản chính bằng cấp của nhân viên trong suốt thời gian làm việc.'],
        keeps=['Người lao động nộp bản sao có chứng thực văn bằng, chứng chỉ để lưu hồ sơ.',
               'Bên A không giữ bản chính bất kỳ giấy tờ tùy thân nào của người lao động.',
               'Công ty chỉ kiểm tra bản chính giấy tờ khi tuyển dụng và trả lại ngay cho người lao động.']),
    'entry': dict(
        breaks=['Bên cho thuê có quyền tự mở cửa vào nhà cho thuê để kiểm tra mà không cần sự đồng ý của Bên thuê.'],
        keeps=['Bên cho thuê phải được Bên thuê đồng ý trước khi vào nhà, trừ khi có sự cố khẩn cấp.']),
}

UNCLEAR_VARIANTS = {
    'pay_vague': ['Bên mua thanh toán khi có điều kiện tài chính phù hợp.',
                  'Việc thanh toán được thực hiện vào thời điểm thích hợp do Bên mua quyết định.',
                  'Bên mua sẽ thanh toán sớm nhất có thể sau khi nhận hàng.',
                  'Tiền hàng được thanh toán trong khoảng thời gian hợp lý kể từ khi giao nhận.'],
    'price_vague': ['Đơn giá do Bên bán thông báo tại thời điểm giao hàng.',
                    'Giá hàng hóa sẽ được điều chỉnh cho phù hợp với thị trường.',
                    'Giá bán được xác định theo mặt bằng chung của thị trường.',
                    'Giá trị hợp đồng được tính theo giá hiện hành khi thanh toán.'],
    'delivery_vague': ['Hàng hóa được giao trong thời gian sớm nhất.',
                       'Bên bán giao hàng khi hàng về kho.',
                       'Thời điểm giao hàng do Bên bán sắp xếp tùy tình hình sản xuất.',
                       'Bên bán sẽ giao hàng ngay khi thuận tiện.'],
    'quality_vague': ['Hàng hóa bảo đảm chất lượng tốt.',
                      'Chất lượng hàng hóa phù hợp với yêu cầu sử dụng thông thường.',
                      'Hàng hóa đạt chất lượng như thỏa thuận miệng giữa hai bên.',
                      'Bên bán cam kết hàng hóa có chất lượng cao.'],
    'accept_vague': ['Việc nghiệm thu do Bên giao thầu quyết định khi thấy công việc hoàn thành.',
                     'Công trình được coi là đạt khi Bên A hài lòng.',
                     'Nghiệm thu được tiến hành vào thời điểm thích hợp.',
                     'Kết quả công việc được nghiệm thu theo đánh giá chung của các bên.'],
    'comp_vague': ['Bên vi phạm bồi thường thiệt hại tương xứng.',
                   'Mức bồi thường do hai bên thương lượng khi xảy ra thiệt hại.',
                   'Bên gây thiệt hại phải bồi thường thỏa đáng cho bên kia.',
                   'Khoản bồi thường được xác định tùy theo mức độ ảnh hưởng.'],
    'adjust_vague': ['Giá có thể thay đổi theo biến động thị trường.',
                     'Bên bán được điều chỉnh đơn giá trong trường hợp chi phí tăng.',
                     'Giá hợp đồng sẽ được xem xét lại khi cần.',
                     'Bên B có quyền tăng giá khi có biến động mà không cần thỏa thuận lại.'],
    'later_vague': ['Phương thức thanh toán cụ thể sẽ được hai bên bàn bạc sau.',
                    'Thời hạn và cách thức thanh toán do các bên thống nhất vào thời điểm thích hợp.',
                    'Các bên sẽ ký phụ lục quy định việc thanh toán khi cần.',
                    'Chi tiết thanh toán được thỏa thuận sau khi giao hàng.'],
    'rent_vague': ['Tiền thuê được trả khi Bên thuê thu xếp được.'],
    'scope_vague': ['Ngoài các hạng mục đã nêu, Bên B làm thêm những việc phát sinh khi Bên A cần.'],
}

DEFAULT_VARIANTS = {
    'pay_term': ['Thời hạn thanh toán là {n} ngày kể từ ngày Bên mua nhận đủ hàng và hóa đơn.',
                 'Bên mua chuyển khoản toàn bộ tiền hàng chậm nhất {n} ngày sau khi nhận hàng.',
                 'Tiền hàng được thanh toán trong {n} ngày làm việc kể từ ngày giao nhận.',
                 'Bên mua trả tiền theo từng lô hàng trong vòng {n} ngày kể từ ngày nhận lô hàng.'],
    'penalty_free': ['Bên vi phạm nghĩa vụ chịu phạt {n}% giá trị phần nghĩa vụ bị vi phạm.',
                     'Mức phạt khi vi phạm hợp đồng là {n}% giá trị hợp đồng.',
                     'Bên chậm thực hiện nghĩa vụ nộp phạt {n}% giá trị phần việc chậm.',
                     'Hai bên thống nhất mức phạt vi phạm là {n}% giá trị phần nghĩa vụ không thực hiện.'],
    'warranty_default': ['Hàng hóa được bảo hành {n} tháng tính từ ngày giao.',
                         'Thời hạn bảo hành sản phẩm là {n} tháng kể từ ngày Bên mua nhận hàng.',
                         'Bên bán chịu trách nhiệm bảo hành hàng hóa trong {n} tháng sau khi giao hàng.',
                         'Sản phẩm được bảo hành miễn phí {n} tháng kể từ ngày bàn giao.'],
    'place': ['Địa điểm giao hàng là kho số {n} của Bên mua.',
              'Hàng hóa được giao tại cảng nội địa số {n} theo chỉ định của Bên mua.',
              'Bên bán giao hàng tại chi nhánh số {n} của Bên mua.',
              'Hàng được giao tại bãi tập kết số {n} gần công trình của Bên mua.'],
    'acceptance': ['Việc nghiệm thu được thực hiện chậm nhất {n} ngày sau khi Bên B thông báo hoàn thành, căn cứ bản vẽ thiết kế đã duyệt.',
                   'Hai bên lập biên bản nghiệm thu trong {n} ngày kể từ ngày hoàn thành theo tiêu chuẩn kỹ thuật tại Phụ lục 02.',
                   'Nghiệm thu được tiến hành trong {n} ngày theo các tiêu chí nêu tại phụ lục hợp đồng.',
                   'Bên A tổ chức nghiệm thu trong vòng {n} ngày theo danh mục tiêu chí kỹ thuật đã ký.'],
    'compensation': ['Bên gây thiệt hại bồi thường theo thiệt hại thực tế có chứng từ, thanh toán trong {n} ngày.',
                     'Khoản bồi thường bằng giá trị thiệt hại thực tế và được trả trong vòng {n} ngày kể từ ngày có biên bản xác định thiệt hại.',
                     'Bên vi phạm bồi thường toàn bộ chi phí sửa chữa thực tế trong vòng {n} ngày.',
                     'Thiệt hại được bồi thường theo giá trị thực tế có hóa đơn, chi trả trong {n} ngày.'],
    'price_change': ['Đơn giá được điều chỉnh khi giá nhiên liệu do cơ quan nhà nước công bố biến động trên {n}%.',
                     'Hai bên điều chỉnh giá khi chỉ số giá tiêu dùng tăng quá {n}% so với tháng ký hợp đồng.',
                     'Giá hợp đồng chỉ thay đổi khi giá vật liệu chính tăng hoặc giảm quá {n}% theo công bố của Sở Xây dựng.',
                     'Đơn giá được tính lại khi chỉ số giá xây dựng thay đổi quá {n}% so với thời điểm ký.'],
    'redemption': ['Thời hạn chuộc lại tài sản là {n} tháng tính từ ngày Bên mua nhận tài sản.',
                   'Trong vòng {n} tháng kể từ ngày giao tài sản, Bên bán có quyền chuộc lại tài sản đã bán.',
                   'Bên bán được mua lại tài sản đã bán trong {n} tháng kể từ ngày bàn giao.',
                   'Quyền chuộc lại của Bên bán kéo dài {n} tháng kể từ thời điểm giao tài sản.'],
    'complaint_terms': ['Thời hạn khiếu nại về số lượng hàng hóa là {n} ngày kể từ ngày giao hàng.',
                        'Bên mua gửi khiếu nại về số lượng cho Bên bán trong {n} ngày kể từ ngày nhận hàng.'],
}

# Ways to explain a numeric conflict and to word vague-clause answers, so answers are not one sentence learned by heart.
NUMERIC_EXPLANATIONS = [
    '{title} quy định {subject} là {shown}, {side} {limit} theo {ref}.',
    '{title} đặt {subject} ở mức {shown}, trong khi {ref} chỉ cho phép {bound} {limit}.',
    '{subject_cap} trong {title} là {shown}, {side} {limit} mà {ref} quy định.',
    'Theo {ref}, {subject} {bound} {limit}; {title} lại quy định {shown}.',
    '{title} ghi {subject} {shown}, không phù hợp với {ref} vì {side} {limit}.',
]
UNCLEAR_EXPLANATIONS = [
    '{title} {why}, dễ dẫn đến tranh chấp khi thực hiện.',
    '{title} {why}; khi phát sinh tranh chấp các bên khó chứng minh nghĩa vụ đã được thực hiện đúng.',
    '{title} {why}, nên mỗi bên có thể hiểu theo một cách khác nhau.',
    'Điều khoản chưa đủ cụ thể: {title} {why}.',
]
UNCLEAR_GENERIC_FIX = [
    'Ghi rõ nội dung cụ thể (con số, thời hạn hoặc tiêu chuẩn) trong điều khoản.',
    'Bổ sung tiêu chí đo được để hai bên cùng đối chiếu khi thực hiện điều khoản.',
    'Thay cách diễn đạt chung chung bằng mức, thời hạn hoặc tiêu chuẩn xác định.',
    'Quy định rõ nghĩa vụ của từng bên và hệ quả khi không thực hiện đúng.',
    'Bổ sung phụ lục nêu chi tiết nội dung mà điều khoản đang để ngỏ.',
]


# --------------------------------------------------------------------------- long articles (b)
# Share of governing provisions written as a long article with numbered paragraphs, and the paragraphs that sit
# around the rule (they set no limit a clause can break, so the rule's paragraph has to be found and quoted alone).
LONG_ARTICLE_SHARE = .5
ARTICLE_PARAGRAPHS = [
    'Hợp đồng phải được lập thành văn bản và có chữ ký của người đại diện hợp pháp của các bên, trừ trường hợp pháp luật có quy định khác.',
    'Các bên có quyền thỏa thuận về nội dung hợp đồng nhưng không được trái với điều cấm của luật và không trái đạo đức xã hội.',
    'Việc sửa đổi, bổ sung nội dung đã giao kết phải được các bên thống nhất và lập thành văn bản.',
    'Bên có quyền lợi bị vi phạm phải áp dụng các biện pháp hợp lý để hạn chế tổn thất, kể cả tổn thất đối với khoản lợi trực tiếp đáng lẽ được hưởng.',
    'Thông báo giữa các bên được gửi bằng văn bản đến địa chỉ đã ghi trong hợp đồng hoặc địa chỉ được thông báo sau đó.',
    'Trường hợp có sự kiện bất khả kháng, bên bị ảnh hưởng phải thông báo ngay cho bên kia và cung cấp bằng chứng về sự kiện đó.',
    'Bên vi phạm nghĩa vụ phải bồi thường thiệt hại phát sinh do hành vi vi phạm gây ra, trừ trường hợp có thỏa thuận khác.',
    'Quyền và nghĩa vụ của các bên được xác định theo hợp đồng và theo quy định của pháp luật có liên quan.',
    'Chính phủ quy định chi tiết các trường hợp áp dụng, hồ sơ và trình tự thực hiện quy định tại Điều này.',
    'Cơ quan nhà nước có thẩm quyền có trách nhiệm hướng dẫn, kiểm tra việc thực hiện quy định tại Điều này.',
    'Trường hợp điều ước quốc tế mà Việt Nam là thành viên có quy định khác thì áp dụng quy định của điều ước quốc tế đó.',
    'Các bên có thể thỏa thuận về việc giải quyết tranh chấp bằng thương lượng, hòa giải, trọng tài hoặc Tòa án.',
    'Hồ sơ, chứng từ liên quan đến việc thực hiện hợp đồng phải được các bên lưu giữ theo quy định của pháp luật về kế toán.',
    'Bên nhận được thông tin bí mật của bên kia không được tiết lộ cho bên thứ ba khi chưa được bên kia đồng ý bằng văn bản.',
    'Quy định tại Điều này không áp dụng đối với hợp đồng được giao kết trước ngày văn bản này có hiệu lực, trừ trường hợp các bên có thỏa thuận khác.',
    'Trường hợp hợp đồng có điều khoản không rõ ràng thì việc giải thích phải căn cứ vào ý chí đích thực của các bên khi xác lập hợp đồng.',
]

# --------------------------------------------------------------------------- party roles (d)
# The two roles of a contract on each topic, so the parties line can name who holds which role and the answer names
# the disadvantaged party by role and name, read from the brief, not from the topic alone.
ROLES = dict(
    interest=('Bên cho vay', 'Bên vay'), pledge=('Bên cho vay', 'Bên vay'), early_demand=('Bên cho vay', 'Bên vay'),
    probation=('Người sử dụng lao động', 'Người lao động'), written_labour=('Người sử dụng lao động', 'Người lao động'),
    id_papers=('Người sử dụng lao động', 'Người lao động'), overtime=('Người sử dụng lao động', 'Người lao động'),
    refund=('Bên bán', 'Bên mua'), complaint=('Bên bán', 'Bên mua'), pay_vague=('Bên mua', 'Bên bán'),
    price_vague=('Bên bán', 'Bên mua'), delivery_vague=('Bên bán', 'Bên mua'), quality_vague=('Bên bán', 'Bên mua'),
    adjust_vague=('Bên bán', 'Bên mua'), later_vague=('Bên mua', 'Bên bán'),
    advance=('Bên giao thầu', 'Bên nhận thầu'), warranty=('Bên nhận thầu', 'Bên giao thầu'),
    accept_vague=('Bên giao thầu', 'Bên nhận thầu'), bid_security=('Bên mời thầu', 'Bên dự thầu'),
    performance_security=('Bên mời thầu', 'Bên trúng thầu'), auction_deposit=('Người tổ chức đấu giá', 'Người tham gia đấu giá'),
    usufruct=('Bên hưởng dụng', 'Bên có tài sản'), deposit=('Bên cho thuê', 'Bên thuê'), rent_notice=('Bên cho thuê', 'Bên thuê'),
    entry=('Bên cho thuê', 'Bên thuê'), rent_vague=('Bên thuê', 'Bên cho thuê'))
