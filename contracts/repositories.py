from .models import Contract, ContractFile, Clause, Risk, AIAnalysis, RiskFinding, Review, AuditLog

class RiskRepository:
    @staticmethod
    def get_all_risks():
        return Risk.objects.all().order_by('risk_name')
        
    @staticmethod
    def get_risk_by_id(risk_id):
        try:
            return Risk.objects.get(id=risk_id)
        except Risk.DoesNotExist:
            return None
            
    @staticmethod
    def create_risk(name, description, severity_level):
        return Risk.objects.create(
            risk_name=name,
            description=description,
            severity_level=severity_level
        )

    @staticmethod
    def get_or_create_risk(name, defaults):
        return Risk.objects.get_or_create(
            risk_name=name,
            defaults=defaults
        )


class AuditLogRepository:
    @staticmethod
    def log_action(user, action, target_model, target_id):
        return AuditLog.objects.create(
            user=user,
            action=action,
            target_model=target_model,
            target_id=target_id
        )


class ContractRepository:
    @staticmethod
    def get_all_contracts():
        return Contract.objects.all().order_by('-created_at')
        
    @staticmethod
    def get_contract_by_id(contract_id):
        try:
            return Contract.objects.prefetch_related(
                'clauses', 'ai_analyses__findings__risk', 'ai_analyses__reviews__user'
            ).get(id=contract_id)
        except Contract.DoesNotExist:
            return None
            
    @staticmethod
    def create_contract(code, title, contract_type, start_date, end_date, contract_value, status='DRAFT'):
        return Contract.objects.create(
            contract_code=code,
            title=title,
            contract_type=contract_type,
            start_date=start_date,
            end_date=end_date,
            contract_value=contract_value,
            status=status
        )


class ContractFileRepository:
    @staticmethod
    def create_file_record(contract, file_path):
        return ContractFile.objects.create(
            contract=contract,
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
    def create_analysis(contract, model_name, overall_score, summary):
        return AIAnalysis.objects.create(
            contract=contract,
            model_name=model_name,
            overall_score=overall_score,
            summary=summary
        )


class ClauseRepository:
    @staticmethod
    def create_clause(contract, title, content):
        return Clause.objects.create(
            contract=contract,
            clause_title=title,
            clause_content=content
        )


class RiskFindingRepository:
    @staticmethod
    def create_finding(analysis, clause, risk, risk_level, explanation, recommendation):
        return RiskFinding.objects.create(
            analysis=analysis,
            clause=clause,
            risk=risk,
            risk_level=risk_level,
            explanation=explanation,
            recommendation=recommendation
        )


class ReviewRepository:
    @staticmethod
    def create_review(analysis, user, comment, final_risk_level):
        return Review.objects.create(
            analysis=analysis,
            user=user,
            comment=comment,
            final_risk_level=final_risk_level
        )
