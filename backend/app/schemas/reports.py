"""Report creation and status response contracts."""

from datetime import datetime

from pydantic import BaseModel

from app.models.entities import ProcessingState


class ReportResponse(BaseModel):
    id: str
    case_id: str
    version: int
    status: ProcessingState
    review_snapshot_hash: str
    redaction_profile: str
    created_at: datetime
    generated_at: datetime | None
    failure_reason: str | None

