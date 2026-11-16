"""Build the risk-skill data: train.jsonl, valid.jsonl (same topics) and eval.jsonl (whole contracts, holdout topics,
changed-law twins).

Run inside the web container (the brief and schema come from the service itself, so training matches inference):
    docker exec riskdl_web python -m ai.training.risk_skill.build --train 2600 --real
A record holds the chat messages, the JSON schema the server enforces, the target answer and what it expects, plus the
clause, its related clauses, the risk catalog and the provisions, so evaluate.py can replay the same brief.

What a brief looks like, as at run time:
  - the risk catalog is there (the administrator's rules, sometimes only some of them, sometimes the same kinds under
    other codes and words, now and then empty); a risk takes the code of the rule that describes it, or OTHER;
  - 1 to 6 provisions: the governing one(s), provisions on the same subject that set no rule the clause breaks, and
    provisions on other subjects;
  - often other clauses of the contract; two of them may disagree (a cross-clause risk);
  - a clause may hold two risks.
"""
import argparse
import json
import os
import random
import re
from pathlib import Path

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai.legal_ai.services import clause_risk_service as risk  # noqa: E402
from ai.training.risk_skill.families import (CLAUSE_VARIANTS, COMBOS, COMPANIES, CONCEPT_OF, CONCEPTS, CROSS, DEFAULT,  # noqa: E402
                                          FILLERS, HOLDOUT,
                                          IN_FORCE, NEUTRAL, NUMERIC, PARTLY_REPEALED, ROLES, RULED, TITLES, TOPIC_TITLES,
                                          UNCLEAR, Maker, number, numeric_explanation, numeric_fix, numeric_level)

OUT = Path(__file__).resolve().parent / 'data'
OTHER = risk.OTHER_RULE
WHY = {'mentions_clause_ids': 'được điều khoản này dẫn chiếu', 'same_block_clause_ids': 'cùng khối trình bày',
       'related_clause_ids': 'nội dung liên quan'}
# How many provisions a brief holds: retrieval gives up to 3 per clause and up to 3 more that those cite.
LAW_COUNTS = ([1, 2, 3, 4, 5, 6], [3, 8, 18, 23, 24, 24])  # v4: more provisions, the governing one at any position
# Topics on one subject: a provision of one is never a distractor for another (it could govern the clause).
SIBLINGS = [{'penalty', 'penalty_free', 'compensation', 'comp_vague'}, {'warranty', 'warranty_default', 'quality_vague'},
            {'pay_term', 'pay_vague', 'price_vague', 'rent_vague', 'later_vague', 'price_change', 'adjust_vague'},
            {'place', 'delivery_vague'}, {'notice', 'rent_notice'}, {'acceptance', 'accept_vague', 'scope_vague'},
            {'complaint', 'complaint_terms'}]
CROSS_EXCLUDES = dict(pay_days={'pay_term'}, delivery_days={'place'}, penalty_twice={'penalty', 'penalty_free', 'compensation'},
                      warranty_twice={'warranty', 'warranty_default'}, notice_twice={'notice'},
                      acceptance_days={'acceptance', 'accept_vague'}, advance_twice={'advance'},
                      rent_price_twice={'rent_vague', 'deposit', 'rent_notice'})


# --------------------------------------------------------------------------- brief parts
def catalog(rng):
    """(rules for the brief, concept -> code). Mostly the real catalog, at times without some rules (their risks are
    then OTHER), at times the same kinds under made-up codes and other words, now and then empty."""
    roll = rng.random()
    if roll < .05:
        return [], {}
    concepts = list(CONCEPTS)
    if rng.random() < .45:
        concepts = rng.sample(concepts, rng.randint(3, len(concepts) - 1))
    rng.shuffle(concepts)
    renamed = roll > .8
    rules, code_of = [], {}
    for index, key in enumerate(concepts, 1):
        c = CONCEPTS[key]
        code, name, description = (f'RR{index:02d}', *c['alt']) if renamed else (c['code'], c['name'], c['description'])
        rules.append(dict(code=code, name=name, severity=c['severity'], description=description))
        code_of[key] = code
    return rules, code_of


def excluded(topics):
    out = set(topics)
    for family in SIBLINGS:
        if out & family:
            out |= family
    return out


