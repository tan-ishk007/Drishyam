"""The shared identifier ledger, and everything it must refuse to say.

Two districts hold cases involving the same phone number and neither knows it. The only way to find
that out today is for one officer to describe their case to another, which is what case-level
authorisation exists to prevent. This makes the question answerable without either side seeing the
other's file.

Most of this file is about the second half of that sentence. A ledger that leaked the identifier,
or the case's contents, or that could be enumerated back to a phone number, would trade a real
protection for a convenience. So: nothing but a digest and a reference is stored, the digest is
keyed so a stolen ledger cannot be brute-forced, the gate defaults shut and refuses rather than
degrading, and the chain is walked to prove nobody removed an entry.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.entities import Case, Entity, LedgerEntry, User
from app.services import ledger
from scripts import benchmark_case

SHARED_KEY = "synthetic-test-key-shared-between-districts"
# Deliberately shares no wording with the case: the contact is free text a person types,
# so it is the one field the system cannot keep case detail out of, and a test that mixed
# the two would be checking the tester rather than the code.
CONTACT = "SI Test Officer, 022-0000-0000"

# The benchmark files write this number four different ways; every one of them must reach the same
# digest, or a ledger match would depend on how a clerk happened to type it.
NUMBER = "+919876543210"


@pytest.fixture
def open_gate(monkeypatch):
    """Both switches on and a shared key present. Anything less is a closed gate.

    The settings object is cached process-wide, so patching it here reaches the same instance the
    service and the route hold. Patching a fresh copy would leave the gate shut where it matters.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "ledger_enabled", True)
    monkeypatch.setattr(settings, "ledger_publication", "enabled")
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "ledger_key", SecretStr(SHARED_KEY))
    return True


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


def _publish(client, case, headers):
    return client.post(f"/api/v1/cases/{case['id']}/ledger/publish", headers=headers, json={"contact": CONTACT})


def _rows() -> list[LedgerEntry]:
    db = SessionLocal()
    try:
        rows = list(db.scalars(select(LedgerEntry).order_by(LedgerEntry.published_at, LedgerEntry.id)))
        for row in rows:
            db.expunge(row)
        return rows
    finally:
        db.close()


# --------------------------------------------------------------------------- the gate


def test_the_gate_is_shut_by_default(client, worked_case) -> None:
    case, headers = worked_case
    response = _publish(client, case, headers)

    assert response.status_code == 409, response.text
    assert _rows() == [], "nothing may be published through a closed gate"


def test_a_closed_gate_refuses_rather_than_returning_nothing(client, worked_case) -> None:
    """"published: 0" from a closed gate reads as "this case has no identifiers". It must not."""
    case, headers = worked_case
    body = _publish(client, case, headers).json()
    assert "switched off" in body["detail"]


def test_one_switch_is_not_enough(client, worked_case, monkeypatch) -> None:
    case, headers = worked_case
    monkeypatch.setattr(get_settings(), "ledger_enabled", True)
    assert _publish(client, case, headers).status_code == 409, "the second switch is not decoration"


def test_without_a_shared_key_there_is_no_ledger(client, worked_case, monkeypatch) -> None:
    """An unkeyed digest of a phone number can be enumerated in an afternoon. Publishing one would
    be publishing the number, so a missing key is a shut gate, not a reason to fall back."""
    case, headers = worked_case
    settings = get_settings()
    monkeypatch.setattr(settings, "ledger_enabled", True)
    monkeypatch.setattr(settings, "ledger_publication", "enabled")
    monkeypatch.setattr(settings, "ledger_key", None)

    assert _publish(client, case, headers).status_code == 409
    assert _rows() == []


def test_a_refused_publish_is_still_recorded(client, worked_case) -> None:
    """An attempt to send identifiers outside a case is worth a line whether or not it succeeded."""
    case, headers = worked_case
    _publish(client, case, headers)

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    refused = [item for item in entries if item["action"] == "ledger.publish"]
    assert refused and refused[0]["outcome"] == "refused"


def test_the_status_is_readable_with_the_gate_shut(client, worked_case) -> None:
    """Somebody has to be able to see that it is off, and the answer discloses nothing."""
    _, headers = worked_case
    body = client.get("/api/v1/ledger/status", headers=headers).json()

    assert body["open"] is False
    assert body["switches"]["ledger_enabled"] is False
    assert body["closed_reason"]


# --------------------------------------------------------------------------- what leaves


def test_nothing_but_a_digest_and_a_reference_is_stored(client, worked_case, open_gate) -> None:
    """The load-bearing test of this feature."""
    case, headers = worked_case
    assert _publish(client, case, headers).status_code == 200

    rows = _rows()
    assert rows, "the benchmark case holds identifiers worth publishing"

    db = SessionLocal()
    try:
        values = {item.value for item in db.scalars(select(Entity).where(Entity.case_id == case["id"]))}
    finally:
        db.close()

    for row in rows:
        written = f"{row.identifier_digest}{row.case_reference}{row.previous_hash}{row.entry_hash}"
        for value in values:
            assert value not in written, f"the identifier {value} reached the ledger"
        assert len(row.identifier_digest) == 64
        assert row.case_reference == case["case_number"]
        # The contact is the publisher's own words, passed through untouched. The system must not
        # be adding anything of the case to it.
        assert row.contact == CONTACT


