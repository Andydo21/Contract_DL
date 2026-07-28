"""
workflow/mappers/request_mapper.py

Transforms raw HTTP request bodies (plain dicts) into typed DTOs,
removing this conversion logic from both views and services.
"""
from workflow.constants import RiskLevel
from workflow.dto import (
    RecommendationRequest,
    BuilderRequest,
    BusinessRules,
)


class RequestMapper:
    """
    Converts parsed JSON request bodies into their corresponding
    DTO instances.  Both methods are static so the class can be
    used without instantiation.
    """

    @staticmethod
    def to_recommendation_request(body: dict) -> RecommendationRequest:
        """
        Map a raw recommendation request body to a
        ``RecommendationRequest`` DTO.

        Args:
            body: Parsed JSON dict from the HTTP request.

        Returns:
            A fully populated ``RecommendationRequest``.
        """
        return RecommendationRequest(
            title=str(body.get('title', '')).strip(),
            contract_type=str(body.get('contract_type', '')).strip(),
            department=str(body.get('department', '')).strip(),
            contract_value=_safe_float(body.get('contract_value', 0)),
            risk_level=_normalise_risk(body.get('risk_level')),
            content=str(body.get('content', '')).strip(),
        )

    @staticmethod
    def to_builder_request(body: dict) -> BuilderRequest:
        """
        Map a raw builder request body to a ``BuilderRequest`` DTO,
        including nested ``BusinessRules``.

        Args:
            body: Parsed JSON dict from the HTTP request.

        Returns:
            A fully populated ``BuilderRequest``.
        """
        rules_raw = body.get('business_rules', {}) or {}

        business_rules = BusinessRules(
            require_legal_review=bool(rules_raw.get('require_legal_review', True)),
            require_finance_review=bool(rules_raw.get('require_finance_review', True)),
            require_ceo_approval=bool(rules_raw.get('require_ceo_approval', False)),
            auto_archive=bool(rules_raw.get('auto_archive', True)),
            international=bool(rules_raw.get('international', False)),
            personal_data=bool(rules_raw.get('personal_data', False)),
            nda_required=bool(rules_raw.get('nda_required', False)),
        )

        return BuilderRequest(
            title=str(body.get('title', '')).strip(),
            contract_type=str(body.get('contract_type', '')).strip(),
            department=str(body.get('department', '')).strip(),
            contract_value=_safe_float(body.get('contract_value', 0)),
            risk_level=_normalise_risk(body.get('risk_level')),
            content=str(body.get('content', '')).strip(),
            business_rules=business_rules,
        )


# ── Private helpers ────────────────────────────────────────────────────────────

def _safe_float(value) -> float:
    """Convert a value to float, returning 0.0 on any failure."""
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _normalise_risk(value) -> str:
    """
    Return a valid RiskLevel string, defaulting to MEDIUM when
    the supplied value is absent or unrecognised.
    """
    if value and str(value).upper() in RiskLevel.ALL:
        return str(value).upper()
    return RiskLevel.DEFAULT
