"""Load Django views only when requested; inference routes need no web ORM."""
__all__ = ['api_summarize_contract', 'api_get_summary', 'api_extract_entities',
           'api_extract_from_text', 'api_get_entities', 'api_extract_clauses', 'api_get_clauses',
           'api_summary_lab_contract', 'api_summary_lab_text', 'api_summary_lab_health',
           'api_summary_lab_compare', 'api_summary_lab_file', 'api_summary_lab_read',
           'api_summary_changes', 'api_summary_overview', 'api_summary_sections', 'api_summary_export', 'api_summary_suggest']


def __getattr__(name):
    if name in __all__:
        from . import extraction_views
        return getattr(extraction_views, name)
    raise AttributeError(name)
