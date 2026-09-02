"""Read-only contracts for structured claims, source context, and contradictions."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.entities import ClaimStatus, ContradictionStatus, SourceRelationship


class SourceLinkResponse(BaseModel):
    source_type: str
    source_id: str
    relationship: SourceRelationship
    note: str | None


class SourceLinkWrite(BaseModel):
    source_type: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=36)
    relationship: SourceRelationship
    note: str | None = Field(default=None, max_length=4000)


class ClaimCreateRequest(BaseModel):
    statement: str = Field(min_length=10, max_length=4000)
    claim_type: str = Field(min_length=1, max_length=80)
    scope_note: str | None = Field(default=None, max_length=4000)
    sources: list[SourceLinkWrite] = Field(min_length=1, max_length=50)


class ClaimStatusUpdateRequest(BaseModel):
    status: ClaimStatus


class ContradictionCreateRequest(BaseModel):
    subject: str = Field(min_length=3, max_length=512)
    description: str = Field(min_length=10, max_length=4000)
    sources: list[SourceLinkWrite] = Field(min_length=2, max_length=50)


class ContradictionStatusUpdateRequest(BaseModel):
    status: ContradictionStatus


class ClaimResponse(BaseModel):
    id: str
    case_id: str
    statement: str
    claim_type: str
    scope_note: str | None
    status: ClaimStatus
    created_by_id: str
    created_at: datetime
    updated_at: datetime
    sources: list[SourceLinkResponse]


class ContradictionResponse(BaseModel):
    id: str
    case_id: str
    subject: str
    description: str
    status: ContradictionStatus
    created_by_id: str
    created_at: datetime
    updated_at: datetime
    sources: list[SourceLinkResponse]
