"""Headings found by models rebuild a nested tree: part > chapter > section > article."""
from django.test import SimpleTestCase

from ai_extract.services.document_structure_service import apply_heading_hierarchy
from ai_extract.services.heading_role_service import RANK, find_headings

LEAVES = [('t0', 'CHƯƠNG I', 'paragraph'), ('t1', 'NHỮNG QUY ĐỊNH CHUNG', 'paragraph'),
          ('a1', 'Điều 1. Phạm vi điều chỉnh', 'paragraph'), ('b1', '1. Luật này quy định về hộ tịch.', 'paragraph'),
          ('m1', 'Mục 1', 'paragraph'), ('a2', 'Điều 2. Đăng ký khai sinh', 'paragraph'), ('b2', 'Cha mẹ đăng ký khai sinh.', 'paragraph'),
          ('tb', 'Bảng', 'table'), ('c2', 'CHƯƠNG II', 'paragraph'), ('a3', 'Điều 3. Khai tử', 'paragraph'),
          ('b3', 'Người thân đăng ký khai tử.', 'paragraph'), ('ph', '5', 'page_header')]
ROLES = {'CHƯƠNG I': ('chapter_heading', 1.), 'CHƯƠNG I\nNHỮNG QUY ĐỊNH CHUNG': ('chapter_heading', .99),
         'Mục 1': ('section_heading', .85), 'Mục 1\nĐiều 2. Đăng ký khai sinh': ('section_heading', .5),
         'CHƯƠNG II': ('chapter_heading', 1.), 'NHỮNG QUY ĐỊNH CHUNG': ('body_text', .7)}


def tree():
    leaves = [dict(chunk_id=i, text=t, layout_type=k, node_id='root', ancestor_ids=['root'], heading_path=['Luật'],
                   source_chunk_id=i, page_number=1) for i, t, k in LEAVES]
    leaves[7]['node_id'] = 'n_table'
    leaves[11]['node_id'] = 'n_header'
    nodes = [dict(id='root', parent_id=None, kind='document', title='Luật', ordinal=0, level=0),
             dict(id='n_flat', parent_id='root', kind='section', title='CHƯƠNG I', ordinal=1, level=1),
             dict(id='n_table', parent_id='root', kind='table', title='Bảng', ordinal=2, level=1),
             dict(id='n_header', parent_id='root', kind='page_header', title='5', ordinal=3, level=1)]
    clauses = [dict(title='Điều 1. Phạm vi điều chỉnh', source_ids=['a1', 'b1']), dict(title='Điều 2. Đăng ký khai sinh', source_ids=['a2', 'b2']),
               dict(title='Điều 3. Khai tử', source_ids=['a3', 'b3'])]
    return dict(nodes=nodes, leaves=leaves, contract_clauses=dict(status='complete', clauses=clauses))


def requester(units, task='role'):
    if task == 'line':
        # Sentences are not heading lines; everything else in these fixtures is.
        return [dict(id=u['id'], role='sentence' if u['text'].endswith('.') else 'heading', confidence=.9) for u in units]
    return [dict(id=u['id'], role=ROLES.get(u['text'], ('body_text', .9))[0], confidence=ROLES.get(u['text'], ('body_text', .9))[1])
            for u in units]


