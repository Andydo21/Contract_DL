"""Which short source blocks head a part, chapter or section, read by multilingual GLiNER2.

Surya's layout called nearly every heading of the civil status law "Text", and reading the page itself returns no
heading tags, so the heading tree was flat. Articles come from the clause split, which numbers them in any language
(Điều, Article, Статья, 第…条, 제…조); parts, chapters and sections come from this classifier. Measured on the civil
status law and the Civil Code: every chapter and part scored 1.00 and every section .75 to .89; on the BXD rate
appendix "1.1. Thành phần công việc" scored .9 as a part, which the part threshold keeps out.
"""
# Measured exactly as written: the classifier reads these descriptions, so rewording them moves its scores
# ("Mục 2" fell from a section at .88 to a chapter at .54 when examples were added to the descriptions).
LABELS = {
    'part_heading': 'Heading of a part or book of a code, the largest division (Phần, Part, Book, 编).',
    'chapter_heading': 'Heading of a chapter (Chương, Chapter, 章, 장, Глава), with or without its title.',
    'section_heading': 'Heading of a section inside a chapter or a numbered work item heading (Mục, Section, 节, 절).',
    'article_heading': 'Heading of a single article or clause with its number and title (Điều 5. ..., Article 5, 第五条, 제5조, Статья 5).',
    'list_item': 'A numbered paragraph or lettered point inside an article: 1. ..., a) ..., (i) ...',
    'body_text': 'Ordinary sentence or paragraph of running text, a signature, date or address line.',
}
SCHEMA = 'gliner2-heading-roles-v3'
# Second question for a block found as a part, chapter or section: is it a heading line at all? On the Civil Code the
# role labels took four sentences holding the word "phần" for parts ("Khi nhiều người ... một phần nghĩa vụ"); asked
# this, they scored .06 to .56 while every true part and chapter scored .75 or more.
LINE_LABELS = {'heading': 'A title line that names a part, chapter or section of a document; not a sentence.',
               'sentence': 'A sentence or numbered provision of running text that states a rule, with a verb.'}
LINE_HEADING = .6
# Per kind: chapters and parts scored 1.00 when right; a work item "1.1. Thành phần công việc" scored .9 as a part.
# Sections: across the library (610 lines: every Phần/Chương/Mục/Tiểu mục line, its name line, page furniture and a
# sample of running text) only true section and sub-section lines took the section label, "Tiểu mục 3" as low as .45
# and "Mục 4" at .55; the heading-or-sentence check then scored each of them .97 or more.
THRESHOLDS = {'part_heading': .95, 'chapter_heading': .9, 'section_heading': .4}
KINDS = {'part_heading': 'part', 'chapter_heading': 'chapter', 'section_heading': 'section'}
RANK = {'part': 1, 'chapter': 2, 'section': 3, 'article': 4}
# The three Civil Code sub-sections and one section the role labels missed scored .53 to .85 as chapters.
WEAK_HEADING = .4
MAX_CHARS = 220
FURNITURE = {'page_header', 'page_footer', 'footnote'}


def candidate(leaf):
    """Short text blocks: a heading is a line or two, never a table or figure. Page headers and footers are read too:
    the layout called "MỤC 2" at the foot of a page a footer, and the classifier puts real page numbers far below
    every threshold (chapter at most .45 against .9 across the library)."""
    return (leaf.get('layout_type') not in {'table', 'figure'}
            and 0 < len(leaf.get('text', '').strip()) <= MAX_CHARS and leaf['text'].count('\n') <= 2)


def infer_roles(units, predictor=None, task='role'):
    """Runtime side: the best role and its confidence for each unit's text; task='line' asks heading or sentence."""
    from .gliner_identity_classifier import run_with_classifier
    if not isinstance(units, list) or any(not isinstance(u, dict) or not isinstance(u.get('id'), str)
                                          or not isinstance(u.get('text'), str) for u in units):
        raise ValueError('Invalid heading units')
    if task not in ('role', 'line'):
        raise ValueError('Invalid heading task')
    name = 'block_role' if task == 'role' else 'line_kind'
    spec = {name: dict(labels=LABELS if task == 'role' else LINE_LABELS, multi_label=False, class_act='softmax',
                       cls_threshold=0., top_k=1)}

    def read(model):
        rows = []
        for unit in units:
            out = model.classify_text(unit['text'], spec, include_confidence=True, max_len=256)[name]
            best = out[0] if isinstance(out, list) else out
            rows.append(dict(id=unit['id'], role=best['label'], confidence=float(best['confidence'])))
        return rows
    return dict(schema=SCHEMA, units=run_with_classifier(read, predictor) if units else [])


