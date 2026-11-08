from django.test import SimpleTestCase

from ai_extract.services import table_lines_service as lines_service

X = [0, 100, 200, 500, 600, 700, 800]   # Mã, Tên dịch vụ, Thành phần, Đơn vị, Hao phí kiểm định, Hao phí GCN
HEADER_RULE, BOTTOM = 100, 1000
RULES = [[0, 0, 800, 0], [0, HEADER_RULE, 800, HEADER_RULE], [600, 50, 800, 50], [0, BOTTOM, 800, BOTTOM]]


def line(column, y, text, height=20):
    middle = (X[column]+X[column+1])/2
    return dict(bbox=[middle-30, y-height/2, middle+30, y+height/2], text=text, probability=.99)


def page_15_body():
    """Name lines 40 apart; a wrapped name's lines 32 apart; its value centred between them."""
    names = [(130, 'Vật liệu, nhiên liệu, dụng cụ'), (162, 'lao động'), (202, 'Điện năng'), (242, 'Mực in'),
             (282, 'Nhân công'), (322, 'Thiết bị kiểm tra phanh'), (362, 'Thiết bị kiểm tra đèn chiếu sáng'),
             (394, 'phía trước'), (434, 'Thiết bị đo khí thải'), (474, 'Máy ảnh'), (514, 'Máy photo')]
    body = [line(2, y, text) for y, text in names]
    body += [line(3, 202, 'kwh'), line(4, 202, '2,3185'), line(5, 202, '0,023'),
             line(3, 242, 'hộp'), line(4, 242, '0,0025'), line(5, 242, '0,0013'),
             line(3, 322, 'ca'), line(4, 322, '0,01'),
             line(3, 378, 'ca'), line(4, 378, '0,0042'),
             line(3, 434, 'ca'), line(4, 434, '0,0085'),
             line(3, 474, 'ca'), line(4, 474, '0,0018'),
             line(3, 514, 'ca'), line(4, 514, '0,0024')]
    # Merged down the body: the service name as a block of lines, the code as one line mid-band.
    body += [line(1, y, text) for y, text in ((500, 'Kiểm định'), (522, 'xe ô tô tải'), (544, '03 trục'))]
    body += [line(0, 550, 'KĐCG.05')]
    header = [line(0, 70, 'Mã dịch vụ'), line(2, 70, 'Thành phần hao phí'), line(4, 30, 'Hao phí'),
              line(4, 70, 'Hao phí'), line(4, 90, 'kiểm định'), line(5, 70, 'Hao phí'), line(5, 90, 'cấp GCN')]
    return header+body


