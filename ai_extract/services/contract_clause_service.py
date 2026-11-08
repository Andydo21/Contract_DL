"""Find contract clauses and parties with the models, without text patterns.

A clause runs from one model-detected clause number to the next one. GLiNER
reads clause numbers and party names in any language. A party's Bên A/B role
comes from the role word the document writes beside its name; GLiNER2 links
them only when that reading is ambiguous. A document without role words, such as
Seller and Buyer, keeps its parties unresolved instead of inventing A and B.
"""
import collections
import contextlib
import re

SCHEMA = 'contract-clauses-v5'
CLAUSE_LABEL = 'clause number'
PARTY_LABEL = 'contracting party'
# Offered so GLiNER does not report the words "Bên A" themselves as a party.
REFERENCE_LABEL = 'party role reference such as Bên A or Party B'
ROLE_OPTIONS = {'Party A (Bên A)': 'A', 'Party B (Bên B)': 'B', 'neither party': None}
PARTY_ENTITY_TYPES = {'A': 'PARTY_A', 'B': 'PARTY_B', None: 'PARTY'}
# Measured on 7 laws with 767 articles: .6 merged 7 articles into the one before, .4 none, with no extra or mid-line cut.
CLAUSE_CONFIDENCE = .4
# A clause number may follow the previous one after one heading the model missed.
MAX_NUMBER_STEP = 2
SUB_NUMBER = re.compile(r'\d\.\d')
CLAUSE_BATCH_SIZE = 8
PARTY_CONFIDENCE = .7
ROLE_CONTEXT_BEFORE = 60
ROLE_CONTEXT_AFTER = 40
MIN_CLAUSES = 2
ROLE_MARKER = re.compile(r'\b(?i:bên|ben|party|partie|parte|partei|сторона)\s+([ABАБ])\b'
                         r'|(甲|乙)方?(?![\u4e00-\u9fff])|(?<![가-힣])(갑|을)(?![가-힣])')
ROLE_BY_WORD = {'A': 'A', 'А': 'A', '甲': 'A', '갑': 'A', 'B': 'B', 'Б': 'B', '乙': 'B', '을': 'B'}
OPENING_CHARS = 1500
PARTY_SEARCH_CHARS = 6000
ROMAN_NUMBER = re.compile(r'\b(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})\b')
ROMAN_VALUES = dict(i=1, v=5, x=10, l=50, c=100)
HAN_NUMBER = re.compile('[一二三四五六七八九十百]+')
HAN_DIGITS = {digit: value for value, digit in enumerate('一二三四五六七八九', 1)}
EXCLUDED_LAYOUTS = {'page_header', 'page_footer'}
PREAMBLE_TITLE = 'Thông tin các bên'


def _read_spans(network, texts, labels, threshold):
    return network.inference(texts=texts, labels=labels, relations=[], threshold=threshold, adjacency_threshold=.6,
                             relation_threshold=.8, return_relations=False, flat_ner=True, multi_label=False, batch_size=2)


def find_clause_numbers(text, units, network):
    """Read one source block at a time; across a whole document the model takes tax codes for numbers."""
    from .gliner_entity_service import text_windows
    pending = [(a+offset, window) for a, b in units for offset, window in text_windows(text[a:b])]
    found = {}
    for index in range(0, len(pending), CLAUSE_BATCH_SIZE):
        batch = pending[index:index+CLAUSE_BATCH_SIZE]
        output = _read_spans(network, [window for _, window in batch], [CLAUSE_LABEL], CLAUSE_CONFIDENCE)
        for (base, _), spans in zip(batch, output):
            for span in spans:
                start = base+span['start']
                if start not in found or found[start]['confidence'] < span['score']:
                    found[start] = dict(label=CLAUSE_LABEL, text=span['text'], start=start, end=base+span['end'],
                                        confidence=float(span['score']))
    return sorted(found.values(), key=lambda item: item['start'])


def find_parties(text, network):
    """GLiNER names the contracting parties; each name is kept once at its best score."""
    best = {}
    for span in _read_spans(network, [text], [PARTY_LABEL, REFERENCE_LABEL], PARTY_CONFIDENCE)[0]:
        if span['label'] != PARTY_LABEL:
            continue
        key = ' '.join(span['text'].casefold().split())
        if key not in best or best[key]['confidence'] < span['score']:
            best[key] = dict(name=span['text'].strip(), start=span['start'], end=span['end'], confidence=float(span['score']))
    return sorted(best.values(), key=lambda party: party['start'])


