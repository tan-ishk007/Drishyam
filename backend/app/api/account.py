"""Authenticated account profile, safe presentation preferences, and server-session records."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, bearer_scheme
from app.core.security import decode_access_token, utcnow
from app.models.entities import AccountSession, AccountSettings, AuditLog, RevokedToken
from app.schemas.auth import (
    AccountActivityResponse,
    AccountPreferencesResponse,
    AccountPreferencesUpdateRequest,
    AccountProfileResponse,
    AccountProfileUpdateRequest,
    AccountSecurityResponse,
    AccountSessionResponse,
    CurrentUserResponse,
)
from app.services.audit import audit


router = APIRouter(prefix="/auth/me", tags=["account"])


def _profile_response(current_user: CurrentUser, settings: AccountSettings | None, last_active_at) -> AccountProfileResponse:
    base = CurrentUserResponse.model_validate(current_user, from_attributes=True)
    return AccountProfileResponse(**base.model_dump(), phone=settings.phone if settings else None, last_active_at=last_active_at)


def _preferences_response(settings: AccountSettings | None) -> AccountPreferencesResponse:
    if not settings:
        return AccountPreferencesResponse()
    return AccountPreferencesResponse(
        language=settings.language,
        timezone=settings.timezone,
        date_format=settings.date_format,
        time_format=settings.time_format,
        items_per_page=settings.items_per_page,
        theme=settings.theme,
        updated_at=settings.updated_at,
    )


@router.get("/profile", response_model=AccountProfileResponse)
def get_profile(current_user: CurrentUser, db: DbSession) -> AccountProfileResponse:
    settings = db.scalar(select(AccountSettings).where(AccountSettings.user_id == current_user.id))
    last_active_at = db.scalar(select(func.max(AccountSession.last_active_at)).where(AccountSession.user_id == current_user.id))
    return _profile_response(current_user, settings, last_active_at)


@router.patch("/profile", response_model=AccountProfileResponse)
def update_profile(payload: AccountProfileUpdateRequest, current_user: CurrentUser, db: DbSession) -> AccountProfileResponse:
    if not payload.model_fields_set:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No profile changes were provided")
    settings = db.scalar(select(AccountSettings).where(AccountSettings.user_id == current_user.id))
    if not settings:
        settings = AccountSettings(user_id=current_user.id)
        db.add(settings)
        db.flush()
    changed_fields: list[str] = []
    if "name" in payload.model_fields_set and payload.name is not None:
        current_user.name = payload.name.strip()
        changed_fields.append("name")
    if "phone" in payload.model_fields_set:
        settings.phone = payload.phone.strip() if payload.phone else None
        changed_fields.append("phone")
    audit(db, action="account.profile_update", object_type="account_settings", object_id=settings.id, outcome="success", actor_id=current_user.id, details={"fields": changed_fields})
    db.commit()
    db.refresh(current_user)
    db.refresh(settings)
    last_active_at = db.scalar(select(func.max(AccountSession.last_active_at)).where(AccountSession.user_id == current_user.id))
    return _profile_response(current_user, settings, last_active_at)


@router.get("/preferences", response_model=AccountPreferencesResponse)
def get_preferences(current_user: CurrentUser, db: DbSession) -> AccountPreferencesResponse:
    settings = db.scalar(select(AccountSettings).where(AccountSettings.user_id == current_user.id))
    return _preferences_response(settings)


@router.patch("/preferences", response_model=AccountPreferencesResponse)
def update_preferences(payload: AccountPreferencesUpdateRequest, current_user: CurrentUser, db: DbSession) -> AccountPreferencesResponse:
    if not payload.model_fields_set:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No preference changes were provided")
    settings = db.scalar(select(AccountSettings).where(AccountSettings.user_id == current_user.id))
    if not settings:
        settings = AccountSettings(user_id=current_user.id)
        db.add(settings)
        db.flush()
    changed_fields: list[str] = []
    for field in ("language", "timezone", "date_format", "time_format", "items_per_page", "theme"):
        if field in payload.model_fields_set:
            setattr(settings, field, getattr(payload, field))
            changed_fields.append(field)
    audit(db, action="account.preference_update", object_type="account_settings", object_id=settings.id, outcome="success", actor_id=current_user.id, details={"fields": changed_fields})
    db.commit()
    db.refresh(settings)
    return _preferences_response(settings)


@router.get("/security", response_model=AccountSecurityResponse)
def get_security_posture(current_user: CurrentUser, db: DbSession) -> AccountSecurityResponse:
    active_session_count = db.scalar(select(func.count(AccountSession.id)).where(AccountSession.user_id == current_user.id, AccountSession.revoked_at.is_(None))) or 0
    return AccountSecurityResponse(
        password_configured=current_user.auth_provider == "password",
        email_verification_status="verified" if current_user.email_verified_at else "pending",
        two_factor_supported=False,
        session_management_supported=True,
        active_session_count=active_session_count,
    )


@router.get("/sessions", response_model=list[AccountSessionResponse])
def list_sessions(current_user: CurrentUser, db: DbSession, credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> list[AccountSessionResponse]:
    payload = decode_access_token(credentials.credentials)
    current_session_id = payload.get("sid")
    records = db.scalars(select(AccountSession).where(AccountSession.user_id == current_user.id).order_by(AccountSession.last_active_at.desc())).all()
    return [
        AccountSessionResponse(
            id=record.id,
            device_label=record.device_label,
            created_at=record.created_at,
            last_active_at=record.last_active_at,
            expires_at=record.expires_at,
            revoked_at=record.revoked_at,
            status="revoked" if record.revoked_at else "active",
            is_current=record.id == current_session_id,
        )
        for record in records
    ]


@router.post("/sessions/{session_id}/revoke", response_model=AccountSessionResponse)
def revoke_other_session(session_id: str, current_user: CurrentUser, db: DbSession, credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> AccountSessionResponse:
    payload = decode_access_token(credentials.credentials)
    if payload.get("sid") == session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use sign out to end the current session")
    record = db.get(AccountSession, session_id)
    if not record or record.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if not record.revoked_at:
        record.revoked_at = utcnow()
        db.add(RevokedToken(token_id=record.token_id, user_id=current_user.id, expires_at=record.expires_at))
        audit(db, action="account.session_revoke", object_type="account_session", object_id=record.id, outcome="success", actor_id=current_user.id)
        db.commit()
        db.refresh(record)
    return AccountSessionResponse(
        id=record.id,
        device_label=record.device_label,
        created_at=record.created_at,
        last_active_at=record.last_active_at,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        status="revoked" if record.revoked_at else "active",
        is_current=False,
    )


@router.get("/activity", response_model=list[AccountActivityResponse])
def list_account_activity(current_user: CurrentUser, db: DbSession, limit: int = Query(default=50, ge=1, le=200)) -> list[AccountActivityResponse]:
    records = db.scalars(select(AuditLog).where(AuditLog.actor_id == current_user.id, AuditLog.case_id.is_(None)).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    return [AccountActivityResponse(id=record.id, action=record.action, object_type=record.object_type, object_id=record.object_id, outcome=record.outcome, created_at=record.created_at) for record in records]
