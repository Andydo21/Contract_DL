"""Reads and writes of the legal corpus."""
import re

from django.contrib.postgres.search import SearchQuery
from django.db import connection
from django.db.models import Count, Max, Q

from legal_kb.models import LegalDocument, LegalProvision, LegalRelation
from legal_kb.parser import fold


def _in_force(on):
    return Q(effective_from__isnull=True) | Q(effective_from__lte=on), Q(effective_to__isnull=True) | Q(effective_to__gt=on)


# ── Import ───────────────────────────────────────────────────────────────

def document_by_source(source_id):
    return LegalDocument.objects.filter(source_id=source_id).first()


def has_provisions(document):
    return document.provisions.exists()


def update_document(document, fields):
    LegalDocument.objects.filter(pk=document.pk).update(**fields)


def replace_document(source_id, fields, provisions):
    """Save a document and its parsed provisions in place of what was stored for it."""
    document, _ = LegalDocument.objects.update_or_create(source_id=source_id, defaults=fields)
    document.provisions.all().delete()
    LegalProvision.objects.bulk_create(
        LegalProvision(document=document, position=index, article=p.article, clause=p.clause,
                       heading=p.heading, chapter=p.chapter, section=p.section, text=p.text)
        for index, p in enumerate(provisions)
    )
    return document


def remove_documents_except(domain, source_ids):
    stale = LegalDocument.objects.filter(domain=domain).exclude(source_id__in=source_ids)
    count = stale.count()
    stale.delete()
    return count


def replace_relations(source_ids, relations):
    """`relations`: dicts of LegalRelation fields; every stored link touching `source_ids` is replaced."""
    LegalRelation.objects.filter(Q(actor_source_id__in=source_ids) | Q(subject_source_id__in=source_ids)).delete()
    LegalRelation.objects.bulk_create(LegalRelation(**r) for r in relations)


def index_documents(document_ids):
    """Full-text vectors: heading weighted above the text, each with and without diacritics."""
    rows = [
        (_index_text(heading), _index_text(text), _index_text(f'{chapter} {section}'), pk)
        for pk, heading, text, chapter, section in LegalProvision.objects.filter(document_id__in=document_ids)
        .values_list('pk', 'heading', 'text', 'chapter', 'section')
    ]
    with connection.cursor() as cursor:
        cursor.executemany(
            "UPDATE legal_kb_legalprovision SET search ="
            " setweight(to_tsvector('simple', %s), 'A')"
            " || setweight(to_tsvector('simple', %s), 'B')"
            " || setweight(to_tsvector('simple', %s), 'C') WHERE id = %s",
            rows,
        )


def _index_text(text):
    text = re.sub(r'\s+', ' ', text or '').lower()
    return f'{text} {fold(text)}'


def provision_count(domain):
    return LegalProvision.objects.filter(document__domain=domain).count()


# ── Lookup ───────────────────────────────────────────────────────────────

def corpus_version(domain):
    """Changes whenever an import touches the domain."""
    return tuple(LegalDocument.objects.filter(domain=domain).aggregate(Max('imported_at'), Count('pk')).values())


def provision_texts(domain):
    return LegalProvision.objects.filter(document__domain=domain).values_list('pk', 'heading', 'text').iterator()


def candidate_provisions(domain, on, any_of, limit):
    """(pk, document_id, article, clause, position) of provisions in force on `on` holding any of the folded words."""
    return list(
        LegalProvision.objects
        .filter(document__in=LegalDocument.objects.filter(*_in_force(on), domain=domain))
        .filter(search=SearchQuery(' | '.join(any_of), search_type='raw', config='simple'))
        .values_list('pk', 'document_id', 'article', 'clause', 'position')[:limit]
    )


def provisions_by_id(ids):
    return LegalProvision.objects.select_related('document').in_bulk(ids)


def document_by_number(number):
    return LegalDocument.objects.filter(number__iexact=number.strip()).first()


def article_provisions(document, article):
    return list(document.provisions.filter(article__iexact=str(article).strip()))


def documents(domain, on):
    """Documents of the domain with their provision counts, and the ids of those in force on `on`."""
    in_force = set(LegalDocument.objects.filter(*_in_force(on), domain=domain).values_list('pk', flat=True))
    return list(LegalDocument.objects.filter(domain=domain).annotate(provision_count=Count('provisions'))), in_force


def changes(source_ids, effects, on):
    """Links in which another document changed one of `source_ids`, in effect on or before `on`."""
    return list(
        LegalRelation.objects.filter(subject_source_id__in=source_ids, effect__in=effects)
        .filter(Q(actor_effective_from__isnull=True) | Q(actor_effective_from__lte=on))
        .order_by('actor_effective_from')
    )
