"""Link a contract passage to the passage it mentions.

GLiNER2 reads each passage for phrases mentioning another provision and for law names.
A numbered phrase goes to the clause with that number; a described one, such as
"điều khoản giao hàng", goes to the clause whose title the BGE reranker scores above
zero. Sharing an entity such as "Bên A" or "thanh toán" does not make a reference.
Links are model proposals, published unreviewed with both passages as evidence.
"""
import re

SCHEMA = 'gliner2-passage-mentions-v2'
ORIGIN = 'gliner2_described_relation'
MENTION_LABEL = 'reference to another clause of this contract'
# A law cites "khoản 3 Điều 30": on two laws the contract label alone found 69 of 89 written citations,
# with this second label 83.
LAW_MENTION_LABEL = 'cross-reference to an Điều (article), khoản (clause) or điểm (point)'
LAW_LABEL = 'name of a law, code or legal regulation'
# Measured on two laws and three contracts: .3 found 31 of 36 written citations against 27 at .5,
# with no wrong link; the extra low-confidence spans fail the number and clause checks below.
MENTION_CONFIDENCE = .3
LAW_CONFIDENCE = .5
MIN_RERANK_LOGIT = 0.
# "Điều 3 Luật Thương mại": a law name attached to the number makes it an outside reference.
LAW_GAP_CHARS = 3
CLAUSE_WORDS = {'điều', 'section', 'sections', 'sec', 'article', 'articles', 'art', 'clause', 'clauses', 'paragraph', 'paragraphs', 'para',
                'artikel', 'abschnitt', 'artículo', 'cláusula', 'статья', 'пункт', 'раздел', '第条', '제조'}
# A described mention must name a provision: "điều khoản giao hàng", not "Bên A" or "hợp đồng".
PROVISION_WORDS = CLAUSE_WORDS | {'khoản', 'mục', 'phần', 'provision', 'provisions', 'part'}
# "Section 5.15 of the China JV Operating Agreement" cites another document.
OTHER_DOCUMENT = re.compile(r'\s*(?:of the|của)\s+(?!(?:agreement|hợp đồng)\b(?!\s+số))', re.IGNORECASE)
# "Điều 3 của Luật này", "khoản 2 Điều 5 Nghị định này", "Article 4 of this Law" name the document they stand in.
THIS_DOCUMENT = re.compile(r'\s*,?\s*(?:(?:của|tại|theo)\s+)?(?:[^\W\d_]+\s+){1,2}này\b|\s*,?\s*of this\b', re.IGNORECASE)


def _spans(model, text, label, threshold):
    found = model.extract_entities(text, [label], threshold=threshold, include_spans=True, include_confidence=True)
    return [dict(text=span['text'], start=span['start'], end=span['end'], confidence=float(span['confidence']))
            for span in found.get('entities', {}).get(label, [])]


def outermost(spans):
    """One span per place: the longest wins, so "Điều 30" inside "khoản 3 Điều 30" adds no second link."""
    kept = []
    for span in sorted(spans, key=lambda s: (s['start'], -(s['end']-s['start']), -s['confidence'])):
        if any(k['start'] <= span['start'] and span['end'] <= k['end'] for k in kept):
            continue
        kept.append(span)
    return kept


def infer_mentions(units, predictor=None):
    """Runtime side: mention and law spans for each passage."""
    from .gliner_identity_classifier import run_with_classifier
    if not isinstance(units, list) or any(not isinstance(u, dict) or not isinstance(u.get('id'), str) or not isinstance(u.get('text'), str) for u in units):
        raise ValueError('Invalid passage units')

    def read(model):
        return [dict(id=unit['id'], mentions=outermost(_spans(model, unit['text'], MENTION_LABEL, MENTION_CONFIDENCE)
                                                       + _spans(model, unit['text'], LAW_MENTION_LABEL, MENTION_CONFIDENCE)),
                     laws=_spans(model, unit['text'], LAW_LABEL, LAW_CONFIDENCE)) for unit in units]
    return dict(schema=SCHEMA, units=run_with_classifier(read, predictor) if units else [])


def request_mentions(units):
    import requests
    from django.conf import settings
    response = requests.post(settings.RAG_INFERENCE_URL.rstrip('/')+'/rag/passage_mentions', json=dict(units=units), timeout=(5, 600))
    response.raise_for_status()
    result = response.json()
    if result.get('schema') != SCHEMA:
        raise ValueError('Passage mention runtime is outdated or invalid')
    return result['units']


