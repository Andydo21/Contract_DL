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
            contract_ids = RiskFinding.objects.filter(risk=r).values_list('analysis__contract_id', flat=True).distinct()
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
                'risk_name': r.risk_name,
                'description': r.description,
                'severity_level': r.severity_level,
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

    def list_all_analyses(self):
        analyses = self.analysis_repo.get_all_analyses()
        result = []
        for a in analyses:
            # Deduplicate findings by risk name
            risk_names_seen = set()
            findings = []
            for f in a.findings.all():
                if f.risk.risk_name not in risk_names_seen:
                    risk_names_seen.add(f.risk.risk_name)
                    findings.append({
                        'risk_name': f.risk.risk_name,
                        'risk_level': f.risk_level,
                        'severity_level': f.risk.severity_level,
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
                'contract_id': a.contract.id,
                'contract_code': a.contract.contract_code,
                'contract_title': a.contract.title,
                'contract_status': a.contract.status,
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

    def list_all_contracts(self):
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

    def get_contract_details(self, contract_id):
        from django.conf import settings
        c = self.contract_repo.get_contract_by_id(contract_id)
        if not c:
            return None
            
        latest_file = c.files.first()
        latest_analysis = c.ai_analyses.first()
        
        clauses_data = [
            {'id': cl.id, 'title': cl.clause_title, 'content': cl.clause_content}
            for cl in c.clauses.all()
        ]
        
        reviews_data = []
        if latest_analysis:
            reviews_data = [
                {
                    'id': r.id,
                    'comment': r.comment,
                    'final_risk_level': r.final_risk_level,
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
                    'clause_id': f.clause.id,
                    'clause_title': f.clause.clause_title,
                    'risk_name': f.risk.risk_name,
                    'risk_level': f.risk_level,
                    'explanation': f.explanation,
                    'recommendation': f.recommendation
                }
                for f in latest_analysis.findings.all()
            ]
            
        # Read original text if available
        raw_content = ""
        if latest_file and latest_file.file_path:
            media_prefix = settings.MEDIA_URL
            rel_path = latest_file.file_path
            if rel_path.startswith(media_prefix):
                rel_path = rel_path[len(media_prefix):]
            
            full_path = os.path.join(settings.MEDIA_ROOT, rel_path.replace('/', os.sep))
            if os.path.exists(full_path):
                if full_path.endswith('.txt') or full_path.endswith('.docx') or full_path.endswith('.doc'):
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            raw_content = f.read()
                    except Exception:
                        pass
        
        # Fallback to reconstructing from clauses if empty
        if not raw_content and clauses_data:
            raw_content = "\n\n".join([f"--- {cl['title']} ---\n{cl['content']}" for cl in clauses_data])
            
        return {
            'id': c.id,
            'contract_code': c.contract_code,
            'title': c.title,
            'contract_type': c.contract_type,
            'start_date': c.start_date.isoformat() if c.start_date else None,
            'end_date': c.end_date.isoformat() if c.end_date else None,
            'contract_value': float(c.contract_value) if c.contract_value else None,
            'status': c.status,
            'file_path': latest_file.file_path if latest_file else None,
            'raw_content': raw_content,
            'clauses': clauses_data,
            'analysis': analysis_data,
            'findings': findings_data,
            'reviews': reviews_data
        }


    def create_and_analyze_contract(self, code, title, contract_type, start_date, end_date, contract_value, file_obj=None, raw_content=None):
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
            status='DRAFT'
        )
        
        # Save Contract File
        saved_file_path = None
        if file_obj:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            filename = fs.save(f"contracts/{file_obj.name}", file_obj)
            saved_file_path = fs.url(filename)
        elif raw_content:
            from django.core.files.storage import FileSystemStorage
            fs = FileSystemStorage()
            # Clean safe filename
            safe_code = "".join(x for x in code if x.isalnum() or x in "-_")
            filename = fs.save(f"contracts/contract_{safe_code}.txt", ContentFile(raw_content.encode('utf-8')))
            saved_file_path = fs.url(filename)
            
        if saved_file_path:
            self.file_repo.create_file_record(contract, saved_file_path)
            
        return contract

    def analyze_contract(self, contract_id):
        contract = self.contract_repo.get_contract_by_id(contract_id)
        if not contract:
            raise ValueError("Contract not found.")
            
        contract.status = 'ANALYZING'
        contract.save()
        
        # Clean up existing clauses and analyses for re-run support
        contract.clauses.all().delete()
        contract.ai_analyses.all().delete()
        
        # Trigger Simulated AI analysis
        self._simulate_ai_analysis(contract)
        
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
        contract = analysis.contract
        contract.status = 'APPROVED'
        contract.save()
        
        # Log Audit
        self.audit_repo.log_action(admin_user, "REVIEW_SUBMITTED", "Review", review.id)
        
        return review

    def _get_raw_content(self, contract):
        latest_file = contract.files.first()
        if not latest_file or not latest_file.file_path:
            return ""
        
        import os
        from django.conf import settings
        rel_path = latest_file.file_path
        url_prefix = settings.MEDIA_URL
        if rel_path.startswith(url_prefix):
            rel_path = rel_path[len(url_prefix):]
        physical_path = os.path.join(settings.MEDIA_ROOT, rel_path)
        
        if os.path.exists(physical_path):
            try:
                with open(physical_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass
        return ""

    def _split_clauses(self, raw_text):
        import re
        if not raw_text or not raw_text.strip():
            return []
            
        # Standardize newlines
        text = raw_text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Heading match pattern (e.g. Điều 1:, Article 2., Section 3, Clause 4, 1. Title)
        pattern = r'(?m)^(?=(?:Điều|Article|Section|Paragraph|Clause|\d+)\s*[:\.\-\d\s]+)'
        
        parts = re.split(pattern, text)
        parts = [p.strip() for p in parts if p.strip()]
        
        clauses = []
        for i, part in enumerate(parts):
            lines = part.split('\n')
            title = lines[0].strip()
            # If the title line is very long, it's not a real heading; treat entire block as content
            if len(title) > 80 or len(lines) == 1:
                title = f"Clause {i+1}"
                content = part
            else:
                content = "\n".join(lines[1:]).strip()
                if not content:
                    content = title
                    title = f"Clause {i+1}"
            
            clauses.append({
                "title": title,
                "content": content
            })
            
        # Fallback to paragraph-based splitting if no structural headers matched
        if len(clauses) <= 1:
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
            clauses = []
            for i, p in enumerate(paragraphs):
                lines = p.split('\n')
                first_line = lines[0].strip()
                if len(first_line) < 60 and (":" in first_line or "-" in first_line or first_line.isupper()):
                    title = first_line
                    content = "\n".join(lines[1:]).strip()
                else:
                    title = f"Clause {i+1}"
                    content = p
                
                if not content:
                    content = title
                    title = f"Clause {i+1}"
                    
                clauses.append({
                    "title": title,
                    "content": content
                })
                
        return clauses

    def _simulate_ai_analysis(self, contract):
        # 1. Retrieve raw text and split dynamically
        raw_text = self._get_raw_content(contract)
        parsed_clauses = self._split_clauses(raw_text)
        
        # Fallback if text is empty or couldn't be loaded
        if not parsed_clauses:
            parsed_clauses = [
                {
                    "title": "Payment Obligations",
                    "content": "The buyer shall settle all invoices within 15 days of issue. Failure to pay will incur an interest charge of 2.0% per day on the outstanding balance."
                },
                {
                    "title": "Limitation of Liability",
                    "content": "To the maximum extent permitted by applicable law, the contractor's entire liability under this agreement shall be limited to $500.00."
                },
                {
                    "title": "Confidentiality & Non-Disclosure",
                    "content": "Both parties agree that all shared technical, operational, and customer records must be protected. However, no encryption controls or security audit rights are specified."
                }
            ]
            
        # 2. Get-or-create master Risk categories
        risk_payment, _ = self.risk_repo.get_or_create_risk(
            "Payment Risk",
            defaults={"description": "High late payment penalty fees.", "severity_level": "HIGH"}
        )
        risk_legal, _ = self.risk_repo.get_or_create_risk(
            "Limitation of Liability Risk",
            defaults={"description": "Unbalanced liability caps.", "severity_level": "CRITICAL"}
        )
        risk_privacy, _ = self.risk_repo.get_or_create_risk(
            "Data Privacy & Security Risk",
            defaults={"description": "Vague data protection policies.", "severity_level": "HIGH"}
        )
        
        # 3. Create Analysis Object
        score = Decimal(str(random.randint(60, 92)))
        analysis = self.analysis_repo.create_analysis(
            contract=contract,
            model_name="ContractGuard-AI-V3",
            overall_score=score,
            summary=f"Analysis of contract '{contract.title}' completed. Scanned all clauses and detected potential contract risk exposures."
        )
        
        # 4. Save clauses and match findings dynamically
        clauses = []
        findings_created = 0
        
        for c_data in parsed_clauses:
            cl = self.clause_repo.create_clause(contract, c_data["title"], c_data["content"])
            clauses.append(cl)
            
            content_lower = cl.clause_content.lower()
            title_lower = cl.clause_title.lower()
            
            # Check for Payment Risk
            if any(k in content_lower or k in title_lower for k in ["payment", "pay", "fee", "penalty", "thanh toán", "phạt", "lãi suất"]):
                self.finding_repo.create_finding(
                    analysis=analysis,
                    clause=cl,
                    risk=risk_payment,
                    risk_level="HIGH",
                    explanation=f"Clause '{cl.clause_title}' contains payment or penalty terms. Excessive daily rates or short window terms present risk.",
                    recommendation="Ensure payment window is at least 30 days and late interest rate is capped at maximum statutory limit (e.g. 9-15% annually)."
                )
                findings_created += 1
                
            # Check for Limitation of Liability Risk
            if any(k in content_lower or k in title_lower for k in ["liability", "limit", "cap", "bồi thường", "trách nhiệm"]):
                self.finding_repo.create_finding(
                    analysis=analysis,
                    clause=cl,
                    risk=risk_legal,
                    risk_level="HIGH",
                    explanation=f"Clause '{cl.clause_title}' restricts or waives vendor liabilities. Extremely low caps leave your business vulnerable to damages.",
                    recommendation="Renegotiate the liability cap to be equal to 1x-2x the annual contract value rather than a flat low fee."
                )
                findings_created += 1
                
            # Check for Data Privacy / Security Risk
            if any(k in content_lower or k in title_lower for k in ["privacy", "security", "confidential", "data", "bảo mật", "bí mật", "thông tin"]):
                self.finding_repo.create_finding(
                    analysis=analysis,
                    clause=cl,
                    risk=risk_privacy,
                    risk_level="MEDIUM",
                    explanation=f"Clause '{cl.clause_title}' regulates information confidentiality but lacks specific technical security audit and breach reporting guarantees.",
                    recommendation="Add standard security compliance (e.g. SOC2, ISO27001) and require a 72-hour security incident notification window."
                )
                findings_created += 1
                
        # If no findings were created because no keywords matched, seed default findings on the first clause
        if findings_created == 0 and clauses:
            self.finding_repo.create_finding(
                analysis=analysis,
                clause=clauses[0],
                risk=risk_payment,
                risk_level="MEDIUM",
                explanation=f"Clause '{clauses[0].clause_title}' was flagged for review. General verification is required to confirm standard operating compliance.",
                recommendation="Review the exact terms to ensure mutual liability and standard commercial definitions."
            )
            
        # Update status
        contract.status = 'ANALYZED'
        contract.save()