def _marker_for(party, markers, peers):
    """Within one scope a document writes either 'Bên A: X' or 'X (Bên A)', not both."""
    if markers[0][0] > peers[0]['start']:
        return next((role for start, _, role in markers if start >= party['end']), None)
    return next((role for _, end, role in reversed(markers) if end <= party['start']), None)


def read_role_markers(text, parties):
    """Give each party the role word on its own line, else the nearest one in reading order."""
    markers = [(match.start(), match.end(), ROLE_BY_WORD[match.group(match.lastindex)]) for match in ROLE_MARKER.finditer(text)]
    markers = [m for m in markers if not any(p['start'] <= m[0] < p['end'] for p in parties)]
    on_own_line = {}
    for index, party in enumerate(parties):
        first = text.rfind('\n', 0, party['start'])+1
        last = text.find('\n', party['end'])
        last = len(text) if last < 0 else last
        nearby = [m for m in markers if first <= m[0] < last]
        peers = [p for p in parties if first <= p['start'] < last]
        party['role'] = _marker_for(party, nearby or markers, peers if nearby else parties) if markers else None
        on_own_line[index] = bool(nearby)
    # A representative named under 'Bên A: X' must not take the role from X itself.
    for role in 'AB':
        direct = [i for i, p in enumerate(parties) if p['role'] == role and on_own_line[i]]
        if len(direct) == 1:
            for index, party in enumerate(parties):
                if party['role'] == role and index != direct[0]:
                    party['role'] = None
    return {role for _, _, role in markers}


def party_index(name, parties):
    """The party a name stands for: its own name, or its role word such as 'Bên A'."""
    from .gliner_identity_classifier import identity_name_key
    wanted = identity_name_key(name)
    same = [i for i, party in enumerate(parties) if identity_name_key(party['name']) == wanted]
    if same:
        return same[0]
    marker = ROLE_MARKER.fullmatch(name.strip())
    if marker:
        holders = [i for i, party in enumerate(parties) if party.get('role') == ROLE_BY_WORD[marker.group(marker.lastindex)]]
        if len(holders) == 1:
            return holders[0]
    return None


def link_roles(text, parties, predictor=None):
    """Read written role words first; GLiNER2 links them only when that reading is ambiguous."""
    from .gliner_identity_classifier import run_with_classifier
    written = read_role_markers(text, parties)
    if collections.Counter(p['role'] for p in parties if p['role']) == {'A': 1, 'B': 1}:
        return parties
    if written != {'A', 'B'}:
        for party in parties:
            party['role'] = None
        return parties
    return run_with_classifier(lambda model: assign_roles(text, parties, model), predictor)


def assign_roles(text, parties, predictor):
    """GLiNER2 links each party to Bên A or B; anything but one A and one B stays unresolved."""
    for party in parties:
        context = text[max(0, party['start']-ROLE_CONTEXT_BEFORE):party['end']+ROLE_CONTEXT_AFTER]
        party['role'] = ROLE_OPTIONS.get(predictor.classify_text(context, {'role': list(ROLE_OPTIONS)}).get('role'))
    counts = collections.Counter(party['role'] for party in parties if party['role'])
    if counts != {'A': 1, 'B': 1}:
        for party in parties:
            party['role'] = None
    return parties


def infer_contract_clauses(text, units=None, predictor=None, network=None):
    """Runtime side: return raw clause-number and party spans for one document.

    Parties are read from the opening passage together, because one block alone
    lacks the two-party context. GLiNER leaves the GPU before GLiNER2 loads.
    """
    if not isinstance(text, str):
        raise ValueError('Invalid contract text')
    units = units or [[0, len(text)]]
    if any(not isinstance(u, list) or len(u) != 2 or not 0 <= u[0] <= u[1] <= len(text) for u in units):
        raise ValueError('Invalid contract source units')
    from . import gliner_entity_service as entity_service
    from .gliner_identity_classifier import MODEL_ID, REVISION
    owned = network is None
    if owned:
        import torch
        precision = torch.autocast('cuda', dtype=torch.float16)
        network = entity_service.runtime()
    else:
        precision = contextlib.nullcontext()
    try:
        with precision:
            starts = find_clause_numbers(text, units, network)
            first = clause_starts(starts, text)
            # Parties are introduced before the first clause; a heading-first
            # contract still gets one passage of opening text to search.
            opening = text[:first[0]['start']] if first and first[0]['start'] > 0 else text[:OPENING_CHARS]
            opening = opening[:PARTY_SEARCH_CHARS]
            parties = find_parties(opening, network)
    finally:
        if owned:
            del network
            entity_service.unload()
    parties = link_roles(opening, parties, predictor) if parties else parties
    return dict(schema=SCHEMA, model=entity_service.MODEL_ID, role_model=MODEL_ID, role_revision=REVISION,
                starts=starts, parties=parties)


