"""Database operations for clause extract workflows."""

def first_layout_extraction_runs_for_extract_version(version):
    return version.layout_extraction_runs.filter(status='COMPLETED').first()


def exists_contexts_for_extract_version(version):
    return version.contexts.filter(context_type='raw_text').exists()


def exists_files_for_extract_version(version):
    return version.files.exclude(file_path='').exists()


def exists_ai_extract_clauses_for_extract_version(version):
    return version.ai_extract_clauses.exists()


def order_by_contexts_for_extract_version(version):
    return version.contexts.filter(context_type='raw_text').order_by('id')


def all_ai_extract_clauses_for_extract_version(version):
    return version.ai_extract_clauses.all()
