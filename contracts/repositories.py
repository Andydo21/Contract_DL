from .models import Contract, ContractVersion, ContractFile, RiskRule, AIAnalysis, RiskFinding, Review, AuditLog
from ai_extract.models import Clause
import os

class RiskRepository:
    @staticmethod
    def get_all_risks():
        return RiskRule.objects.all().order_by('rule_name')
        
    @staticmethod
    def get_risk_by_id(risk_id):
        try:
            return RiskRule.objects.get(id=risk_id)
        except RiskRule.DoesNotExist:
            return None
            
    @staticmethod
    def create_risk(name, description, severity_level):
        code = name.upper().replace(" ", "_").replace("-", "_")
        return RiskRule.objects.create(
            rule_code=code,
            rule_name=name,
            description=description,
            severity=severity_level
        )

    @staticmethod
    def get_or_create_risk(name, defaults):
        name_clean = name.strip()
        # Look up case-insensitively first to avoid duplicate risk rules
        existing = RiskRule.objects.filter(rule_name__iexact=name_clean).first()
        if existing:
            return existing, False
            
        mapped_defaults = {}
        for k, v in defaults.items():
            if k == 'severity_level':
                mapped_defaults['severity'] = v
            else:
                mapped_defaults[k] = v
        if 'rule_code' not in mapped_defaults:
            # Clean up non-alphanumeric chars for clean code
            import re
            cleaned_code = re.sub(r'[^A-Z0-9_]', '', name_clean.upper().replace(" ", "_").replace("-", "_"))
            mapped_defaults['rule_code'] = cleaned_code
        return RiskRule.objects.get_or_create(
            rule_name=name_clean,
            defaults=mapped_defaults
        )


class AuditLogRepository:
    @staticmethod
    def log_action(user, action, target_model, target_id):
        contract = None
        if target_model == "Contract":
            try:
                contract = Contract.objects.get(id=target_id)
            except Contract.DoesNotExist:
                pass
        elif target_model == "Review":
            try:
                review = Review.objects.get(id=target_id)
                contract = review.analysis.version.contract
            except Exception:
                pass
        
        return AuditLog.objects.create(
            user=user,
            contract=contract,
            action=action
        )


class ContractRepository:
    @staticmethod
    def get_all_contracts():
        return Contract.objects.all().order_by('-created_at')
        
    @staticmethod
    def get_contracts_by_company(company):
        return Contract.objects.filter(company=company).order_by('-created_at')
        
    @staticmethod
    def get_contract_by_id(contract_id):
        try:
            return Contract.objects.prefetch_related(
                'versions__files',
                'versions__ai_extract_clauses', 
                'versions__ai_analyses__findings__rule', 
                'versions__ai_analyses__reviews__user'
            ).get(id=contract_id)
        except Contract.DoesNotExist:
            return None
            
    @staticmethod
    def create_contract(code, title, contract_type, start_date, end_date, contract_value, status='DRAFT', company=None):
        return Contract.objects.create(
            contract_code=code,
            title=title,
            contract_type=contract_type,
            start_date=start_date,
            end_date=end_date,
            contract_value=contract_value,
            status=status,
            company=company
        )


class ContractFileRepository:
    @staticmethod
    def create_file_record(contract_or_version, file_path):
        if isinstance(contract_or_version, Contract):
            version, _ = ContractVersion.objects.get_or_create(contract=contract_or_version, version_number=1)
        else:
            version = contract_or_version
            
        file_name = os.path.basename(file_path)
        return ContractFile.objects.create(
            version=version,
            file_name=file_name,
            file_path=file_path
        )


class AIAnalysisRepository:
    @staticmethod
    def get_analysis_by_id(analysis_id):
        try:
            return AIAnalysis.objects.get(id=analysis_id)
        except AIAnalysis.DoesNotExist:
            return None
            
    @staticmethod
    def create_analysis(contract_or_version, model_name, overall_score, summary):
        if isinstance(contract_or_version, Contract):
            version, _ = ContractVersion.objects.get_or_create(contract=contract_or_version, version_number=1)
        else:
            version = contract_or_version
        return AIAnalysis.objects.create(
            version=version,
            model_name=model_name,
            overall_score=overall_score,
            summary=summary
        )

    @staticmethod
    def get_all_analyses():
        return AIAnalysis.objects.select_related('version__contract').prefetch_related(
            'findings__rule'
        ).order_by('-created_at')


class ClauseRepository:
    @staticmethod
    def create_clause(contract_or_version, title, content):
        if isinstance(contract_or_version, Contract):
            version, _ = ContractVersion.objects.get_or_create(contract=contract_or_version, version_number=1)
        else:
            version = contract_or_version
        return Clause.objects.create(
            version=version,
            clause_title=title,
            clause_content=content
        )


class RiskFindingRepository:
    @staticmethod
    def create_finding(analysis, clause, risk, risk_level, explanation, recommendation, disadvantaged_party=None):
        return RiskFinding.objects.create(
            analysis=analysis,
            clause=clause,
            rule=risk,
            risk_level=risk_level,
            explanation=explanation,
            recommendation=recommendation,
            disadvantaged_party=disadvantaged_party
        )


class ReviewRepository:
    @staticmethod
    def create_review(analysis, user, comment, final_risk_level):
        return Review.objects.create(
            analysis=analysis,
            user=user,
            note=comment,
            decision=final_risk_level
        )


class UserRepository:
    @staticmethod
    def get_all_users_with_roles():
        from .models import User
        return User.objects.all().select_related('role')


class ContractVersionRepository:
    @staticmethod
    def get_version_by_id(version_id):
        try:
            return ContractVersion.objects.select_related('contract').get(id=version_id)
        except ContractVersion.DoesNotExist:
            return None

    @staticmethod
    def get_versions_by_ids(version_ids):
        return ContractVersion.objects.filter(id__in=version_ids).select_related('contract')
