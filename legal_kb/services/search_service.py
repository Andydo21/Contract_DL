"""Look up provisions in force on a given date.

`search` finds candidate clauses with the Postgres full-text index (any less common query word, diacritics ignored),
then ranks them with BM25 over syllables and syllable pairs (most Vietnamese words are two syllables), the article
heading counting extra. Results are one per article: its best clause, with the other clauses that matched.
"""
import math
import re
from collections import Counter
from datetime import date

from legal_kb.parser import fold, ref
from legal_kb.repositories import legal_repository

# Changes that can make a provision's text out of date.
CHANGES = ('amends', 'supplements', 'repeals', 'replaces', 'ends', 'ends_part')
# Chosen on sources/labour_eval.json (manage.py eval_laws); a short b keeps long clauses from being penalised much,
# since a long list of points is often exactly the clause asked about.
K1, B, HEADING_WEIGHT = 1.2, 0.5, 4
CANDIDATES = 3000
_stats = {}


def _syllables(text):
    return re.findall(r'\w+', fold(text or ''))


def _terms(syllables):
    return syllables + [f'{a} {b}' for a, b in zip(syllables, syllables[1:])]


def _counts(heading, text):
    counts = Counter(_terms(_syllables(text)))
    for term, n in Counter(_terms(_syllables(heading))).items():
        counts[term] += HEADING_WEIGHT * n
    return counts


def _corpus_stats(domain):
    """Term counts per provision and document frequencies over the domain, rebuilt when an import changes it."""
    key = legal_repository.corpus_version(domain)
    cached = _stats.get(domain)
    if cached and cached[0] == key:
        return cached[1]
    df, counts = Counter(), {}
    for pk, heading, text in legal_repository.provision_texts(domain):
        terms = _counts(heading, text)
        df.update(terms.keys())
        counts[pk] = (terms, sum(terms.values()))
    stats = {'df': df, 'counts': counts, 'n': len(counts),
             'avgdl': sum(n for _, n in counts.values()) / len(counts) if counts else 1}
    _stats[domain] = (key, stats)
    return stats


def search(query, on=None, domain='labour', limit=8):
    on = on or date.today()
    syllables = list(dict.fromkeys(_syllables(query)))
    stats = _corpus_stats(domain)
    if not syllables or not stats['n']:
        return []
    idf = {
        t: math.log(1 + (stats['n'] - stats['df'][t] + 0.5) / (stats['df'][t] + 0.5))
        for t in _terms(_syllables(query)) if stats['df'][t]
    }
    if not idf:
        return []
    anchors = [s for s in syllables if idf.get(s, 0) >= 1.0] or [max(syllables, key=lambda s: idf.get(s, 0))]

    articles = {}
    for pk, document_id, article_, clause, position in legal_repository.candidate_provisions(
            domain, on, anchors, CANDIDATES):
        if pk not in stats['counts']:
            continue  # imported after the stats were built; picked up on the next rebuild
        counts, length = stats['counts'][pk]
        score = sum(
            weight * counts[t] * (K1 + 1) / (counts[t] + K1 * (1 - B + B * length / stats['avgdl']))
            for t, weight in idf.items() if counts[t]
        )
        entry = articles.setdefault((document_id, article_), {'best': pk, 'score': score, 'matched': []})
        entry['matched'].append((position, clause))
        if score > entry['score']:
            entry['best'], entry['score'] = pk, score

    ranked = sorted(articles.values(), key=lambda e: -e['score'])[:limit]
    rows = legal_repository.provisions_by_id([e['best'] for e in ranked])
    changes = _changes({p.document.source_id for p in rows.values()}, on)
    return [
        _provision(rows[e['best']], changes, on, score=round(e['score'], 3),
                   matched_clauses=[ref(rows[e['best']].article, c) for _, c in sorted(e['matched'])])
        for e in ranked
    ]


def article(number, article_number, on=None):
    """Every clause of one article, or None. `number` is the document's số ký hiệu."""
    document = legal_repository.document_by_number(number)
    provisions = legal_repository.article_provisions(document, article_number) if document else []
    if not provisions:
        return None
    on = on or date.today()
    return {
        **_document(document, _changes({document.source_id}, on), on),
        'article': provisions[0].article,
        'heading': provisions[0].heading,
        'chapter': provisions[0].chapter,
        'clauses': [{'ref': p.ref, 'clause': p.clause, 'text': p.text} for p in provisions],
    }


def documents(domain='labour', on=None):
    on = on or date.today()
    rows, in_force = legal_repository.documents(domain, on)
    changes = _changes({d.source_id for d in rows}, on)
    return [
        {**_document(d, changes, on), 'provisions': d.provision_count, 'parse_warnings': d.parse_warnings,
         'in_force': d.pk in in_force}
        for d in rows
    ]


def _changes(source_ids, on):
    """Documents that changed each of `source_ids` on or before `on`."""
    result = {}
    for r in legal_repository.changes(source_ids, CHANGES, on):
        result.setdefault(r.subject_source_id, []).append({
            'number': r.actor_number, 'effect': r.effect, 'label': r.label, 'title': r.actor_title,
            'effective_from': r.actor_effective_from.isoformat() if r.actor_effective_from else None,
        })
    return result


def _document(d, changes, on):
    return {
        'document': d.number,
        'title': d.title,
        'doc_type': d.doc_type,
        'effective_from': d.effective_from.isoformat() if d.effective_from else None,
        'effective_to': d.effective_to.isoformat() if d.effective_to else None,
        'status': d.status,
        'status_note': d.status_note,
        'gaps': d.gaps,
        # Document-level only: vbpl does not say which clauses these changed, so a clause may be out of date.
        'changed_by': changes.get(d.source_id, []),
        'as_of': on.isoformat(),
    }


def _provision(p, changes, on, **extra):
    return {
        **_document(p.document, changes, on),
        'ref': p.ref,
        'article': p.article,
        'clause': p.clause,
        'heading': p.heading,
        'chapter': p.chapter,
        'text': p.text,
        **extra,
    }
