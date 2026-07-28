"""
workflow/dto/builder_dto.py

Data Transfer Objects for the Dynamic Workflow Builder feature.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any

from workflow.constants import RiskLevel


@dataclass
class BusinessRules:
    """
    Encapsulates all configurable business rule toggles for the builder.

    Attributes match the field names sent by the frontend so that the
    mapper can construct this object directly from the request payload.
    """
    require_legal_review: bool = True
    require_finance_review: bool = True
    require_ceo_approval: bool = False
    auto_archive: bool = True
    international: bool = False
    personal_data: bool = False
    nda_required: bool = False

    def to_dict(self) -> dict:
        """Serialise to a plain dict for passing to service methods."""
        return {
            'require_legal_review': self.require_legal_review,
            'require_finance_review': self.require_finance_review,
            'require_ceo_approval': self.require_ceo_approval,
            'auto_archive': self.auto_archive,
            'international': self.international,
            'personal_data': self.personal_data,
            'nda_required': self.nda_required,
        }


@dataclass
class BuilderRequest:
    """
    Represents a validated, normalised builder request.

    Attributes:
        title:          Contract title.
        contract_type:  Contract category slug.
        department:     Requesting department (optional).
        contract_value: Monetary value in USD; defaults to 0.
        risk_level:     Risk classification; defaults to MEDIUM.
        content:        Raw contract text.
        business_rules: Configured business rule constraints.
    """
    title: str = ''
    contract_type: str = ''
    department: str = ''
    contract_value: float = 0.0
    risk_level: str = RiskLevel.DEFAULT
    content: str = ''
    business_rules: BusinessRules = field(default_factory=BusinessRules)

    def to_contract_dict(self) -> dict:
        """Return only contract metadata as a plain dict."""
        return {
            'title': self.title,
            'contract_type': self.contract_type,
            'department': self.department,
            'contract_value': self.contract_value,
            'risk_level': self.risk_level,
            'content': self.content,
        }


@dataclass
class BuilderResponse:
    """
    Represents the generated workflow returned by the builder service.

    Attributes:
        workflow:              Ordered list of step dicts
                               (keys: step, owner, estimated_days).
        total_estimated_days:  Cumulative duration in working days.
        generated_from:        Identifier of the engine that produced
                               the workflow (for traceability).
    """
    workflow: List[Dict[str, Any]] = field(default_factory=list)
    total_estimated_days: int = 0
    generated_from: str = 'mock_ai_builder_v1'

    def to_api_dict(self) -> dict:
        """
        Serialise to the JSON structure expected by the frontend.
        The ``success`` key is added by the view layer.
        """
        return {
            'workflow': self.workflow,
            'total_estimated_days': self.total_estimated_days,
            'generated_from': self.generated_from,
        }
