from contracts.models import RiskFinding


class RiskFindingRepository:
    @staticmethod
    def create_finding(analysis, clause, risk, risk_level, explanation, recommendation, disadvantaged_party=None, is_suggestion=False):
        return RiskFinding.objects.create(
            analysis=analysis,
            clause=clause,
            rule=risk,
            risk_level=risk_level,
            explanation=explanation,
            recommendation=recommendation,
            disadvantaged_party=disadvantaged_party,
            is_suggestion=is_suggestion
        )
