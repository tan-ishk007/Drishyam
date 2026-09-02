"""Private in-app notification registers; outbound delivery remains intentionally absent."""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.entities import Notification, NotificationPreference
from app.schemas.notifications import NotificationPreferenceResponse, NotificationPreferenceUpdateRequest, NotificationResponse
from app.services.audit import audit
from app.services.cases import require_case_access


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
def list_notifications(current_user: CurrentUser, db: DbSession, case_id: str | None = Query(default=None)) -> list[NotificationResponse]:
    """List private in-app records for the current user only; no read-state or audit mutation occurs."""
    if case_id:
        require_case_access(db, case_id, current_user)
    statement = select(Notification).where(Notification.user_id == current_user.id)
    if case_id:
        statement = statement.where(Notification.case_id == case_id)
    return [NotificationResponse.model_validate(record, from_attributes=True) for record in db.scalars(statement.order_by(Notification.created_at.desc())).all()]


@router.get("/preferences", response_model=list[NotificationPreferenceResponse])
def list_notification_preferences(current_user: CurrentUser, db: DbSession) -> list[NotificationPreferenceResponse]:
    """List existing in-app preferences only; no defaults are inserted on read."""
    records = db.scalars(select(NotificationPreference).where(NotificationPreference.user_id == current_user.id).order_by(NotificationPreference.category)).all()
    return [NotificationPreferenceResponse.model_validate(record, from_attributes=True) for record in records]


@router.put("/preferences/{category}", response_model=NotificationPreferenceResponse)
def update_notification_preference(category: str, payload: NotificationPreferenceUpdateRequest, current_user: CurrentUser, db: DbSession) -> NotificationPreferenceResponse:
    """Create or update one in-app-only preference after an explicitly approved caller invokes this route."""
    normalized_category = category.strip().lower()
    if not normalized_category or len(normalized_category) > 80:
        raise HTTPException(status_code=422, detail="Notification category must be between 1 and 80 characters")
    preference = db.scalar(select(NotificationPreference).where(NotificationPreference.user_id == current_user.id, NotificationPreference.category == normalized_category))
    if preference:
        preference.in_app_enabled = payload.in_app_enabled
    else:
        preference = NotificationPreference(user_id=current_user.id, category=normalized_category, in_app_enabled=payload.in_app_enabled)
        db.add(preference)
        db.flush()
    audit(db, action="notification.preference_update", object_type="notification_preference", object_id=preference.id, case_id=None, outcome="success", actor_id=current_user.id, details={"category": normalized_category, "in_app_enabled": payload.in_app_enabled})
    db.commit()
    db.refresh(preference)
    return NotificationPreferenceResponse.model_validate(preference, from_attributes=True)