class HeadingHierarchyTests(SimpleTestCase):
    def build(self):
        data = tree()
        apply_heading_hierarchy(data, find_headings(data, requester), RANK)
        return data, {l['chunk_id']: l for l in data['leaves']}

    def test_articles_nest_in_sections_and_chapters(self):
        _, leaves = self.build()
        self.assertEqual(leaves['b2']['heading_path'], ['Luật', 'CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG', 'Mục 1', 'Điều 2. Đăng ký khai sinh'])
        self.assertEqual(leaves['b1']['heading_path'], ['Luật', 'CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG', 'Điều 1. Phạm vi điều chỉnh'])

    def test_a_new_chapter_closes_the_previous_chapter_and_its_section(self):
        _, leaves = self.build()
        self.assertEqual(leaves['b3']['heading_path'], ['Luật', 'CHƯƠNG II', 'Điều 3. Khai tử'])

    def test_a_heading_split_over_two_blocks_is_one_node(self):
        data, leaves = self.build()
        chapters = [n for n in data['nodes'] if n['kind'] == 'chapter']
        self.assertEqual([n['title'] for n in chapters], ['CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG', 'CHƯƠNG II'])
        self.assertEqual(leaves['t1']['node_id'], leaves['t0']['node_id'])

    def test_a_pair_the_model_no_longer_calls_a_heading_is_not_joined(self):
        _, leaves = self.build()
        # "Mục 1" + "Điều 2..." read together scored .5: the article stays its own heading.
        self.assertNotEqual(leaves['a2']['node_id'], leaves['m1']['node_id'])

    def test_tables_move_under_the_open_heading_and_page_furniture_stays_at_the_root(self):
        data, leaves = self.build()
        nodes = {n['id']: n for n in data['nodes']}
        self.assertEqual(nodes[nodes['n_table']['parent_id']]['title'], 'Điều 2. Đăng ký khai sinh')
        self.assertEqual(nodes['n_header']['parent_id'], 'root')
        self.assertEqual(leaves['tb']['heading_path'][-1], 'Bảng')

    def test_old_flat_heading_nodes_are_replaced(self):
        data, _ = self.build()
        self.assertNotIn('n_flat', {n['id'] for n in data['nodes']})
        self.assertEqual(sorted(n['level'] for n in data['nodes'] if n['kind'] == 'article'), [2, 2, 3])

    def test_a_layout_title_right_after_a_ranked_heading_is_its_name(self):
        data = tree()
        data['leaves'][1]['layout_type'] = 'title'
        def model(units, task='role'):
            if task == 'line':
                return [dict(id=u['id'], role='heading', confidence=.9) for u in units]
            return [dict(id=u['id'], role='chapter_heading' if u['text'] == 'CHƯƠNG I' else 'body_text', confidence=1.) for u in units]
        apply_heading_hierarchy(data, find_headings(data, model), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['b1']['heading_path'], ['Luật', 'CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG', 'Điều 1. Phạm vi điều chỉnh'])
        self.assertEqual([n['title'] for n in data['nodes'] if n['kind'] == 'chapter'], ['CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG'])

    def test_a_heading_and_its_name_split_by_a_page_break_stay_one_heading(self):
        data = tree()
        page = dict(data['leaves'][11], chunk_id='pn', text='3', layout_type='page_footer', node_id='n_header')
        data['leaves'].insert(1, page)
        apply_heading_hierarchy(data, find_headings(data, requester), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['t1']['node_id'], leaves['t0']['node_id'])
        self.assertEqual(leaves['b1']['heading_path'][1], 'CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG')
        self.assertEqual(leaves['pn']['ancestor_ids'][0], 'root')

    def test_the_tree_follows_the_reading_sequence_not_the_list_order(self):
        data = tree()
        sequence = [l['chunk_id'] for l in data['leaves']]
        data['reading_sequence'] = sequence
        data['leaves'] = list(reversed(data['leaves']))
        apply_heading_hierarchy(data, find_headings(data, requester), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['b2']['heading_path'], ['Luật', 'CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG', 'Mục 1', 'Điều 2. Đăng ký khai sinh'])

    def test_a_sentence_the_role_labels_call_a_part_is_not_a_heading(self):
        data = tree()
        data['leaves'][3]['text'] = 'Khi nhiều người cùng thực hiện một nghĩa vụ, mỗi người có một phần nghĩa vụ.'
        roles = dict(ROLES, **{data['leaves'][3]['text']: ('part_heading', .97)})
        def model(units, task='role'):
            if task == 'line':
                return [dict(id=u['id'], role='sentence' if u['text'].endswith('.') else 'heading', confidence=.94) for u in units]
            return [dict(id=u['id'], role=roles.get(u['text'], ('body_text', .9))[0], confidence=roles.get(u['text'], ('body_text', .9))[1]) for u in units]
        apply_heading_hierarchy(data, find_headings(data, model), RANK)
        self.assertEqual([n for n in data['nodes'] if n['kind'] == 'part'], [])
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['b2']['heading_path'], ['Luật', 'CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG', 'Mục 1', 'Điều 2. Đăng ký khai sinh'])

    def test_an_unranked_title_inside_an_article_stays_a_line_of_that_article(self):
        data = tree()
        # "4. Nội dung đăng ký khai tử gồm:" read as a layout title in the middle of Điều 2, before its points.
        line = dict(data['leaves'][6], chunk_id='k4', text='4. Nội dung đăng ký khai tử gồm:', layout_type='title')
        point = dict(data['leaves'][6], chunk_id='p4', text='a) Họ, tên người chết;', layout_type='paragraph')
        data['leaves'][7:7] = [line, point]
        data['contract_clauses']['clauses'][1]['source_ids'] += ['k4', 'p4']
        apply_heading_hierarchy(data, find_headings(data, requester), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['k4']['heading_path'], ['Luật', 'CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG', 'Mục 1', 'Điều 2. Đăng ký khai sinh'])
        self.assertEqual(leaves['p4']['heading_path'], leaves['k4']['heading_path'])
        self.assertNotIn('4. Nội dung đăng ký khai tử gồm:', [n['title'] for n in data['nodes']])
        self.assertEqual(leaves['b3']['heading_path'], ['Luật', 'CHƯƠNG II', 'Điều 3. Khai tử'])

    def test_an_unranked_title_right_before_the_next_article_keeps_its_node(self):
        data = tree()
        # A section name the model did not rank, between Điều 2 and the table that precedes CHƯƠNG II.
        name = dict(data['leaves'][6], chunk_id='sn', text='TÍN CHẤP', layout_type='title')
        data['leaves'].insert(7, name)
        data['leaves'].insert(8, dict(data['leaves'][6], chunk_id='a9', text='Điều 9. Tín chấp', layout_type='paragraph'))
        data['contract_clauses']['clauses'].insert(2, dict(title='Điều 9. Tín chấp', source_ids=['a9']))
        apply_heading_hierarchy(data, find_headings(data, requester), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertIn('TÍN CHẤP', leaves['a9']['heading_path'])

    def test_the_heading_of_the_next_group_leaves_the_end_of_the_previous_article(self):
        data = tree()
        clause = data['contract_clauses']['clauses'][0]
        clause.update(source_ids=['a1', 'b1', 'm1'], content='Điều 1. Phạm vi điều chỉnh\n1. Luật này quy định về hộ tịch.\nMục 1')
        data['contract_clauses']['clauses'][1]['source_ids'] = ['a2', 'b2', 'c2']
        data['contract_clauses']['clauses'][1]['content'] = 'Điều 2. Đăng ký khai sinh\nCha mẹ đăng ký khai sinh.\nCHƯƠNG II'
        apply_heading_hierarchy(data, find_headings(data, requester), RANK)
        first, second = data['contract_clauses']['clauses'][:2]
        self.assertEqual(first['source_ids'], ['a1', 'b1'])
        self.assertEqual(first['content'], 'Điều 1. Phạm vi điều chỉnh\n1. Luật này quy định về hộ tịch.')
        self.assertEqual(second['source_ids'], ['a2', 'b2'])
        self.assertTrue(second['content'].endswith('Cha mẹ đăng ký khai sinh.'))

    def test_a_section_the_layout_called_a_page_footer_heads_its_articles_with_its_name(self):
        data = tree()
        # "Mục 1" at the foot of a page read as a footer, its name a layout title at the top of the next page.
        data['leaves'][4]['layout_type'] = 'page_footer'
        data['leaves'].insert(5, dict(data['leaves'][4], chunk_id='mn', text='ĐĂNG KÝ KHAI SINH', layout_type='title'))
        apply_heading_hierarchy(data, find_headings(data, requester), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['b2']['heading_path'], ['Luật', 'CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG', 'Mục 1 ĐĂNG KÝ KHAI SINH', 'Điều 2. Đăng ký khai sinh'])

    def test_a_sub_section_nests_inside_its_section_and_the_next_section_closes_it(self):
        data = tree()
        extra = [('s1', 'Tiểu mục 1', 'paragraph'), ('a5', 'Điều 5. Chiếm hữu', 'paragraph'), ('b5', 'Chiếm hữu là nắm giữ.', 'paragraph'),
                 ('s2', 'Tiểu mục 2', 'paragraph'), ('a6', 'Điều 6. Sử dụng', 'paragraph'), ('b6', 'Sử dụng là khai thác.', 'paragraph'),
                 ('m2', 'Mục 2', 'paragraph'), ('a7', 'Điều 7. Sở hữu chung', 'paragraph'), ('b7', 'Sở hữu chung là của nhiều người.', 'paragraph')]
        base = data['leaves'][6]
        data['leaves'][7:7] = [dict(base, chunk_id=i, text=t, layout_type=k) for i, t, k in extra]
        data['contract_clauses']['clauses'][2:2] = [dict(title=t, source_ids=[a, b]) for t, a, b in
            (('Điều 5. Chiếm hữu', 'a5', 'b5'), ('Điều 6. Sử dụng', 'a6', 'b6'), ('Điều 7. Sở hữu chung', 'a7', 'b7'))]
        roles = dict(ROLES, **{'Tiểu mục 1': ('section_heading', .5), 'Tiểu mục 2': ('section_heading', .54), 'Mục 2': ('section_heading', .8)})
        def model(units, task='role'):
            if task == 'line':
                return requester(units, task)
            return [dict(id=u['id'], role=roles.get(u['text'], ('body_text', .9))[0], confidence=roles.get(u['text'], ('body_text', .9))[1]) for u in units]
        apply_heading_hierarchy(data, find_headings(data, model), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        chapter = 'CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG'
        self.assertEqual(leaves['b5']['heading_path'], ['Luật', chapter, 'Mục 1', 'Tiểu mục 1', 'Điều 5. Chiếm hữu'])
        self.assertEqual(leaves['b6']['heading_path'], ['Luật', chapter, 'Mục 1', 'Tiểu mục 2', 'Điều 6. Sử dụng'])
        self.assertEqual(leaves['b7']['heading_path'], ['Luật', chapter, 'Mục 2', 'Điều 7. Sở hữu chung'])
        self.assertEqual(leaves['b3']['heading_path'], ['Luật', 'CHƯƠNG II', 'Điều 3. Khai tử'])

    def test_a_numbered_layout_title_that_continues_the_article_list_stays_in_the_article(self):
        data = tree()
        # "2.Khi …" read as a layout title right after "1. …" and right before the next article.
        data['leaves'][6]['text'] = '1. Cha mẹ đăng ký khai sinh.'
        data['leaves'].insert(7, dict(data['leaves'][6], chunk_id='k2', text='2.Khi đăng ký, xuất trình giấy tờ', layout_type='title'))
        data['contract_clauses']['clauses'][1]['source_ids'].append('k2')
        apply_heading_hierarchy(data, find_headings(data, requester), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['k2']['heading_path'][-1], 'Điều 2. Đăng ký khai sinh')
        self.assertNotIn('2.Khi đăng ký, xuất trình giấy tờ', [n['title'] for n in data['nodes']])

    def test_a_plain_line_between_a_section_and_the_next_article_is_the_section_name(self):
        data = tree()
        # "Mục 1" then "ĐĂNG KÝ KHAI SINH" read as a plain paragraph the pair check did not join, then Điều 2.
        data['leaves'].insert(5, dict(data['leaves'][4], chunk_id='mn', text='ĐĂNG KÝ KHAI SINH', layout_type='paragraph'))
        data['contract_clauses']['clauses'][0].update(source_ids=['a1', 'b1', 'm1', 'mn'],
            content='Điều 1. Phạm vi điều chỉnh\n1. Luật này quy định về hộ tịch.\nMục 1\nĐĂNG KÝ KHAI SINH')
        apply_heading_hierarchy(data, find_headings(data, requester), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['b2']['heading_path'][2], 'Mục 1 ĐĂNG KÝ KHAI SINH')
        first = data['contract_clauses']['clauses'][0]
        self.assertEqual(first['source_ids'], ['a1', 'b1'])
        self.assertEqual(first['content'], 'Điều 1. Phạm vi điều chỉnh\n1. Luật này quy định về hộ tịch.')

    def test_a_heading_found_before_an_article_has_text_is_that_article_text(self):
        data = tree()
        # The model called the only sentence of Điều 3 a chapter.
        data['leaves'][10]['text'] = 'Người thân có thể là người đăng ký khai tử'
        roles = dict(ROLES, **{'Người thân có thể là người đăng ký khai tử': ('chapter_heading', .95)})
        def model(units, task='role'):
            if task == 'line':
                return [dict(id=u['id'], role='heading', confidence=.9) for u in units]
            return [dict(id=u['id'], role=roles.get(u['text'], ('body_text', .9))[0], confidence=roles.get(u['text'], ('body_text', .9))[1]) for u in units]
        data['contract_clauses']['clauses'][2]['content'] = 'Điều 3. Khai tử\nNgười thân có thể là người đăng ký khai tử'
        apply_heading_hierarchy(data, find_headings(data, model), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['b3']['heading_path'], ['Luật', 'CHƯƠNG II', 'Điều 3. Khai tử'])
        self.assertIn('Người thân', data['contract_clauses']['clauses'][2]['content'])

    def test_a_provision_the_model_took_for_a_section_stays_in_its_article(self):
        data = tree()
        # Inside Điều 2, "2. … trong các trường hợp sau:" scored as a section, followed by its points.
        extra = [('k2', '2. Ủy ban nhân dân cấp huyện đăng ký trong các trường hợp sau', 'paragraph'),
                 ('pa', 'a) Khai sinh có yếu tố nước ngoài', 'paragraph'), ('pb', 'b) Kết hôn có yếu tố nước ngoài', 'paragraph')]
        data['leaves'][7:7] = [dict(data['leaves'][6], chunk_id=i, text=t, layout_type=k) for i, t, k in extra]
        roles = dict(ROLES, **{extra[0][1]: ('section_heading', .45)})
        def model(units, task='role'):
            if task == 'line':
                return [dict(id=u['id'], role='heading', confidence=.9) for u in units]
            return [dict(id=u['id'], role=roles.get(u['text'], ('body_text', .9))[0], confidence=roles.get(u['text'], ('body_text', .9))[1]) for u in units]
        apply_heading_hierarchy(data, find_headings(data, model), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        for chunk in ('k2', 'pa', 'pb'):
            self.assertEqual(leaves[chunk]['heading_path'][-1], 'Điều 2. Đăng ký khai sinh')

    def test_a_section_name_over_several_lines_joins_the_section(self):
        data = tree()
        names = [('n1', 'GHI VÀO SỔ HỘ TỊCH VIỆC THAY ĐỔI', 'paragraph'), ('n2', 'THEO BẢN ÁN, QUYẾT ĐỊNH CỦA', 'paragraph'),
                 ('n3', 'CƠ QUAN NHÀ NƯỚC CÓ THẨM QUYỀN', 'paragraph')]
        data['leaves'][5:5] = [dict(data['leaves'][4], chunk_id=i, text=t, layout_type=k) for i, t, k in names]
        roles = dict(ROLES, **{'GHI VÀO SỔ HỘ TỊCH VIỆC THAY ĐỔI': ('section_heading', .7)})
        def model(units, task='role'):
            if task == 'line':
                return [dict(id=u['id'], role='heading', confidence=.9) for u in units]
            return [dict(id=u['id'], role=roles.get(u['text'], ('body_text', .9))[0], confidence=roles.get(u['text'], ('body_text', .9))[1]) for u in units]
        apply_heading_hierarchy(data, find_headings(data, model), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['b2']['heading_path'][2],
                         'Mục 1 GHI VÀO SỔ HỘ TỊCH VIỆC THAY ĐỔI THEO BẢN ÁN, QUYẾT ĐỊNH CỦA CƠ QUAN NHÀ NƯỚC CÓ THẨM QUYỀN')
        self.assertEqual(len([n for n in data['nodes'] if n['kind'] == 'section']), 1)

    def test_a_weak_heading_with_the_numbering_of_an_open_section_is_its_sibling(self):
        data = tree()
        extra = [('s1', 'Tiểu mục 1', 'paragraph'), ('a5', 'Điều 5. Chiếm hữu', 'paragraph'), ('b5', 'Chiếm hữu là nắm giữ.', 'paragraph'),
                 ('s2', 'Tiểu mục 2', 'paragraph'), ('n2', 'BẢO LƯU QUYỀN SỞ HỮU', 'title'), ('a6', 'Điều 6. Sử dụng', 'paragraph'),
                 ('b6', 'Sử dụng là khai thác.', 'paragraph'), ('w9', 'Mục 9', 'paragraph'), ('x9', 'Một câu thường.', 'paragraph')]
        base = data['leaves'][6]
        data['leaves'][7:7] = [dict(base, chunk_id=i, text=t, layout_type=k) for i, t, k in extra]
        data['contract_clauses']['clauses'][2:2] = [dict(title=t, source_ids=[a, b]) for t, a, b in
            (('Điều 5. Chiếm hữu', 'a5', 'b5'), ('Điều 6. Sử dụng', 'a6', 'b6'))]
        # "Tiểu mục 2" scored .53 as a chapter, below every threshold; "Mục 9" too, with no open "mục" around it.
        roles = dict(ROLES, **{'Tiểu mục 1': ('section_heading', .5), 'Tiểu mục 2': ('chapter_heading', .53),
                               'Mục 9': ('chapter_heading', .5)})
        def model(units, task='role'):
            if task == 'line':
                return [dict(id=u['id'], role='heading', confidence=.9) for u in units]
            return [dict(id=u['id'], role=roles.get(u['text'], ('body_text', .9))[0], confidence=roles.get(u['text'], ('body_text', .9))[1]) for u in units]
        apply_heading_hierarchy(data, find_headings(data, model), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        chapter = 'CHƯƠNG I NHỮNG QUY ĐỊNH CHUNG'
        self.assertEqual(leaves['b6']['heading_path'], ['Luật', chapter, 'Mục 1', 'Tiểu mục 2 BẢO LƯU QUYỀN SỞ HỮU', 'Điều 6. Sử dụng'])

    def test_outline_numbers_that_continue_a_heading_are_headings_in_a_document_without_articles(self):
        rows = [('h9', '9. Kiểm định rơ moóc', 'title'), ('h92', '9.2. Bảng mức tính toán', 'title'), ('t9', 'Bảng 9', 'table'),
                ('h10', '10. Kiểm định xe ô tô chở người', 'paragraph'), ('h101', '10.1. Thành phần công việc', 'paragraph'),
                ('b10', '- Tiếp nhận hồ sơ', 'paragraph'), ('h102', '10.2. Bảng mức tính toán', 'paragraph'), ('t10', 'Bảng 10', 'table'),
                ('x', '5. Một dòng lạc số', 'paragraph')]
        leaves = [dict(chunk_id=i, text=t, layout_type=k, node_id='root', ancestor_ids=['root'], heading_path=['Phụ lục'],
                       source_chunk_id=i, page_number=1) for i, t, k in rows]
        data = dict(nodes=[dict(id='root', parent_id=None, kind='document', title='Phụ lục', ordinal=0, level=0)], leaves=leaves,
                    contract_clauses=dict(status='no_clauses', clauses=[]))
        apply_heading_hierarchy(data, find_headings(data, lambda units, task='role': [dict(id=u['id'], role='body_text', confidence=.9) for u in units]), RANK)
        by = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(by['t10']['heading_path'][-1], '10.2. Bảng mức tính toán')
        self.assertEqual(by['t9']['heading_path'][-1], '9.2. Bảng mức tính toán')
        self.assertNotIn('5. Một dòng lạc số', [n['title'] for n in data['nodes']])

    def test_outline_marker_is_the_words_before_the_number(self):
        from ai_extract.services.document_structure_service import outline_marker
        self.assertEqual(outline_marker('Tiểu mục 1 QUYỀN CHIẾM HỮU'), 'tiểu mục')
        self.assertEqual(outline_marker('MỤC 2 HỢP ĐỒNG'), 'mục')
        self.assertEqual(outline_marker('Section 3. Scope'), 'section')
        self.assertEqual(outline_marker('Chương IV Điều khoản thi hành'), 'chương')
        self.assertEqual(outline_marker('QUY ĐỊNH CHUNG'), '')

    def test_without_clauses_or_model_headings_layout_titles_still_head_their_text(self):
        data = tree()
        data['contract_clauses'] = dict(status='no_clauses')
        data['leaves'][2]['layout_type'] = 'title'
        apply_heading_hierarchy(data, find_headings(data, lambda units, task='role': [dict(id=u['id'], role='body_text', confidence=.9) for u in units]), RANK)
        leaves = {l['chunk_id']: l for l in data['leaves']}
        self.assertEqual(leaves['b1']['heading_path'], ['Luật', 'Điều 1. Phạm vi điều chỉnh'])


class ClauseRowSyncTests(SimpleTestCase):
    def test_stored_clauses_take_the_trimmed_text_in_place_and_a_changed_list_is_left_alone(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from ai_extract.repositories import extraction_repository as repo
        rows = [SimpleNamespace(pk=1, clause_title='Điều 1. A', clause_content='Điều 1. A\nNội dung\nMục 2'),
                SimpleNamespace(pk=2, clause_title='Điều 2. B', clause_content='Điều 2. B\nKhác')]
        tree = [dict(title='Điều 1. A', content='Điều 1. A\nNội dung'), dict(title='Điều 2. B', content='Điều 2. B\nKhác')]
        manager = SimpleNamespace(filter=lambda **k: SimpleNamespace(order_by=lambda *a: rows), bulk_update=lambda changed, fields: None)
        with patch.object(repo.Clause, 'objects', manager):
            self.assertEqual(repo.update_clause_contents('version', tree), 1)
            self.assertEqual(rows[0].clause_content, 'Điều 1. A\nNội dung')
            self.assertEqual(repo.update_clause_contents('version', tree[:1]), 0)


class ClauseEntityRowsTests(SimpleTestCase):
    """ExtractedEntity holds the GLiNER entities of each clause; the parties live in ContractParty."""
    def test_each_entity_is_stored_once_under_the_clauses_it_was_read_from(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        from ai_extract.models import Clause, ExtractedEntity
        from ai_extract.repositories import extraction_repository as repo
        rows = [Clause(pk=1, clause_title='Điều 1. A'), Clause(pk=2, clause_title='Điều 2. B')]
        clauses = [dict(title='Điều 1. A', source_ids=['b1', 'b2']), dict(title='Điều 2. B', source_ids=['b3'])]
        entities = [dict(name='Bên  bán', identity_name_key='bên bán', confidence=0.61, source_ids=['b1'], entity_type='ENTITY'),
                    dict(name='Bên bán', identity_name_key='bên bán', confidence=0.9, source_ids=['b2', 'b3'], entity_type='ENTITY'),
                    dict(name='Phụ lục', confidence=0.5, source_ids=['elsewhere'])]
        stored = MagicMock()
        with patch.object(Clause, 'objects', SimpleNamespace(filter=lambda **k: SimpleNamespace(order_by=lambda *a: rows))), \
             patch.object(ExtractedEntity, 'objects', stored), patch('django.db.transaction.atomic'):
            self.assertEqual(repo.replace_clause_entities('version', clauses, entities), 2)
            self.assertIsNone(repo.replace_clause_entities('version', clauses[:1], entities))
        written = list(stored.bulk_create.call_args_list[0].args[0])
        self.assertEqual([(e.clause_id, e.entity_value, e.normalized_value, float(e.confidence_score)) for e in written],
                         [(1, 'Bên bán', 'bên bán', 0.9), (2, 'Bên bán', 'bên bán', 0.9)])
