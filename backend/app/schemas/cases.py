"""Pydantic contracts for protected investigation case operations."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.entities import CaseStatus, Priority, Role


class IncidentWindowFields(BaseModel):
    """The span an investigator declares to be the incident.

    Declaring it is what lets the case say a contact fell before, during or after the incident.
    Leaving it out is a legitimate answer -- an investigator who does not yet know when something
    happened must not be made to guess -- and the temporal sections stay silent rather than
    inventing a moment to measure from.

    An end before its start is refused rather than quietly swapped: it is far more likely a typo
    than an intention, and silently reinterpreting it would place records on the wrong side of the
    incident with nothing on screen to show it happened.
    """

    date_range_start: datetime | None = None
    date_range_end: datetime | None = None

    @model_validator(mode="after")
    def _window_runs_forwards(self):
        if self.date_range_start and self.date_range_end and self.date_range_end < self.date_range_start:
            raise ValueError("The incident window ends before it starts.")
        return self


class CaseCreateRequest(IncidentWindowFields):
    title: str = Field(min_length=3, max_length=255)
    crime_type: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=5000)
    fir_number: str | None = Field(default=None, max_length=120)
    victim_alias: str | None = Field(default=None, max_length=160)
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
    # The declared incident window. Returned so the workspace can show what was declared and say
    # so when nothing was -- a window the server holds and never reports back cannot be corrected.
    date_range_start: datetime | None
    date_range_end: datetime | None
    status: CaseStatus
    priority: Priority
    owner_id: str
    created_at: datetime
    updated_at: datetime


class IncidentWindowRequest(IncidentWindowFields):
    """Declaring, changing or clearing the incident window on a case already open.

    Sending both fields as null clears it, which is the honest move when a declared window turns
    out to be wrong: the case goes back to reporting that no window has been declared rather than
    keeping a span nobody stands behind.
    """


class CaseMemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    case_role: Role


class CaseMemberResponse(BaseModel):
    user_id: str
    case_id: str
    case_role: Role

