from contracts.repositories import contract_data_repository as data_repository
import logging
import os
from decimal import Decimal
from django.core.files.base import ContentFile
from contracts.repositories import ContractRepository, ContractFileRepository, ClauseRepository, RiskRepository, AIAnalysisRepository, RiskFindingRepository, ReviewRepository, AuditLogRepository

logger = logging.getLogger(__name__)


class ContractService:

    def __init__(self):
        self.contract_repo = ContractRepository()
        self.file_repo = ContractFileRepository()
        self.clause_repo = ClauseRepository()
        self.risk_repo = RiskRepository()
        self.analysis_repo = AIAnalysisRepository()
        self.finding_repo = RiskFindingRepository()
        self.review_repo = ReviewRepository()
        self.audit_repo = AuditLogRepository()

    def list_all_contracts(self, company=None):
        if company:
            contracts = self.contract_repo.get_contracts_by_company(company)
        else:
            contracts = self.contract_repo.get_all_contracts()
        data = []
        for c in contracts:
            latest_analysis = data_repository.first_ai_analyses_for_list_all_contracts(c)
            data.append({'id': c.id, 'contract_code': c.contract_code, 'title': c.title, 'contract_type': c.contract_type, 'start_date': c.start_date.isoformat() if c.start_date else None, 'end_date': c.end_date.isoformat() if c.end_date else None, 'contract_value': float(c.contract_value) if c.contract_value else None, 'status': c.status, 'risk_score': int(latest_analysis.overall_score) if latest_analysis and latest_analysis.overall_score is not None else None, 'risk_level': latest_analysis.risk_level if latest_analysis else None, 'created_at': c.created_at.isoformat()})
        return data

    def get_contract_details(self, contract_id, version_id=None):
        from django.conf import settings
        from contracts.services.workflow_service import WorkflowService
        c = self.contract_repo.get_contract_by_id(contract_id)
        if not c:
            return None
        if version_id:
            try:
                version = data_repository.get_versions_for_get_contract_details(c, version_id)
            except Exception:
                version = c.latest_version
        else:
            version = c.latest_version
        if not version:
            version = data_repository.create_contract_version_for_get_contract_details(c)
        latest_file = data_repository.first_files_for_get_contract_details(version)
        # Only a real AI run is an analysis: opening the page records nothing.
        latest_analysis = data_repository.first_ai_analyses_for_get_contract_details(version)
        if latest_analysis is not None and latest_analysis.model_name == 'N/A':
            latest_analysis = None
        clauses_data = []
        from contracts.repositories import party_tag_repository
        from contracts.services.party_tag_service import serialize_party
        # Parties are the ones the user entered; the AI does not guess them.
        parties_data = [dict(serialize_party(party), label=party.party_type, name=party.party_name)
                        for party in party_tag_repository.parties_of(c)]
        chosen_tags = {tag.pk for tag in party_tag_repository.tags_of(c)}
        tags_data = [dict(id=tag.pk, name=tag.tag_name, selected=tag.pk in chosen_tags) for tag in party_tag_repository.all_tags()]
        source_pages = data_repository.clause_source_pages_for_get_contract_details(version)
        for cl in data_repository.all_ai_extract_clauses_for_get_contract_details(version):
            entities_list = [{'id': ee.id, 'entity_type': ee.entity_type, 'entity_value': ee.entity_value, 'confidence_score': float(ee.confidence_score)} for ee in data_repository.all_ai_extract_entities_for_get_contract_details(cl)]
            clauses_data.append({'id': cl.id, 'title': cl.clause_title, 'clause_type': cl.clause_type, 'content': cl.clause_content, 'entities': entities_list, 'source_pages': source_pages.get(cl.clause_title, [])})
        reviews_data = []
        for analysis in data_repository.all_ai_analyses_for_get_contract_details(version):
            for r in data_repository.all_reviews_for_get_contract_details(analysis):
                reviews_data.append({'id': r.id, 'comment': r.note, 'final_risk_level': r.decision, 'reviewer': r.user.username if r.user else 'Legal Expert', 'reviewed_at': r.reviewed_at.isoformat() if r.reviewed_at else ''})
        analysis_data = None
        findings_data = []
        if latest_analysis:
            analysis_data = {'id': latest_analysis.id, 'model_name': latest_analysis.model_name, 'overall_score': float(latest_analysis.overall_score), 'risk_level': latest_analysis.risk_level, 'summary': latest_analysis.summary, 'created_at': latest_analysis.created_at.isoformat()}
            findings_data = [{'id': f.id, 'clause_id': f.clause.id if f.clause else None, 'clause_title': f.clause.clause_title if f.clause else '', 'risk_name': f.rule.rule_name, 'risk_level': f.risk_level, 'explanation': f.explanation, 'recommendation': f.recommendation, 'disadvantaged_party': f.disadvantaged_party, 'is_suggestion': f.is_suggestion} for f in data_repository.all_findings_for_get_contract_details(latest_analysis)]
            # Legal risks first, then the drafting suggestions under their own heading.
            findings_data.sort(key=lambda f: f['is_suggestion'])
        raw_content = ''
        contexts = data_repository.order_by_contexts_for_get_contract_details(version)
        if contexts.exists():
            raw_content = '\n\n'.join([ctx.content for ctx in contexts])
        if not raw_content and latest_file and latest_file.file_path:
            media_prefix = settings.MEDIA_URL
            import urllib.parse
            rel_path = urllib.parse.unquote(latest_file.file_path)
            if rel_path.startswith(media_prefix):
                rel_path = rel_path[len(media_prefix):]
            full_path = os.path.join(settings.MEDIA_ROOT, rel_path.replace('/', os.sep))
            if os.path.exists(full_path):
                try:
                    ext = os.path.splitext(latest_file.file_name)[1].lower() if latest_file.file_name else ''
                    if ext == '.txt':
                        from contracts.services.document_encryption_service import decrypt_pdf
                        with open(full_path, 'rb') as f:
                            encrypted_bytes = f.read()
                        decrypted_bytes = decrypt_pdf(encrypted_bytes)
                        raw_content = decrypted_bytes.decode('utf-8', errors='ignore')
                    elif ext == '.pdf':
                        from contracts.services.document_encryption_service import decrypt_pdf
                        import fitz
                        with open(full_path, 'rb') as f:
                            encrypted_bytes = f.read()
                        decrypted_bytes = decrypt_pdf(encrypted_bytes)
                        doc = fitz.open(stream=decrypted_bytes, filetype='pdf')
                        text_list = []
                        for page in doc:
                            text_list.append(page.get_text())
                        raw_content = '\n\n'.join(text_list)
                        doc.close()
                except Exception:
                    pass
        if not raw_content and clauses_data:
            raw_content = '\n\n'.join([f"--- {cl['title']} ---\n{cl['content']}" for cl in clauses_data])
        versions_list = []
        for v in data_repository.order_by_versions_for_get_contract_details(c):
            v_analysis = data_repository.latest_analysis_for_listed_version(v)
            versions_list.append({'id': v.id, 'version_number': v.version_number, 'change_summary': v.change_summary or 'Initial version', 'created_at': v.created_at.isoformat(), 'overall_score': float(v_analysis.overall_score) if v_analysis and v_analysis.overall_score is not None else None, 'risk_level': v_analysis.risk_level if v_analysis else 'NONE'})
        summary_obj = data_repository.first_contract_summary_for_get_contract_details(version)
        summary_data = {'id': summary_obj.id, 'summary': summary_obj.summary, 'model_id': summary_obj.model_id, 'created_at': summary_obj.created_at.isoformat(), 'updated_at': summary_obj.updated_at.isoformat()} if summary_obj else None
        has_workflow = False
        workflow_id = None
        try:
            wf_status = WorkflowService().get_workflow_status(c.id, version_id=version.id)
            if wf_status and wf_status.get('workflow_id'):
                has_workflow = True
                workflow_id = wf_status.get('workflow_id')
        except Exception:
            pass
        return {'id': c.id, 'contract_code': c.contract_code, 'title': c.title, 'contract_type': c.contract_type, 'start_date': c.start_date.isoformat() if c.start_date else None, 'end_date': c.end_date.isoformat() if c.end_date else None, 'contract_value': float(c.contract_value) if c.contract_value else None, 'status': c.status, 'file_path': f'/api/contracts/{c.id}/download-pdf/?version_id={version.id}', 'raw_content': raw_content, 'clauses': clauses_data, 'parties': parties_data, 'tags': tags_data, 'analysis': analysis_data, 'findings': findings_data, 'reviews': reviews_data, 'active_version_id': version.id, 'active_version_number': version.version_number, 'active_version_change_summary': version.change_summary, 'versions': versions_list, 'ai_summary': summary_data, 'has_workflow': has_workflow, 'workflow_id': workflow_id}

    def create_and_analyze_contract(self, code, title, contract_type, start_date, end_date, contract_value, file_obj=None, raw_content=None, company=None, summarize=None):
        if not code or not title:
            raise ValueError('Contract code and title are required.')
        contract = self.contract_repo.create_contract(code=code, title=title, contract_type=contract_type, start_date=start_date, end_date=end_date, contract_value=contract_value, status='DRAFT', company=company)
        version = data_repository.create_contract_version_for_create_and_analyze_contract(contract)
        saved_file_path = None
        from contracts.services.document_encryption_service import encrypt_pdf
        if file_obj:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            file_data = file_obj.read()
            encrypted_data = encrypt_pdf(file_data)
            filename = fs.save(f'contracts/{file_obj.name}', ContentFile(encrypted_data))
            saved_file_path = fs.url(filename)
        elif raw_content:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            safe_code = ''.join((x for x in code if x.isalnum() or x in '-_'))
            encrypted_data = encrypt_pdf(raw_content.encode('utf-8'))
            filename = fs.save(f'contracts/contract_{safe_code}.txt', ContentFile(encrypted_data))
            saved_file_path = fs.url(filename)
        if saved_file_path:
            self.file_repo.create_file_record(version, saved_file_path)
            from ai_extract.services.summary_service import schedule_auto_summary
            schedule_auto_summary(version, summarize)
        return contract

    def create_new_version(self, contract_id, file_obj=None, raw_content=None, change_summary='', summarize=None):
        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError('Contract not found.')
        latest = contract.latest_version
        next_num = latest.version_number + 1 if latest else 1
        version = data_repository.create_contract_version_for_create_new_version(change_summary, contract, next_num)
        saved_file_path = None
        from contracts.services.document_encryption_service import encrypt_pdf
        if file_obj:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            file_data = file_obj.read()
            encrypted_data = encrypt_pdf(file_data)
            filename = fs.save(f'contracts/{file_obj.name}', ContentFile(encrypted_data))
            saved_file_path = fs.url(filename)
        elif raw_content:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            safe_code = ''.join((x for x in contract.contract_code if x.isalnum() or x in '-_'))
            encrypted_data = encrypt_pdf(raw_content.encode('utf-8'))
            filename = fs.save(f'contracts/contract_{safe_code}_v{next_num}.txt', ContentFile(encrypted_data))
            saved_file_path = fs.url(filename)
        if saved_file_path:
            self.file_repo.create_file_record(version, saved_file_path)
            from ai_extract.services.summary_service import schedule_auto_summary
            schedule_auto_summary(version, summarize)
        contract.status = 'DRAFT'
        data_repository.save_contract_for_create_new_version(contract)
        return version

    def analyze_contract(self, contract_id, version_id=None, user=None, progress=None):
        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError('Contract not found.')
        contract.status = 'ANALYZING'
        data_repository.save_contract_for_create_new_version(contract)
        from contracts.models import ContractVersion
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
        return contract

    def manual_extract_contract(self, contract_id, version_id=None):
        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError('Contract not found.')
        from contracts.models import ContractVersion
        if version_id:
            try:
                version = data_repository.get_versions_for_analyze_contract(contract, version_id)
            except ContractVersion.DoesNotExist:
                raise ValueError('Version not found.')
        else:
            version = contract.latest_version
            if not version:
                version = data_repository.create_contract_version_for_create_and_analyze_contract(contract)
        self.extract_clauses_from_a3(version)
        contract.status = 'DRAFT'
        data_repository.save_contract_for_create_new_version(contract)
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
        from ai_extract.services import ClauseExtractService
        extractor = ClauseExtractService()
        extractor.extract_version(version, re_extract=True)

    def _run_ai_analysis_via_api(self, contract, version, user=None, progress=None):
        from django.conf import settings
        from decimal import Decimal
        if not data_repository.exists_ai_extract_clauses_for_run_ai_analysis_via_api(version):
            self.extract_clauses_from_a3(version)
        clauses = list(data_repository.all_ai_extract_clauses_for_get_contract_details(version))
        if not clauses:
            raise ValueError('No clauses found in contract to analyze.')
        from django.db import connection, transaction
        from ai_extract.services.contract_pipeline_service import QwenGatewayError
        from NewIdea.services.risk_review_service import RiskReviewUnavailable
        from NewIdea.services.clause_risk_service import review_version
        from NewIdea.services.errors import KnowledgeError
        if user is None:
            raise ValueError('Risk analysis needs the account whose legal library it searches.')
        try:
            # Clause by clause against the stored law, then the contract as a whole.
            result = review_version(version, user, progress)
        except (RiskReviewUnavailable, QwenGatewayError, KnowledgeError, ValueError) as e:
            # The model call can outlive a pooled database connection.
            connection.close()
            contract.status = 'DRAFT'
            data_repository.save_contract_for_create_new_version(contract)
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
                analysis.save(update_fields=['risk_level'])
            for finding in result.get('findings', []):
                risk_level = finding.get('risk_level', 'MEDIUM')
                # Each finding is filed under a risk rule the administrator set, or the catch-all OTHER rule; the
                # model's own label for the risk opens the explanation.
                from contracts.repositories.risk_rule_repository import rule_for
                risk = rule_for(finding.get('rule_code'))
                if finding.get('risk_category') and finding.get('risk_category') != risk.rule_name:
                    finding = dict(finding, explanation=f"{finding['risk_category']}: {finding.get('explanation', '')}")
                # A finding without a known clause is still a finding the reviewer must see.
                self.finding_repo.create_finding(analysis=analysis, clause=by_title.get((finding.get('clause_title') or '').strip()), risk=risk, risk_level=risk_level, explanation=finding.get('explanation', ''), recommendation=finding.get('recommendation', ''), disadvantaged_party=(finding.get('disadvantaged_party') or '')[:255] or None, is_suggestion=bool(finding.get('suggestion')))
        contract.status = 'ANALYZED'
        data_repository.save_contract_for_create_new_version(contract)
