"""Score the served model on the risk-skill evaluation set, through the service's own clause review.

    docker exec riskdl_web python -m training.risk_skill.evaluate --label base

Per clause the expectation is one of: a conflict with a given provision, a drafting suggestion (vague clause), or
nothing. Reported:
  conflict recall      conflicts found as a legal risk citing the right provision
  false legal risks    legal risks on clauses that break nothing (compliant, agreed-otherwise or vague clauses)
  vague as suggestion  vague clauses reported as a suggestion, not as a legal risk
  changed-law twins    pairs (same clause, limit moved) where both readings are right: the model read the law
Holdout topics (never trained on) are also scored apart.
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

from ai_extract.services.contract_pipeline_service import request_qwen  # noqa: E402
from NewIdea.services import clause_risk_service as risk  # noqa: E402
from training.risk_skill.families import HOLDOUT  # noqa: E402

DATA = Path(__file__).resolve().parent / 'data'


def judge(row, confirmed):
    expect = row['expect']
    legal = [r for r in confirmed if r.get('legal')]
    suggestions = [r for r in confirmed if not r.get('legal')]
    if expect['conflict']:
        return 'hit' if any(expect['law_id'] in r['law_ids'] for r in legal) else 'miss'
    if expect['unclear']:
        return 'false_legal' if legal else 'suggested' if suggestions else 'silent'
    return 'false_legal' if legal else 'clean'


def run(row):
    clause = row['clause']
    try:
        _, confirmed, _ = risk.review_clause(clause, {clause['id']: clause}, row['laws'], row['expect']['title'], row['parties'],
                                             request_qwen)
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
                  errors=sum(o == 'error' for o in outcomes))
    held = [(r, o) for r, o in pairs if r['expect']['topic'] in HOLDOUT]
    report['holdout'] = dict(conflict_recall=share((o for r, o in held if r['expect']['conflict']), {'hit'}),
                             false_legal_risks=f'{sum(o == "false_legal" for r, o in held if not r["expect"]["conflict"])}/'
                                               f'{sum(not r["expect"]["conflict"] for r, o in held)}')
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
    print(json.dumps(report, ensure_ascii=False, indent=1))
    out = DATA / f'{args.split}_results_{args.label}.json'
    out.write_text(json.dumps(dict(report=report, items=[dict(expect=r['expect'], outcome=o, answer=a)
                                                         for r, (o, a) in zip(rows, results)]), ensure_ascii=False, indent=1),
                   encoding='utf-8')
    print('saved', out.name)


if __name__ == '__main__':
    main()