def other_law(rng, maker, exclude, holdout):
    """A provision on another subject, as retrieval also returns."""
    pool = [k for k in (*NUMERIC, *RULED, *DEFAULT) if k not in exclude and (holdout or k not in HOLDOUT)]
    key = rng.choice(pool)
    if key in NUMERIC:
        t = NUMERIC[key]
        return maker.law(t['law_title'], maker.article_body(key, maker.law_template(key, t).format(limit=number(rng.choice(t['limits'])))))
    if key in RULED:
        return maker.law(RULED[key]['law_title'], maker.article_body(key, RULED[key]['law']))
    return maker.default(key)[1]


def laws_for(rng, maker, governing, topics, holdout, exclude=()):
    """The governing provisions, then same-subject provisions that govern nothing here, then other subjects."""
    count = max(len(governing), rng.choices(*LAW_COUNTS)[0])
    laws = list(governing)
    hard = [law for topic in topics for law in maker.hard(topic)]
    rng.shuffle(hard)
    for law in hard:
        if len(laws) < count and rng.random() < .7:
            laws.append(law)
    skip = excluded(topics) | set(exclude)
    while len(laws) < count:
        laws.append(other_law(rng, maker, skip, holdout))
    rng.shuffle(laws)
    # v4: a shuffle leaves the governing provision mostly at L1-L3 (few briefs hold six); in half of the one-governing
    # briefs it moves to a later position, so the model learns to read the number in front of the words it copies.
    if len(governing) == 1 and len(laws) > 2 and rng.random() < .5:
        law = governing[0]
        laws.remove(law)
        laws.insert(rng.choices(range(len(laws) + 1), weights=range(1, len(laws) + 2))[0], law)
    return laws


def neutral_clauses(rng, taken):
    out = []
    for title, text in rng.sample(NEUTRAL, rng.randint(1, 2)):
        number_ = rng.choice([n for n in range(2, 20) if n not in taken])
        taken.add(number_)
        out.append((dict(id=number_, title=f'Điều {number_}. {title}', content=f'Điều {number_}. {title}\n{text}'), rng.choice(list(WHY))))
    return out


def body(clause):
    """The clause's own sentences, without the filler sentence a clause may end with."""
    text = clause['content'].split('\n', 1)[1]
    for filler in FILLERS:
        if filler:
            text = text.replace(' ' + filler, '')
    return text.strip()


def summary(clause):
    sentences = [s.strip().rstrip('.') for s in re.split(r'(?<=\.)\s+', body(clause)) if s.strip()]
    return 'Điều khoản quy định ' + '; '.join(s[0].lower() + s[1:] for s in sentences) + '.'


def title_for(rng, topic):
    titles = TOPIC_TITLES.get(topic)
    return rng.choice(titles) if titles and rng.random() < .8 else rng.choice(TITLES)


def parties_for(rng, topic=None):
    """The parties line. For a topic with known roles it often says who holds which role ("Bên A (Bên vay): …"), in
    either order, so the disadvantaged party is read from the brief."""
    a, b = rng.sample(COMPANIES, 2)
    if rng.random() < .2:
        return []
    roles = ROLES.get(topic)
    if roles and rng.random() < .7:
        first, second = roles if rng.random() < .5 else roles[::-1]
        return [f'Bên A ({first}): {a}', f'Bên B ({second}): {b}']
    return [f'Bên A: {a}', f'Bên B: {b}']


def party_names(parties):
    """role -> 'Role (Name)' from a parties line that names the roles."""
    out = {}
    for line in parties:
        m = re.match(r'Bên [AB] \((.+?)\): (.+)$', line)
        if m:
            out[m.group(1)] = f'{m.group(1)} ({m.group(2)})'
    return out