class TableLinesTests(SimpleTestCase):
    def rebuild(self, lines):
        chosen = lines_service.body_bands(lines, X, RULES, 0, BOTTOM+5)
        pitch = lines_service._pitch(lines)
        aligned = [lines_service.align_band(lines, X, band, pitch) for band in chosen]
        return chosen, aligned

    def test_bands_are_found_from_boxes_before_any_text_is_read(self):
        boxes = [dict(bbox=l['bbox']) for l in page_15_body()]
        self.assertEqual(lines_service.body_bands(boxes, X, RULES, 0, BOTTOM+5), [(HEADER_RULE, BOTTOM)])

    def test_header_band_is_not_rebuilt(self):
        chosen, _ = self.rebuild(page_15_body())
        self.assertEqual(chosen, [(HEADER_RULE, BOTTOM)])

    def test_value_between_wrapped_lines_stays_with_its_name(self):
        _, [(rows, cells, warnings)] = self.rebuild(page_15_body())
        by_name = {row[2]: row for row in rows}
        self.assertEqual(by_name['Thiết bị kiểm tra đèn chiếu sáng phía trước'][4], '0,0042')
        self.assertEqual(by_name['Thiết bị đo khí thải'][4], '0,0085')
        self.assertEqual(by_name['Máy photo'][4], '0,0024')
        self.assertEqual(by_name['Điện năng'][3:], ['kwh', '2,3185', '0,023'])
        self.assertEqual(warnings, [])

    def test_heading_without_value_stays_its_own_row_unless_wrapped_tight(self):
        _, [(rows, _, _)] = self.rebuild(page_15_body())
        names = [row[2] for row in rows]
        self.assertIn('Vật liệu, nhiên liệu, dụng cụ lao động', names)
        self.assertIn('Nhân công', names)
        self.assertEqual(rows[names.index('Nhân công')][3:], ['', '', ''])

    def test_justified_line_split_into_word_boxes_is_one_line(self):
        lines = [l for l in page_15_body() if l['text'] != 'Thiết bị đo khí thải']
        lines += [dict(bbox=[210, 424, 260, 444], text='Thiết bị', probability=.99),
                  dict(bbox=[300, 425, 340, 445], text='đo khí', probability=.99),
                  dict(bbox=[420, 424, 470, 444], text='thải', probability=.99)]
        _, [(rows, _, issues)] = self.rebuild(lines)
        self.assertEqual(issues, [])
        self.assertIn(['', '', 'Thiết bị đo khí thải', 'ca', '0,0085', ''], [[''] * 2 + row[2:] for row in rows])

    def test_merged_columns_are_one_cell_over_the_band(self):
        _, [(rows, cells, _)] = self.rebuild(page_15_body())
        service = [c for c in cells if c['column'] == 2]
        code = [c for c in cells if c['column'] == 1]
        self.assertEqual([(c['row'], c['rowspan'], c['text']) for c in service], [(1, len(rows), 'Kiểm định xe ô tô tải 03 trục')])
        self.assertEqual([(c['rowspan'], c['text']) for c in code], [(len(rows), 'KĐCG.05')])

    def test_value_fitting_no_name_line_flags_the_table(self):
        lines = page_15_body()+[line(4, 293, '0,5')]   # between "Nhân công" and the next line, but not midway
        _, [(_, _, warnings)] = self.rebuild(lines)
        self.assertTrue(warnings)

    def test_two_values_in_one_row_flag_the_table(self):
        lines = page_15_body()+[line(5, 378, '0,1'), line(5, 394, '0,2')]   # both land on the wrapped name's row
        _, [(_, _, warnings)] = self.rebuild(lines)
        self.assertTrue(warnings)

    def test_assembled_grid_has_no_holes(self):
        from ai_extract.services.layout_service import validate_table_cells
        chosen, aligned = self.rebuild(page_15_body())
        header = [dict(row=1, column=c+1, rowspan=1, colspan=1, text=f'h{c}', bbox=[X[c], 1, X[c+1], HEADER_RULE])
                  for c in range(6)]
        rows, cells = lines_service.assemble(header, chosen, aligned, 6)
        self.assertEqual(rows[0], ['h0', 'h1', 'h2', 'h3', 'h4', 'h5'])
        validate_table_cells(dict(table_rows=rows, table_cells=cells, table_structure_status='cell_aware',
                                  table_structure_review=dict(rows=len(rows), columns=6)), (800, BOTTOM+5))

    def test_whole_table_from_lines_when_grid_crosses_band_rules(self):
        from ai_extract.services.layout_service import validate_table_cells
        lines = page_15_body()
        chosen, aligned = self.rebuild(lines)
        crossing = dict(row=1, column=1, rowspan=1, colspan=1, text='', bbox=[0, 40, 100, 300])
        self.assertTrue(lines_service.straddles(crossing, chosen, 5))
        everything = lines_service.text_bands(lines, X, RULES, 0, BOTTOM+5)
        results = [aligned[0] if band in chosen else lines_service.band_row(lines, X, band) for band in everything]
        rows, cells = lines_service.assemble([], everything, results, 6)
        self.assertEqual(rows[0][:4], ['Mã dịch vụ', '', 'Thành phần hao phí', ''])
        self.assertEqual(rows[0][4], 'Hao phí Hao phí kiểm định')
        validate_table_cells(dict(table_rows=rows, table_cells=cells, table_structure_status='cell_aware',
                                  table_structure_review=dict(rows=len(rows), columns=6)), (800, BOTTOM+5))

    def test_line_over_a_column_boundary_is_cut_there(self):
        self.assertEqual(lines_service.split_at_columns([[150, 0, 260, 10], [210, 0, 300, 10]], X),
                         [[150, 0, 200, 10], [200, 0, 260, 10], [210, 0, 300, 10]])

    def test_ruled_rows_are_left_to_the_grid(self):
        lines = [line(2, 130, 'A'), line(4, 130, '1'), line(2, 230, 'B'), line(4, 230, '2'), line(2, 330, 'C')]
        rules = RULES+[[0, 180, 800, 180], [0, 280, 800, 280]]
        self.assertEqual(lines_service.body_bands(lines, X, rules, 0, BOTTOM), [])


