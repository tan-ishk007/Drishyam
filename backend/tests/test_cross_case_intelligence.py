"""Synthetic, read-only authorization coverage for cross-case intelligence."""

from uuid import uuid4

from app.core.db import SessionLocal
from app.core.security import create_access_token, hash_password
from app.models.entities import AccountStatus, Priority, Role, User


def _headers(name: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        user = User(
            name=name,
            email=f"{name.lower().replace(' ', '.')}.{uuid4().hex[:12]}@example.com",
            password_hash=hash_password("SyntheticOnlyPassword!2026"),
            role=Role.INVESTIGATOR,
            status=AccountStatus.ACTIVE,
        )
        db.add(user)
        db.commit()
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}
    finally:
        db.close()


def _case(client, headers: dict[str, str], title: str) -> dict:
    response = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"title": title, "crime_type": "synthetic_cross_case_test", "priority": Priority.HIGH.value},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, case_id, headers, filename, content):
    response = client.post(
        f"/api/v1/cases/{case_id}/evidence",
        headers=headers,
        data={"source_category": "whatsapp_chat"},
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_cross_case_links_return_exact_authorized_synthetic_matches_only(client):
    headers = _headers("Synthetic Cross Case Owner")
    first_case = _case(client, headers, "Synthetic cross-case first")
    second_case = _case(client, headers, "Synthetic cross-case second")
    shared_text = b"SYNTHETIC TRAINING ONLY. UPI fraudcollect@upi. Phone +91 9876543210. UTR: ABCD1234EFGH."
    _upload(client, first_case["id"], headers, "synthetic-first.txt", shared_text)
    _upload(client, second_case["id"], headers, "synthetic-second.txt", shared_text)

    response = client.get(f"/api/v1/cases/{first_case['id']}/cross-case-links", headers=headers)
    assert response.status_code == 200, response.text
    links = response.json()
    assert {item["signal_type"] for item in links} >= {"upi_id", "phone", "utr", "evidence_sha256"}
    assert all(item["linked_case"]["id"] == second_case["id"] for item in links)
    assert all("not an identity or culpability finding" in item["explanation"] or "not a conclusion" in item["explanation"] for item in links)


def test_cross_case_links_never_disclose_inaccessible_case_metadata(client):
    owner_headers = _headers("Synthetic Access Owner")
    outsider_headers = _headers("Synthetic Cross Case Outsider")
    visible_case = _case(client, owner_headers, "Synthetic visible case")
    authorized_related_case = _case(client, owner_headers, "Synthetic authorized related case")
    inaccessible_case = _case(client, outsider_headers, "Synthetic inaccessible case")
    shared = b"SYNTHETIC ONLY. UPI visibilitycheck@upi."
    _upload(client, visible_case["id"], owner_headers, "synthetic-visible.txt", shared)
    _upload(client, authorized_related_case["id"], owner_headers, "synthetic-authorized-related.txt", shared)
    _upload(client, inaccessible_case["id"], outsider_headers, "synthetic-hidden.txt", shared)

    response = client.get(f"/api/v1/cases/{visible_case['id']}/cross-case-links", headers=owner_headers)
    assert response.status_code == 200, response.text
    linked_case_ids = {item["linked_case"]["id"] for item in response.json()}
    assert authorized_related_case["id"] in linked_case_ids
    assert inaccessible_case["id"] not in linked_case_ids
