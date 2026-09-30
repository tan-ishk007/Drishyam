"""Asking whether another force is already looking for the same identity.

The profile's own "known to other cases" section lists cases the reader can already open. This is
the other half and the harder one: a district whose file this reader may never see. The ledger can
answer it because it holds nothing that could carry an answer to any other question -- a keyed
digest, a case reference, a contact.

So the tests that matter here are the refusals. No field of the other case may appear. A reader
outside this case gets nothing. The check is recorded, because an officer who runs it has learned
that another force's case exists, which is not nothing even when the answer is no. And a number
written four ways is one identity, or the whole thing answers by accident of typing.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.entities import Entity
from scripts import benchmark_case

SHARED_KEY = "synthetic-test-key-shared-between-districts"
CONTACT = "SI Test Officer, 022-0000-0000"
NUMBER = "+919876543210"


@pytest.fixture
def open_gate(monkeypatch):
    from pydantic import SecretStr

    settings = get_settings()
    monkeypatch.setattr(settings, "ledger_enabled", True)
    monkeypatch.setattr(settings, "ledger_publication", "enabled")
    monkeypatch.setattr(settings, "ledger_key", SecretStr(SHARED_KEY))
    return True


def _cdr_case(client, case_factory, headers=None):
    case, headers = case_factory(headers)
    with next(item for item in benchmark_case.generate().values() if "cdr" in item.name).open("rb") as stream:
        client.post(
            f"/api/v1/cases/{case['id']}/evidence",
            headers=headers,
            data={"source_category": "cdr"},
            files={"file": ("cdr_synthetic.csv", stream, "application/octet-stream")},
        )
    return case, headers


def _entity_id(case_id: str, value: str) -> str:
    db = SessionLocal()
    try:
        found = db.scalar(select(Entity).where(Entity.case_id == case_id, Entity.value == value))
        assert found is not None, f"{value} is not in this case"
        return found.id
    finally:
        db.close()


def _ask(client, case, headers, value: str) -> dict:
    entity_id = _entity_id(case["id"], value)
    response = client.get(
        f"/api/v1/cases/{case['id']}/grounded/entities/{entity_id}/elsewhere", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def two_districts(client, case_factory, account, open_gate):
    """One force has published; another holds the same number and does not know it."""
    theirs, their_headers = _cdr_case(client, case_factory)
    published = client.post(
        f"/api/v1/cases/{theirs['id']}/ledger/publish", headers=their_headers, json={"contact": CONTACT}
    )
    assert published.status_code == 200, published.text

    _, our_headers = account()
    ours, our_headers = _cdr_case(client, case_factory, our_headers)
    return ours, our_headers, theirs


# --------------------------------------------------------------------------- the answer


def test_another_force_holding_the_same_number_is_reported(client, two_districts) -> None:
    ours, our_headers, theirs = two_districts
    body = _ask(client, ours, our_headers, NUMBER)

    assert body["available"] is True
    assert body["matches"], "the other district published this exact number"
    assert body["matches"][0]["case_reference"] == theirs["case_number"]
    assert body["matches"][0]["contact"] == CONTACT


def test_nothing_of_the_other_case_appears(client, two_districts) -> None:
    """The load-bearing refusal."""
    ours, our_headers, theirs = two_districts
    body = _ask(client, ours, our_headers, NUMBER)

    rendered = str(body)
    assert theirs["id"] not in rendered, "the other case's id is not the reader's to have"
    assert theirs["title"] not in rendered
    assert theirs["crime_type"] not in rendered
    for match in body["matches"]:
        assert set(match.keys()) == {"case_reference", "contact", "published_at", "your_identity"}


def test_the_caveat_is_on_screen_not_left_to_be_inferred(client, two_districts) -> None:
    ours, our_headers, _ = two_districts
    body = _ask(client, ours, our_headers, NUMBER)

    assert "cannot say what their case is" in body["caveat"]


def test_an_identity_nobody_published_says_so_carefully(client, two_districts) -> None:
    """Absence from the ledger is not absence from the world, and the wording keeps that apart."""
    ours, our_headers, _ = two_districts
    db = SessionLocal()
    try:
        other = db.scalar(
            select(Entity).where(Entity.case_id == ours["id"], Entity.entity_type == "phone", Entity.value != NUMBER)
        )
        assert other is not None
        value = other.value
    finally:
        db.close()

    body = _ask(client, ours, our_headers, value)
    if not body["matches"]:
        assert "not a statement about cases whose force has not published" in body["note"]


def test_a_case_is_not_told_about_itself(client, case_factory, open_gate) -> None:
    ours, our_headers = _cdr_case(client, case_factory)
    client.post(f"/api/v1/cases/{ours['id']}/ledger/publish", headers=our_headers, json={"contact": CONTACT})

    assert _ask(client, ours, our_headers, NUMBER)["matches"] == []


# --------------------------------------------------------------------------- matching across spellings


def test_the_same_number_written_differently_still_matches(client, case_factory, account, open_gate) -> None:
    """Two districts type a number differently. It is one identity or the feature answers by luck."""
    theirs, their_headers = _cdr_case(client, case_factory)
    client.post(f"/api/v1/cases/{theirs['id']}/ledger/publish", headers=their_headers, json={"contact": CONTACT})

    _, our_headers = account()
    ours, our_headers = case_factory(our_headers)
    db = SessionLocal()
    try:
        # The same subscriber, written the way a different clerk would write it.
        upload = client.post(
            f"/api/v1/cases/{ours['id']}/evidence",
            headers=our_headers,
            data={"source_category": "other"},
            files={"file": ("note.txt", b"SYNTHETIC TEST ONLY. Contact 09876543210 for details.", "text/plain")},
        )
        assert upload.status_code == 201, upload.text
        written = db.scalar(
            select(Entity).where(Entity.case_id == ours["id"], Entity.entity_type == "phone")
        )
    finally:
        db.close()

    assert written is not None, "the number should have been extracted from the note"
    response = client.get(
        f"/api/v1/cases/{ours['id']}/grounded/entities/{written.id}/elsewhere", headers=our_headers
    )
    assert response.json()["matches"], f"{written.value} should reach the same digest as {NUMBER}"


# --------------------------------------------------------------------------- refusals


def test_an_outsider_is_told_nothing(client, two_districts, account) -> None:
    ours, _, _ = two_districts
    _, outsider = account()
    entity_id = _entity_id(ours["id"], NUMBER)
    response = client.get(
        f"/api/v1/cases/{ours['id']}/grounded/entities/{entity_id}/elsewhere", headers=outsider
    )
    assert response.status_code in {403, 404}


def test_the_check_is_recorded(client, two_districts) -> None:
    """An officer who runs this has learned another force's case exists. That is an access event."""
    ours, our_headers, _ = two_districts
    _ask(client, ours, our_headers, NUMBER)

    entries = client.get(f"/api/v1/cases/{ours['id']}/audit", headers=our_headers).json()
    assert "ledger.identity_check" in [item["action"] for item in entries]


def test_a_closed_ledger_says_so_rather_than_failing(client, case_factory) -> None:
    """The gate being shut is a deployment decision, not an error the reader caused."""
    ours, our_headers = _cdr_case(client, case_factory)
    body = _ask(client, ours, our_headers, NUMBER)

    assert body["available"] is False
    assert body["matches"] == []
    assert "switched off" in body["note"]


def test_an_entity_from_another_case_is_refused(client, two_districts, case_factory) -> None:
    ours, our_headers, _ = two_districts
    elsewhere, _ = case_factory(our_headers)
    entity_id = _entity_id(ours["id"], NUMBER)
    response = client.get(
        f"/api/v1/cases/{elsewhere['id']}/grounded/entities/{entity_id}/elsewhere", headers=our_headers
    )
    assert response.status_code == 404
