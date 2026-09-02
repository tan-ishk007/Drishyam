"""Synthetic authentication tests for verified-user-only case access."""

from app.models.entities import Role

from tests.conftest import latest_otp


def _signup(client, email: str, *, role: str | None = None):
    payload = {"name": "Synthetic Identity", "email": email, "password": "SyntheticAuthPassword!2026"}
    if role:
        payload["role"] = role
    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201, response.text
    return response


def _verify(client, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/verify", json={"email": email, "otp": latest_otp(email)})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_signup_forces_investigator_and_blocks_unverified_access(client):
    email = "synthetic.role.boundary@example.com"
    _signup(client, email, role="admin")
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "SyntheticAuthPassword!2026"}).status_code == 403
    headers = _verify(client, email)
    profile = client.get("/api/v1/auth/me", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["role"] == Role.INVESTIGATOR.value
    assert profile.json()["status"] == "active"
    assert profile.json()["auth_provider"] == "password"
    assert profile.json()["email_verified_at"]


def test_email_otp_login_creates_active_in_memory_session_token(client):
    email = "synthetic.otp.login@example.com"
    _signup(client, email)
    _verify(client, email)
    request = client.post("/api/v1/auth/otp/request", json={"email": email})
    assert request.status_code == 202, request.text
    login = client.post("/api/v1/auth/otp/verify", json={"email": email, "otp": latest_otp(email)})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).json()["email"] == email


def test_signup_code_can_be_used_during_resend_cooldown(client):
    email = "synthetic.signup.cooldown@example.com"
    _signup(client, email)
    resend = client.post("/api/v1/auth/verification/resend", json={"email": email})
    assert resend.status_code == 429, resend.text
    verified = client.post("/api/v1/auth/verify", json={"email": email, "otp": latest_otp(email)})
    assert verified.status_code == 200, verified.text


def test_google_sign_in_stays_disabled_until_a_real_client_is_configured(client):
    response = client.post("/api/v1/auth/google", json={"credential": "x" * 120})
    assert response.status_code == 503
    assert response.json()["detail"] == "Google sign-in is not configured"
