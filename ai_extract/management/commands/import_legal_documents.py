"""Load public law through the normal upload and extraction path; a finished document is skipped."""
from datetime import datetime
import io
import json
import time
from xml.sax.saxutils import escape
from django.core.files import File
from django.core.management.base import BaseCommand
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate
from ai_extract.services.layout_service import LayoutExtractionService
from contracts.models import Company, Contract
from contracts.services.contract_service import ContractService
from NewIdea.repositories import contract_repository, knowledge_repository

LAW_COMPANY = dict(tax_code='SYSTEM-LEGAL', company_name='Kho pháp luật')
FONT = 'LegalText'


def render_pdf(text, font_path):
    """The extraction path reads PDF files; the dataset holds plain text."""
    pdfmetrics.registerFont(TTFont(FONT, font_path))
    style = ParagraphStyle('legal', fontName=FONT, fontSize=11, leading=15, spaceAfter=6)
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4).build([Paragraph(escape(line), style) for line in text.split('\n') if line.strip()])
    buffer.seek(0)
    return buffer


def _date(value):
    try:
        return datetime.strptime(value or '', '%d/%m/%Y').date()
    except ValueError:
        return None


def register(row, company, font_path):
    code = f'LAW-{row["id"]}'
    contract = Contract.objects.filter(contract_code=code).first()
    if contract is None:
        contract = ContractService().create_and_analyze_contract(code=code, title=row['title'][:255], contract_type='LEGAL_DOCUMENT', start_date=None, end_date=None, contract_value=None,
                                                                 file_obj=File(render_pdf(row['text'], font_path), name=code+'.pdf'), company=company)
    knowledge_repository.mark_legal(contract, public=True, source_id=row['id'], number=row['number'], title=row['title'], doc_type=row['type'], status=row['status'],
                                    authority=row.get('authority') or '', issued_on=_date(row.get('issued')), effective_on=_date(row.get('effective')),
                                    amended_by=row.get('amended_by') or [], text_source=row.get('text_source', ''))
    return contract


class Command(BaseCommand):
    help = 'Register legal documents from a JSON Lines file and run the normal extraction on each.'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--font', required=True, help='A TrueType font with Vietnamese letters.')
        parser.add_argument('--numbers', help='Comma separated document numbers; translations are left out.')

    def handle(self, *args, **options):
        wanted = {number.strip() for number in options['numbers'].split(',')} if options['numbers'] else None
        with open(options['path'], encoding='utf-8') as source:
            rows = [row for row in map(json.loads, source) if wanted is None or (row['number'] in wanted and row['type'] != 'Bản dịch văn bản')]
        company, _ = Company.objects.get_or_create(tax_code=LAW_COMPANY['tax_code'], defaults=LAW_COMPANY)
        for index, row in enumerate(rows, 1):
            contract = register(row, company, options['font'])
            version = contract.latest_version
            if contract_repository.completed_extraction_run(version):
                self.stdout.write(f'{index}/{len(rows)} {row["number"]}: already extracted')
                continue
            started = time.time()
            run = LayoutExtractionService().extract_version(version, defer_colpali=True)
            tree = run.structure or {}
            self.stdout.write(f'{index}/{len(rows)} {row["number"]}: {run.status} {round(time.time()-started)}s pages={run.total_pages} '
                              f'clauses={len(tree.get("contract_clauses", {}).get("clauses", []))} graph={tree.get("graph_index", {}).get("status")} dense={run.dense_index_status}')
