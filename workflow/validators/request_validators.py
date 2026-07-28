"""
workflow/validators/request_validators.py

Centralised validation logic for all Workflow API endpoints.
Moving validation out of views keeps views thin and makes
the rules reusable and independently testable.

Each validator exposes a single ``validate(body)`` method that
raises ``WorkflowValidationException`` on failure and returns
nothing on success.
"""
from workflow.constants import RiskLevel
from workflow.exceptions import WorkflowValidationException


class RecommendationValidator:
    """
    Validates a raw parsed-JSON body for the Recommendation endpoint.

    Rules
    -----
    - ``title``         : required, non-empty string.
    - ``contract_type`` : required, non-empty string.
    - ``risk_level``    : when present, must be one of RiskLevel.ALL.
    - ``contract_value``: when present, must be numeric and non-negative.
    """

    @staticmethod
    def validate(body: dict) -> None:
        """
        Args:
            body: Parsed request JSON as a dict.

        Raises:
            WorkflowValidationException: if any rule is violated.
        """
        title = body.get('title', '')
        if not isinstance(title, str) or not title.strip():
            raise WorkflowValidationException(
                "Field 'title' is required and must be a non-empty string.",
                code='MISSING_FIELD',
            )

        contract_type = body.get('contract_type', '')
        if not isinstance(contract_type, str) or not contract_type.strip():
            raise WorkflowValidationException(
                "Field 'contract_type' is required and must be a non-empty string.",
                code='MISSING_FIELD',
            )

        risk_level = body.get('risk_level')
        if risk_level is not None and risk_level not in RiskLevel.ALL:
            raise WorkflowValidationException(
                f"Invalid 'risk_level': '{risk_level}'. "
                f"Must be one of {sorted(RiskLevel.ALL)}.",
                code='INVALID_VALUE',
            )

        contract_value = body.get('contract_value')
        if contract_value is not None:
            try:
                value = float(contract_value)
                if value < 0:
                    raise ValueError()
            except (TypeError, ValueError):
                raise WorkflowValidationException(
                    "Field 'contract_value' must be a non-negative number.",
                    code='INVALID_VALUE',
                )


class BuilderValidator:
    """
    Validates a raw parsed-JSON body for the Builder endpoint.

    Rules
    -----
    - ``risk_level``    : when present, must be one of RiskLevel.ALL.
    - ``contract_value``: when present, must be numeric and non-negative.
    - ``business_rules``: when present, must be a dict; boolean values
                          within it must be actual booleans.
    """

    BOOLEAN_RULE_KEYS = {
        'require_legal_review',
        'require_finance_review',
        'require_ceo_approval',
        'auto_archive',
        'international',
        'personal_data',
        'nda_required',
    }

    @staticmethod
    def validate(body: dict) -> None:
        """
        Args:
            body: Parsed request JSON as a dict.

        Raises:
            WorkflowValidationException: if any rule is violated.
        """
        risk_level = body.get('risk_level')
        if risk_level is not None and risk_level not in RiskLevel.ALL:
            raise WorkflowValidationException(
                f"Invalid 'risk_level': '{risk_level}'. "
                f"Must be one of {sorted(RiskLevel.ALL)}.",
                code='INVALID_VALUE',
            )

        contract_value = body.get('contract_value')
        if contract_value is not None:
            try:
                value = float(contract_value)
                if value < 0:
                    raise ValueError()
            except (TypeError, ValueError):
                raise WorkflowValidationException(
                    "Field 'contract_value' must be a non-negative number.",
                    code='INVALID_VALUE',
                )

        rules = body.get('business_rules')
        if rules is not None:
            if not isinstance(rules, dict):
                raise WorkflowValidationException(
                    "Field 'business_rules' must be a JSON object.",
                    code='INVALID_VALUE',
                )
            for key in BuilderValidator.BOOLEAN_RULE_KEYS:
                value = rules.get(key)
                if value is not None and not isinstance(value, bool):
                    raise WorkflowValidationException(
                        f"Business rule '{key}' must be a boolean (true/false).",
                        code='INVALID_VALUE',
                    )
