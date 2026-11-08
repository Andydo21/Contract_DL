"""Build the risk-skill data: train.jsonl, valid.jsonl (same topics) and eval.jsonl (whole contracts, holdout topics,
changed-law twins).

Run inside the web container (the brief and schema come from the service itself, so training matches inference):
    docker exec riskdl_web python -m training.risk_skill.build --train 2400 --real
A record holds the chat messages, the JSON schema the server enforces, the target answer and what it expects.
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

from NewIdea.services import clause_risk_service as risk  # noqa: E402
from training.risk_skill.families import (DEFAULT, HOLDOUT, NUMERIC, RULED, UNCLEAR, COMPANIES, TITLES,  # noqa: E402
                                          Maker, number)

OUT = Path(__file__).resolve().parent / 'data'
RULE_SETS = [
    [dict(code='LAI_SUAT', name='Lãi suất vượt mức', severity='HIGH', description='Lãi suất vượt mức luật cho phép'),
     dict(code='PHAT_VI_PHAM', name='Phạt vi phạm', severity='MEDIUM', description='Mức phạt vượt quy định'),
     dict(code='HINH_THUC', name='Hình thức hợp đồng', severity='HIGH', description='Không đúng hình thức bắt buộc')],
    [dict(code='THOI_HAN', name='Thời hạn', severity='MEDIUM', description='Thời hạn trái quy định hoặc không rõ'),
     dict(code='QUYEN_MOT_PHIA', name='Quyền một phía', severity='HIGH', description='Một bên có quyền trái luật')],
]
RULE_OF = dict(interest='LAI_SUAT', penalty='PHAT_VI_PHAM', notarise='HINH_THUC', written_labour='HINH_THUC',
               arbitration_form='HINH_THUC', notice='THOI_HAN', warranty='THOI_HAN', complaint='THOI_HAN', refund='THOI_HAN',
               probation='THOI_HAN', early_demand='QUYEN_MOT_PHIA', pledge='QUYEN_MOT_PHIA', id_papers='QUYEN_MOT_PHIA')


def record(rng, made, title, parties, holdout, maker, extra_laws=()):
    """Chat messages, schema, target and expectation for one clause."""
    clause, law, risk_target, expect = made
    laws = [law, *maker.distractors(expect['topic'], holdout), *extra_laws]
    rng.shuffle(laws)
    rules = rng.choice(RULE_SETS) if rng.random() < .3 else []
    brief = risk.clause_brief(title, parties, clause, [], laws, rules)
    law_id = f'L{laws.index(law) + 1}'
    answer = dict(clause_summary=f'Điều khoản quy định {clause["content"].split(chr(10), 1)[1].split(".")[0].strip()[0].lower()}'
                                 f'{clause["content"].split(chr(10), 1)[1].split(".")[0].strip()[1:]}.', risks=[])
    if risk_target:
        codes = {r['code'] for r in rules}
        code = RULE_OF.get(expect['topic'])
        cited = [law_id] if risk_target['kind'] == 'conflict' else []
        answer['risks'].append(dict(rule_code=code if code in codes else 'OTHER', category=risk_target['category'],
            risk_level=risk_target['risk_level'], explanation=risk_target['explanation'],
            recommendation=risk_target['recommendation'], disadvantaged_party=risk_target['disadvantaged_party'],
            contract_quote=risk_target['contract_quote'], law_ids=cited, law_quote=risk_target['law_quote'],
            kind=risk_target['kind'], related_clause_ids=[]))
        # The target must pass the same checks the service applies to the model's answer.
        assert risk.grounded(answer['risks'][0], clause, {f'L{i}' for i in range(1, len(laws) + 1)}, set()), clause
        if cited:
            assert risk.law_quoted(risk_target['law_quote'], [law]), (risk_target['law_quote'], law['text'])
    return dict(messages=[dict(role='system', content=risk.CLAUSE_RULES), dict(role='user', content=brief)],
                schema=risk.clause_schema(len(laws), set()), target=answer,
                expect=dict(expect, law_id=law_id if expect['conflict'] else None, title=title),
                clause=clause, laws=[{k: v for k, v in l.items() if k not in ('name', 'article')} for l in laws], parties=parties)


def sample(rng, maker, holdout):
    """One clause from any group; holdout topics only for evaluation."""
    allowed = lambda keys: [k for k in keys if holdout or k not in HOLDOUT]
    group = rng.choices(['numeric', 'ruled', 'default', 'unclear'], weights=[45, 25, 15, 15])[0]
    if group == 'numeric':
        return maker.numeric(rng.choice(allowed(NUMERIC)))
    if group == 'ruled':
        return maker.ruled(rng.choice(allowed(RULED)))
    if group == 'default':
        return maker.default(rng.choice(list(DEFAULT)))
    return maker.unclear(rng.choice(allowed(UNCLEAR)))


def parties_for(rng):
    a, b = rng.sample(COMPANIES, 2)
    return [] if rng.random() < .2 else [f'Bên A: {a}', f'Bên B: {b}']


def build_split(n, seed, holdout=False):
    rng = random.Random(seed)
    maker = Maker(rng)
    rows = []
    while len(rows) < n:
        made = sample(rng, maker, holdout)
        rows.append(record(rng, made, rng.choice(TITLES), parties_for(rng), holdout, maker))
        # A changed-law twin of a numeric clause: the same clause value, the limit moved across it.
        if made[3]['group'] in ('max', 'min') and rng.random() < .5 and len(rows) < n:
            rows.append(twin(rng, maker, made, holdout))
    return rows


def twin(rng, maker, made, holdout, title=None, parties=None):
    """The same clause under a provision whose limit is on the other side of the clause's value."""
    expect = made[3]
    t = NUMERIC[expect['topic']]
    value = expect['value']
    if expect['conflict']:
        limit = value + (0 if rng.random() < .3 else max(1, round(value * .5)))  # now compliant (on or above / below)
        if t['kind'] == 'min':
            limit = max(1, value - (0 if rng.random() < .3 else max(1, round(value * .5))))
    else:
        limit = max(1, value - max(1, round(value * .3))) if t['kind'] == 'max' else value + max(1, round(value * .3))
    clause, law, _, _ = made
    text = law['text'].split('\n', 1)[0] + '\n' + t['law'].format(limit=number(limit))
    law2 = dict(law, text=text, source_id=f'{law["source_id"]}-twin')
    breaks = value > limit if t['kind'] == 'max' else value < limit
    risk_target = None
    if breaks:
        sentence = clause['content'].split('\n', 1)[1].split(' Các bên')[0].split(' Mọi thay')[0].split(' Điều khoản này')[0].strip()
        ref = f'Điều {law["article"]} {law["name"]}'
        risk_target = dict(category=t['category'], risk_level=t['level'],
                           explanation=f'{clause["title"]} quy định {t["subject"]} là {number(value)}{"%/năm" if expect["topic"] == "interest" else t["unit"]}, '
                                       f'{"vượt mức tối đa" if t["kind"] == "max" else "thấp hơn mức tối thiểu"} {number(limit)}{t["unit"]} theo {ref}.',
                           recommendation=f'Điều chỉnh {t["subject"]} {"không vượt quá" if t["kind"] == "max" else "không thấp hơn"} {number(limit)}{t["unit"]}.',
                           disadvantaged_party=t['party'], contract_quote=sentence, law_quote=law2['text'].split('\n', 1)[1], kind='conflict')
    expect2 = dict(expect, conflict=breaks, limit=limit, twin_of=law['source_id'])
    return record(rng, (clause, law2, risk_target, expect2), title or rng.choice(TITLES), parties if parties is not None else parties_for(rng),
                  holdout, maker)


