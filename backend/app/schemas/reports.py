"""Report creation and status response contracts."""

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field

from app.models.entities import ProcessingState


class ReportRequest(BaseModel):
    """Which document is being asked for.

    The profile decides what the reader is handed; `redaction_profile` decides what is hidden from
    them. They are separate because a court annexure with nothing redacted and a briefing with a
    victim's name removed are both ordinary requests.
    """

    profile: Literal["case_file", "briefing", "court_annexure", "handover"] = "case_file"
    redaction_profile: Literal["protected", "identified"] = "protected"


class ReportResponse(BaseModel):
    id: str
    case_id: str
    version: int
    status: ProcessingState
    review_snapshot_hash: str
    redaction_profile: str
    profile: str
    created_at: datetime
    generated_at: datetime | None
    failure_reason: str | None

