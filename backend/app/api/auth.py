"""Verified identity, email OTP, Google sign-in, and server-tracked JWT session endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hmac import compare_digest
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, bearer_scheme
from app.core.config import get_settings
from app.core.security import create_access_token, create_otp, decode_access_token, hash_otp, hash_password, utcnow, verify_password
from app.models.entities import AccountSession, AccountStatus, RevokedToken, Role, User, VerificationCode
from app.schemas.auth import CurrentUserResponse, GoogleSignInRequest, LoginRequest, OtpRequest, SignupRequest, SignupResponse, TokenResponse, VerifyRequest
from app.services.audit import audit
from app.services.email import get_email_provider
from app.services.google_identity import verify_google_credential


router = APIRouter(prefix="/auth", tags=["authentication"])
settings = get_settings()
SIGNUP_PURPOSE = "signup_verification"
LOGIN_PURPOSE = "login_otp"


@router.get("/config")
def public_auth_config() -> dict[str, str | None]:
    """Return browser-safe identity configuration only; no secret is exposed."""
    return {"google_client_id": settings.google_client_id}


def _token_for(db: DbSession, user: User, request: Request) -> TokenResponse:
    """Issue a token bound to a persisted session record; raw tokens are never stored."""
    user_agent = (request.headers.get("user-agent") or "Browser session").strip()
    account_session = AccountSession(user_id=user.id, token_id="pending", device_label=user_agent[:255], expires_at=utcnow())
    db.add(account_session)
    db.flush()
    token = create_access_token(user.id, user.role.value, session_id=account_session.id)
    payload = decode_access_token(token)
    account_session.token_id = payload["jti"]
    account_session.expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    audit(
        db,
        action="account.session_issued",
        object_type="account_session",
        object_id=account_session.id,
        outcome="success",
        actor_id=user.id,
        details={"auth_provider": user.auth_provider},
    )
    db.commit()
    return TokenResponse(access_token=token, expires_in_seconds=settings.access_token_expire_minutes * 60)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _issue_otp(db: DbSession, user: User, purpose: str) -> str:
    """Invalidate prior unused codes and create one bounded-lifetime OTP for one purpose."""
    existing = db.scalars(
        select(VerificationCode)
        .where(VerificationCode.user_id == user.id, VerificationCode.purpose == purpose, VerificationCode.consumed_at.is_(None))
        .order_by(VerificationCode.created_at.desc())
    ).all()
    if existing and _as_utc(existing[0].created_at) > utcnow() - timedelta(seconds=settings.otp_request_cooldown_seconds):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Please wait before requesting another code")
    now = utcnow()
    for previous in existing:
        previous.consumed_at = now
    code = create_otp()
    db.add(
        VerificationCode(
            user_id=user.id,
            purpose=purpose,
            code_hash=hash_otp(code),
            expires_at=now + timedelta(minutes=settings.otp_expire_minutes),
        )
    )
    return code


def _send_otp_or_raise(db: DbSession, user: User, code: str, purpose: str) -> None:
    try:
        get_email_provider().send_otp(user.email, code, purpose=purpose)
    except Exception as exc:
        audit(
            db,
            action="account.otp_delivery",
            object_type="user",
            object_id=user.id,
            outcome="failed",
            actor_id=user.id,
            details={"provider": settings.email_provider, "purpose": purpose},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Verification email delivery is unavailable") from exc


def _verify_otp(db: DbSession, user: User, otp: str, purpose: str, request: Request) -> TokenResponse:
    verification = db.scalar(
        select(VerificationCode)
        .where(
            VerificationCode.user_id == user.id,
            VerificationCode.purpose == purpose,
            VerificationCode.consumed_at.is_(None),
        )
        .order_by(VerificationCode.created_at.desc())
    )
    if not verification or _as_utc(verification.expires_at) < utcnow() or verification.attempts >= settings.otp_max_attempts:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Verification code is expired or unavailable")
    verification.attempts += 1
    if not compare_digest(verification.code_hash, hash_otp(otp)):
        audit(db, action="account.otp_verify", object_type="user", object_id=user.id, outcome="failed", actor_id=user.id, details={"purpose": purpose})
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code")
    verification.consumed_at = utcnow()
    if purpose == SIGNUP_PURPOSE:
        user.status = AccountStatus.ACTIVE
        user.email_verified_at = utcnow()
        audit(db, action="account.verify_email", object_type="user", object_id=user.id, outcome="success", actor_id=user.id)
    else:
        audit(db, action="account.otp_login", object_type="user", object_id=user.id, outcome="success", actor_id=user.id)
    db.commit()
    return _token_for(db, user, request)


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: DbSession) -> SignupResponse:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        role=Role.INVESTIGATOR,
        auth_provider="password",
    )
    db.add(user)
    db.flush()
    code = _issue_otp(db, user, SIGNUP_PURPOSE)
    audit(db, action="account.signup", object_type="user", object_id=user.id, outcome="success", actor_id=user.id, details={"role": user.role.value})
    db.commit()
    _send_otp_or_raise(db, user, code, SIGNUP_PURPOSE)
    return SignupResponse(user_id=user.id, email=user.email, status=user.status, message="Verification code issued")


@router.post("/verify", response_model=TokenResponse)
def verify_account(payload: VerifyRequest, db: DbSession, request: Request) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or user.status != AccountStatus.PENDING_VERIFICATION:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification attempt")
    return _verify_otp(db, user, payload.otp, SIGNUP_PURPOSE, request)


@router.post("/verification/resend", status_code=status.HTTP_202_ACCEPTED)
def resend_signup_verification(payload: OtpRequest, db: DbSession) -> dict[str, str]:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or user.status != AccountStatus.PENDING_VERIFICATION:
        return {"message": "If an eligible account exists, a verification email has been issued"}
    code = _issue_otp(db, user, SIGNUP_PURPOSE)
    audit(db, action="account.verification_resend", object_type="user", object_id=user.id, outcome="success", actor_id=user.id)
    db.commit()
    _send_otp_or_raise(db, user, code, SIGNUP_PURPOSE)
    return {"message": "If an eligible account exists, a verification email has been issued"}


@router.post("/otp/request", status_code=status.HTTP_202_ACCEPTED)
def request_login_otp(payload: OtpRequest, db: DbSession) -> dict[str, str]:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or user.status != AccountStatus.ACTIVE:
        return {"message": "If an active account exists, a sign-in code has been issued"}
    code = _issue_otp(db, user, LOGIN_PURPOSE)
    audit(db, action="account.otp_requested", object_type="user", object_id=user.id, outcome="success", actor_id=user.id)
    db.commit()
    _send_otp_or_raise(db, user, code, LOGIN_PURPOSE)
    return {"message": "If an active account exists, a sign-in code has been issued"}


@router.post("/otp/verify", response_model=TokenResponse)
def verify_login_otp(payload: VerifyRequest, db: DbSession, request: Request) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or user.status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid sign-in attempt")
    return _verify_otp(db, user, payload.otp, LOGIN_PURPOSE, request)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession, request: Request) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        audit(db, action="account.login", object_type="user", object_id=user.id if user else None, outcome="failed")
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account must be verified before login")
    audit(db, action="account.login", object_type="user", object_id=user.id, outcome="success", actor_id=user.id)
    db.commit()
    return _token_for(db, user, request)


@router.post("/google", response_model=TokenResponse)
def google_sign_in(payload: GoogleSignInRequest, db: DbSession, request: Request) -> TokenResponse:
    identity = verify_google_credential(payload.credential)
    user = db.scalar(select(User).where(User.google_subject == identity.subject))
    if not user:
        existing_email = db.scalar(select(User).where(User.email == identity.email))
        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This email already has a password account; use email sign-in first")
        user = User(
            name=identity.name,
            email=identity.email,
            password_hash=hash_password(token_urlsafe(48)),
            role=Role.INVESTIGATOR,
            status=AccountStatus.ACTIVE,
            auth_provider="google",
            google_subject=identity.subject,
            email_verified_at=utcnow(),
        )
        db.add(user)
        db.flush()
        outcome = "created"
    elif user.status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
    else:
        outcome = "success"
    audit(db, action="account.google_signin", object_type="user", object_id=user.id, outcome=outcome, actor_id=user.id)
    db.commit()
    return _token_for(db, user, request)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: CurrentUser, db: DbSession, credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> Response:
    payload = decode_access_token(credentials.credentials)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    db.add(RevokedToken(token_id=payload["jti"], user_id=current_user.id, expires_at=expires_at))
    session_id = payload.get("sid")
    if session_id:
        account_session = db.get(AccountSession, session_id)
        if account_session and account_session.user_id == current_user.id:
            account_session.revoked_at = utcnow()
    audit(db, action="account.logout", object_type="account_session", object_id=session_id, outcome="success", actor_id=current_user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user, from_attributes=True)