def request_contract_clauses(text, units=None):
    import requests
    from django.conf import settings
    response = requests.post(settings.RAG_INFERENCE_URL.rstrip('/')+'/rag/contract_clauses',
                             json=dict(text=text, units=units), timeout=(5, 600))
    response.raise_for_status()
    result = response.json()
    if result.get('schema') != SCHEMA:
        raise ValueError('Contract clause runtime is outdated or invalid')
    return result


def _number_value(text):
    """The value of Arabic, Roman or Han clause numbers; contracts number clauses in all three."""
    digits = re.search(r'\d+', text)
    if digits:
        return int(digits.group())
    roman = next((match.group() for match in ROMAN_NUMBER.finditer(text.casefold()) if match.group()), None)
    if roman:
        values = [ROMAN_VALUES[letter] for letter in roman]
        return sum(-value if value < following else value for value, following in zip(values, values[1:]+[0]))
    han = HAN_NUMBER.search(text)
    if han:
        total = current = 0
        for character in han.group():
            if character in HAN_DIGITS:
                current = HAN_DIGITS[character]
            else:
                total += max(current, 1)*(10 if character == '十' else 100)
                current = 0
        return total+current
    return None


def numbering_word(text):
    """"Điều 5" and "tháng 5" carry the same number; the word in front tells a clause from a date."""
    words = text.split()
    return re.sub(r'[\d\W_]', '', words[0]).casefold() if words else ''


def _opens_line(text, span):
    start = _heading_start(text, span)
    return not text[text.rfind('\n', 0, start)+1:start].strip()


def clause_starts(spans, text):
    """Keep the best sequence of nearly consecutive numbers; a tax code or amount is too far away.
    "theo Điều 5" inside Điều 4 has the same number as the heading of Điều 5, so a number counts
    for more when it opens a line, is not a sub-number such as 5.1, and repeats the previous word.
    A line opened by a numbering word ("Điều 2", "Article 2", "第二条") outweighs a bare "2." there: an
    amending law quotes the numbered items of the law it changes, and nine quoted "2. … 9." items
    outscored its own six articles."""
    numbered = [(value, span) for span in spans for value in [_number_value(span['text'])] if value is not None]
    if not numbered:
        return list(spans)
    words = [numbering_word(text[_heading_start(text, span):span['start']+len(span['text'])]) for _, span in numbered]
    opens = [_opens_line(text, span) for _, span in numbered]
    weight = [1+opens[i]+(not SUB_NUMBER.search(span['text']))+3*(opens[i] and bool(words[i])) for i, (_, span) in enumerate(numbered)]
    best = [(weight[index], [index]) for index in range(len(numbered))]
    for index, (value, _) in enumerate(numbered):
        for previous in range(index):
            if 0 < value-numbered[previous][0] <= MAX_NUMBER_STEP:
                score = best[previous][0]+weight[index]+(words[previous] == words[index])
                if score > best[index][0]:
                    best[index] = (score, best[previous][1]+[index])
    return [numbered[index][1] for index in max(best, key=lambda row: (row[0], len(row[1])))[1]]


def _heading_start(text, span):
    """A span holding only '1' belongs to the word before it, such as 'Điều 1'."""
    start = span['start']
    if not span['text'].strip().isdigit():
        return start
    cursor = start
    while cursor > 0 and text[cursor-1].isspace():
        cursor -= 1
    if cursor == 0 or not text[cursor-1].isalpha():
        return start
    while cursor > 0 and not text[cursor-1].isspace():
        cursor -= 1
    return cursor


def _title(text, span, start, end):
    cursor = span['end']
    while cursor < end and text[cursor] in ' .:：。\t-':
        cursor += 1
    stop = cursor
    while stop < end and text[stop] not in '.\n:：。':
        stop += 1
    return ' '.join(text[start:stop].split())[:255]


