from typing import Literal

from pydantic import BaseModel, Field

Perspective = Literal['general', 'employee', 'hr']
Length = Literal['one_sentence', 'short', 'detailed']


class RenderOptions(BaseModel):
    perspective: Perspective = 'general'
    length: Length = 'detailed'
    explain_terms: bool = False


class SummarizeRequest(RenderOptions):
    model_config = {'protected_namespaces': ()}

    text: str = Field(min_length=1)
    contract_metadata: dict = {}
    force: bool = False
    model: str | None = None


class SummarizeResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    summary: str
    structured: dict
    facts: dict
    unverified: list
    checklist: dict | None
    model_id: str
    cached: bool
    chunks: int
    elapsed_ms: int


class CompareRequest(RenderOptions):
    model_config = {'protected_namespaces': ()}

    old_text: str = Field(min_length=1)
    new_text: str = Field(min_length=1)
    force: bool = False
    model: str | None = None


ITEM = {'type': 'object', 'additionalProperties': False, 'required': ['text', 'section'],
        'properties': {'text': {'type': 'string'}, 'section': {'type': 'string'}}}
# maxItems: guided decoding must close every list, so a small model cannot loop until max_tokens.
MAX_ITEMS = 8
ITEMS = {'type': 'array', 'items': ITEM, 'maxItems': MAX_ITEMS}

# Guided decoding keeps small models on this shape; every list item cites a section id.
# job/salary/benefits/working_time/insurance are labour-contract fields and stay empty elsewhere.
SUMMARY_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['contract_type', 'purpose', 'parties', 'value', 'term', 'effective_date',
                 'job', 'salary', 'working_time', 'insurance',
                 'payment', 'benefits', 'obligations', 'penalties', 'termination', 'risks'],
    'properties': {
        'contract_type': {'type': 'string'},
        'purpose': {'type': 'string'},
        'parties': {'type': 'array', 'maxItems': 6, 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['role', 'name', 'representative', 'tax_code'],
            'properties': {k: {'type': 'string'} for k in ('role', 'name', 'representative', 'tax_code')}}},
        'value': {'type': 'string'},
        'term': {'type': 'string'},
        'effective_date': {'type': 'string'},
        'job': {'type': 'string'},
        'salary': {'type': 'string'},
        'working_time': {'type': 'string'},
        'insurance': {'type': 'string'},
        'payment': ITEMS,
        'benefits': ITEMS,
        'obligations': {'type': 'array', 'maxItems': MAX_ITEMS, 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['party', 'text', 'section'],
            'properties': {k: {'type': 'string'} for k in ('party', 'text', 'section')}}},
        'penalties': ITEMS,
        'termination': ITEMS,
        'risks': ITEMS,
    },
}
