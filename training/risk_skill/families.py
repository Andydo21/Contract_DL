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

STATUSES = ['Còn hiệu lực'] * 3 + ['Hết hiệu lực một phần. Các điều của văn bản này có thể không còn áp dụng nguyên văn.']
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
    # Evaluation only.
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
    # Evaluation only.
    'rent_vague': dict(law='pay_term', clause_title='Tiền thuê', clause='Bên thuê trả tiền thuê theo định kỳ phù hợp với khả năng của Bên thuê.',
        category='Kỳ thanh toán tiền thuê không xác định', why='không xác định được kỳ và thời hạn trả tiền thuê', party='Bên cho thuê'),
}
HOLDOUT = {'deposit', 'overtime', 'rent_notice', 'entry', 'rent_vague'}


def number(v):
    """Vietnamese decimal comma: 2.5 -> '2,5'."""
    return (f'{v:.2f}'.rstrip('0').rstrip('.') if v != int(v) else str(int(v))).replace('.', ',')


class Maker:
    def __init__(self, rng):
        self.rng = rng

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
        law = self.law(t['law_title'], t['law'].format(limit=number(limit)))
        sentence = t['clause'].format(value=shown)
        clause = self.clause(t['clause_title'], sentence)
        breaks = value > limit if t['kind'] == 'max' else value < limit
        expect = dict(group=t['kind'], topic=key, conflict=breaks, unclear=False, limit=limit, value=value)
        if not breaks:
            return clause, law, None, expect
        ref = f'Điều {law["article"]} {law["name"]}'
        extra = f' (tương đương {number(value)}%/năm)' if key == 'interest' and '/tháng' in shown else ''
        explanation = (f'{clause["title"]} quy định {t["subject"]} là {shown}{extra}, '
                       f'{"vượt mức tối đa" if t["kind"] == "max" else "thấp hơn mức tối thiểu"} {number(limit)}{t["unit"]} theo {ref}.')
        risk = dict(category=t['category'], risk_level=t['level'], explanation=explanation,
                    recommendation=f'Điều chỉnh {t["subject"]} {"không vượt quá" if t["kind"] == "max" else "không thấp hơn"} {number(limit)}{t["unit"]}.',
                    disadvantaged_party=t['party'], contract_quote=sentence, law_quote=law['text'].split('\n', 1)[1], kind='conflict')
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
        law = self.law(t['law_title'], t['law'].format(d=self.rng.choice([6, 12, 24])))
        clause = self.clause(t['clause_title'], t['clause'].format(n=n))
        return clause, law, None, dict(group='default', topic=key, conflict=False, unclear=False)

    def ruled(self, key, breaks=None):
        t = RULED[key]
        breaks = self.rng.random() < .6 if breaks is None else breaks
        law = self.law(t['law_title'], t['law'])
        sentence = t['breaks'] if breaks else t['keeps']
        clause = self.clause(t['clause_title'], sentence)
        expect = dict(group=t['group'], topic=key, conflict=breaks, unclear=False)
        if not breaks:
            return clause, law, None, expect
        ref = f'Điều {law["article"]} {law["name"]}'
        risk = dict(category=t['category'], risk_level=t['level'],
                    explanation=f'{clause["title"]} {t["why"]}, trái với {ref}: {t["rule"]}.',
                    recommendation=f'Sửa điều khoản để bảo đảm {t["rule"]}.', disadvantaged_party=t['party'],
                    contract_quote=sentence, law_quote=t['law'], kind='conflict')
        return clause, law, risk, expect

    def unclear(self, key):
        t = UNCLEAR[key]
        law = self.default(t['law'])[1]
        clause = self.clause(t['clause_title'], t['clause'])
        risk = dict(category=t['category'], risk_level='LOW', explanation=f'{clause["title"]} {t["why"]}, dễ dẫn đến tranh chấp khi thực hiện.',
                    recommendation='Ghi rõ nội dung cụ thể (con số, thời hạn hoặc tiêu chuẩn) trong điều khoản.', disadvantaged_party=t['party'],
                    contract_quote=t['clause'], law_quote='', kind='unclear')
        return clause, law, risk, dict(group='unclear', topic=key, conflict=False, unclear=True)

    def distractors(self, exclude, holdout):
        """Provisions on other subjects, as retrieval also returns."""
        pool = [k for k in (*NUMERIC, *RULED, *DEFAULT) if k != exclude and (holdout or k not in HOLDOUT)]
        out = []
        for key in self.rng.sample(pool, self.rng.choice([0, 1, 1, 2])):
            if key in NUMERIC:
                t = NUMERIC[key]
                out.append(self.law(t['law_title'], t['law'].format(limit=number(self.rng.choice(t['limits'])))))
            elif key in RULED:
                out.append(self.law(RULED[key]['law_title'], RULED[key]['law']))
            else:
                out.append(self.default(key)[1])
        return out