# --------------------------------------------------------------------------- one record
def record(rng, maker, clause, items, expect, holdout, title, parties, related=(), exclude=()):
    """items: (provision or None, risk or None, concept) for each risk the clause may hold."""
    governing = []
    for law, _, _ in items:
        if law is not None and all(law is not g for g in governing):
            governing.append(law)
    topics = [t for t in expect.get('topics', [expect['topic']]) if t in NUMERIC or t in RULED or t in DEFAULT or t in UNCLEAR]
    laws = laws_for(rng, maker, governing, topics, holdout, exclude)
    rules, code_of = catalog(rng)
    clause = dict(clause)
    related = list(related)
    if not related and rng.random() < .35:
        related = neutral_clauses(rng, {clause['id']})
    for other, key in related:
        clause[key] = clause.get(key, []) + [other['id']]
    brief = risk.clause_brief(title, parties, clause, [(other, WHY[key]) for other, key in related], laws, rules)
    law_ids = {f'L{i}' for i in range(1, len(laws) + 1)}
    related_ids = {other['id'] for other, _ in related}
    risks, law_codes = [], {}
    named = party_names(parties)
    for law, target, concept in items:
        if not target:
            continue
        target = dict(target, disadvantaged_party=named.get(target['disadvantaged_party'], target['disadvantaged_party']))
        cited = [f'L{next(i for i, l in enumerate(laws, 1) if l is law)}'] if target['kind'] == 'conflict' else []
        code = code_of.get(concept, OTHER) if concept else OTHER
        entry = dict(rule_code=code, category=target['category'], risk_level=target['risk_level'],
                     explanation=target['explanation'], recommendation=target['recommendation'],
                     disadvantaged_party=target['disadvantaged_party'], contract_quote=target['contract_quote'],
                     law_ids=cited, law_quote=target['law_quote'] if cited else '', kind=target['kind'],
                     related_clause_ids=target.get('related', []))
        # The target must pass the same checks the service applies to the model's answer.
        assert risk.grounded(entry, clause, law_ids, related_ids), (entry, clause)
        if cited:
            assert risk.law_quoted(entry['law_quote'], [law]), (entry['law_quote'], law['text'])
            law_codes[cited[0]] = code
        risks.append(entry)
    conflict_ids = [r['law_ids'][0] for r in risks if r['kind'] == 'conflict']
    cross_code = next((r['rule_code'] for r in risks if r['related_clause_ids']), None)
    expect = dict(expect, title=title, law_ids=conflict_ids, law_id=conflict_ids[0] if conflict_ids else None,
                  law_codes=law_codes, cross_code=cross_code, rule_codes=[r['rule_code'] for r in risks])
    return dict(messages=[dict(role='system', content=risk.CLAUSE_RULES), dict(role='user', content=brief)],
                schema=risk.clause_schema(len(laws), related_ids), target=dict(clause_summary=summary(clause), risks=risks),
                expect=expect, clause=clause, related=[other for other, _ in related], rules=rules,
                laws=[{k: v for k, v in l.items() if k not in ('name', 'article')} for l in laws], parties=parties)


# --------------------------------------------------------------------------- samples
def piece(rng, maker, key, holdout, breaks=None):
    """(clause, provision, risk or None, expect) for one topic; breaks: chance the clause breaks its provision."""
    if key in NUMERIC:
        return maker.numeric(key, side=None if breaks is None else 'over' if rng.random() < breaks else rng.choice(['on', 'under']))
    if key in RULED:
        return maker.ruled(key, breaks=None if breaks is None else rng.random() < breaks)
    if key in DEFAULT:
        return maker.default(key)
    return maker.unclear(key)


def single(rng, maker, holdout):
    allowed = lambda keys: [k for k in keys if holdout or k not in HOLDOUT]
    group = rng.choices(['numeric', 'ruled', 'default', 'unclear'], weights=[36, 21, 12, 14])[0]
    keys = {'numeric': NUMERIC, 'ruled': RULED, 'default': DEFAULT, 'unclear': UNCLEAR}[group]
    key = rng.choice(allowed(keys))
    clause, law, target, expect = piece(rng, maker, key, holdout)
    return clause, [(law, target, CONCEPT_OF.get(key))], expect, [], ()