def request_rerank(pairs):
    import requests
    from django.conf import settings
    scores = []
    for offset in range(0, len(pairs), 120):
        response = requests.post(settings.RAG_INFERENCE_URL.rstrip('/')+'/rag/rerank', json=dict(pairs=pairs[offset:offset+120]), timeout=(5, 120))
        response.raise_for_status()
        scores.extend(response.json()['scores'])
    return scores


def _plain(text):
    return ' '.join(text.split())


SELF_WORDS = {'này', 'this'}


def _article_part(mention):
    """"khoản 2 Điều 68" cites article 68, not 2: the number that counts follows a clause word.
    Returns SELF for "khoản 2 Điều này", and None when no clause word is followed by a number,
    as in "4.1" or "điều khoản giao hàng"."""
    from .contract_clause_service import _number_value
    words = mention.split()
    for index, word in enumerate(words[:-1]):
        if word.strip('.,;:()[]"“”').casefold() in CLAUSE_WORDS:
            if words[index+1].strip('.,;:()[]"“”').casefold() in SELF_WORDS:
                return SELF
            part = ' '.join(words[index:index+2])
            if _number_value(part) is not None:
                return part
    return None


LIST_JOINERS = {'và', 'and', 'hoặc', 'or', ','}
PARAGRAPH_WORDS = {'khoản', 'paragraph', 'paragraphs', 'para'}


def _numbers_after(words, index):
    """The numbers a clause word governs: "Điều 26, 27 và 28" governs three."""
    found = []
    for word in words[index+1:]:
        bare = word.strip('.,;:()[]"“”')
        if not bare or bare.casefold() in LIST_JOINERS:
            continue
        if not bare.isdigit():
            break  # "Điều 43 của Luật này": the list ends at the first word that is not a number
        found.append(int(bare))
    return found


def cited_numbers(mention):
    """Articles a mention cites and the paragraphs it names inside the first of them.
    "khoản 2 Điều 68" -> ([68], [2]); "các Điều 26, 27 và 28" -> ([26, 27, 28], []); "Điều này" -> SELF."""
    if _article_part(mention) is SELF:
        return SELF
    words = mention.split()
    articles, paragraphs = [], []
    for index, word in enumerate(words):
        key = word.strip('.,;:()[]"“”').casefold()
        if key in CLAUSE_WORDS and key not in PARAGRAPH_WORDS and not articles:
            articles = _numbers_after(words, index)
        elif key in PARAGRAPH_WORDS and not paragraphs:
            paragraphs = _numbers_after(words, index)
    return articles, paragraphs


def paragraph_leaf(leaf_ids, leaves, number):
    """The passage of an article that opens with the cited paragraph number, as "2." for "khoản 2"."""
    for leaf_id in leaf_ids:
        opening = re.match(r'\s*(\d+)\s*[.)]', leaves[leaf_id]['text'])
        if opening and int(opening.group(1)) == number:
            return leaf_id
    return None


SELF = object()


def _cites_clause(mention, title, passage):
    """A passage's opening number and a bare "4.1" number that text rather than cite another clause.
    A title may be a bare "5. Term" or "ARTICLE V" while the text cites "Section 5"."""
    from .contract_clause_service import numbering_word
    word = numbering_word(mention)
    if not word or passage.lstrip().startswith(mention):
        return False
    return word == numbering_word(title) or word in CLAUSE_WORDS


def _is_outside(mention, laws):
    """The law label also fires on the mention itself ("Điều 5"), so an identical span proves
    nothing unless it starts with the number, as in "3 Luật Thương mại 2005"."""
    for law in laws:
        if (law['start'], law['end']) == (mention['start'], mention['end']):
            if mention['text'].strip()[:1].isdigit() and any(c.isalpha() for c in mention['text']):
                return True
        elif law['end'] > mention['end'] and law['start'] < mention['end']+LAW_GAP_CHARS and mention['start'] < law['end']:
            return True
    return False


CITED_NUMBERS = re.compile(r'\s*(?:(?:các|the)\s+)?(?:(?:điểm|point|points|khoản|paragraph|paragraphs|para|điều|article|articles|'
                           r'art|clause|clauses|section|sections|sec|mục|chương)\s+[\w.]+(?:\s*(?:,|và|and|hoặc|or)\s*[\w.]+)*\s*)+',
                           re.IGNORECASE)


