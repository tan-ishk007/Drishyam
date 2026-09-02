"""Pydantic contracts for protected investigation case operations."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.entities import CaseStatus, Priority, Role


class CaseCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    crime_type: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    fir_number: str | None = Field(default=None, max_length=120)
    victim_alias: str | None = Field(default=None, max_length=160)
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    notes: str | None = Field(default=None, max_length=5000)
    priority: Priority = Priority.MEDIUM


class CaseResponse(BaseModel):
    id: str
    case_number: str
    title: str
    crime_type: str
    description: str | None
    fir_number: str | None
    victim_alias: str | None
    status: CaseStatus
    priority: Priority
    owner_id: str
    created_at: datetime
    updated_at: datetime


class CaseMemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    case_role: Role


class CaseMemberResponse(BaseModel):
    user_id: str
    case_id: str
    case_role: Role