def cross(rng, maker, holdout):
    """Two clauses of the contract on one amount; different values are a cross-clause risk, equal ones are fine."""
    key = rng.choice([k for k in CROSS if holdout or k not in HOLDOUT])
    t = CROSS[key]
    a = rng.choice(t['values'])
    b = a if rng.random() < .3 else rng.choice([v for v in t['values'] if v != a])
    id_a, id_b = rng.sample(range(2, 16), 2)
    sentence_a, sentence_b = t['a'].format(a=number(a)), t['b'].format(b=number(b))
    clause = dict(id=id_a, title=f'Điều {id_a}. {t["title_a"]}', content=f'Điều {id_a}. {t["title_a"]}\n{sentence_a}')
    other = dict(id=id_b, title=f'Điều {id_b}. {t["title_b"]}', content=f'Điều {id_b}. {t["title_b"]}\n{sentence_b}')
    target = None
    if a != b:
        unit = t['unit']
        target = dict(category=f'{t["subject"][0].upper()}{t["subject"][1:]} mâu thuẫn giữa các điều', risk_level='LOW',
                      explanation=(f'{clause["title"]} quy định {t["subject"]} là {number(a)}{unit} nhưng {other["title"]} quy định '
                                   f'{number(b)}{unit}; có thể hiểu {t["subject"]} là {number(a)}{unit} hoặc {number(b)}{unit}.'),
                      recommendation=rng.choice([
                          f'Thống nhất {t["subject"]} giữa {clause["title"]} và {other["title"]}, chỉ giữ một mức.',
                          f'Sửa {other["title"]} cho cùng {t["subject"]} {number(a)}{unit} như {clause["title"]}, hoặc ngược lại.',
                          f'Ghi một {t["subject"]} duy nhất ở {clause["title"]} và để {other["title"]} dẫn chiếu sang.',
                          f'Xác định rõ {t["subject"]} nào được áp dụng và bỏ con số còn lại để tránh hiểu khác nhau.',
                          f'Rà soát {clause["title"]} và {other["title"]}, sửa để hai điều cùng một {t["subject"]}.']),
                      disadvantaged_party=t['party'], contract_quote=sentence_a, law_quote='', kind='unclear', related=[id_b])
    expect = dict(group='cross', topic=key, topics=[], conflict=False, unclear=False, cross=a != b, related_id=id_b)
    return clause, [(None, target, 'cross')], expect, [(other, rng.choice(list(WHY)))], CROSS_EXCLUDES[key]


def double(rng, maker, holdout):
    """One clause with two sentences, each on its own topic: zero, one or two risks."""
    a, b = rng.choice(COMBOS)
    parts = [piece(rng, maker, key, holdout, breaks=.8) for key in (a, b)]
    first, second = parts[0][0], parts[1][0]
    clause = dict(id=first['id'], title=first['title'], content=f'{first["content"].split(chr(10), 1)[0]}\n{body(first)} {body(second)}')
    # The second sentence was made as its own clause: its answer must name the merged clause, not that one.
    fix_title = lambda target: target and {k: v.replace(second['title'], clause['title']) if isinstance(v, str) else v  # noqa: E731
                                           for k, v in target.items()}
    items = [(law, target if index == 0 else fix_title(target), CONCEPT_OF.get(key))
             for index, ((_, law, target, _), key) in enumerate(zip(parts, (a, b)))]
    expect = dict(group='double', topic=f'{a}+{b}', topics=[a, b], conflict=any(p[3]['conflict'] for p in parts),
                  unclear=False, cross=False, parts=[p[3] for p in parts])
    return clause, items, expect, [], ()


def absent(rng, maker, holdout):
    """(a) Retrieval missed the governing provision: only same-subject provisions that set no rule and provisions on
    other subjects are supplied. With no supplied rule broken there is no legal risk to report."""
    key = rng.choice([k for k in (*NUMERIC, *RULED) if holdout or k not in HOLDOUT])
    clause, _, _, piece_expect = piece(rng, maker, key, holdout, breaks=.8)
    expect = dict(group='absent', topic=key, conflict=False, unclear=False, would_conflict=piece_expect['conflict'])
    return clause, [(None, None, CONCEPT_OF.get(key))], expect, [], ()


