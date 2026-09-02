"""Isolated Gmail API provider tests; no real OAuth credentials or email delivery are used."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr

from app.services import gmail_api
from app.services import email
from app.services.email import GmailApiProvider


class _Response:
    def __init__(self, status_code: int, body: dict[str, str]):
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, str]:
        return self._body


class _Client:
    calls: list[tuple[str, dict]] = []

    def __init__(self, timeout: int):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if url == gmail_api.GMAIL_TOKEN_URL:
            return _Response(200, {"access_token": "synthetic-access-token"})
        return _Response(200, {"id": "synthetic-message-id"})


def test_gmail_api_provider_uses_https_and_never_places_otp_in_logs(monkeypatch, tmp_path: Path):
    token_file = tmp_path / "gmail-token.json"
    token_file.write_text(json.dumps({"refresh_token": "synthetic-refresh-token"}), encoding="utf-8")
    fake_settings = SimpleNamespace(
        gmail_api_client_id="synthetic-client-id",
        gmail_api_client_secret=SecretStr("synthetic-client-secret"),
        gmail_api_sender="sender@example.test",
        gmail_api_token_file=token_file,
        gmail_api_redirect_uri="http://127.0.0.1:8000/api/v1/system/gmail-api/callback",
        secret_key=SecretStr("synthetic-state-key"),
    )
    _Client.calls = []
    monkeypatch.setattr(gmail_api, "settings", fake_settings)
    monkeypatch.setattr(email, "settings", fake_settings)
    monkeypatch.setattr(gmail_api.httpx, "Client", _Client)
    GmailApiProvider().send_otp("recipient@example.test", "654321", purpose="signup_verification")
    assert [url for url, _ in _Client.calls] == [gmail_api.GMAIL_TOKEN_URL, gmail_api.GMAIL_SEND_URL]
    raw = _Client.calls[-1][1]["json"]["raw"]
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
    assert "654321" in decoded
    assert "recipient@example.test" in decoded
