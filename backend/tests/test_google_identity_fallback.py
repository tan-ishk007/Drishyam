"""Offline regression tests for the constrained Google token-info fallback."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from google.oauth2 import id_token

from app.services import google_identity


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def _force_primary_validation_failure(*_args: object, **_kwargs: object) -> None:
    raise ValueError("synthetic primary validation failure")


def test_google_tokeninfo_fallback_accepts_only_verified_matching_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(google_identity, "settings", SimpleNamespace(google_client_id="test-client.apps.googleusercontent.com", google_allowed_workspace_domain=None))
    monkeypatch.setattr(id_token, "verify_oauth2_token", _force_primary_validation_failure)
    monkeypatch.setattr(google_identity.httpx, "get", lambda *_args, **_kwargs: _Response({"aud": "test-client.apps.googleusercontent.com", "iss": "https://accounts.google.com", "sub": "subject-123", "email": "verified@gmail.com", "email_verified": "true", "name": "Verified Test"}))

    identity = google_identity.verify_google_credential("synthetic-token")

    assert identity.subject == "subject-123"
    assert identity.email == "verified@gmail.com"


def test_google_tokeninfo_fallback_rejects_wrong_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(google_identity, "settings", SimpleNamespace(google_client_id="test-client.apps.googleusercontent.com", google_allowed_workspace_domain=None))
    monkeypatch.setattr(id_token, "verify_oauth2_token", _force_primary_validation_failure)
    monkeypatch.setattr(google_identity.httpx, "get", lambda *_args, **_kwargs: _Response({"aud": "other-client.apps.googleusercontent.com", "iss": "https://accounts.google.com", "sub": "subject-123", "email": "verified@gmail.com", "email_verified": "true"}))

    with pytest.raises(HTTPException) as error:
        google_identity.verify_google_credential("synthetic-token")

    assert error.value.status_code == 401