def amended(rng, maker, holdout):
    """(a) A rule changed by an amending law: the original provision (partly repealed, "amended by" note) and the
    amending provision (in force) with another limit are both supplied. The clause's value lies between the two
    limits, so the answer follows the provision in force, never the old number."""
    key = rng.choice([k for k in NUMERIC if (holdout or k not in HOLDOUT) and k != 'interest'])
    t = NUMERIC[key]
    old = rng.choice(t['limits'])
    step = max(2, round(old * .4))
    new = old - step if old - step >= 1 and rng.random() < .5 else old + step  # two different limits, 2+ apart
    low, high = sorted((old, new))
    value = rng.randint(low + 1, high) if t['kind'] == 'max' else rng.randint(low, high - 1)
    template = maker.law_template(key, t)
    stored, name = maker.document()
    original = maker.law(t['law_title'], maker.article_body(key, template.format(limit=number(old))))
    original['status'] = f'{PARTLY_REPEALED} Đã được sửa đổi hoặc bổ sung bởi: {name}.'
    rule = template.format(limit=number(new))
    amending = maker.law(f'Sửa đổi, bổ sung Điều {original["article"]} của {original["name"]}',
                         f'Khoản 1 Điều {original["article"]} được sửa đổi, bổ sung như sau:\n"{rule}"')
    amending.update(document=stored, name=name, status=IN_FORCE)
    shown = f'{number(value)}{t["unit"]}'
    sentence = maker.sentence(key, t['clause'], CLAUSE_VARIANTS).format(value=shown)
    clause = maker.clause(t['clause_title'], sentence)
    breaks = value > new if t['kind'] == 'max' else value < new
    target = None
    if breaks:
        ref = f'Điều {amending["article"]} {name} (sửa đổi Điều {original["article"]} {original["name"]})'
        target = dict(category=t['category'], risk_level=numeric_level(t, value, new),
                      explanation=numeric_explanation(rng, t, clause['title'], shown, new, ref),
                      recommendation=numeric_fix(rng, t, value, new, clause['title'], ref),
                      disadvantaged_party=t['party'], contract_quote=sentence, law_quote=rule, kind='conflict')
    expect = dict(group='amended', topic=key, conflict=breaks, unclear=False, limit=new, old_limit=old, value=value)
    return clause, [(amending, target, CONCEPT_OF.get(key)), (original, None, None)], expect, [], ()


def sample(rng, maker, holdout):
    kind = rng.choices(['single', 'cross', 'double', 'absent', 'amended'], weights=[68, 9, 17, 7, 8])[0]  # v4: more two-risk
    return {'single': single, 'cross': cross, 'double': double, 'absent': absent, 'amended': amended}[kind](rng, maker, holdout)


def build_split(n, seed, holdout=False, split='train'):
    rng = random.Random(seed)
    maker = Maker(rng, split)
    rows = []
    while len(rows) < n:
        clause, items, expect, related, exclude = sample(rng, maker, holdout)
        title = rng.choice(CROSS[expect['topic']]['contracts']) if expect['group'] == 'cross' else title_for(rng, expect['topic'].split('+')[0])
        parties = parties_for(rng, expect['topic'].split('+')[0])
        rows.append(record(rng, maker, clause, items, expect, holdout, title, parties, related, exclude))
        # A changed-law twin of a numeric clause: the same clause value, the limit moved across it.
        if expect['group'] in ('max', 'min') and rng.random() < .5 and len(rows) < n:
            rows.append(twin(rng, maker, clause, items[0][0], expect, holdout, title, parties))
    return rows


def twin(rng, maker, clause, law, expect, holdout, title, parties):
    """The same clause under a provision whose limit is on the other side of the clause's value."""
    t = NUMERIC[expect['topic']]
    value = expect['value']
    if expect['conflict']:
        limit = value + (0 if rng.random() < .3 else max(1, round(value * .5)))  # now compliant (on or above / below)
        if t['kind'] == 'min':
            limit = max(1, value - (0 if rng.random() < .3 else max(1, round(value * .5))))
    else:
        limit = max(1, value - max(1, round(value * .3))) if t['kind'] == 'max' else value + max(1, round(value * .3))
    rule = expect.get('law_template', t['law']).format(limit=number(limit))
    # Only the rule's own paragraph changes; a long article keeps its other paragraphs.
    text = law['text'].replace(expect['law_rule'], rule) if expect.get('law_rule') in law['text'] \
        else law['text'].split('\n', 1)[0] + '\n' + rule
    law2 = dict(law, text=text, source_id=f'{law["source_id"]}-twin')
    breaks = value > limit if t['kind'] == 'max' else value < limit
    target = None
    if breaks:
        sentence = body(clause)
        ref = f'Điều {law["article"]} {law["name"]}'
        shown = f'{number(value)}{"%/năm" if expect["topic"] == "interest" else t["unit"]}'
        target = dict(category=t['category'], risk_level=numeric_level(t, value, limit),
                      explanation=numeric_explanation(rng, t, clause['title'], shown, limit, ref),
                      recommendation=numeric_fix(rng, t, value, limit, clause['title'], ref),
                      disadvantaged_party=t['party'], contract_quote=sentence, law_quote=rule, kind='conflict')
    expect2 = dict(expect, conflict=breaks, limit=limit, twin_of=law['source_id'], law_rule=rule)
    return record(rng, maker, clause, [(law2, target, CONCEPT_OF.get(expect['topic']))], expect2, holdout, title, parties)


