"""What the national record holds about an identity, and the line it must not cross.

An investigator looking at a number wants to know whether it has been seen before, and today that
means ringing round until somebody remembers. This reads a store entitled to hold the answer.

The tests that matter are about restraint rather than retrieval. Under section 46 of the Bharatiya
Sakshya Adhiniyam previous bad character is generally not relevant, and "he has done this before"
is exactly the inference the rest of this product refuses to make. So a lookup that showed
convictions and quietly dropped acquittals, or that added a record up into a score, would be worse
than no lookup at all — and most of this file exists to stop that.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import Entity, PriorRecord
from scripts import benchmark_case, seed_prior_records

YASH_PHONE = "+919876543210"


@pytest.fixture
def recorded_case(client, case_factory):
    """A case whose identities the synthetic national dataset already knows."""
    seed_prior_records.seed(clear=True)
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


def _entity_id(case_id: str, value: str) -> str:
    db = SessionLocal()
    try:
        found = db.scalar(select(Entity).where(Entity.case_id == case_id, Entity.value == value))
        assert found is not None, f"{value} is not in this case"
        return found.id
    finally:
        db.close()


def _lookup(client, case, headers, value: str) -> dict:
    response = client.get(
        f"/api/v1/cases/{case['id']}/grounded/entities/{_entity_id(case['id'], value)}/prior-record",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- what it returns


def test_a_registered_case_is_reported_with_where_and_when(client, recorded_case) -> None:
    case, headers = recorded_case
    body = _lookup(client, case, headers, YASH_PHONE)

    assert body["entries"], "the seeded dataset names this number"
    for entry in body["entries"]:
        assert entry["record_reference"]
        assert entry["police_station"]
        assert entry["registered_on"]
        assert entry["sections"]


def test_every_disposal_is_shown_not_only_the_convictions(client, recorded_case) -> None:
    """A store that surfaced convictions and dropped acquittals would be a lie told by arithmetic."""
    case, headers = recorded_case
    body = _lookup(client, case, headers, YASH_PHONE)

    disposals = {entry["disposal"] for entry in body["entries"]}
    assert "acquitted" in disposals, "the seeded record includes an acquittal and it must be returned"
    for entry in body["entries"]:
        assert entry["disposal_reading"], "a disposal a reader cannot understand is not shown"
        assert entry["disposal_state"] in {"open", "closed", "unknown"}


def test_the_dataset_is_not_a_wall_of_convictions() -> None:
    """The demo data itself must not teach the inference the product refuses."""
    # Unpacked rather than indexed: a positional index into this row silently read the wrong
    # column once already, and a guard that reads the wrong column guards nothing.
    outcomes = [disposal for *_, disposal, _disposed, _officer in seed_prior_records.RECORDS]
    assert outcomes.count("convicted") <= 1, (
        "a dataset of convictions makes the feature look impressive and teaches every viewer that a "
        "prior record is evidence of the present one"
    )
    assert {"acquitted", "closed", "quashed"} & set(outcomes)


def test_nothing_is_scored_or_ranked(client, recorded_case) -> None:
    """Four registered cases is four registered cases. It is not a number about the person."""
    case, headers = recorded_case
    rendered = str(_lookup(client, case, headers, YASH_PHONE)).lower()

    for forbidden in ("risk", "score", "likelihood", "propensity", "habitual", "repeat offender"):
        assert forbidden not in rendered, f"the lookup states {forbidden!r}"


def test_the_caveat_travels_with_every_answer(client, recorded_case) -> None:
    case, headers = recorded_case
    for value in (YASH_PHONE, "Yash Kumar Gupt"):
        body = _lookup(client, case, headers, value)
        assert "not evidence in this case" in body["caveat"]
        assert "section 46" in body["caveat"].lower()


# --------------------------------------------------------------------------- what it refuses


def test_an_identity_with_no_record_says_so_carefully(client, recorded_case) -> None:
    """Absence from this dataset is not absence of a record, and the wording keeps them apart."""
    case, headers = recorded_case
    body = _lookup(client, case, headers, "Yash Kumar Gupt")

    assert body["entries"] == []
    assert "statement about this record, not about the person" in body["statement"]


def test_matching_is_on_the_canonical_value(client, recorded_case) -> None:
    """A number written four ways is one identity; a near-miss attaches somebody else's history."""
    case, headers = recorded_case
    body = _lookup(client, case, headers, YASH_PHONE)
    assert body["matched_on"] == "9876543210"


def test_the_lookup_is_recorded_whatever_it_returns(client, recorded_case) -> None:
    """An officer who ran the check has learned something the case did not contain."""
    case, headers = recorded_case
    _lookup(client, case, headers, "Yash Kumar Gupt")

    entries = client.get(f"/api/v1/cases/{case['id']}/audit", headers=headers).json()
    assert "prior_record.lookup" in [item["action"] for item in entries]


def test_an_outsider_cannot_run_the_check(client, recorded_case, account) -> None:
    case, headers = recorded_case
    entity_id = _entity_id(case["id"], YASH_PHONE)
    _, outsider = account()
    response = client.get(
        f"/api/v1/cases/{case['id']}/grounded/entities/{entity_id}/prior-record", headers=outsider
    )
    assert response.status_code in {403, 404}


def test_an_entity_from_another_case_is_refused(client, recorded_case, case_factory) -> None:
    case, headers = recorded_case
    other, _ = case_factory(headers)
    entity_id = _entity_id(case["id"], YASH_PHONE)
    response = client.get(
        f"/api/v1/cases/{other['id']}/grounded/entities/{entity_id}/prior-record", headers=headers
    )
    assert response.status_code == 404


def test_the_record_is_separate_from_the_shared_ledger(client, recorded_case) -> None:
    """Two sources answering two questions. Folding them together would make the ledger disclose
    what it is built not to hold."""
    case, headers = recorded_case
    entity_id = _entity_id(case["id"], YASH_PHONE)

    elsewhere = client.get(
        f"/api/v1/cases/{case['id']}/grounded/entities/{entity_id}/elsewhere", headers=headers
    ).json()
    prior = _lookup(client, case, headers, YASH_PHONE)

    # The ledger reply carries no case detail at all; the record reply carries no live-case reference.
    assert "entries" not in elsewhere
    assert "matches" not in prior

    db = SessionLocal()
    try:
        seeded = list(db.scalars(select(PriorRecord)))
    finally:
        db.close()
    assert seeded, "the national dataset is its own store"