def test_the_digest_is_keyed_so_a_stolen_ledger_cannot_be_enumerated(open_gate, monkeypatch) -> None:
    """Without the key, the same number must not produce the same digest."""
    from pydantic import SecretStr

    ours = ledger.digest("phone", NUMBER)
    monkeypatch.setattr(get_settings(), "ledger_key", SecretStr("a-different-districts-key"))
    theirs = ledger.digest("phone", NUMBER)

    assert ours != theirs, "an unkeyed digest is the identifier with extra steps"


def test_the_type_is_folded_in_so_unlike_identifiers_cannot_collide(open_gate) -> None:
    assert ledger.digest("phone", "9876543210") != ledger.digest("account", "9876543210")


# --------------------------------------------------------------------------- matching


def test_the_same_number_written_differently_still_matches(open_gate) -> None:
    """A number written +91 98765 43210 in one file and 09876543210 in another is one identifier.
    A ledger that published the written form would match neither against the other."""
    written = ["+919876543210", "919876543210", "09876543210", "98765 43210"]
    digests = {ledger.digest("phone", ledger.canonicalize_indicator("phone", item).canonical_value) for item in written}
    assert len(digests) == 1, f"the same number reached {len(digests)} different digests"


def test_two_districts_find_a_shared_identifier_without_seeing_each_other(client, case_factory, open_gate, account) -> None:
    """The done-when for this step."""
    first, first_headers = case_factory()
    second_email, second_headers = account()
    second, _ = case_factory(second_headers)

    for case, headers in ((first, first_headers), (second, second_headers)):
        with next(item for item in benchmark_case.generate().values() if "cdr" in item.name).open("rb") as stream:
            client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": "cdr"},
                files={"file": ("cdr_synthetic.csv", stream, "application/octet-stream")},
            )

    assert _publish(client, first, first_headers).status_code == 200

    found = client.get(f"/api/v1/cases/{second['id']}/ledger/matches", headers=second_headers).json()
    assert found["matches"], "the second district holds the same numbers and should be told"

    match = found["matches"][0]
    assert match["case_reference"] == first["case_number"]
    assert match["contact"] == CONTACT
    assert set(match.keys()) == {"case_reference", "contact", "published_at", "your_identity"}, (
        "a match may name a reference and an officer, and nothing else"
    )
    assert first["title"] not in str(found), "no field of the other case may appear"


def test_a_case_is_not_told_it_matches_itself(client, worked_case, open_gate) -> None:
    case, headers = worked_case
    _publish(client, case, headers)

    found = client.get(f"/api/v1/cases/{case['id']}/ledger/matches", headers=headers).json()
    assert found["matches"] == []


def test_an_outsider_cannot_publish_or_match(client, worked_case, open_gate, account) -> None:
    case, _ = worked_case
    _, outsider = account()
    assert _publish(client, case, outsider).status_code in {403, 404}
    assert client.get(f"/api/v1/cases/{case['id']}/ledger/matches", headers=outsider).status_code in {403, 404}


def test_matching_is_audited(client, worked_case, open_gate) -> None:
    """Asking whether an identifier appears elsewhere is itself an access event."""
    case, headers = worked_case
    client.get(f"/api/v1/cases/{case['id']}/ledger/matches", headers=headers)

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    assert "ledger.match" in [item["action"] for item in entries]


# --------------------------------------------------------------------------- the chain


def test_publishing_twice_adds_nothing(client, worked_case, open_gate) -> None:
    case, headers = worked_case
    first = _publish(client, case, headers).json()
    again = _publish(client, case, headers).json()

    assert first["published"] > 0
    assert again["published"] == 0
    assert again["already_present"] == first["published"]


def test_an_untouched_ledger_verifies(client, worked_case, open_gate) -> None:
    case, headers = worked_case
    _publish(client, case, headers)

    body = client.get("/api/v1/ledger/status", headers=headers).json()["chain"]
    assert body["status"] == ledger.INTACT
    assert body["verified"] == body["entries"] > 0


def test_removing_an_entry_is_visible_to_everybody_reading(client, worked_case, open_gate) -> None:
    """A withdrawal that could not be seen would make the chain worth nothing."""
    case, headers = worked_case
    _publish(client, case, headers)
    assert len(_rows()) >= 3, "this needs a middle entry to remove"

    db = SessionLocal()
    try:
        rows = list(db.scalars(select(LedgerEntry).order_by(LedgerEntry.published_at, LedgerEntry.id)))
        db.delete(rows[1])
        db.commit()
    finally:
        db.close()

    body = client.get("/api/v1/ledger/status", headers=headers).json()["chain"]
    assert body["status"] == ledger.BROKEN
    assert body["broken_at"] == 2
    assert "removed" in body["statement"]


def test_editing_a_published_entry_is_caught(client, worked_case, open_gate) -> None:
    case, headers = worked_case
    _publish(client, case, headers)

    db = SessionLocal()
    try:
        row = db.scalar(select(LedgerEntry).order_by(LedgerEntry.published_at))
        row.contact = "somebody else entirely"
        db.commit()
    finally:
        db.close()

    body = client.get("/api/v1/ledger/status", headers=headers).json()["chain"]
    assert body["status"] == ledger.BROKEN
    assert body["broken_at"] == 1


def test_a_case_can_withdraw_what_it_published(client, worked_case, open_gate) -> None:
    """An identifier that can never be taken back, however wrongly published, is the worse trade."""
    case, headers = worked_case
    published = _publish(client, case, headers).json()["published"]

    response = client.delete(f"/api/v1/cases/{case['id']}/ledger/publish", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["withdrawn"] == published
    assert _rows() == []