def source_text(tree):
    """Join readable sources in document order and remember where each one sits."""
    parts, sources, cursor = [], [], 0
    for leaf in tree.get('leaves', []):
        value = (leaf.get('text') or '').strip()
        if not value or leaf.get('retrieval_excluded') or leaf.get('layout_type') in EXCLUDED_LAYOUTS:
            continue
        parts.append(value)
        sources.append((cursor, cursor+len(value), leaf['chunk_id']))
        cursor += len(value)+1
    return '\n'.join(parts), sources


def _source_ids(sources, start, end):
    return [identity for a, b, identity in sources if a < end and start < b]


def clause_segments(text, sources, starts):
    """Cut text at the chosen clause numbers; any text before the first one is the preamble."""
    clauses = []
    positions = [_heading_start(text, span) for span in starts]
    if text[:positions[0]].strip():
        clauses.append(dict(title=PREAMBLE_TITLE, clause_type='preamble', content=text[:positions[0]].strip(),
                            source_ids=_source_ids(sources, 0, positions[0])))
    for index, span in enumerate(starts):
        start = positions[index]
        end = positions[index+1] if index+1 < len(positions) else len(text)
        clauses.append(dict(title=_title(text, span, start, end), clause_type='clause', number=text[start:span['end']],
                            content=text[start:end].strip(), source_ids=_source_ids(sources, start, end)))
    return clauses


def build_clauses(text, sources, result, is_contract=True):
    """Turn raw spans into clause segments and the best-supported party per role. Whether a document is a contract
    comes from where it is stored (a law has a LegalDocument row), so the parties read do not decide the split:
    a scan whose parties are misread still gets its clauses. A law keeps no parties."""
    starts = clause_starts(result.get('starts', []), text)
    if len(starts) < MIN_CLAUSES:
        return dict(status='no_clauses', clauses=[], parties=[])
    parties = result.get('parties', []) if is_contract else []
    return dict(status='complete', clauses=clause_segments(text, sources, starts), parties=[
        dict(role=party.get('role'), name=party['name'], confidence=party['confidence']) for party in parties])


def extract_from_text(text, sources=(), requester=None, is_contract=True):
    if not text.strip():
        return dict(status='empty', clauses=[], parties=[])
    units = [[a, b] for a, b, _ in sources] or None
    return build_clauses(text, sources, (requester or request_contract_clauses)(text, units), is_contract)


def attach_clause_headings(tree, clauses):
    """Each passage is headed by the clause the clause step placed it in, so a body such as
    "Ủy ban nhân dân cấp xã nơi cư trú…" is searched and cited as part of "Điều 13. Thẩm quyền…".
    Layout headings mark only some clause titles, and such a title would otherwise head every
    later passage up to the next marked one."""
    plain = lambda text: ' '.join(str(text).split())
    titles = {plain(c['title']) for c in clauses if c.get('title')}
    owner = {source: plain(c['title']) for c in clauses if c.get('title') for source in c['source_ids']}
    for leaf in tree.get('leaves', []):
        path = [h for h in leaf.get('heading_path', []) if plain(h) not in titles]
        if leaf['chunk_id'] in owner:
            path.append(owner[leaf['chunk_id']])
        leaf['heading_path'] = path


def prepare_contract_clauses(tree, version, requester=None):
    """Store clauses on the tree for Neo4j and in the database. Other entities stay graph-only."""
    from ai_extract.repositories import extraction_repository
    text, sources = source_text(tree)
    # A law has numbered articles but no contracting parties; the LegalDocument row says which one this is.
    result = extract_from_text(text, sources, requester, not extraction_repository.is_legal_document(version))
    result.update(schema=SCHEMA, source_fingerprint=tree.get('source_fingerprint', ''))
    pages = {leaf['chunk_id']: leaf.get('page_number') for leaf in tree.get('leaves', [])}
    for clause in result['clauses']:
        clause['source_pages'] = sorted({pages[i] for i in clause['source_ids'] if pages.get(i)})
    if result['status'] == 'complete':
        # Model inference can outlive a pooled database connection.
        from ai_extract.repositories import layout_repository
        layout_repository.ensure_write_connection()
        extraction_repository.replace_contract_clauses(version, result['clauses'], result['parties'],
                                                       PARTY_ENTITY_TYPES)
    tree['contract_clauses'] = result
    if result['status'] == 'complete':
        attach_clause_headings(tree, result['clauses'])
    # One name is one node, so a later mention links back to the earlier one; GLiNER2's
    # "different" keeps two things with one name apart. Retrieval gates these links by the question.
    from .gliner_identity_classifier import merge_contract_names
    merge_contract_names(tree)
    return result
