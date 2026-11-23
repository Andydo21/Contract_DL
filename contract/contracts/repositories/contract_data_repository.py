"""Database operations for contract workflows."""
from contract.contracts.models import AIAnalysis, ContractVersion
from ai.ai_extract.models import ContractSummary

def latest_analyses_by_contract(contracts):
    """contract id -> the newest analysis of its latest version, in two queries for the whole list."""
    latest_version = {}
    for contract_id, version_id in ContractVersion.objects.filter(contract__in=contracts).order_by(
            'contract_id', 'version_number').values_list('contract_id', 'id'):
        latest_version[contract_id] = version_id
    newest = {}
    for analysis in AIAnalysis.objects.filter(version_id__in=latest_version.values()).order_by('created_at', 'pk'):
        newest[analysis.version_id] = analysis
    return {contract_id: newest.get(version_id) for contract_id, version_id in latest_version.items()}


def first_files_for_get_contract_details(version):
    return version.files.first()


def first_ai_analyses_for_get_contract_details(version):
    return version.ai_analyses.order_by('-created_at').first()


def all_ai_extract_clauses_for_get_contract_details(version):
    # Clauses are created in reading order, which the whole-contract review relies on.
    return version.ai_extract_clauses.order_by('id')


def clause_source_pages_for_get_contract_details(version):
    from django.db.models.fields.json import KeyTransform
    stored = version.layout_extraction_runs.filter(status='COMPLETED').annotate(
        stored_clauses=KeyTransform('contract_clauses', 'structure')).values_list('stored_clauses', flat=True).first()
    return {clause['title']: clause.get('source_pages', []) for clause in (stored or {}).get('clauses', [])}


def order_by_contexts_for_get_contract_details(version):
    return version.contexts.filter(context_type='raw_text').order_by('id')


def first_contract_summary_for_get_contract_details(version):
    return ContractSummary.objects.filter(version=version).exclude(summary='').first()


def create_contract_version_for_create_and_analyze_contract(contract):
    return ContractVersion.objects.create(contract=contract, version_number=1, change_summary='Initial version')


def create_contract_version_for_create_new_version(change_summary, contract, next_num):
    return ContractVersion.objects.create(contract=contract, version_number=next_num, change_summary=change_summary)


def save_contract_for_create_new_version(contract):
    return contract.save()


def get_versions_for_analyze_contract(contract, version_id):
    return contract.versions.get(id=version_id)


def delete_ai_analyses_for_analyze_contract(version):
    return version.ai_analyses.all().delete()


def exists_ai_extract_clauses_for_run_ai_analysis_via_api(version):
    return version.ai_extract_clauses.exists()




# ── Batched reads for the contract detail page: a fixed number of queries whatever the clause or version count ──

def version_of(contract, version_id):
    """The contract's version with this id, or None (also for an id that is not a number)."""
    try:
        return contract.versions.filter(pk=int(version_id)).first()
    except (TypeError, ValueError):
        return None


def clauses_with_entities(version):
    # Clauses are created in reading order, which the whole-contract review relies on.
    return version.ai_extract_clauses.order_by('id').prefetch_related('ai_extract_entities')


def reviews_of_version(version):
    from contract.contracts.models import Review
    return Review.objects.filter(analysis__version=version).select_related('user').order_by('analysis_id', 'id')


def findings_of_analysis(analysis):
    return analysis.findings.select_related('clause', 'rule')


def versions_with_latest_analysis(contract):
    """[(version, its newest analysis or None)], newest version first, in two queries."""
    versions = list(contract.versions.order_by('-version_number'))
    newest = {}
    for analysis in AIAnalysis.objects.filter(version__in=versions).order_by('created_at', 'pk'):
        newest[analysis.version_id] = analysis
    return [(version, newest.get(version.pk)) for version in versions]


def next_version_number(contract):
    from django.db.models import Max
    return (contract.versions.aggregate(top=Max('version_number'))['top'] or 0) + 1


def set_file_hash(version, digest):
    ContractVersion.objects.filter(pk=version.pk).update(file_hash=digest)
    version.file_hash = digest


def contract_list_rows(contracts, query=None, status=None):
    """The contract list, only the columns it shows, optionally filtered by a search text and a status."""
    from django.db.models import Q
    rows = contracts.only('id', 'contract_code', 'title', 'contract_type', 'start_date', 'end_date', 'contract_value',
                          'status', 'created_at')
    if query:
        rows = rows.filter(Q(contract_code__icontains=query) | Q(title__icontains=query) | Q(contract_type__icontains=query))
    if status:
        rows = rows.filter(status=status)
    return rows
