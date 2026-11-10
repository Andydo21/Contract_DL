"""Score corpus search on sources/<domain>_eval.json: a query is a hit when an expected article is in the top k."""
import json
from datetime import date

from django.core.management.base import BaseCommand

from legal_kb.services import import_service, search_service as search


class Command(BaseCommand):
    help = 'Hit rate of legal search on the golden queries.'

    def add_arguments(self, parser):
        parser.add_argument('--domain', default='labour')
        parser.add_argument('-k', type=int, default=5)

    def handle(self, *args, **options):
        k = options['k']
        cases = json.loads((import_service.SOURCES / f'{options["domain"]}_eval.json').read_text(encoding='utf-8'))
        hits = first = 0
        for case in cases:
            on = date.fromisoformat(case['date']) if case.get('date') else None
            got = [(r['document'], r['article']) for r in search.search(case['q'], on, options['domain'], k)]
            expected = {tuple(e) for e in case['expect']}
            rank = next((i + 1 for i, g in enumerate(got) if g in expected), None)
            hits += rank is not None
            first += rank == 1
            mark = f'#{rank}' if rank else 'MISS'
            self.stdout.write(f'{mark:5} {case["q"]} {case.get("date", "")}  -> {", ".join(" ".join(g) for g in got[:3])}')
        self.stdout.write(f'hit@{k} {hits}/{len(cases)}  hit@1 {first}/{len(cases)}')
