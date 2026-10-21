from decimal import Decimal
"""Read extraction runs, page blocks and contract files; persist A3 extraction results."""
from ai_extract.models import LayoutExtractionRun, LayoutExtractionPage, LayoutExtractionBlock
from NewIdea.repositories.contract_repository import visible_contracts
from django.db import transaction


def dashboard_contracts(user):
    return list(visible_contracts(user).prefetch_related('versions__files', 'versions__layout_extraction_runs').order_by('-updated_at'))


def contract_for(user, contract_id):
    return visible_contracts(user).prefetch_related('versions__files', 'versions__layout_extraction_runs__pages__blocks').get(pk=contract_id)


def latest_run(version, completed=False):
    if not version:
        return None
    if completed:
        cached = getattr(version, '_prefetched_objects_cache', {}).get('layout_extraction_runs')
        if cached is not None:
            return next((run for run in cached if run.status == 'COMPLETED'), None)
    rows = version.layout_extraction_runs
    return rows.filter(status='COMPLETED').first() if completed else rows.first()


def pages(run):
    return list(run.pages.all()) if run else []


def page_for(run, page_number):
    return LayoutExtractionPage.objects.prefetch_related('blocks').get(run=run, page_number=page_number)


def run_for_version(version, run_id):
    return version.layout_extraction_runs.get(pk=run_id)


def page_blocks(page):
    return list(page.blocks.all())


def page_numbers(run):
    return list(run.pages.order_by('page_number').values_list('page_number', flat=True))


def latest_file(version):
    return version.files.order_by('-uploaded_at').first()


def create_run(version, pipeline_name):
    return LayoutExtractionRun.objects.create(version=version, pipeline_name=pipeline_name, status='RUNNING')


def save_run(run, fields):
    run.save(update_fields=fields)


def indexed_run(run):
    return LayoutExtractionRun.objects.select_related('version__contract').get(pk=run.pk)


def persist_rendered_page(run, page_number, image_path, width, height):
    """Persist the rendered page before Surya detects source blocks."""
    return LayoutExtractionPage.objects.create(run=run, page_number=page_number,
        image_path=image_path, width=width, height=height)


@transaction.atomic
def persist_pages(run, result, *, incremental=False, cumulative=True):
    from ai_extract.models import LayoutExtractionPage, LayoutExtractionBlock
    from contracts.models import ContractContext
    contexts = []
    new_records = []
    total_blocks = 0
    for page_result in result.pages:
        defaults = dict(width=page_result.width, height=page_result.height,
                        image_path=page_result.image_path, extracted_text=page_result.text)
        if incremental:
            page, created = LayoutExtractionPage.objects.update_or_create(
                run=run, page_number=page_result.page_number, defaults=defaults)
            # Retrying a page replaces its derived blocks instead of appending
            # a second OCR copy. Other pages and historical runs are untouched.
            if not created:
                page.blocks.all().delete()
        else:
            page = LayoutExtractionPage.objects.create(run=run, page_number=page_result.page_number, **defaults)
        blocks = [LayoutExtractionBlock(page=page, block_order=block.order, layout_type=block.layout_type, text=block.text, bbox=block.bbox, structure_metadata=getattr(block, 'structure_metadata', {}), confidence=Decimal(str(round(max(0.0, min(1.0, block.confidence)), 4)))) for block in page_result.blocks]
        LayoutExtractionBlock.objects.bulk_create(blocks)
        new_records.extend(dict(chunk_id=f'block:{block.pk}', text=block.text,
            page_number=page.page_number, bbox=block.bbox, layout_type=block.layout_type,
            image_path=page.image_path, structure_metadata=block.structure_metadata) for block in blocks)
        total_blocks += len(blocks)
        contexts.append(ContractContext(version=run.version, context_type='raw_text', source=f'plan-a:page:{page_result.page_number}', content=page_result.text, relevance_score=Decimal('1.00') if page_result.text else Decimal('0.00')))
    contexts_query = ContractContext.objects.filter(version=run.version, context_type='raw_text',source__startswith='plan-a:page:')
    if incremental:
        contexts_query = contexts_query.filter(source__in=[c.source for c in contexts])
    contexts_query.delete()
    ContractContext.objects.bulk_create(contexts)
    if not cumulative:
        return new_records, total_blocks
    records = [dict(chunk_id=f'block:{block.pk}', text=block.text, page_number=page.page_number, bbox=block.bbox, layout_type=block.layout_type, image_path=page.image_path, structure_metadata=block.structure_metadata) for page in run.pages.prefetch_related('blocks').order_by('page_number') for block in page.blocks.all()]
    return records, total_blocks


def retire_old_page_contexts(run):
    """Remove obsolete page contexts only after a newer complete source exists."""
    from contracts.models import ContractContext
    if run.status!='COMPLETED' or LayoutExtractionRun.objects.filter(
            version_id=run.version_id,pk__gt=run.pk,status__in=['RUNNING','COMPLETED']).exists():
        return 0
    sources=[f'plan-a:page:{number}' for number in run.pages.values_list('page_number',flat=True)]
    deleted,_=ContractContext.objects.filter(version_id=run.version_id,context_type='raw_text',
        source__startswith='plan-a:page:').exclude(source__in=sources).delete()
    return deleted


def completed_runs(version_id=None):
    from django.db.models import Q
    rows = LayoutExtractionRun.objects.filter(status='COMPLETED').select_related('version__contract').order_by('-started_at','-pk')
    if version_id:
        rows = rows.filter(version_id=version_id)
    # Transaction-pooled Postgres connections cannot retain named cursors
    # across fetches. Keyset batches use ordinary queries and bounded memory.
    cursor=None
    while True:
        query=rows if cursor is None else rows.filter(
            Q(started_at__lt=cursor.started_at)|Q(started_at=cursor.started_at,pk__lt=cursor.pk))
        batch=list(query[:10])
        if not batch:return
        yield from batch
        cursor=batch[-1]


def structure_records(run):
    return [dict(chunk_id=f'block:{block.pk}', text=block.text, page_number=page.page_number,
        bbox=block.bbox, layout_type=block.layout_type, image_path=page.image_path, structure_metadata=block.structure_metadata)
        for page in run.pages.prefetch_related('blocks').order_by('page_number')
        for block in page.blocks.all()]


def graph_source_blocks(run, block_ids):
    """Resolve graph labels from original blocks of this extraction only."""
    if not block_ids:
        return {}
    rows = LayoutExtractionBlock.objects.filter(page__run_id=run.pk, pk__in=block_ids).values(
        'id', 'block_order', 'text', 'page__page_number')
    return {str(row['id']): row for row in rows}
