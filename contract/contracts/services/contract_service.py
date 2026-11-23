from contract.contracts.repositories import contract_data_repository as data_repository
import logging
from decimal import Decimal
from django.core.files.base import ContentFile
from django.db import transaction
from contract.contracts.repositories.contract_repository import ContractRepository
from contract.contracts.repositories.contract_file_repository import ContractFileRepository
from ai.analysis.repositories.ai_analysis_repository import AIAnalysisRepository
from ai.analysis.repositories.risk_finding_repository import RiskFindingRepository
from ai.analysis.repositories.review_repository import ReviewRepository
from contract.core.repositories.audit_log_repository import AuditLogRepository

logger = logging.getLogger(__name__)


def _store_document(file_obj, raw_content, text_name):
    """Encrypt and store an uploaded file, or pasted text as a .txt file.

    Returns {'url', 'name', 'sha256'} (the hash is of the original bytes, before encryption), or None for neither."""
    import hashlib
    from django.core.files.storage import FileSystemStorage
    from contract.core.services.document_encryption_service import encrypt_pdf
    if file_obj:
        name, data = f'contract/contracts/{file_obj.name}', file_obj.read()
    elif raw_content:
        name, data = f'contract/contracts/{text_name}', raw_content.encode('utf-8')
    else:
        return None
    storage = FileSystemStorage()
    saved = storage.save(name, ContentFile(encrypt_pdf(data)))
    return {'url': storage.url(saved), 'name': saved, 'sha256': hashlib.sha256(data).hexdigest()}


def _discard_stored(stored):
    """Remove a stored file whose database rows were rolled back; it would otherwise be an orphan on disk."""
    if not stored:
        return
    from django.core.files.storage import FileSystemStorage
    try:
        FileSystemStorage().delete(stored['name'])
    except OSError:
        logger.warning('Could not remove orphaned upload %s', stored['name'], exc_info=True)


def _attach_document(version, stored, summarize):
    """File record and hash of the stored document; its automatic summary starts once the transaction commits."""
    if not stored:
        return
    ContractFileRepository().create_file_record(version, stored['url'])
    data_repository.set_file_hash(version, stored['sha256'])
    from ai.ai_extract.services.summary_service import schedule_auto_summary
    schedule_auto_summary(version, summarize)


def _version_row(version, analysis):
    return {'id': version.id, 'version_number': version.version_number, 'change_summary': version.change_summary or 'Initial version',
            'created_at': version.created_at.isoformat(), 'file_hash': version.file_hash,
            'overall_score': float(analysis.overall_score) if analysis and analysis.overall_score is not None else None,
            'risk_level': analysis.risk_level if analysis else 'NONE'}


def versions_list(contract):
    """The versions of a contract, newest first, with the risk level of each one's newest analysis."""
    return [_version_row(version, analysis) for version, analysis in data_repository.versions_with_latest_analysis(contract)]


def _safe_code(code):
    return ''.join(x for x in code if x.isalnum() or x in '-_')


