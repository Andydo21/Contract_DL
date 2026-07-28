"""
workflow/services/recommendation_service.py

Mock implementation of the Workflow Recommendation service.
Business logic lives here; constants keep literals out of the code.
This service will be replaced with real AI inference in a future phase.
"""
from workflow.constants import (
    RiskLevel,
    ContractType,
    WorkflowName,
    Confidence,
    StepMeta,
    HIGH_VALUE_THRESHOLD,
)
from workflow.exceptions import WorkflowServiceException


class WorkflowRecommendationService:
    """
    Generates a workflow recommendation based on contract attributes.

    Currently returns deterministic mock data based on simple branching
    rules.  The public interface (``recommend``) is stable and will
    accept the same dict contract when the real AI backend is connected.
    """

    def recommend(self, contract_data: dict) -> dict:
        """
        Generate a workflow recommendation for the given contract.

        Args:
            contract_data: A dict containing contract metadata.
                           Expected keys: title, contract_type,
                           department, contract_value, risk_level, content.

        Returns:
            dict with keys: workflow_name, confidence, reasoning, steps.

        Raises:
            WorkflowServiceException: if the recommendation logic fails.
        """
        try:
            return self._select_workflow(contract_data)
        except Exception as exc:
            raise WorkflowServiceException(
                f"Recommendation service failed: {exc}"
            ) from exc

    # ── Private helpers ────────────────────────────────────────────────────

    def _select_workflow(self, contract_data: dict) -> dict:
        """Select and return the appropriate mock workflow branch."""
        contract_type = str(contract_data.get('contract_type', '')).lower()
        risk_level = str(contract_data.get('risk_level', RiskLevel.DEFAULT)).upper()
        contract_value = self._parse_value(contract_data.get('contract_value', 0))

        if self._is_high_value_or_high_risk(risk_level, contract_value):
            return self._enterprise_high_value_workflow()

        if contract_type in ContractType.NDA_TYPES:
            return self._standard_nda_workflow()

        return self._default_procurement_workflow()

    @staticmethod
    def _is_high_value_or_high_risk(risk_level: str, contract_value: float) -> bool:
        return risk_level == RiskLevel.HIGH or contract_value > HIGH_VALUE_THRESHOLD

    @staticmethod
    def _parse_value(raw) -> float:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _enterprise_high_value_workflow() -> dict:
        return {
            'workflow_name': WorkflowName.ENTERPRISE_HIGH_VALUE,
            'confidence': Confidence.HIGH_VALUE,
            'reasoning': [
                f'Contract value exceeds ${HIGH_VALUE_THRESHOLD:,} threshold',
                'High risk level requires additional approval layers',
                'Contains procurement clauses requiring finance review',
                'Regulatory compliance verification needed',
            ],
            'steps': [
                StepMeta.LEGAL_REVIEW,
                StepMeta.COMPLIANCE_CHECK,
                StepMeta.FINANCE_REVIEW,
                StepMeta.MANAGER_APPROVAL,
                StepMeta.DIRECTOR_APPROVAL,
                StepMeta.CONTRACT_SIGNING,
                StepMeta.ARCHIVE,
            ],
        }

    @staticmethod
    def _standard_nda_workflow() -> dict:
        return {
            'workflow_name': WorkflowName.STANDARD_NDA,
            'confidence': Confidence.NDA,
            'reasoning': [
                'Non-disclosure agreement detected',
                'Standard confidentiality terms identified',
                'Low complexity — fast-track eligible',
            ],
            'steps': [
                StepMeta.LEGAL_REVIEW,
                StepMeta.MANAGER_APPROVAL,
                StepMeta.CONTRACT_SIGNING,
                StepMeta.ARCHIVE,
            ],
        }

    @staticmethod
    def _default_procurement_workflow() -> dict:
        return {
            'workflow_name': WorkflowName.ENTERPRISE_PROCUREMENT,
            'confidence': Confidence.DEFAULT,
            'reasoning': [
                'Contract value is within standard range',
                'Contains procurement clauses',
                'Contains payment schedule',
                'Standard approval path recommended',
            ],
            'steps': [
                StepMeta.LEGAL_REVIEW,
                StepMeta.FINANCE_REVIEW,
                StepMeta.MANAGER_APPROVAL,
                StepMeta.DIRECTOR_APPROVAL,
                StepMeta.CONTRACT_SIGNING,
                StepMeta.ARCHIVE,
            ],
        }
