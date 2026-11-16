"""Score the served model on the risk-skill evaluation set, through the service's own clause review.

    docker exec riskdl_web python -m training.risk_skill.evaluate --label base

Per clause the expectation is one of: a conflict with a given provision, a drafting suggestion (vague clause), or
nothing. Reported:
  conflict recall      conflicts found as a legal risk citing the right provision
  false legal risks    legal risks on clauses that break nothing (compliant, agreed-otherwise or vague clauses)
  vague as suggestion  vague clauses reported as a suggestion, not as a legal risk
  changed-law twins    pairs (same clause, limit moved) where both readings are right: the model read the law
  two-risk clauses     clauses holding two conflicts, both found
  cross-clause risks   two clauses that disagree, reported as a suggestion naming the other clause
  rule codes           found risks filed under the catalog rule the brief lists for them (or OTHER)
Holdout topics (never trained on) are also scored apart. The brief is replayed as built: the same catalog, provisions
and related clauses.
"""
import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from ai.ai_extract.services.contract_pipeline_service import request_qwen  # noqa: E402
from ai.legal_ai.services import clause_risk_service as risk  # noqa: E402
from ai.training.risk_skill.families import HOLDOUT  # noqa: E402

DATA = Path(__file__).resolve().parent / 'data'


def judge(row, confirmed):
    expect = row['expect']
    legal = [r for r in confirmed if r.get('legal')]
    suggestions = [r for r in confirmed if not r.get('legal')]
    if expect.get('cross'):
        if legal:
            return 'false_legal'
        return 'hit' if any(expect['related_id'] in r.get('related_clause_ids', []) for r in suggestions) else 'miss'
    if expect['conflict']:
        found = {i for r in legal for i in r['law_ids']}
        wanted = set(expect.get('law_ids') or [expect['law_id']])
        return 'hit' if wanted <= found else 'partial' if wanted & found else 'miss'
    if expect['unclear']:
        return 'false_legal' if legal else 'suggested' if suggestions else 'silent'
    return 'false_legal' if legal else 'clean'


def codes_right(row, confirmed):
    """(right, checked) rule codes of the expected risks the model found."""
    expect, right, checked = row['expect'], 0, 0
    for law_id, code in (expect.get('law_codes') or {}).items():
        mine = [r for r in confirmed if r.get('legal') and law_id in r['law_ids']]
        if mine:
            checked += 1
            right += any(r.get('rule_code') == code for r in mine)
    if expect.get('cross') and expect.get('cross_code'):
        mine = [r for r in confirmed if expect['related_id'] in r.get('related_clause_ids', [])]
        if mine:
            checked += 1
            right += any(r.get('rule_code') == expect['cross_code'] for r in mine)
    return right, checked


def run(row):
    clause = row['clause']
    by_id = {clause['id']: clause, **{other['id']: other for other in row.get('related', [])}}
    try:
        _, confirmed, _ = risk.review_clause(clause, by_id, row['laws'], row['expect']['title'], row['parties'],
                                             request_qwen, rules=row.get('rules', ()))
        return judge(row, confirmed), confirmed
    except Exception as error:  # a failed call counts against the model, and is listed
        return 'error', [dict(error=f'{type(error).__name__}: {error}')]


def score(rows, outcomes):
    def share(selected, good):
        selected = list(selected)
        return f'{sum(o in good for o in selected)}/{len(selected)}'
    pairs = list(zip(rows, outcomes))
    conflicts = [o for r, o in pairs if r['expect']['conflict']]
    clean = [o for r, o in pairs if not r['expect']['conflict'] and not r['expect']['unclear']]
    vague = [o for r, o in pairs if r['expect']['unclear']]
    twins = {}
    for r, o in pairs:
        if r['expect'].get('group') in ('max', 'min'):
            twins.setdefault((r['expect']['contract'], r['expect']['position']), []).append(o)
    report = dict(conflict_recall=share(conflicts, {'hit'}),
                  false_legal_risks=f'{sum(o == "false_legal" for o in clean + vague)}/{len(clean) + len(vague)}',
                  vague_as_suggestion=share(vague, {'suggested'}),
                  changed_law_twins=f'{sum(all(o in ("hit", "clean") for o in v) for v in twins.values() if len(v) == 2)}/'
                                    f'{sum(len(v) == 2 for v in twins.values())}',
                  two_risk_clauses=share((o for r, o in pairs if r['expect'].get('group') == 'double'
                                          and len(r['expect'].get('law_ids') or []) == 2), {'hit'}),
                  cross_clause=share((o for r, o in pairs if r['expect'].get('cross')), {'hit'}),
                  errors=sum(o == 'error' for o in outcomes))
    held = [(r, o) for r, o in pairs if r['expect']['topic'] in HOLDOUT]
    report['holdout'] = dict(conflict_recall=share((o for r, o in held if r['expect']['conflict']), {'hit'}),
                             false_legal_risks=f'{sum(o == "false_legal" for r, o in held if not r["expect"]["conflict"])}/'
                                               f'{sum(not r["expect"]["conflict"] for r, o in held)}')
    # (a) no governing provision supplied: nothing may be reported as a legal conflict; amended law: the answer must
    # follow the provision in force (hit when it breaks it, clean when it does not), not the original's old limit.
    report['governing_absent'] = share((o for r, o in pairs if r['expect'].get('group') == 'absent'), {'clean'})
    report['amended_law'] = share((o for r, o in pairs if r['expect'].get('group') == 'amended'), {'hit', 'clean'})
    real = [(r, o) for r, o in pairs if r['expect'].get('real_law')]
    if real:  # provisions worded as in the real law (some articles never trained on)
        report['real_law'] = dict(conflict_recall=share((o for r, o in real if r['expect']['conflict']), {'hit'}),
                                  false_legal_risks=f'{sum(o == "false_legal" for r, o in real if not r["expect"]["conflict"])}/'
                                                    f'{sum(not r["expect"]["conflict"] for r, o in real)}')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', default='base', help='name of the model being scored, used in the output file')
    parser.add_argument('--split', default='eval')
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    rows = [json.loads(line) for line in (DATA / f'{args.split}.jsonl').open(encoding='utf-8')]
    rows = rows[:args.limit] if args.limit else rows
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, rows))
    outcomes = [o for o, _ in results]
    report = dict(score(rows, outcomes), label=args.label, clauses=len(rows), seconds=round(time.time() - started, 1))
    right_checked = [codes_right(r, a) for r, (o, a) in zip(rows, results) if o != 'error']
    report['rule_codes'] = f'{sum(r for r, _ in right_checked)}/{sum(c for _, c in right_checked)}'
    print(json.dumps(report, ensure_ascii=False, indent=1))
    out = DATA / f'{args.split}_results_{args.label}.json'
    out.write_text(json.dumps(dict(report=report, items=[dict(expect=r['expect'], outcome=o, answer=a)
                                                         for r, (o, a) in zip(rows, results)]), ensure_ascii=False, indent=1),
                   encoding='utf-8')
    print('saved', out.name)


if __name__ == '__main__':
    main()