class ContractService:

    def __init__(self):
        self.contract_repo = ContractRepository()
        self.file_repo = ContractFileRepository()
        self.analysis_repo = AIAnalysisRepository()
        self.finding_repo = RiskFindingRepository()
        self.review_repo = ReviewRepository()
        self.audit_repo = AuditLogRepository()

    def list_all_contracts(self, company=None, query=None, status=None, limit=None, offset=0):
        """Rows for the contract list. With limit, only that page (from offset) and the total that matched."""
        if company:
            contracts = self.contract_repo.get_contracts_by_company(company)
        else:
            contracts = self.contract_repo.get_all_contracts()
        contracts = data_repository.contract_list_rows(contracts, query=query, status=status)
        total = None
        if limit is not None:
            total = contracts.count()
            contracts = contracts[offset:offset + limit]
        contracts = list(contracts)
        data = []
        analyses = data_repository.latest_analyses_by_contract(contracts)
        for c in contracts:
            latest_analysis = analyses.get(c.id)
            data.append(dict(self.contract_summary(c), risk_score=int(latest_analysis.overall_score) if latest_analysis and latest_analysis.overall_score is not None else None, risk_level=latest_analysis.risk_level if latest_analysis else None))
        if limit is None:
            return data
        return {'items': data, 'total': total, 'offset': offset, 'limit': limit}

    @staticmethod
    def contract_summary(c):
        return {'id': c.id, 'contract_code': c.contract_code, 'title': c.title, 'contract_type': c.contract_type, 'start_date': c.start_date.isoformat() if c.start_date else None, 'end_date': c.end_date.isoformat() if c.end_date else None, 'contract_value': float(c.contract_value) if c.contract_value is not None else None, 'status': c.status, 'created_at': c.created_at.isoformat()}

    def get_contract_details(self, contract_id, version_id=None):
        """Everything the detail page shows for one version (the latest when version_id is not given).

        None when the contract does not exist or version_id is not one of its versions: the caller answers 404 rather
        than silently showing another version. Reading the page never writes anything."""
        from contract.approvals.services.workflow_service import WorkflowService
        c = self.contract_repo.get_contract(contract_id)
        if not c:
            return None
        if version_id not in (None, ''):
            version = data_repository.version_of(c, version_id)
            if version is None:
                return None
        else:
            version = c.latest_version
        from contract.contracts.repositories import party_tag_repository
        from contract.contracts.services.party_tag_service import serialize_party
        # Parties are the ones the user entered; the AI does not guess them.
        parties_data = [dict(serialize_party(party), label=party.party_type, name=party.party_name)
                        for party in party_tag_repository.parties_of(c)]
        chosen_tags = {tag.pk for tag in party_tag_repository.tags_of(c)}
        tags_data = [dict(id=tag.pk, name=tag.tag_name, selected=tag.pk in chosen_tags) for tag in party_tag_repository.all_tags()]
        from contract.contracts.services.legal_mark_service import STATUSES, serialize
        from ai.legal_ai.repositories.knowledge_repository import legal_document_for
        legal_data = serialize(legal_document_for(c))
        details = {'id': c.id, 'contract_code': c.contract_code, 'title': c.title, 'contract_type': c.contract_type,
                   'start_date': c.start_date.isoformat() if c.start_date else None,
                   'end_date': c.end_date.isoformat() if c.end_date else None,
                   'contract_value': float(c.contract_value) if c.contract_value is not None else None, 'status': c.status,
                   'parties': parties_data, 'tags': tags_data, 'legal': legal_data, 'legal_statuses': STATUSES,
                   'file_path': None, 'raw_content': '', 'clauses': [], 'analysis': None, 'findings': [], 'reviews': [],
                   'active_version_id': None, 'active_version_number': None, 'active_version_change_summary': None,
                   'versions': versions_list(c), 'ai_summary': None, 'has_workflow': False, 'workflow_id': None}
        if version is None:  # a contract that never got a version (older data): the page shows it empty
            return details
        latest_file = data_repository.first_files_for_get_contract_details(version)
        # Only a real AI run is an analysis: opening the page records nothing.
        latest_analysis = data_repository.first_ai_analyses_for_get_contract_details(version)
        if latest_analysis is not None and latest_analysis.model_name == 'N/A':
            latest_analysis = None
        source_pages = data_repository.clause_source_pages_for_get_contract_details(version)
        clauses_data = [{'id': cl.id, 'title': cl.clause_title, 'clause_type': cl.clause_type, 'content': cl.clause_content,
                         'entities': [{'id': ee.id, 'entity_type': ee.entity_type, 'entity_value': ee.entity_value,
                                       'confidence_score': float(ee.confidence_score)} for ee in cl.ai_extract_entities.all()],
                         'source_pages': source_pages.get(cl.clause_title, [])}
                        for cl in data_repository.clauses_with_entities(version)]
        reviews_data = [{'id': r.id, 'comment': r.note, 'final_risk_level': r.decision,
                         'reviewer': r.user.username if r.user else 'Legal Expert',
                         'reviewed_at': r.reviewed_at.isoformat() if r.reviewed_at else ''}
                        for r in data_repository.reviews_of_version(version)]
        analysis_data = None
        findings_data = []
        if latest_analysis:
            analysis_data = {'id': latest_analysis.id, 'model_name': latest_analysis.model_name, 'overall_score': float(latest_analysis.overall_score), 'risk_level': latest_analysis.risk_level, 'summary': latest_analysis.summary, 'created_at': latest_analysis.created_at.isoformat()}
            findings_data = [{'id': f.id, 'clause_id': f.clause.id if f.clause else None, 'clause_title': f.clause.clause_title if f.clause else '', 'risk_name': f.rule.rule_name, 'risk_level': f.risk_level, 'explanation': f.explanation, 'recommendation': f.recommendation, 'disadvantaged_party': f.disadvantaged_party, 'is_suggestion': f.is_suggestion} for f in data_repository.findings_of_analysis(latest_analysis)]
            # Legal risks first, then the drafting suggestions under their own heading.
            findings_data.sort(key=lambda f: f['is_suggestion'])
        from contract.core.services.stored_file_service import document_text
        raw_content = '\n\n'.join(ctx.content for ctx in data_repository.order_by_contexts_for_get_contract_details(version))
        if not raw_content:
            raw_content = document_text(latest_file)
        if not raw_content and clauses_data:
            raw_content = '\n\n'.join([f"--- {cl['title']} ---\n{cl['content']}" for cl in clauses_data])
        summary_obj = data_repository.first_contract_summary_for_get_contract_details(version)
        summary_data = {'id': summary_obj.id, 'summary': summary_obj.summary, 'model_id': summary_obj.model_id, 'created_at': summary_obj.created_at.isoformat(), 'updated_at': summary_obj.updated_at.isoformat()} if summary_obj else None
        has_workflow = False
        workflow_id = None
        try:
            wf_status = WorkflowService().get_workflow_status(c.id, version_id=version.id)
            if wf_status and wf_status.get('workflow_id'):
                has_workflow = True
                workflow_id = wf_status.get('workflow_id')
        except Exception as error:
            # The page still opens without the workflow service; the log says why the approval button is missing.
            logger.warning('Workflow status of contract %s unavailable: %s', c.id, error)
        return dict(details, file_path=f'/api/contracts/{c.id}/download-pdf/?version_id={version.id}', raw_content=raw_content,
                    clauses=clauses_data, analysis=analysis_data, findings=findings_data, reviews=reviews_data,
                    active_version_id=version.id, active_version_number=version.version_number,
                    active_version_change_summary=version.change_summary, ai_summary=summary_data,
                    has_workflow=has_workflow, workflow_id=workflow_id)

    def create_and_analyze_contract(self, code, title, contract_type, start_date, end_date, contract_value, file_obj=None, raw_content=None, company=None, summarize=None, after_create=None):
        """Create the contract, its first version and its stored document together, or none of them.

        after_create(contract) runs in the same transaction (the caller's audit row, the legal mark), so a failure
        there also leaves no contract behind; the stored file is removed whenever the rows are rolled back."""
        if not code or not title:
            raise ValueError('Contract code and title are required.')
        stored = _store_document(file_obj, raw_content, f'contract_{_safe_code(code)}.txt')
        try:
            with transaction.atomic():
                contract = self.contract_repo.create_contract(code=code, title=title, contract_type=contract_type, start_date=start_date, end_date=end_date, contract_value=contract_value, status='DRAFT', company=company)
                version = data_repository.create_contract_version_for_create_and_analyze_contract(contract)
                _attach_document(version, stored, summarize)
                if after_create:
                    after_create(contract)
        except BaseException:
            _discard_stored(stored)
            raise
        return contract

    def create_new_version(self, contract_id, file_obj=None, raw_content=None, change_summary='', summarize=None, after_create=None):
        """Add the next version with its stored document. The contract row is locked while the number is chosen, so
        two uploads at once become v2 and v3 instead of two v2s."""
        if not self.contract_repo.get_contract(contract_id):
            raise ValueError('Contract not found.')
        stored = None
        try:
            with transaction.atomic():
                contract = self.contract_repo.lock_contract(contract_id)
                if not contract:  # deleted in between
                    raise ValueError('Contract not found.')
                next_num = data_repository.next_version_number(contract)
                stored = _store_document(file_obj, raw_content, f'contract_{_safe_code(contract.contract_code)}_v{next_num}.txt')
                version = data_repository.create_contract_version_for_create_new_version(change_summary, contract, next_num)
                _attach_document(version, stored, summarize)
                contract.status = 'DRAFT'
                data_repository.save_contract_for_create_new_version(contract)
                if after_create:
                    after_create(version)
        except BaseException:
            _discard_stored(stored)
            raise
        return version

    def analyze_contract(self, contract_id, version_id=None, user=None, progress=None):
        contract = self.contract_repo.get_contract(contract_id)
        if not contract:
            raise ValueError('Contract not found.')
        if user is None:
            raise ValueError('Risk analysis needs the account whose legal library it searches.')
        contract.status = 'ANALYZING'
        data_repository.save_contract_for_create_new_version(contract)
        from contract.contracts.models import ContractVersion
        try:
            if version_id:
                try:
                    version = data_repository.get_versions_for_analyze_contract(contract, version_id)
                except ContractVersion.DoesNotExist:
                    raise ValueError('Version not found.')
            else:
                version = contract.latest_version
                if not version:
                    version = data_repository.create_contract_version_for_create_and_analyze_contract(contract)
            self._run_ai_analysis_via_api(contract, version, user, progress)
        except Exception:
            # Whatever stops the analysis (no clauses, extraction or model failure), the contract must not stay
            # marked as being analysed.
            contract.status = 'DRAFT'
            data_repository.save_contract_for_create_new_version(contract)
            raise
        return contract

    def submit_expert_review(self, analysis_id, comment, final_risk_level, user):
        """One review of a whole AI analysis by the signed-in user. Only a low-risk verdict approves the contract;
        a medium or high one asks for changes."""
        analysis = self.analysis_repo.get_analysis_by_id(analysis_id)
        if not analysis:
            raise ValueError('Analysis not found.')
        if final_risk_level not in ['LOW', 'MEDIUM', 'HIGH']:
            raise ValueError('Invalid risk level.')
        review = self.review_repo.create_review(analysis, user, comment, final_risk_level)
        contract = analysis.version.contract
        contract.status = 'APPROVED' if final_risk_level == 'LOW' else 'ANALYZED'
        data_repository.save_contract_for_create_new_version(contract)
        self.audit_repo.log_action(user, 'REVIEW_SUBMITTED', 'Review', review.id)
        return review

    def extract_clauses_from_a3(self, version):
        """
        Delegates document processing, text extraction, page saving, and clause splitting
        to the unified ClauseExtractService.
        """
        from ai.ai_extract.services import ClauseExtractService
        extractor = ClauseExtractService()
        extractor.extract_version(version, re_extract=True)

    def _run_ai_analysis_via_api(self, contract, version, user=None, progress=None):
        from django.conf import settings
        if not data_repository.exists_ai_extract_clauses_for_run_ai_analysis_via_api(version):
            self.extract_clauses_from_a3(version)
        clauses = list(data_repository.all_ai_extract_clauses_for_get_contract_details(version))
        if not clauses:
            raise ValueError('No clauses found in contract to analyze.')
        from django.db import connection, transaction
        from ai.ai_extract.services.contract_pipeline_service import QwenGatewayError
        from ai.legal_ai.services.risk_review_service import RiskReviewUnavailable
        from ai.legal_ai.services.clause_risk_service import review_version
        from ai.legal_ai.services.errors import KnowledgeError
        try:
            # Clause by clause against the stored law, then the contract as a whole.
            result = review_version(version, user, progress)
        except (RiskReviewUnavailable, QwenGatewayError, KnowledgeError, ValueError) as e:
            # The model call can outlive a pooled database connection; analyze_contract puts the status back.
            connection.close()
            logger.warning('Risk analysis failed: %s', type(e).__name__)
            if isinstance(e, RiskReviewUnavailable):
                raise RuntimeError(str(e))
            if isinstance(e, KnowledgeError):
                raise RuntimeError('Chưa tìm được văn bản pháp luật để đối chiếu: ' + str(e))
            raise RuntimeError('Qwen chưa phân tích được hợp đồng. Hãy kiểm tra máy chủ Qwen rồi thử lại.')
        connection.close()
        overall_score = Decimal(str(result.get('overall_score', 0)))
        summary = result.get('summary', 'Analysis completed.')
        by_title = {(cl.clause_title or '').strip(): cl for cl in clauses}
        # Earlier results stay until the complete new analysis can replace them.
        with transaction.atomic():
            data_repository.delete_ai_analyses_for_analyze_contract(version)
            analysis = self.analysis_repo.create_analysis(contract_or_version=version, model_name=getattr(settings, 'QWEN_MODEL_ID', 'Qwen'), overall_score=overall_score, summary=summary)
            if result.get('risk_level') and analysis.risk_level != result['risk_level']:
                analysis.risk_level = result['risk_level']
                self.analysis_repo.save(analysis, ['risk_level'])
            for finding in result.get('findings', []):
                risk_level = finding.get('risk_level', 'MEDIUM')
                # Each finding is filed under a risk rule the administrator set, or the catch-all OTHER rule; the
                # model's own label for the risk opens the explanation.
                from ai.analysis.repositories.risk_rule_repository import rule_for
                risk = rule_for(finding.get('rule_code'))
                if finding.get('risk_category') and finding.get('risk_category') != risk.rule_name:
                    finding = dict(finding, explanation=f"{finding['risk_category']}: {finding.get('explanation', '')}")
                # A finding without a known clause is still a finding the reviewer must see.
                self.finding_repo.create_finding(analysis=analysis, clause=by_title.get((finding.get('clause_title') or '').strip()), risk=risk, risk_level=risk_level, explanation=finding.get('explanation', ''), recommendation=finding.get('recommendation', ''), disadvantaged_party=(finding.get('disadvantaged_party') or '')[:255] or None, is_suggestion=bool(finding.get('suggestion')))
        contract.status = 'ANALYZED'
        data_repository.save_contract_for_create_new_version(contract)
