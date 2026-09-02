"""Integration-test environment for the standalone PostgreSQL-backed backend."""

import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / ".test_data"
os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "postgresql+psycopg://drishyam:drishyam@localhost:5432/drishyam")
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["EMAIL_PROVIDER"] = "console"
os.environ["ALLOW_LOCAL_CONSOLE_EMAIL"] = "true"
os.environ["ENVIRONMENT"] = "development"
os.environ["STORAGE_ROOT"] = str(TEST_DATA / "private_storage")
os.environ["GENERATED_REPORTS_ROOT"] = str(TEST_DATA / "reports")

from app.core.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database_and_storage():
    shutil.rmtree(TEST_DATA, ignore_errors=True)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    yield
    shutil.rmtree(TEST_DATA, ignore_errors=True)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def latest_otp(email: str) -> str:
    mailbox = TEST_DATA / "dev_mailbox"
    messages = sorted(mailbox.glob("verification-*.json"), key=lambda path: path.stat().st_mtime)
    for message in reversed(messages):
        payload = json.loads(message.read_text(encoding="utf-8"))
        if payload["to"] == email:
            return payload["verification_code"]
    raise AssertionError("No verification code found for test account")


@pytest.fixture
def account(client):
    def _create(name: str = "Test Investigator") -> tuple[str, dict[str, str]]:
        email = f"{name.lower().replace(' ', '.')}.{uuid4().hex[:10]}@example.com"
        response = client.post("/api/v1/auth/signup", json={"name": name, "email": email, "password": "TestingBackendPassword!2026", "role": "investigator"})
        assert response.status_code == 201, response.text
        verified = client.post("/api/v1/auth/verify", json={"email": email, "otp": latest_otp(email)})
        assert verified.status_code == 200, verified.text
        return email, {"Authorization": f"Bearer {verified.json()['access_token']}"}
    return _create


@pytest.fixture
def case_factory(client, account):
    def _create(headers: dict[str, str] | None = None) -> tuple[dict, dict[str, str]]:
        if headers is None:
            _, headers = account()
        response = client.post("/api/v1/cases", headers=headers, json={"title": "Synthetic test investigation", "crime_type": "job_offer_fraud", "description": "SYNTHETIC TEST DESCRIPTION ONLY.", "priority": "high"})
        assert response.status_code == 201, response.text
        return response.json(), headers
    return _create
