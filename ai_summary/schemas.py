from pydantic import BaseModel
from typing import List, Optional

class ClauseInput(BaseModel):
    title: str
    content: str

class SummarizeRequest(BaseModel):
    clauses: List[ClauseInput]
    contract_metadata: dict = {}

class SummarizeResponse(BaseModel):
    summary: str

class EntityExtractRequest(BaseModel):
    text: str

class EntityExtractResponse(BaseModel):
    entities: dict