def numbers_end(mention):
    """Where the cited numbers of a span end: "Khoản 1 Điều 16" in "Khoản 1 Điều 16 của Luật Hộ tịch"."""
    match = CITED_NUMBERS.match(mention)
    return len(mention.rstrip()) if not match or not match.group().strip() else len(match.group().rstrip())


def _law_inside(mention, after, text):
    """The law a span names after its numbers, without the joining word: "Luật Hộ tịch"."""
    rest = text[after:mention['end']]
    name = re.sub(r'^\s*(?:của|tại|theo|of the|of)\s+', '', rest, flags=re.IGNORECASE).strip(' ,;.')
    if not name or not any(c.isalpha() for c in name):
        return None
    start = mention['end']-len(rest)+rest.find(name)
    return dict(text=name, start=start, end=start+len(name))


def _law_after(mention, laws):
    """The law a cited number belongs to: "Điều 3 Luật Thương mại", "Điều 17 của Luật Hộ tịch"."""
    following = [law for law in laws if law['end'] > mention['end'] and mention['start'] <= law['start'] <= mention['end']+OUTSIDE_LAW_GAP]
    return min(following, key=lambda law: law['start'], default=None)


# "Điều 17 và Điều 18 của Luật Hộ tịch": the law may follow the number by a few words.
OUTSIDE_LAW_GAP = 12


def _names_this_document(law, text):
    """"Luật này", "Bộ luật này", "this Law" name the document the passage stands in."""
    return law['text'].split()[-1:] in (['này'], ['this']) or bool(re.match(r'\s*này\b', text[law['end']:]))


def _names_provision(mention):
    return any(word.strip('.,;:()[]"“”').casefold() in PROVISION_WORDS for word in mention.split())