def eval_contracts(count, seed):
    """Whole contracts of 6-8 clauses, holdout topics included, each numeric clause also under a changed law."""
    rng = random.Random(seed)
    maker = Maker(rng)
    rows = []
    for number_ in range(1, count + 1):
        title, parties = rng.choice(TITLES), parties_for(rng)
        for position in range(rng.randint(6, 8)):
            made = sample(rng, maker, holdout=True)
            row = record(rng, made, title, parties, True, maker)
            row['expect'].update(contract=number_, position=position)
            rows.append(row)
            if made[3]['group'] in ('max', 'min'):
                pair = twin(rng, maker, made, True, title, parties)
                pair['expect'].update(contract=number_, position=position, changed_law=True)
                rows.append(pair)
    return rows


def real_law_rows(n, seed):
    """Provisions from the knowledge base, with their numbers moved, so the wording is real law."""
    from ai_extract.models import LayoutExtractionRun, LegalDocument
    rng = random.Random(seed)
    maker = Maker(rng)
    wanted = {('91/2015/QH13', 'Điều 468.'): 'interest', ('36/2005/QH11', 'Điều 301.'): 'penalty'}
    found = {}
    for document in LegalDocument.objects.filter(number__in={k[0] for k in wanted}).select_related('contract'):
        run = LayoutExtractionRun.objects.filter(version__contract=document.contract, status='COMPLETED').order_by('-pk').first()
        for clause in ((run.structure or {}).get('contract_clauses') or {}).get('clauses', []) if run else []:
            for (law_number, prefix), topic in wanted.items():
                if document.number == law_number and re.match(re.escape(prefix.rstrip('.')) + r'(?!\d)', clause['title']):
                    found[topic] = (document, clause)
    rows = []
    pattern = {'interest': r'20%/năm', 'penalty': r'\b8%'}
    while found and len(rows) < n:
        topic = rng.choice(list(found))
        document, clause = found[topic]
        limit = rng.choice(NUMERIC[topic]['limits'])
        clause_made, law, risk_target, expect = maker.numeric(topic, limit=limit)
        text = re.sub(pattern[topic], f'{number(limit)}%' + ('/năm' if topic == 'interest' else ''), clause['content'], count=1)
        # The rule's own sentence around the number: from the last sentence break (or a numbered paragraph's heading,
        # which ends without a full stop) before it to the next one after it.
        flat = ' '.join(text.split())
        at = flat.find(f'{number(limit)}%')
        start = max(flat.rfind('. ', 0, at) + 2, flat.rfind('; ', 0, at) + 2, flat.rfind('Trường hợp', 0, at), flat.rfind('Mức phạt', 0, at))
        end = min(i for i in (flat.find('.', at), flat.find(';', at), len(flat) - 1) if i >= 0)
        sentence = flat[start:end + 1]
        law = dict(law, text=text, clause_title=clause['title'], document=f'{document.contract.contract_code} — {document.title}',
                   status='Còn hiệu lực' if topic == 'interest' else document.status, name=document.title,
                   article=re.match(r'Điều (\d+)', clause['title']).group(1))
        if risk_target:
            risk_target = dict(risk_target, law_quote=sentence,
                               explanation=risk_target['explanation'].rsplit(' theo ', 1)[0] + f' theo Điều {law["article"]} {document.title}.')
        rows.append(record(rng, (clause_made, law, risk_target, dict(expect, real_law=True)), rng.choice(TITLES), parties_for(rng), False, maker))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--train', type=int, default=2400)
    parser.add_argument('--valid', type=int, default=200)
    parser.add_argument('--contracts', type=int, default=20)
    parser.add_argument('--real', action='store_true', help='add samples from real provisions in the knowledge base')
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    train = build_split(args.train, seed=1)
    if args.real:
        train += real_law_rows(max(1, args.train // 8), seed=2)
    random.Random(3).shuffle(train)
    splits = dict(train=train, valid=build_split(args.valid, seed=4), eval=eval_contracts(args.contracts, seed=5))
    for name, rows in splits.items():
        with (OUT / f'{name}.jsonl').open('w', encoding='utf-8') as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + '\n')
        groups = {}
        for row in rows:
            key = 'conflict' if row['expect']['conflict'] else 'unclear' if row['expect']['unclear'] else 'none'
            groups[key] = groups.get(key, 0) + 1
        print(name, len(rows), groups)


if __name__ == '__main__':
    main()