def request_roles(units, task='role'):
    from django.conf import settings
    from .contract_pipeline_service import runtime_post
    rows = []
    for offset in range(0, len(units), 256):
        # Waits while the GPU serves another request, as every other runtime call does.
        response = runtime_post(settings.RAG_INFERENCE_URL.rstrip('/')+'/rag/heading_roles',
                                dict(units=units[offset:offset+256], task=task), timeout=(5, 600))
        response.raise_for_status()
        result = response.json()
        if result.get('schema') != SCHEMA or len(result.get('units', [])) != len(units[offset:offset+256]):
            raise ValueError('Heading role runtime is outdated or invalid')
        rows.extend(result['units'])
    return rows


def is_heading_line(row):
    if not row:
        return False
    return row['confidence'] >= LINE_HEADING if row['role'] == 'heading' else 1-row['confidence'] >= LINE_HEADING


def accepted(row):
    return row['role'] in THRESHOLDS and row['confidence'] >= THRESHOLDS[row['role']]


def find_headings(tree, requester=None):
    """{leaf id: (kind, title)} for parts, chapters and sections (this model) and articles (the clause split).
    A heading split over two blocks ("CHƯƠNG I" / "NHỮNG QUY ĐỊNH CHUNG") is read again as one text, and the
    second block joins the heading when the model still calls the pair a heading of that kind."""
    from .document_structure_service import reading_order
    requester = requester or request_roles
    leaves = reading_order(tree)
    clauses = tree.get('contract_clauses') or {}
    articles = {}
    if clauses.get('status') == 'complete':
        by_id = {leaf['chunk_id']: leaf for leaf in leaves}
        for clause in clauses['clauses']:
            first = next((i for i in clause['source_ids'] if i in by_id), None)
            if first and ' '.join(by_id[first]['text'].split()).startswith(' '.join(clause['title'].split())[:40]):
                articles[first] = ('article', ' '.join(clause['title'].split()))
    units = [dict(id=leaf['chunk_id'], text=leaf['text']) for leaf in leaves
             if candidate(leaf) and leaf['chunk_id'] not in articles]
    roles = {row['id']: row for row in requester(units)} if units else {}
    headings = dict(articles)
    # Page numbers, running heads and footers sit between a heading at the foot of a page and its name at the top
    # of the next; the pairing looks past them.
    texts = {leaf['chunk_id']: leaf['text'] for leaf in leaves}
    found = {i: r for i, r in roles.items() if accepted(r)}
    # Heading roles below their threshold ("Tiểu mục 5" read as a chapter at .53) are kept as weak: the tree takes
    # one only when it carries the same numbering word as a section open around it.
    weak = {i: r for i, r in roles.items() if r['role'] in KINDS and not accepted(r) and r['confidence'] >= WEAK_HEADING}
    if found or weak:
        lines = {row['id']: row for row in requester([dict(id=i, text=texts[i]) for i in [*found, *weak]], task='line')}
        found = {i: r for i, r in found.items() if is_heading_line(lines.get(i))}
        weak = {i: r for i, r in weak.items() if is_heading_line(lines.get(i))}
    # A heading the layout called page furniture stays in the sequence so its name on the next page can join it.
    order = [leaf['chunk_id'] for leaf in leaves if leaf.get('layout_type') not in FURNITURE or leaf['chunk_id'] in found]
    position = {chunk: i for i, chunk in enumerate(order)}
    pairs = []
    for chunk, row in found.items():
        if chunk not in position:
            continue
        nxt = order[position[chunk]+1] if position[chunk]+1 < len(order) else None
        if nxt and nxt in roles and nxt not in found and nxt not in articles:
            pairs.append(dict(id=chunk+'|'+nxt, text=texts[chunk]+'\n'+texts[nxt]))
    joined = {row['id']: row for row in requester(pairs)} if pairs else {}
    for chunk, row in found.items():
        kind = KINDS[row['role']]
        title = ' '.join(texts[chunk].split())
        for pair_id, pair in joined.items():
            first, second = pair_id.split('|')
            if first == chunk and pair['role'] == row['role'] and accepted(pair):
                title += ' ' + ' '.join(texts[second].split())
                headings[second] = ('continuation', chunk)
        headings[chunk] = (kind, title)
    for chunk in weak:
        if chunk not in headings:
            headings[chunk] = ('weak', ' '.join(texts[chunk].split()))
    return headings
