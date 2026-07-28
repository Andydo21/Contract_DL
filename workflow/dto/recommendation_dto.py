"""
workflow/dto/recommendation_dto.py

Data Transfer Objects for the Workflow Recommendation feature.
DTOs act as typed contracts between the API surface (views) and
the service layer.  They centralise field defaults and conversion
logic so neither views nor services need to know about raw HTTP
request structure.
"""
from dataclasses import dataclass, field
from typing import List

from workflow.constants import RiskLevel


@dataclass
class RecommendationRequest:
    """
    Represents a validated, normalised recommendation request.

    Attributes:
        title:          Contract title (required, non-empty).
        contract_type:  Contract category slug (e.g. 'procurement').
        department:     Requesting department (optional).
        contract_value: Monetary value in USD; defaults to 0.
        risk_level:     Risk classification; defaults to MEDIUM.
        content:        Raw contract text for future AI analysis.
    """
    title: str
    contract_type: str
    department: str = ''
    contract_value: float = 0.0
    risk_level: str = RiskLevel.DEFAULT
    content: str = ''

    def to_dict(self) -> dict:
        """Serialise to a plain dict for passing to service methods."""
        return {
            'title': self.title,
            'contract_type': self.contract_type,
            'department': self.department,
            'contract_value': self.contract_value,
            'risk_level': self.risk_level,
            'content': self.content,
        }


@dataclass
class RecommendationResponse:
    """
    Represents a workflow recommendation result returned by the service.

    Attributes:
        workflow_name:  Human-readable name of the recommended workflow.
        confidence:     AI confidence score (0-100).
        reasoning:      List of human-readable justification strings.
        steps:          Ordered list of workflow step name strings.
    """
    workflow_name: str
    confidence: int
    reasoning: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)

    def to_api_dict(self) -> dict:
        """
        Serialise to the JSON structure expected by the frontend.
        The ``success`` key is added by the view layer.
        """
        return {
            'workflow_name': self.workflow_name,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'steps': self.steps,
        }