class HeaderSplitTests(SimpleTestCase):
    def test_header_line_is_cut_at_a_rule_but_not_at_glyph_strokes(self):
        from unittest.mock import patch
        from PIL import Image
        from ai_extract.services import surya_inference_service as surya
        captured = {}

        def read_lines(image, split=None, models=None):
            captured['pieces'] = split([[20, 60, 180, 80], [610, 25, 790, 40]])
            return [dict(bbox=box, text='Mã dịch vụ', probability=.99) for box in captured['pieces']]

        vertical = [[100, 0, 100, 1000],      # the rule between Mã dịch vụ and Tên dịch vụ
                    [60, 62, 60, 78],         # a stroke of a letter inside the line
                    [150, 55, 150, 85],       # a taller stroke, still far from any column boundary
                    [700, 50, 700, 1000]]     # the rule under "Hao phí" starts below it
        with patch('ai_extract.services.vietocr_service.read_lines', read_lines), \
                patch('ai_extract.services.language_service.language', return_value='vi'):
            surya.vietocr_table_lines(Image.new('RGB', (800, 1005), 'white'), X, RULES, 1.0, vertical)
        self.assertEqual(captured['pieces'], [[20, 60, 100, 80], [100, 60, 180, 80], [610, 25, 790, 40]])


class HeaderGridTests(SimpleTestCase):
    def test_header_cells_follow_its_rules(self):
        lines = [l for l in page_15_body() if _c(l) < HEADER_RULE]
        vertical = [[x, 0, x, BOTTOM] for x in X[1:5]]+[[700, 50, 700, BOTTOM]]   # none under "Hao phí"
        rows, cells, issues = lines_service.header_grid(lines, X, (0, HEADER_RULE), RULES, vertical)
        spans = {(c['row'], c['column']): (c['rowspan'], c['colspan'], c['text']) for c in cells}
        self.assertEqual(spans[(1, 1)], (2, 1, 'Mã dịch vụ'))
        self.assertEqual(spans[(1, 3)], (2, 1, 'Thành phần hao phí'))
        self.assertEqual(spans[(1, 5)], (1, 2, 'Hao phí'))
        self.assertEqual(spans[(2, 5)], (1, 1, 'Hao phí kiểm định'))
        self.assertEqual(spans[(2, 6)], (1, 1, 'Hao phí cấp GCN'))
        self.assertEqual(issues, [])

    def test_header_without_inner_rules_is_one_row(self):
        lines = [l for l in page_15_body() if _c(l) < HEADER_RULE]
        rows, _, _ = lines_service.header_grid(lines, X, (0, HEADER_RULE), [], [])
        self.assertEqual(len(rows), 1)


class WrappedHeadingTests(SimpleTestCase):
    def test_heading_running_to_the_column_edge_continues_on_the_next_line(self):
        names = [(130, 'Vật liệu, nhiên liệu, dụng cụ'), (170, 'lao động'), (210, 'Điện năng'), (250, 'Mực in'),
                 (290, 'Nhân công'), (330, 'Đăng kiểm viên')]
        lines = [line(2, y, text) for y, text in names]
        lines[0]['bbox'] = [205, 120, 495, 140]        # full width: it wrapped
        lines += [line(4, 210, '1,6'), line(4, 250, '0,3'), line(4, 330, '0,08')]
        rows, _, _ = lines_service.align_band(lines, X, (HEADER_RULE, BOTTOM), lines_service._pitch(lines))
        self.assertEqual([r[2] for r in rows], ['Vật liệu, nhiên liệu, dụng cụ lao động', 'Điện năng', 'Mực in',
                                                'Nhân công', 'Đăng kiểm viên'])


def _c(l):
    return (l['bbox'][1]+l['bbox'][3])/2
