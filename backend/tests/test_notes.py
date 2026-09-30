"""What an investigator knows, kept beside what the system read and never mistaken for it.

An investigator holds things no evidence file states: what a witness said on the doorstep, which of
two spellings is the same person, why a lead was dropped. That belongs in the case rather than in a
notebook that leaves with them.

The line this file defends is the one the whole extraction layer is built on. A note is what
somebody concluded; a finding is what a source states and can be opened at that source. A note that
reached a reader looking like a finding would erase the distinction, so it is stored apart, returned
apart, and labelled wherever it appears -- including in the report.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import CaseNote, Entity
from scripts import benchmark_case


@pytest.fixture
def worked_case(client, case_factory):
    case, headers = case_factory()
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )
    return case, headers


def _entity_id(case_id: str) -> str:
    db = SessionLocal()
    try:
        return db.scalar(select(Entity).where(Entity.case_id == case_id)).id
    finally:
        db.close()


def _write(client, case, headers, body: str, subject_id: str | None = None) -> dict:
    return client.post(
        f"/api/v1/cases/{case['id']}/notes",
        headers=headers,
        json={
            "subject_type": "entity",
            "subject_id": subject_id or _entity_id(case["id"]),
            "body": body,
        },
    )


def test_a_note_is_attributed_and_timestamped(client, worked_case) -> None:
    case, headers = worked_case
    response = _write(client, case, headers, "Complainant recognised the voice on the second call.")

    assert response.status_code == 201, response.text
    note = response.json()["note"]
    assert note["author"], "an unattributed note is a rumour"
    assert note["created_at"]
    assert note["kind"] == "investigator_commentary"


def test_a_note_says_what_it_is_wherever_it_is_returned(client, worked_case) -> None:
    case, headers = worked_case
    _write(client, case, headers, "Second spelling is probably the same man.")

    listed = client.get(f"/api/v1/cases/{case['id']}/notes", headers=headers).json()
    assert "not a statement any source in this case makes" in listed["caveat"]
    assert all(item["kind"] == "investigator_commentary" for item in listed["notes"])


def test_notes_never_appear_among_findings(client, worked_case) -> None:
    """A note given the standing of a finding would undo the line the extraction layer draws."""
    case, headers = worked_case
    _write(client, case, headers, "SYNTHETIC NOTE: treat this as commentary only.")

    created = client.post(f"/api/v1/cases/{case['id']}/reports", headers=headers)
    report_id = created.json()["id"]
    findings = client.get(f"/api/v1/cases/{case['id']}/reports/{report_id}/findings", headers=headers).json()

    for finding in findings["findings"]:
        assert "SYNTHETIC NOTE" not in finding["statement"]


def test_a_note_on_another_cases_object_is_refused(client, worked_case, case_factory) -> None:
    case, headers = worked_case
    other, _ = case_factory(headers)
    response = _write(client, other, headers, "Note about the wrong case.", subject_id=_entity_id(case["id"]))
    assert response.status_code == 404


def test_an_outsider_can_neither_write_nor_read(client, worked_case, account) -> None:
    case, headers = worked_case
    _write(client, case, headers, "Only the case team should see this.")
    _, outsider = account()

    assert _write(client, case, outsider, "Not mine to write.").status_code in {403, 404}
    assert client.get(f"/api/v1/cases/{case['id']}/notes", headers=outsider).status_code in {403, 404}


def test_withdrawing_is_recorded_rather_than_silent(client, worked_case) -> None:
    """A note that shaped an investigation and vanished without trace is a gap a defence should see."""
    case, headers = worked_case
    note_id = _write(client, case, headers, "Dropping this lead, the number belongs to a shop.").json()["note"]["id"]

    assert client.delete(f"/api/v1/cases/{case['id']}/notes/{note_id}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/cases/{case['id']}/notes", headers=headers).json()["notes"] == []

    db = SessionLocal()
    try:
        kept = db.scalar(select(CaseNote).where(CaseNote.id == note_id))
        assert kept is not None, "the row stays; only the content stops being shown"
        assert kept.deleted_at is not None and kept.deleted_by_id is not None
    finally:
        db.close()

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    assert "note.withdraw" in [item["action"] for item in entries]


def test_only_the_author_may_withdraw_a_note(client, worked_case, case_factory, account) -> None:
    case, headers = worked_case
    note_id = _write(client, case, headers, "My reasoning, not yours to remove.").json()["note"]["id"]

    colleague_email, colleague = account()
    client.post(
        f"/api/v1/cases/{case['id']}/members",
        headers=headers,
        json={"email": colleague_email, "case_role": "investigator"},
    )
    response = client.delete(f"/api/v1/cases/{case['id']}/notes/{note_id}", headers=colleague)
    assert response.status_code == 403
