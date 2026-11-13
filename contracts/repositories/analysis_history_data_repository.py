"""Database operations for analysis history workflows."""
from contracts.models import AIAnalysis

def order_by_ai_analysis_for_list_all_analyses(company):
    return AIAnalysis.objects.filter(version__contract__company=company, version__contract__deleted_at__isnull=True).order_by('-created_at')


def all_findings_for_list_all_analyses(a):
    return a.findings.all()


def count_findings_for_list_all_analyses(a, risks_only=False):
    return a.findings.filter(is_suggestion=False).count() if risks_only else a.findings.count()
