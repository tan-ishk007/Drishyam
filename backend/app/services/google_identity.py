"""Server-side verification for Google Identity Services ID tokens."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings


settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    name: str
    hosted_domain: str | None


def _tokeninfo_fallback(credential: str) -> dict:
    """Ask Google, the token issuer, to validate an ID token if local JWKS validation fails.

    The credential is never logged or returned. The configured audience plus the
    issuer, verified-email, and optional domain checks below remain mandatory.
    """
    try:
        response = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": credential},
            timeout=10.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("google_tokeninfo_fallback_failed category=%s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google identity token could not be verified") from exc
    if payload.get("aud") != settings.google_client_id:
        logger.warning("google_tokeninfo_audience_mismatch")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google sign-in client configuration does not match this token")
    return payload


def _verified_email_claim(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "true")


def verify_google_credential(credential: str) -> GoogleIdentity:
    """Verify signature, audience, issuer, expiry, and authoritative email claims.

    The Google subject is the durable identity key. Email is retained for contact and
    display after Google has established it as authoritative for Gmail or Workspace.
    """
    if not settings.google_client_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Google sign-in is not configured")
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        payload = id_token.verify_oauth2_token(credential, google_requests.Request(), settings.google_client_id)
    except Exception as exc:
        logger.warning("google_id_token_primary_validation_failed category=%s", type(exc).__name__)
        payload = _tokeninfo_fallback(credential)
    if payload.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google identity issuer is invalid")
    subject = str(payload.get("sub") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    hosted_domain = str(payload.get("hd") or "").strip().lower() or None
    if not subject or not email or not _verified_email_claim(payload.get("email_verified")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google account email is not verified")
    if settings.google_allowed_workspace_domain and hosted_domain != settings.google_allowed_workspace_domain.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Google Workspace domain is not authorized")
    if not hosted_domain and not email.endswith("@gmail.com"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Use email OTP to verify this non-Gmail account")
    return GoogleIdentity(subject=subject, email=email, name=str(payload.get("name") or email.split("@", 1)[0]).strip()[:160], hosted_domain=hosted_domain)
