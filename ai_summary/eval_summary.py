"""Golden-set evaluation of a running ai_summary service.

Usage (from ai_summary/):  python eval_summary.py [--url http://127.0.0.1:8004] [--out report.json] [--cached]
Every case is sent with force=true unless --cached, so latency reflects a real model call.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import requests
from shared.jwt_middleware import get_system_auth_header

FILLER = ('Các bên phối hợp lập, lưu trữ và chuyển giao hồ sơ theo đúng biểu mẫu được hai bên thống nhất. '
          'Việc trao đổi thông tin được thực hiện qua thư điện tử và văn bản có chữ ký của người đại diện. '
          'Mọi điều chỉnh về biểu mẫu phải được hai bên xác nhận trước khi áp dụng. ') * 6


def build_text(case):
    filler = case.get('filler')
    if not filler:
        return case['text']
    sections = [f"Điều {n}. Quy định về hồ sơ, biểu mẫu và thủ tục hành chính\n{FILLER.strip()}"
                for n in range(filler['start'], filler['start'] + filler['count'])]
    return case['text'].replace('{{FILLER}}', '\n'.join(sections))


def squash(text):
    return ' '.join(str(text).lower().split())


def field_text(body, field):
    if field == 'any':
        return body['summary']
    value = body['structured'].get(field, '')
    if isinstance(value, list):
        return ' | '.join(' '.join(str(v) for v in item.values()) for item in value)
    return value


def evaluate(case, body):
    checks = []
    expect = case['expect']
    for field, wanted in expect.items():
        if field in ('absent', 'empty', 'min_chunks', 'party', 'checklist_missing'):
            continue
        haystack = squash(field_text(body, field))
        for item in wanted:
            options = item if isinstance(item, list) else [item]
            checks.append(dict(check=f'{field} ∋ {" | ".join(options)}', ok=any(squash(o) in haystack for o in options),
                               got=field_text(body, field)[:160]))
    # Confidence scores are numbers too (prob 0.999 would match an absent "999"); only the content counts.
    content = json.loads(json.dumps(body['structured']), object_hook=lambda d: {k: v for k, v in d.items() if k != 'confidence'})
    everything = squash(body['summary'] + json.dumps(content, ensure_ascii=False))
    for text in expect.get('absent', []):
        checks.append(dict(check=f'không có “{text}”', ok=squash(text) not in everything, got=''))
    for field in expect.get('empty', []):
        value = body['structured'].get(field)
        checks.append(dict(check=f'{field} để trống', ok=not value, got=str(value)[:160]))
    # Per-party attributes: an empty expected value means the field must stay empty.
    for name, attributes in expect.get('party', {}).items():
        party = next((p for p in body['structured']['parties'] if squash(name) in squash(p['name'])), None)
        for key, wanted in attributes.items():
            got = party[key] if party else '(không thấy bên này)'
            ok = party is not None and (squash(wanted) in squash(got) if wanted else not got.strip())
            checks.append(dict(check=f'{name}.{key} = {wanted or "trống"}', ok=ok, got=got))
    gaps = ' | '.join(i['message'] for i in (body.get('checklist') or {}).get('items', []) if i['status'] != 'found')
    for wanted in expect.get('checklist_missing', []):
        checks.append(dict(check=f'checklist báo thiếu {wanted}', ok=squash(wanted) in squash(gaps), got=gaps[:160]))
    if 'min_chunks' in expect:
        checks.append(dict(check=f"chunks ≥ {expect['min_chunks']}", ok=body['chunks'] >= expect['min_chunks'],
                           got=str(body['chunks'])))
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8004')
    parser.add_argument('--out', default=str(ROOT / 'eval_report.json'))
    parser.add_argument('--cached', action='store_true', help='allow cached results (no force)')
    parser.add_argument('--only', nargs='*', help='case ids to run')
    parser.add_argument('--model', help='served model id to evaluate instead of SUMMARY_MODEL_ID')
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    cases = json.loads((ROOT / 'eval_cases.json').read_text(encoding='utf-8'))
    if args.only:
        cases = [c for c in cases if c['id'] in args.only]
    report, passed, total = [], 0, 0
    for case in cases:
        text = build_text(case)
        started = time.monotonic()
        response = requests.post(f'{args.url}/api/v1/summarize', json=dict(text=text, force=not args.cached, model=args.model),
                                 headers=get_system_auth_header(), timeout=900)
        wall = time.monotonic() - started
        if not response.ok:
            report.append(dict(id=case['id'], error=f'HTTP {response.status_code}: {response.text[:300]}'))
            print(f"✗ {case['id']}: HTTP {response.status_code} {response.text[:200]}")
            continue
        body = response.json()
        checks = evaluate(case, body)
        ok = sum(c['ok'] for c in checks)
        passed, total = passed + ok, total + len(checks)
        report.append(dict(id=case['id'], note=case.get('note', ''), chars=len(text), chunks=body['chunks'],
                           seconds=round(wall, 1), passed=ok, checks_total=len(checks), checks=checks,
                           unverified=body['unverified'], summary=body['summary'], structured=body['structured']))
        print(f"{'✓' if ok == len(checks) else '✗'} {case['id']:<18} {ok}/{len(checks)}  "
              f"{len(text):>6} ký tự  {body['chunks']} chunk  {wall:5.1f}s  loại {len(body['unverified'])}")
        for check in checks:
            if not check['ok']:
                print(f"    ✗ {check['check']}  — nhận: {check['got']!r}")
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nTổng: {passed}/{total} kiểm tra đạt. Báo cáo: {args.out}')


if __name__ == '__main__':
    main()