def link_references(tree, requester=None, reranker=None):
    """Return validated passage links and what happened to the mentions that were not linked."""
    from .contract_clause_service import _number_value
    contract = tree.get('contract_clauses') or {}
    if contract.get('status') != 'complete':
        return [], dict(status='not_applicable', accepted_reference_relations=0)
    leaves = {leaf['chunk_id']: leaf for leaf in tree.get('leaves', [])}
    clauses = contract['clauses']
    titles = {_plain(clause['title']).rstrip('.') for clause in clauses}
    owners, body = {}, []
    for index, clause in enumerate(clauses):
        rows = []
        for leaf_id in clause['source_ids']:
            if leaf_id in leaves:
                owners.setdefault(leaf_id, set()).add(index)
                if _plain(leaves[leaf_id]['text']).rstrip('.') not in titles:
                    rows.append(leaf_id)
        body.append(rows)
    numbered = {_number_value(clause['title']): index for index, clause in enumerate(clauses)}
    numbered.pop(None, None)
    units = [dict(id=leaf_id, text=leaves[leaf_id]['text']) for leaf_id in dict.fromkeys(i for rows in body for i in rows)]
    links, outside = {}, []

    def add(source, mention, target, kind, score=None, title=None):
        key = (source, target)
        if key not in links:
            links[key] = dict(from_id=source, to_id=target, kind='references', reference_type=kind, from_quote=leaves[source]['text'],
                              to_quote=leaves[target]['text'], from_char_start=mention['start'], from_char_end=mention['end'],
                              mention=mention['text'], matched_title=title, relation_confidence=None, rerank_logit=score,
                              endpoint_confidences=dict(head=mention['confidence']), score_semantics='mention_span_only',
                              origin=ORIGIN, review_status='unreviewed')

    citations = []

    def cite(source, mention, law, articles, paragraphs):
        # Kept for linking to other documents: a citation names its target by law and number, never by a
        # passage of that document, so it survives when either document is extracted again.
        citations.append(dict(source_id=source, start=mention['start'], end=mention['end'], mention=mention['text'],
                              confidence=mention['confidence'], law=law['text'] if law else None,
                              law_start=law['start'] if law else None, law_end=law['end'] if law else None,
                              articles=list(articles), paragraphs=list(paragraphs) if len(articles) <= 1 else []))

    described = []
    for row in (requester or request_mentions)(units):
        source = row['id']
        text = leaves[source]['text']
        spans = [(m['start'], m['end']) for m in row['mentions']]
        attached = [_law_after(m, row['laws']) for m in row['mentions']]
        for law in row['laws']:
            # A law named without an article ("theo quy định của Bộ luật Dân sự") cites the whole document.
            if (law in attached or any(a < law['end'] and law['start'] < b for a, b in spans)
                    or _names_this_document(law, text)):
                continue
            if any(c.isalpha() for c in law['text']) and not _article_part(law['text']):
                cite(source, dict(law, text=law['text']), law, [], [])
        for mention in row['mentions']:
            numbers = cited_numbers(mention['text'])
            if numbers is SELF:
                continue  # "khoản 2 Điều này" points inside its own article
            articles, paragraphs = numbers
            part = _article_part(mention['text'])
            cited = part or mention['text']
            first = _number_value(cited)
            values = articles or ([first] if first is not None else [])
            # The span may run on past its numbers: "Khoản 1 Điều 16 của Luật Hộ tịch". What follows the numbers,
            # inside the span or after it, tells this document ("của Luật này") from another one.
            after = mention['start']+numbers_end(mention['text'])
            here = THIS_DOCUMENT.match(text, after)
            if not here and (_is_outside(mention, row['laws']) or OTHER_DOCUMENT.match(text, after)):
                outside.append(mention['text'])
                cite(source, mention, _law_after(mention, row['laws']) or _law_inside(mention, after, text), values, paragraphs)
                continue
            if not values:
                if _names_provision(mention['text']):
                    described.append((source, mention))
                continue
            for value in values:
                if value not in numbered:
                    outside.append(mention['text'])
                    continue
                index = numbered[value]
                if index in owners[source] or not _cites_clause(cited, clauses[index]['title'], leaves[source]['text']):
                    continue
                clause = clauses[index]
                article = next(iter(body[index]), None) or next((i for i in clause['source_ids'] if i in leaves), None)
                # "khoản 2 Điều 68" lands on paragraph 2 of article 68; with several articles the paragraphs are unclear.
                named = [paragraph_leaf([i for i in clause['source_ids'] if i in leaves], leaves, p)
                         for p in (paragraphs if len(values) == 1 else [])]
                for target in [t for t in named if t] or [article]:
                    if target:
                        add(source, mention, target, 'references_clause_number')
    pairs, bindings = [], []
    # Described mentions ("điều khoản giao hàng") linked almost nothing real: on the Civil Code and the Commercial
    # Law the 31 links came from "điều kiện", "điều lệ", "điều ước quốc tế" and "một phần". Off unless enabled.
    from django.conf import settings
    if not getattr(settings, 'A3_DESCRIBED_REFERENCES_ENABLED', False):
        described = []
    for source, mention in described:
        for index, clause in enumerate(clauses):
            if index not in owners[source] and body[index] and _number_value(clause['title']) is not None:
                pairs.append([mention['text'], clause['title']])
                bindings.append((source, mention, body[index][0], clause['title']))
    best = {}
    for score, (source, mention, candidate, name) in zip((reranker or request_rerank)(pairs) if pairs else [], bindings):
        key = (source, mention['start'])
        if score >= MIN_RERANK_LOGIT and (key not in best or best[key][0] < score):
            best[key] = (score, source, mention, candidate, name)
    for score, source, mention, candidate, name in best.values():
        add(source, mention, candidate, 'references_described_passage', float(score), name)
    return list(links.values()), dict(status='complete', schema=SCHEMA, provider='gliner2+bge-reranker', accepted_reference_relations=len(links),
                                      passages=len(units), outside_mentions=list(dict.fromkeys(outside)), outside_citations=citations)


def attach_document_references(tree, requester=None, reranker=None):
    """Replace earlier references; a failure here must not undo extraction or change entity status."""
    from django.conf import settings
    knowledge = tree.get('knowledge_graph') or {}
    kept = [row for row in knowledge.get('source_relations', []) if row.get('origin') != ORIGIN]
    if requester is None and not getattr(settings, 'A3_DOCUMENT_REFERENCES_ENABLED', True):
        document = dict(status='disabled', accepted_reference_relations=0)
    else:
        try:
            links, document = link_references(tree, requester, reranker)
            kept += links
        except Exception as error:
            document = dict(status='unavailable', error_type=type(error).__name__, accepted_reference_relations=0)
    tree['knowledge_graph'] = dict(knowledge, source_relations=kept, document_relations=document)
    return document
