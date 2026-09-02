"""Gmail API authorization and sending primitives with no credential logging."""

from __future__ import annotations

import json
import logging
import os
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
_STATE_ALGORITHM = "HS256"
_STATE_PURPOSE = "gmail_api_setup"


class GmailApiConfigurationError(RuntimeError):
    """Raised only when required local Gmail API setup values are absent."""


class GmailApiDeliveryError(RuntimeError):
    """Raised for safe-to-report Gmail API authorization or delivery failures."""


def _secret(value) -> str:
    return value.get_secret_value().strip() if value else ""


def _configuration() -> tuple[str, str, str]:
    client_id = (settings.gmail_api_client_id or "").strip()
    client_secret = _secret(settings.gmail_api_client_secret)
    sender = (settings.gmail_api_sender or "").strip()
    if not client_id or not client_secret or not sender:
        raise GmailApiConfigurationError(
            "GMAIL_API_CLIENT_ID, GMAIL_API_CLIENT_SECRET, and GMAIL_API_SENDER are required when EMAIL_PROVIDER=gmail_api"
        )
    return client_id, client_secret, sender


def _token_file() -> Path:
    return Path(settings.gmail_api_token_file)


def has_authorization() -> bool:
    try:
        _read_refresh_token()
    except GmailApiConfigurationError:
        return False
    return True


def _read_refresh_token() -> str:
    path = _token_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        token = payload.get("refresh_token") if isinstance(payload, dict) else None
    except (OSError, ValueError, TypeError) as exc:
        raise GmailApiConfigurationError("Gmail API sender has not been authorized locally") from exc
    if not isinstance(token, str) or not token.strip():
        raise GmailApiConfigurationError("Gmail API sender has not been authorized locally")
    return token.strip()


def _write_refresh_token(refresh_token: str) -> None:
    path = _token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"refresh_token": refresh_token, "authorized_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)


def authorization_url() -> str:
    client_id, _, _ = _configuration()
    payload = {
        "purpose": _STATE_PURPOSE,
        "nonce": token_urlsafe(24),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    state = jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=_STATE_ALGORITHM)
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": settings.gmail_api_redirect_uri,
            "response_type": "code",
            "scope": GMAIL_SEND_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"


def exchange_and_store_authorization_code(code: str, state: str) -> None:
    try:
        payload = jwt.decode(state, settings.secret_key.get_secret_value(), algorithms=[_STATE_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise GmailApiConfigurationError("Gmail API authorization request is invalid or expired") from exc
    if payload.get("purpose") != _STATE_PURPOSE or not payload.get("nonce"):
        raise GmailApiConfigurationError("Gmail API authorization request is invalid or expired")
    client_id, client_secret, _ = _configuration()
    try:
        response = httpx.post(
            GMAIL_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": settings.gmail_api_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
    except httpx.HTTPError as exc:
        logger.warning("Gmail API authorization exchange unavailable: error_class=%s", type(exc).__name__)
        raise GmailApiDeliveryError("Gmail API authorization exchange is unavailable") from exc
    if response.status_code != 200:
        logger.warning("Gmail API authorization exchange rejected: http_status=%s", response.status_code)
        raise GmailApiDeliveryError("Gmail API authorization exchange was rejected")
    refresh_token = response.json().get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        logger.warning("Gmail API authorization did not return a refresh token")
        raise GmailApiDeliveryError("Gmail API authorization did not complete")
    _write_refresh_token(refresh_token)
    logger.info("Gmail API sender authorization stored in protected local Docker volume")


def _access_token(client: httpx.Client) -> str:
    client_id, client_secret, _ = _configuration()
    response = client.post(
        GMAIL_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": _read_refresh_token(),
            "grant_type": "refresh_token",
        },
    )
    if response.status_code != 200:
        logger.warning("Gmail API refresh-token exchange rejected: http_status=%s", response.status_code)
        raise GmailApiDeliveryError("Gmail API sender authorization needs to be renewed")
    token = response.json().get("access_token")
    if not isinstance(token, str) or not token:
        logger.warning("Gmail API refresh-token exchange returned no access token")
        raise GmailApiDeliveryError("Gmail API sender authorization needs to be renewed")
    return token


def send_message(message: EmailMessage) -> None:
    """Send a precomposed message through Gmail HTTPS without logging its content."""
    _configuration()
    encoded = urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
    try:
        with httpx.Client(timeout=15) as client:
            access_token = _access_token(client)
            response = client.post(
                GMAIL_SEND_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": encoded},
            )
    except httpx.HTTPError as exc:
        logger.warning("Gmail API OTP connection failure: error_class=%s", type(exc).__name__)
        raise GmailApiDeliveryError("Gmail API connection failed") from exc
    if response.status_code not in {200, 202}:
        logger.warning("Gmail API OTP delivery rejected: http_status=%s", response.status_code)
        raise GmailApiDeliveryError("Gmail API rejected OTP delivery")
    logger.info("Gmail API accepted a transactional OTP message")
