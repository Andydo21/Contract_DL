import os
import random
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from .repositories import (
    ContractRepository, ContractFileRepository, ClauseRepository,
    RiskRepository, AIAnalysisRepository, RiskFindingRepository,
    ReviewRepository, AuditLogRepository
)
from document_processor.services.document_service import DocumentService

User = get_user_model()

class RiskService:
    def __init__(self):
        self.risk_repo = RiskRepository()
        self.audit_repo = AuditLogRepository()
        
    def list_all_risks(self):
        risks = self.risk_repo.get_all_risks()
        result = []
        for r in risks:
            # Query related contracts with findings of this risk category
            from .models import RiskFinding, Contract
            contract_ids = RiskFinding.objects.filter(rule=r).values_list('analysis__version__contract_id', flat=True).distinct()
            contracts = Contract.objects.filter(id__in=contract_ids).only('id', 'title', 'contract_code')
            
            contracts_list = [
                {
                    'id': c.id,
                    'title': c.title,
                    'contract_code': c.contract_code
                }
                for c in contracts
            ]
            
            result.append({
                'id': r.id,
                'risk_name': r.rule_name,
                'risk_code': r.rule_code,
                'description': r.description,
                'severity_level': r.severity,
                'contracts': contracts_list
            })
        return result
        
    def create_new_risk(self, name, description, severity_level):
        if not name:
            raise ValueError("Risk name is required.")
        if severity_level not in ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']:
            raise ValueError("Invalid severity level. Must be LOW, MEDIUM, HIGH, or CRITICAL.")
            
        risk = self.risk_repo.create_risk(name, description, severity_level)
        
        # Log Audit Trail
        admin_user = User.objects.filter(is_superuser=True).first()
        self.audit_repo.log_action(admin_user, "RISK_CREATED", "Risk", risk.id)
        
        return risk