def eval_contracts(count, seed):
    """Whole contracts of 6-8 clauses, holdout topics included, each numeric clause also under a changed law."""
    rng = random.Random(seed)
    maker = Maker(rng, 'eval')
    rows = []
    for number_ in range(1, count + 1):
        title, parties = rng.choice(TITLES), parties_for(rng)
        for position in range(rng.randint(6, 8)):
            clause, items, expect, related, exclude = sample(rng, maker, holdout=True)
            row = record(rng, maker, clause, items, expect, True, title, parties, related, exclude)
            row['expect'].update(contract=number_, position=position)
            rows.append(row)
            if expect['group'] in ('max', 'min'):
                pair = twin(rng, maker, clause, items[0][0], expect, True, title, parties)
                pair['expect'].update(contract=number_, position=position, changed_law=True)
                rows.append(pair)
    return rows


# Provisions of the knowledge base used as real law. kind max: the number is moved (pattern -> the new limit) and the
# clause value falls on either side; kind default: the provision leaves the matter to the parties, so no clause value
# conflicts with it. Training uses TRAIN_REAL; the evaluation uses EVAL_REAL (three articles never trained on, plus
# the trained ones under new numbers).
REAL_LAW = {
    'interest': dict(number='91/2015/QH13', article='468', kind='max', pattern=r'20%/năm', unit='%/năm'),
    'penalty': dict(number='36/2005/QH11', article='301', kind='max', pattern=r'\b8%', unit='%'),
    'bid_security': dict(number='36/2005/QH11', article='222', kind='max', pattern=r'\b3%', unit='%'),
    'usufruct': dict(number='91/2015/QH13', article='260', kind='max', pattern=r'\b30 năm', unit=' năm'),
    'redemption': dict(number='91/2015/QH13', article='454', kind='default'),
    'performance_security': dict(number='36/2005/QH11', article='231', kind='max', pattern=r'\b10%', unit='%'),
    'auction_deposit': dict(number='36/2005/QH11', article='199', kind='max', pattern=r'\b2%', unit='%'),
    'complaint_terms': dict(number='36/2005/QH11', article='318', kind='default'),
}
TRAIN_REAL = ('interest', 'penalty', 'bid_security', 'usufruct', 'redemption')
EVAL_REAL = ('performance_security', 'auction_deposit', 'complaint_terms')  # (c) articles never trained on


def real_provisions(topics):
    """topic -> (legal document, provision) for the wanted topics found in the knowledge base."""
    from ai.ai_extract.models import LayoutExtractionRun, LegalDocument
    wanted = {topic: REAL_LAW[topic] for topic in topics}
    found = {}
    for document in LegalDocument.objects.filter(number__in={w['number'] for w in wanted.values()}).select_related('contract'):
        run = LayoutExtractionRun.objects.filter(version__contract=document.contract, status='COMPLETED').order_by('-pk').first()
        for clause in ((run.structure or {}).get('contract_clauses') or {}).get('clauses', []) if run else []:
            for topic, w in wanted.items():
                if document.number == w['number'] and re.match(rf'Điều {w["article"]}(?!\d)', clause['title']):
                    found[topic] = (document, clause)
    return found


