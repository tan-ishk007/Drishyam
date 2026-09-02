"""Protected request dependencies for real JWT sessions and case object authorization."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token, utcnow
from app.models.entities import AccountSession, AccountStatus, RevokedToken, User

bearer_scheme = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)], db: DbSession
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer authentication is required")
    payload = decode_access_token(credentials.credentials)
    if db.scalar(select(RevokedToken).where(RevokedToken.token_id == payload["jti"])):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")
    user = db.get(User, payload["sub"])
    if not user or user.status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is not active")
    session_id = payload.get("sid")
    if session_id:
        account_session = db.get(AccountSession, session_id)
        if not account_session or account_session.user_id != user.id or account_session.token_id != payload["jti"] or account_session.revoked_at:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")
        account_session.last_active_at = utcnow()
        db.commit()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
