"""Walking the audit chain, and proving it notices when somebody has been at it.

The chain has been written since the beginning: every action carries the hash of the one before it.
Nothing ever walked it. The receipt reported the head and never recomputed it, so the system had a
tamper-evident structure and no way to answer "prove it" — which makes it a table that looks like
tamper-evidence rather than tamper-evidence.

A verifier that only ever reports "intact" is worth nothing, so most of this file tampers with the
record on purpose and insists the check notices, names the exact entry, and says which of the two
things went wrong. Editing a row and removing a row are different failures and a reviewer needs to
be told which one they are looking at.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import AuditLog
from app.services import integrity
from app.services.audit import audit


@pytest.fixture
def worked_case(client, case_factory):
    """A case with a handful of recorded actions behind it.

    The actions are written through the real audit writer rather than by uploading evidence: this
    file is about the chain, and dragging the extraction pipeline into it only adds ways for the
    test to fail for reasons that have nothing to do with hashing.
    """
    case, headers = case_factory()
    db = SessionLocal()
    try:
        for index in range(4):
            audit(
                db,
                action=f"test.recorded_action_{index}",
                object_type="case",
                object_id=case["id"],
                case_id=case["id"],
                outcome="success",
                details={"step": index},
            )
        db.commit()
    finally:
        db.close()
    return case, headers


def _verify(case_id: str) -> integrity.ChainVerification:
    db = SessionLocal()
    try:
        return integrity.verify_chain(db, case_id)
    finally:
        db.close()


def _entries(case_id: str) -> list[AuditLog]:
    db = SessionLocal()
    try:
        rows = list(db.scalars(select(AuditLog).where(AuditLog.case_id == case_id).order_by(AuditLog.created_at, AuditLog.id)))
        for row in rows:
            db.expunge(row)
        return rows
    finally:
        db.close()


# --------------------------------------------------------------------------- an untouched chain


def test_an_untouched_chain_verifies(worked_case) -> None:
    case, _ = worked_case
    result = _verify(case["id"])

    assert result.status == integrity.INTACT
    assert result.entries > 0
    assert result.verified == result.entries
    assert result.breaks == []
    assert result.head


def test_a_case_with_no_actions_is_empty_rather_than_broken(client, case_factory) -> None:
    """An empty record is not a failure, and must not be reported as one."""
    case, _ = case_factory()
    db = SessionLocal()
    try:
        db.query(AuditLog).filter(AuditLog.case_id == case["id"]).delete()
        db.commit()
    finally:
        db.close()

    result = _verify(case["id"])
    assert result.status == integrity.EMPTY
    assert result.breaks == []
    assert "not a failure" in result.statement


# --------------------------------------------------------------------------- somebody edited a row


def test_editing_an_entry_is_caught_and_named(worked_case) -> None:
    case, _ = worked_case
    entries = _entries(case["id"])
    target = entries[len(entries) // 2]

    db = SessionLocal()
    try:
        row = db.get(AuditLog, target.id)
        row.outcome = "success" if row.outcome != "success" else "failure"
        db.commit()
    finally:
        db.close()

    result = _verify(case["id"])
    assert result.status == integrity.BROKEN
    assert result.breaks, "an edited row must not verify"

    first = result.breaks[0]
    assert first.entry_id == target.id, "the wrong entry was blamed"
    assert first.fault == "content_altered"
    assert first.action == target.action
    assert str(first.position) in result.statement


def test_editing_the_details_of_an_entry_is_caught(worked_case) -> None:
    """The details carry what was done. A hash that ignored them would protect nothing useful."""
    case, _ = worked_case
    entries = _entries(case["id"])
    target = entries[-1]

    db = SessionLocal()
    try:
        row = db.get(AuditLog, target.id)
        row.details = {**(row.details or {}), "injected": "value"}
        db.commit()
    finally:
        db.close()

    result = _verify(case["id"])
    assert result.status == integrity.BROKEN
    assert result.breaks[0].entry_id == target.id
    assert result.breaks[0].fault == "content_altered"


# --------------------------------------------------------------------------- somebody removed a row


def test_removing_an_entry_is_caught_even_though_every_row_still_hashes(worked_case) -> None:
    """This is the failure the per-entry hash cannot see and the link between them can."""
    case, _ = worked_case
    entries = _entries(case["id"])
    assert len(entries) >= 3, "this case needs a middle entry to remove"
    removed = entries[1]

    db = SessionLocal()
    try:
        db.delete(db.get(AuditLog, removed.id))
        db.commit()
    finally:
        db.close()

    result = _verify(case["id"])
    assert result.status == integrity.BROKEN
    assert result.breaks[0].fault == "link_broken"
    assert result.breaks[0].entry_id == entries[2].id, "the break is at the entry that no longer follows"
    assert "removed, inserted or reordered" in result.breaks[0].detail


def test_the_two_faults_are_told_apart(worked_case) -> None:
    """A reviewer acts differently on an edited row than on a missing one."""
    case, _ = worked_case
    entries = _entries(case["id"])

    db = SessionLocal()
    try:
        row = db.get(AuditLog, entries[1].id)
        row.action = "tampered.action"
        db.commit()
    finally:
        db.close()

    result = _verify(case["id"])
    assert {item.fault for item in result.breaks} == {"content_altered"}
    assert all("content is not what was sealed" in item.detail for item in result.breaks)


# --------------------------------------------------------------------------- entries written before the chain


def test_an_entry_with_no_hash_is_reported_not_blamed(worked_case) -> None:
    """Rows written before the chain existed carry no hash. Nothing was altered; the guarantee
    simply does not reach back that far, and saying so is more honest than either verdict."""
    case, _ = worked_case
    entries = _entries(case["id"])

    db = SessionLocal()
    try:
        row = db.get(AuditLog, entries[0].id)
        row.event_hash = None
        row.previous_hash = None
        db.commit()
    finally:
        db.close()

    result = _verify(case["id"])
    assert result.status == integrity.UNCHAINED
    assert result.breaks == [], "a missing hash is not tampering"
    assert "does not reach them" in result.statement


# --------------------------------------------------------------------------- through the API


def test_the_endpoint_reports_the_chain(client, worked_case) -> None:
    case, headers = worked_case
    response = client.get(f"/api/v1/cases/{case['id']}/trustify/chain", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == integrity.INTACT
    assert body["verified"] == body["entries"]
    assert body["statement"]


def test_verifying_is_itself_recorded(client, worked_case) -> None:
    """Checking a case is an action against it. The next verification has one more entry to check."""
    case, headers = worked_case
    before = _verify(case["id"]).entries

    response = client.get(f"/api/v1/cases/{case['id']}/trustify/chain", headers=headers)
    assert response.status_code == 200

    after = _verify(case["id"])
    assert after.entries > before
    assert after.status == integrity.INTACT, "recording the check must not break the chain it checked"


def test_another_users_chain_is_refused(client, worked_case, account) -> None:
    case, _ = worked_case
    _, outsider = account()
    response = client.get(f"/api/v1/cases/{case['id']}/trustify/chain", headers=outsider)
    assert response.status_code in {403, 404}


# --------------------------------------------------------------------------- writing the chain


def test_two_actions_recorded_before_one_commit_still_chain(client, case_factory) -> None:
    """Found by this file: the session does not autoflush, so an entry added earlier in the same
    transaction was invisible to the next one and both claimed the same predecessor. The chain then
    read as broken with nothing tampered with -- a verifier crying wolf is as useless as none."""
    case, _ = case_factory()
    db = SessionLocal()
    try:
        for index in range(3):
            audit(
                db,
                action=f"test.same_transaction_{index}",
                object_type="case",
                object_id=case["id"],
                case_id=case["id"],
                outcome="success",
            )
        db.commit()
    finally:
        db.close()

    written = _entries(case["id"])[-3:]
    assert len({entry.previous_hash for entry in written}) == 3, "each must follow a different entry"
    assert _verify(case["id"]).status == integrity.INTACT