def rule_sentence(text, at):
    """The sentence of the provision around position at (in text), returned exactly as written there (line breaks
    kept), so the quote is a substring of the brief."""
    flat = ' '.join(text.split())
    words_before = len(text[:at].split())
    flat_at = len(' '.join(text.split()[:words_before])) + (1 if words_before else 0)
    heading = len(' '.join(text.split('\n', 1)[0].split())) + 1  # never start inside the article's own title line
    start = max(heading, flat.rfind('. ', 0, flat_at) + 2, flat.rfind('; ', 0, flat_at) + 2, flat.rfind(': ', 0, flat_at) + 2)
    tail = re.search(r'[.;](?=\s|$)|\s\d+\.\s', flat[flat_at:])
    end = flat_at + (tail.start() + (1 if tail.group(0) in '.;' else 0) if tail else len(flat) - flat_at)
    piece = flat[start:end].strip()
    match = re.search(r'\s+'.join(re.escape(w) for w in piece.split()), text)
    return match.group(0) if match else piece


def real_law_rows(n, seed, topics=TRAIN_REAL, split='train'):
    """Provisions from the knowledge base, with their numbers moved, so the wording is real law."""
    rng = random.Random(seed)
    maker = Maker(rng, split)
    found = real_provisions(topics)
    rows = []
    while found and len(rows) < n:
        topic = rng.choice(list(found))
        document, provision = found[topic]
        spec = REAL_LAW[topic]
        article = re.match(r'Điều (\d+)', provision['title']).group(1)
        law = maker.law('', '')
        law = dict(law, clause_title=provision['title'], document=f'{document.contract.contract_code} — {document.title}',
                   status=IN_FORCE if topic == 'interest' or document.status == IN_FORCE else PARTLY_REPEALED,
                   name=document.title, article=article)
        if spec['kind'] == 'default':
            clause, _, _, expect = maker.default(topic)
            law['text'] = provision['content']
            rows.append(record(rng, maker, clause, [(law, None, CONCEPT_OF.get(topic))], dict(expect, real_law=True),
                               topic in HOLDOUT, title_for(rng, topic), parties_for(rng, topic)))
            continue
        limit = rng.choice(NUMERIC[topic]['limits'])
        clause, _, target, expect = maker.numeric(topic, limit=limit)
        shown = f'{number(limit)}{spec["unit"]}'
        text = re.sub(spec['pattern'], shown, provision['content'], count=1)
        law['text'] = text
        if target:
            target = dict(target, law_quote=rule_sentence(text, text.find(shown)),
                          explanation=numeric_explanation(rng, NUMERIC[topic], clause['title'], expect['shown'], limit,
                                                          f'Điều {article} {document.title}'))
        rows.append(record(rng, maker, clause, [(law, target, CONCEPT_OF[topic])], dict(expect, real_law=True),
                           topic in HOLDOUT, title_for(rng, topic), parties_for(rng, topic)))
    return rows


def describe(name, rows):
    labels = {}
    for row in rows:
        e = row['expect']
        key = 'cross' if e.get('cross') else 'conflict' if e['conflict'] else 'unclear' if e['unclear'] else 'none'
        labels[key] = labels.get(key, 0) + 1
    risks = [r for row in rows for r in row['target']['risks']]
    coded = sum(r['rule_code'] != OTHER for r in risks)
    print(name, len(rows), labels, f'risks {len(risks)}, with a catalog code {coded}',
          f'two risks {sum(len(row["target"]["risks"]) == 2 for row in rows)}',
          f'provisions/brief {sum(len(row["laws"]) for row in rows) / max(1, len(rows)):.1f}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--train', type=int, default=2600)
    parser.add_argument('--valid', type=int, default=220)
    parser.add_argument('--contracts', type=int, default=24)
    parser.add_argument('--real', action='store_true', help='add samples from real provisions in the knowledge base')
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    train = build_split(args.train, seed=1)
    evaluation = eval_contracts(args.contracts, seed=5)
    if args.real:
        train += real_law_rows(max(1, args.train // 8), seed=2)
        for index, row in enumerate(real_law_rows(max(1, args.contracts * 2), seed=6, topics=EVAL_REAL, split='eval')):
            row['expect'].update(contract=f'real-{index}', position=0)
            evaluation.append(row)
    random.Random(3).shuffle(train)
    splits = dict(train=train, valid=build_split(args.valid, seed=4, split='valid'), eval=evaluation)
    for name, rows in splits.items():
        with (OUT / f'{name}.jsonl').open('w', encoding='utf-8') as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + '\n')
        describe(name, rows)


if __name__ == '__main__':
    main()