class AnalysisHistoryService:
    def __init__(self):
        self.analysis_repo = AIAnalysisRepository()

    def list_all_analyses(self, company=None):
        if company:
            from .models import AIAnalysis
            analyses = AIAnalysis.objects.filter(version__contract__company=company).order_by('-created_at')
        else:
            analyses = self.analysis_repo.get_all_analyses()
        result = []
        for a in analyses:
            # Deduplicate findings by risk name
            risk_names_seen = set()
            findings = []
            for f in a.findings.all():
                if f.rule.rule_name not in risk_names_seen:
                    risk_names_seen.add(f.rule.rule_name)
                    findings.append({
                        'risk_name': f.rule.rule_name,
                        'risk_level': f.risk_level,
                        'severity_level': f.rule.severity,
                    })

            score = int(a.overall_score) if a.overall_score is not None else 0
            if score >= 80:
                risk_label = 'HIGH'
            elif score >= 50:
                risk_label = 'MEDIUM'
            else:
                risk_label = 'LOW'

            result.append({
                'id': a.id,
                'contract_id': a.version.contract.id,
                'contract_code': a.version.contract.contract_code,
                'contract_title': a.version.contract.title,
                'contract_status': a.version.contract.status,
                'model_name': a.model_name,
                'overall_score': score,
                'risk_label': risk_label,
                'summary': a.summary,
                'findings_count': a.findings.count(),
                'findings_preview': findings[:3],
                'created_at': a.created_at.strftime('%Y-%m-%d %H:%M'),
            })
        return result


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
            latest_analysis = c.ai_analyses.first()
            data.append({
                'id': c.id,
                'contract_code': c.contract_code,
                'title': c.title,
                'contract_type': c.contract_type,
                'start_date': c.start_date.isoformat() if c.start_date else None,
                'end_date': c.end_date.isoformat() if c.end_date else None,
                'contract_value': float(c.contract_value) if c.contract_value else None,
                'status': c.status,
                'risk_score': int(latest_analysis.overall_score) if (latest_analysis and latest_analysis.overall_score is not None) else None,
                'created_at': c.created_at.isoformat()
            })
        return data

    def get_contract_details(self, contract_id, version_id=None):
        from django.conf import settings
        c = self.contract_repo.get_contract_by_id(contract_id)
        if not c:
            return None
            
        from .models import ContractVersion
        if version_id:
            try:
                version = c.versions.get(id=version_id)
            except Exception:
                version = c.latest_version
        else:
            version = c.latest_version
            
        if not version:
            version = ContractVersion.objects.create(contract=c, version_number=1)
            
        latest_file = version.files.first()
        latest_analysis = version.ai_analyses.first()
        
        clauses_data = []
        for cl in version.ai_extract_clauses.all():
            entities_list = [
                {
                    'id': ee.id,
                    'entity_type': ee.entity_type,
                    'entity_value': ee.entity_value,
                    'confidence_score': float(ee.confidence_score)
                }
                for ee in cl.ai_extract_entities.all()
            ]
            clauses_data.append({
                'id': cl.id,
                'title': cl.clause_title,
                'content': cl.clause_content,
                'entities': entities_list
            })
        
        reviews_data = []
        if latest_analysis:
            reviews_data = [
                {
                    'id': r.id,
                    'comment': r.note,
                    'final_risk_level': r.decision,
                    'reviewer': r.user.username,
                    'reviewed_at': r.reviewed_at.isoformat()
                }
                for r in latest_analysis.reviews.all()
            ]
        
        analysis_data = None
        findings_data = []
        
        if latest_analysis:
            analysis_data = {
                'id': latest_analysis.id,
                'model_name': latest_analysis.model_name,
                'overall_score': float(latest_analysis.overall_score),
                'summary': latest_analysis.summary,
                'created_at': latest_analysis.created_at.isoformat()
            }
            findings_data = [
                {
                    'id': f.id,
                    'clause_id': f.clause.id if f.clause else None,
                    'clause_title': f.clause.clause_title if f.clause else "",
                    'risk_name': f.rule.rule_name,
                    'risk_level': f.risk_level,
                    'explanation': f.explanation,
                    'recommendation': f.recommendation,
                    'disadvantaged_party': f.disadvantaged_party
                }
                for f in latest_analysis.findings.all()
            ]
            
        # Read original text if available (reconstructing from ContractContext first)
        raw_content = ""
        from .models import ContractContext
        contexts = version.contexts.filter(context_type='raw_text').order_by('id')
        if contexts.exists():
            raw_content = "\n\n".join([ctx.content for ctx in contexts])
            
        if not raw_content and latest_file and latest_file.file_path:
            media_prefix = settings.MEDIA_URL
            import urllib.parse
            rel_path = urllib.parse.unquote(latest_file.file_path)
            if rel_path.startswith(media_prefix):
                rel_path = rel_path[len(media_prefix):]
            
            full_path = os.path.join(settings.MEDIA_ROOT, rel_path.replace('/', os.sep))
            if os.path.exists(full_path):
                try:
                    from .crypto_utils import decrypt_pdf
                    with open(full_path, 'rb') as f:
                        encrypted_bytes = f.read()
                    decrypted_bytes = decrypt_pdf(encrypted_bytes)
                    raw_content = decrypted_bytes.decode('utf-8', errors='ignore')
                except Exception:
                    pass
        
        # Fallback to reconstructing from clauses if empty
        if not raw_content and clauses_data:
            raw_content = "\n\n".join([f"--- {cl['title']} ---\n{cl['content']}" for cl in clauses_data])
            
        versions_list = []
        for v in c.versions.all().order_by('-version_number'):
            v_analysis = v.ai_analyses.first()
            versions_list.append({
                'id': v.id,
                'version_number': v.version_number,
                'change_summary': v.change_summary or "Initial version",
                'created_at': v.created_at.isoformat(),
                'overall_score': float(v_analysis.overall_score) if (v_analysis and v_analysis.overall_score is not None) else None,
                'risk_level': v_analysis.risk_level if v_analysis else 'NONE',
            })

        # Fetch AI summary if exists for this version
        from ai_extract.models import ContractSummary
        summary_obj = ContractSummary.objects.filter(version=version).first()
        summary_data = {
            'id': summary_obj.id,
            'summary': summary_obj.summary,
            'model_id': summary_obj.model_id,
            'created_at': summary_obj.created_at.isoformat(),
            'updated_at': summary_obj.updated_at.isoformat(),
        } if summary_obj else None
            
        return {
            'id': c.id,
            'contract_code': c.contract_code,
            'title': c.title,
            'contract_type': c.contract_type,
            'start_date': c.start_date.isoformat() if c.start_date else None,
            'end_date': c.end_date.isoformat() if c.end_date else None,
            'contract_value': float(c.contract_value) if c.contract_value else None,
            'status': c.status,
            'file_path': f"/api/contracts/files/{latest_file.id}/download/" if latest_file else None,
            'raw_content': raw_content,
            'clauses': clauses_data,
            'analysis': analysis_data,
            'findings': findings_data,
            'reviews': reviews_data,
            'active_version_id': version.id,
            'active_version_number': version.version_number,
            'active_version_change_summary': version.change_summary,
            'versions': versions_list,
            'ai_summary': summary_data
        }

    def create_and_analyze_contract(self, code, title, contract_type, start_date, end_date, contract_value, file_obj=None, raw_content=None, company=None):
        if not code or not title:
            raise ValueError("Contract code and title are required.")
            
        # Create Contract as DRAFT first, without running AI analysis immediately
        contract = self.contract_repo.create_contract(
            code=code,
            title=title,
            contract_type=contract_type,
            start_date=start_date,
            end_date=end_date,
            contract_value=contract_value,
            status='DRAFT',
            company=company
        )
        
        # Create default version 1
        from .models import ContractVersion
        version = ContractVersion.objects.create(contract=contract, version_number=1, change_summary="Initial version")
        
        # Save Contract File (Encrypted with AES-256)
        saved_file_path = None
        from django.core.files.base import ContentFile
        from .crypto_utils import encrypt_pdf
        
        if file_obj:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            file_data = file_obj.read()
            encrypted_data = encrypt_pdf(file_data)
            filename = fs.save(f"contracts/{file_obj.name}", ContentFile(encrypted_data))
            saved_file_path = fs.url(filename)
        elif raw_content:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            safe_code = "".join(x for x in code if x.isalnum() or x in "-_")
            encrypted_data = encrypt_pdf(raw_content.encode('utf-8'))
            filename = fs.save(f"contracts/contract_{safe_code}.txt", ContentFile(encrypted_data))
            saved_file_path = fs.url(filename)
            
        if saved_file_path:
            self.file_repo.create_file_record(version, saved_file_path)
            
        # Extract and save clauses immediately upon creation
        try:
            self.extract_and_save_clauses_via_processor(version)
        except Exception as e:
            import logging
            logger = logging.getLogger("django")
            logger.warning(f"Failed to auto-extract clauses on creation: {e}")
            
        return contract

    def create_new_version(self, contract_id, file_obj=None, raw_content=None, change_summary=""):
        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError("Contract not found.")
            
        latest = contract.latest_version
        next_num = (latest.version_number + 1) if latest else 1
        
        from .models import ContractVersion
        version = ContractVersion.objects.create(
            contract=contract,
            version_number=next_num,
            change_summary=change_summary
        )
        
        saved_file_path = None
        from django.core.files.base import ContentFile
        from .crypto_utils import encrypt_pdf
        
        if file_obj:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            file_data = file_obj.read()
            encrypted_data = encrypt_pdf(file_data)
            filename = fs.save(f"contracts/{file_obj.name}", ContentFile(encrypted_data))
            saved_file_path = fs.url(filename)
        elif raw_content:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            safe_code = "".join(x for x in contract.contract_code if x.isalnum() or x in "-_")
            encrypted_data = encrypt_pdf(raw_content.encode('utf-8'))
            filename = fs.save(f"contracts/contract_{safe_code}_v{next_num}.txt", ContentFile(encrypted_data))
            saved_file_path = fs.url(filename)
            
        if saved_file_path:
            self.file_repo.create_file_record(version, saved_file_path)
            
        try:
            self.extract_and_save_clauses_via_processor(version)
        except Exception as e:
            import logging
            logger = logging.getLogger("django")
            logger.warning(f"Failed to auto-extract clauses on new version: {e}")
            
        return version

    def analyze_contract(self, contract_id, version_id=None):
        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError("Contract not found.")
            
        contract.status = 'ANALYZING'
        contract.save()
        
        from .models import ContractVersion
        if version_id:
            try:
                version = contract.versions.get(id=version_id)
            except ContractVersion.DoesNotExist:
                raise ValueError("Version not found.")
        else:
            version = contract.latest_version
            if not version:
                version = ContractVersion.objects.create(contract=contract, version_number=1, change_summary="Initial version")
        
        version.ai_extract_clauses.all().delete()
        version.ai_analyses.all().delete()
        
        self._run_ai_analysis_via_api(contract, version)
        
        return contract

    def manual_extract_contract(self, contract_id, version_id=None):
        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError("Contract not found.")
            
        from .models import ContractVersion
        if version_id:
            try:
                version = contract.versions.get(id=version_id)
            except ContractVersion.DoesNotExist:
                raise ValueError("Version not found.")
        else:
            version = contract.latest_version
            if not version:
                version = ContractVersion.objects.create(contract=contract, version_number=1, change_summary="Initial version")
        
        # Clear existing clauses (which will cascade delete local entities)
        from ai_extract.models import Clause
        Clause.objects.filter(version=version).delete()
        
        # Run local rules/document processor clause splitting
        self.extract_and_save_clauses_via_processor(version, force_rule_based=True)
        for cl in Clause.objects.filter(version=version):
            # Extract local heuristic basic entities
            self._extract_and_save_basic_entities(cl)
            
        contract.status = 'DRAFT'
        contract.save()
        return contract

    def submit_expert_review(self, analysis_id, comment, final_risk_level):
        analysis = self.analysis_repo.get_analysis_by_id(analysis_id)
        if not analysis:
            raise ValueError("Analysis not found.")
            
        if final_risk_level not in ['LOW', 'MEDIUM', 'HIGH']:
            raise ValueError("Invalid risk level.")
            
        admin_user = User.objects.filter(is_superuser=True).first()
        
        # Create review
        review = self.review_repo.create_review(analysis, admin_user, comment, final_risk_level)
        
        # Update Contract status
        contract = analysis.version.contract
        contract.status = 'APPROVED'
        contract.save()
        
        # Log Audit
        self.audit_repo.log_action(admin_user, "REVIEW_SUBMITTED", "Review", review.id)
        
        return review

    def push_to_workflow(self, contract_id, version_id=None):
        """Đẩy contract lên workflow-service để tạo quy trình phê duyệt."""
        import requests
        from django.conf import settings

        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError("Contract not found.")

        from .models import ContractVersion
        if version_id:
            try:
                version = contract.versions.get(id=version_id)
            except ContractVersion.DoesNotExist:
                raise ValueError("Version not found.")
        else:
            version = contract.latest_version
            if not version:
                raise ValueError("Contract has no version to push.")

        workflow_url = getattr(settings, 'WORKFLOW_SERVICE_URL', 'http://workflow-service:8000')

        payload = {
            "version_id":    version.id,
            "workflow_name": f"Approval Workflow – {contract.title}",
            "steps": [
                {"step_order": 1, "step_name": "Legal Review"},
                {"step_order": 2, "step_name": "Manager Approval"},
                {"step_order": 3, "step_name": "Sign & Archive"},
            ],
        }

        try:
            resp = requests.post(
                f"{workflow_url}/workflows/",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Workflow service error: {e}")

        # Cập nhật trạng thái contract
        contract.status = 'PENDING_WORKFLOW'
        contract.save()

        admin_user = User.objects.filter(is_superuser=True).first()
        self.audit_repo.log_action(admin_user, "PUSHED_TO_WORKFLOW", "Contract", contract.id)

        return {
            "contract_id":   contract.id,
            "workflow_id":   result.get("workflow_id"),
            "workflow_name": result.get("workflow_name"),
            "status":        result.get("status"),
            "steps":         result.get("steps", []),
        }

    def get_workflow_status(self, contract_id, version_id=None):
        """Lấy trạng thái workflow từ workflow-service."""
        import requests
        from django.conf import settings

        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError("Contract not found.")

        from .models import ContractVersion
        if version_id:
            try:
                version = contract.versions.get(id=version_id)
            except ContractVersion.DoesNotExist:
                raise ValueError("Version not found.")
        else:
            version = contract.latest_version

        workflow_url = getattr(settings, 'WORKFLOW_SERVICE_URL', 'http://workflow-service:8000')

        try:
            resp = requests.get(f"{workflow_url}/workflows/{version.id}/", timeout=10)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Workflow service error: {e}")

    def extract_and_save_clauses_via_processor(self, version, force_rule_based=False):
        """
        Delegates document processing, text extraction, page saving, and clause splitting
        to the unified ClauseExtractService.
        """
        from ai_extract.services import ClauseExtractService
        extractor = ClauseExtractService()
        extractor.extract_version(version, re_extract=True, force_rule_based=force_rule_based)

    def _run_ai_analysis_via_api(self, contract, version):
        import requests
        from django.conf import settings
        from decimal import Decimal
        
        # 1. Run local rules/document processor clause splitting
        self.extract_and_save_clauses_via_processor(version)
        
        # 2. Save clauses and immediately pre-extract basic entities (so they exist in the DB before AI analysis)
        clauses = list(version.ai_extract_clauses.all())
        if not clauses:
            raise ValueError("No clauses found in contract to analyze.")
            
        for cl in clauses:
            self._extract_and_save_basic_entities(cl)
            
        # 3. Retrieve the newly saved ExtractedEntity records to pass in the API payload
        from ai_extract.models import ExtractedEntity
        db_entities = ExtractedEntity.objects.filter(clause__in=clauses)
        
        # Retrieve existing risk rules from the database to guide the prompt
        existing_rules = self.risk_repo.get_all_risks()
        
        payload = {
            "clauses": [
                {"title": cl.clause_title, "content": cl.clause_content}
                for cl in clauses
            ],
            "extracted_entities": [
                {
                    "clause_title": ee.clause.clause_title,
                    "entity_type": ee.entity_type,
                    "entity_value": ee.entity_value,
                    "normalized_value": ee.normalized_value or "",
                    "confidence_score": float(ee.confidence_score)
                }
                for ee in db_entities
            ],
            "risk_rules": [
                {"name": r.rule_name, "description": r.description}
                for r in existing_rules
            ]
        }
        
        try:
            response = requests.post(
                f"{settings.AI_SERVICE_URL}/api/v1/analyze",
                json=payload,
                timeout=600  # LLM generation can take time
            )
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as e:
            from django.db import connection
            connection.close()
            # Revert status to DRAFT so it can be re-run, but keep the extracted clauses
            contract.status = 'DRAFT'
            contract.save()
            raise RuntimeError(f"AI Service communication failed: {e}")
            
        from django.db import connection
        connection.close()
            
        # 4. Create Analysis Object
        overall_score = Decimal(str(result.get("overall_score", 0)))
        summary = result.get("summary", "Analysis completed.")
        
        analysis = self.analysis_repo.create_analysis(
            contract_or_version=version,
            model_name="Qwen2.5-3B-Instruct (Fine-tuned)",
            overall_score=overall_score,
            summary=summary
        )
        
        # 5. Match findings returned by the API to the already saved clauses
        for cl in clauses:
            # Find findings belonging to this clause in the API output
            for finding in result.get("findings", []):
                if finding.get("clause_title") == cl.clause_title:
                    # Get or create Risk category
                    risk_name = finding.get("risk_category", "Rủi ro chung")
                    risk_level = finding.get("risk_level", "MEDIUM")
                    explanation = finding.get("explanation", "")
                    recommendation = finding.get("recommendation", "")
                    disadvantaged = finding.get("disadvantaged_party")
                    
                    risk, _ = self.risk_repo.get_or_create_risk(
                        risk_name,
                        defaults={"description": f"Auto-created category for {risk_name}.", "severity_level": risk_level}
                    )
                    
                    self.finding_repo.create_finding(
                        analysis=analysis,
                        clause=cl,
                        risk=risk,
                        risk_level=risk_level,
                        explanation=explanation,
                        recommendation=recommendation,
                        disadvantaged_party=disadvantaged
                    )
            
            # Find any additional entities returned by the API that were not pre-extracted
            for entity in result.get("entities", []):
                if entity.get("clause_title") == cl.clause_title:
                    ExtractedEntity.objects.get_or_create(
                        clause=cl,
                        entity_type=entity.get("entity_type"),
                        entity_value=entity.get("entity_value"),
                        defaults={
                            "normalized_value": entity.get("normalized_value"),
                            "confidence_score": Decimal(str(entity.get("confidence_score", 1.0)))
                        }
                    )
                    
        # Update status
        contract.status = 'ANALYZED'
        contract.save()

    def _extract_and_save_basic_entities(self, clause):
        from ai_extract.models import ExtractedEntity
        content_lower = clause.clause_content.lower()
        
        # 1. Identify Parties
        party_found = []
        if "bên a" in content_lower:
            party_found.append("Bên A")
        if "bên b" in content_lower:
            party_found.append("Bên B")
        if "landlord" in content_lower or "bên cho thuê" in content_lower:
            party_found.append("Bên cho thuê (Landlord)")
        if "tenant" in content_lower or "bên thuê" in content_lower:
            party_found.append("Bên thuê (Tenant)")
        if "client" in content_lower or "khách hàng" in content_lower:
            party_found.append("Khách hàng (Client)")
        if "consultant" in content_lower or "nhà tư vấn" in content_lower:
            party_found.append("Nhà tư vấn (Consultant)")
        if "developer" in content_lower or "nhà phát triển" in content_lower:
            party_found.append("Nhà phát triển (Developer)")
        if "distributor" in content_lower or "nhà phân phối" in content_lower:
            party_found.append("Nhà phân phối (Distributor)")
        if "techvibe" in content_lower:
            party_found.append("Công ty TechVibe")
        if "devcore" in content_lower:
            party_found.append("Công ty DevCore")
        if "landmark" in content_lower:
            party_found.append("Landmark")
        if "smartacademy" in content_lower:
            party_found.append("SmartAcademy")

        for p in party_found:
            ExtractedEntity.objects.get_or_create(
                clause=clause,
                entity_type="PARTY",
                entity_value=p,
                defaults={"normalized_value": p.upper(), "confidence_score": Decimal("0.95")}
            )

        # 2. Identify Actions
        action_found = []
        if "đơn phương chấm dứt" in content_lower or "unilaterally terminate" in content_lower or "terminate for convenience" in content_lower:
            action_found.append(("Đơn phương chấm dứt hợp đồng", "TERMINATION"))
        if "chậm thanh toán" in content_lower or "chậm trả" in content_lower or "late payment" in content_lower:
            action_found.append(("Chậm thanh toán nghĩa vụ tài chính", "PAYMENT_DEFAULT"))
        if "sở hữu trí tuệ" in content_lower or "quyền tác giả" in content_lower or "intellectual property" in content_lower or "bản quyền" in content_lower:
            action_found.append(("Sở hữu trí tuệ và bản quyền tác giả", "IP_OWNERSHIP"))
        if "độc quyền" in content_lower or "exclusivity" in content_lower or "exclusive" in content_lower:
            action_found.append(("Cam kết độc quyền thương mại", "EXCLUSIVITY"))
        if "phạt vi phạm" in content_lower or "penalty" in content_lower or "forfeit" in content_lower or "tiền cọc" in content_lower:
            action_found.append(("Áp dụng chế tài phạt vi phạm/tịch thu cọc", "PENALTY"))
        if "tranh chấp" in content_lower or "dispute" in content_lower or "arbitration" in content_lower or "tòa án" in content_lower or "trọng tài" in content_lower:
            action_found.append(("Giải quyết tranh chấp phát sinh", "DISPUTE_RESOLUTION"))

        for act_val, act_norm in action_found:
            ExtractedEntity.objects.get_or_create(
                clause=clause,
                entity_type="ACTION",
                entity_value=act_val,
                defaults={"normalized_value": act_norm, "confidence_score": Decimal("0.90")}
            )
