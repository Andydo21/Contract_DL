from workflow.constants import StepMeta
from workflow.exceptions import WorkflowServiceException


class DynamicWorkflowBuilderService:
    """
    Generates a dynamic workflow pipeline from contract data and
    a set of configurable business rules.

    Currently returns deterministic mock data.  The public interface
    (``build``) is stable and will accept the same arguments when
    real AI-based step ordering is introduced.
    """

    def build(self, contract_data: dict, business_rules: dict = None) -> dict:
        """
        Generate a workflow pipeline for the given contract and rules.

        Args:
            contract_data:  Dict containing contract metadata (unused
                            by the mock but forwarded to the future
                            AI engine).
            business_rules: Dict of boolean rule flags.

        Returns:
            dict with keys: workflow, total_estimated_days, generated_from.

        Raises:
            WorkflowServiceException: if step construction fails.
        """
        try:
            rules = business_rules or {}
            steps, total_days = self._build_steps(rules)
            return {
                'workflow': steps,
                'total_estimated_days': total_days,
                'generated_from': 'mock_ai_builder_v1',
            }
        except Exception as exc:
            raise WorkflowServiceException(
                f"Builder service failed: {exc}"
            ) from exc

    # ── Private helpers ────────────────────────────────────────────────────

    def _build_steps(self, rules: dict):
        """Construct the ordered step list from business rule flags."""
        steps = []
        total_days = 0

        if rules.get('require_legal_review', True):
            steps.append(self._make_step(
                StepMeta.LEGAL_REVIEW,
                StepMeta.OWNER_LEGAL,
                StepMeta.DAYS_LEGAL,
            ))
            total_days += StepMeta.DAYS_LEGAL

        # nda_required: insert NDA-specific review directly after Legal Review
        if rules.get('nda_required', False):
            steps.append(self._make_step(
                StepMeta.NDA_REVIEW,
                StepMeta.OWNER_LEGAL,
                StepMeta.DAYS_NDA_REVIEW,
            ))
            total_days += StepMeta.DAYS_NDA_REVIEW

        # personal_data: insert a privacy / GDPR assessment step
        if rules.get('personal_data', False):
            steps.append(self._make_step(
                StepMeta.PRIVACY_ASSESSMENT,
                StepMeta.OWNER_DPO,
                StepMeta.DAYS_PRIVACY_ASSESSMENT,
            ))
            total_days += StepMeta.DAYS_PRIVACY_ASSESSMENT

        # international: insert a cross-border compliance review
        if rules.get('international', False):
            steps.append(self._make_step(
                StepMeta.CROSS_BORDER_COMPLIANCE,
                StepMeta.OWNER_COMPLIANCE,
                StepMeta.DAYS_CROSS_BORDER,
            ))
            total_days += StepMeta.DAYS_CROSS_BORDER

        if rules.get('require_finance_review', True):
            steps.append(self._make_step(
                StepMeta.FINANCE_REVIEW,
                StepMeta.OWNER_FINANCE,
                StepMeta.DAYS_FINANCE,
            ))
            total_days += StepMeta.DAYS_FINANCE

        # Manager approval is always required
        steps.append(self._make_step(
            StepMeta.MANAGER_APPROVAL,
            StepMeta.OWNER_MANAGER,
            StepMeta.DAYS_MANAGER,
        ))
        total_days += StepMeta.DAYS_MANAGER

        if rules.get('require_ceo_approval', False):
            steps.append(self._make_step(
                StepMeta.DIRECTOR_APPROVAL,
                StepMeta.OWNER_DIRECTOR,
                StepMeta.DAYS_DIRECTOR,
            ))
            total_days += StepMeta.DAYS_DIRECTOR

            steps.append(self._make_step(
                StepMeta.CEO_APPROVAL,
                StepMeta.OWNER_CEO,
                StepMeta.DAYS_CEO,
            ))
            total_days += StepMeta.DAYS_CEO

        # Contract signing is always required
        steps.append(self._make_step(
            StepMeta.CONTRACT_SIGNING,
            StepMeta.OWNER_SIGNERS,
            StepMeta.DAYS_SIGNING,
        ))
        total_days += StepMeta.DAYS_SIGNING

        if rules.get('auto_archive', True):
            steps.append(self._make_step(
                StepMeta.ARCHIVE,
                StepMeta.OWNER_SYSTEM,
                StepMeta.DAYS_ARCHIVE,
            ))

        return steps, total_days

    @staticmethod
    def _make_step(name: str, owner: str, estimated_days: int) -> dict:
        """Create a single step dict in the canonical API format."""
        return {
            'step': name,
            'owner': owner,
            'estimated_days': estimated_days,
        }

