"""Read-only contracts for private in-app notification records and preferences."""

from datetime import datetime

from pydantic import BaseModel

from app.models.entities import NotificationLevel


class NotificationResponse(BaseModel):
    id: str
    case_id: str | None
    category: str
    level: NotificationLevel
    title: str
    body: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationPreferenceResponse(BaseModel):
    id: str
    category: str
    in_app_enabled: bool
    created_at: datetime
    updated_at: datetime


class NotificationPreferenceUpdateRequest(BaseModel):
    in_app_enabled: bool
