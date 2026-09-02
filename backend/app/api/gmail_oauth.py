"""Local-only one-time Gmail API authorization endpoints for the prototype sender."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.gmail_api import GmailApiConfigurationError, GmailApiDeliveryError, authorization_url, exchange_and_store_authorization_code

router = APIRouter(prefix="/system/gmail-api", tags=["local setup"])


@router.get("/start", include_in_schema=False)
def start_gmail_api_authorization() -> RedirectResponse:
    """Redirect only a local browser to Google’s consent flow; no access tokens enter the frontend."""
    try:
        return RedirectResponse(authorization_url(), status_code=status.HTTP_302_FOUND)
    except GmailApiConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gmail API setup is incomplete") from exc


@router.get("/callback", include_in_schema=False)
def complete_gmail_api_authorization(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> HTMLResponse:
    """Store the refresh token inside the local Docker volume and disclose no token material."""
    if error or not code or not state:
        return HTMLResponse("<h1>Gmail authorization was cancelled or could not complete.</h1>", status_code=status.HTTP_400_BAD_REQUEST)
    try:
        exchange_and_store_authorization_code(code, state)
    except GmailApiConfigurationError:
        return HTMLResponse("<h1>Gmail authorization link is invalid or expired. Start again locally.</h1>", status_code=status.HTTP_400_BAD_REQUEST)
    except GmailApiDeliveryError:
        return HTMLResponse("<h1>Gmail authorization could not complete. Check local backend logs for the safe failure category.</h1>", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return HTMLResponse(
        "<h1>Gmail API is connected.</h1><p>You may close this tab and return to DRISHYAM. No credentials were displayed.</p>",
        status_code=status.HTTP_200_OK,
    )
