"""Everything one case records about one identity — and the line it must not cross.

The page lists the ways an identity was written down. Listing them together records how the case
wrote it; it does not decide they are one person. That distinction is the whole reason the two
Yashes in the benchmark case stay two people, and a page that quietly joined them would undo the
restraint the extraction layer is built around.

The other line is disclosure. A profile may say that another case knows this identifier only when
the reader can already open that case, and it may never describe what that case contains.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import Entity, User
from app.services import entity_profile
from scripts import benchmark_case


@pytest.fixture
def profiled_case(client, case_factory):
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


def _entity(case_id: str, label: str) -> Entity:
    db = SessionLocal()
    try:
        found = db.scalar(select(Entity).where(Entity.case_id == case_id, Entity.value == label))
        assert found is not None, f"{label} is not in this case"
        db.expunge(found)
        return found
    finally:
        db.close()


def _profile(case_id: str, label: str, email: str | None = None):
    db = SessionLocal()
    try:
        viewer = (
            db.scalar(select(User).where(User.email == email)) if email else db.scalar(select(User).limit(1))
        )
        return entity_profile.build(db, case_id, _entity(case_id, label).id, viewer)
    finally:
        db.close()


# --------------------------------------------------------------------------- what it gathers


def test_it_lists_every_way_the_identity_was_written(profiled_case) -> None:
    case, _ = profiled_case
    profile = _profile(case["id"], "+919876543210")

    assert profile.aliases, "an identity found in four files was written at least one way"
    assert all(alias.value for alias in profile.aliases)
    assert profile.alias_caveat


def test_an_alias_list_is_not_a_merge(profiled_case) -> None:
    """Two names one letter apart stay two profiles. The page records spellings; it decides nothing."""
    case, _ = profiled_case
    one = _profile(case["id"], "Yash Kumar Gupta")
    two = _profile(case["id"], "Yash Kumar Gupt")

    assert one.entity_id != two.entity_id
    assert "Yash Kumar Gupt" not in [alias.value for alias in one.aliases]
    assert "Yash Kumar Gupta" not in [alias.value for alias in two.aliases]
    assert "does not decide" in one.alias_caveat


def test_every_appearance_names_the_file_it_was_read_from(profiled_case) -> None:
    case, _ = profiled_case
    profile = _profile(case["id"], "+919876543210")

    assert profile.appearances
    for appearance in profile.appearances:
        assert appearance.evidence_id, "an appearance with no file cannot be opened"
        assert appearance.observed_value


def test_every_relationship_carries_its_source_and_meaning(profiled_case) -> None:
    case, _ = profiled_case
    profile = _profile(case["id"], "+919876543210")

    assert profile.connections
    for connection in profile.connections:
        assert connection.evidence_id
        assert connection.meaning, "a relationship type with no stated meaning is a label, not evidence"
        assert connection.other_label


def test_the_role_a_source_stated_reaches_the_profile(profiled_case) -> None:
    case, _ = profiled_case
    assert _profile(case["id"], "Yash Kumar Gupta").roles == ["accused"]
    assert _profile(case["id"], "Yash Kumar Gupt").roles == ["self-identified"]


# --------------------------------------------------------------------------- chronology


def test_the_chronology_holds_only_what_a_source_timed(profiled_case) -> None:
    """A record whose time was never established must not be given a position it does not have."""
    case, _ = profiled_case
    profile = _profile(case["id"], "+919876543210")

    for moment in profile.timeline:
        assert moment.when, "a moment with no time does not belong in a chronology"
        assert moment.evidence_id


def test_the_chronology_is_in_order(profiled_case) -> None:
    case, _ = profiled_case
    profile = _profile(case["id"], "+919876543210")
    assert profile.timeline == sorted(profile.timeline, key=lambda item: item.when)


# --------------------------------------------------------------------------- an identity alone


def test_an_identity_connected_to_nothing_still_renders(profiled_case) -> None:
    case, _ = profiled_case
    profile = _profile(case["id"], "Yash Kumar Gupt")

    assert profile.connections == []
    assert profile.appearances, "it was seen somewhere, even with nothing stated about it"
    assert profile.label == "Yash Kumar Gupt"


# --------------------------------------------------------------------------- disclosure


def test_another_case_is_named_only_when_the_reader_can_open_it(client, case_factory) -> None:
    """The same number in two cases is a lead. It is only offered to somebody already inside both."""
    owner_case, owner_headers = case_factory()
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            client.post(
                f"/api/v1/cases/{owner_case['id']}/evidence",
                headers=owner_headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )

    second, _ = case_factory(owner_headers)
    with next(item for item in benchmark_case.generate().values() if "cdr" in item.name).open("rb") as stream:
        client.post(
            f"/api/v1/cases/{second['id']}/evidence",
            headers=owner_headers,
            data={"source_category": "cdr"},
            files={"file": ("cdr_synthetic.csv", stream, "application/octet-stream")},
        )

    db = SessionLocal()
    try:
        owner = db.scalar(select(User).order_by(User.created_at.desc()))
        owner_email = owner.email
    finally:
        db.close()

    seen_by_owner = _profile(owner_case["id"], "+919876543210", owner_email)
    assert any(item.case_id == second["id"] for item in seen_by_owner.other_cases), (
        "the owner of both cases should be told the identifier appears in the other"
    )
    for other in seen_by_owner.other_cases:
        assert other.case_number and other.title
        assert not hasattr(other, "evidence"), "no content of the other case may be described"


def test_an_outsider_is_told_nothing_about_other_cases(client, case_factory, account) -> None:
    case, headers = case_factory()
    for name, path in benchmark_case.generate().items():
        with path.open("rb") as stream:
            client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": benchmark_case.ARTIFACTS[name]},
                files={"file": (path.name, stream, "application/octet-stream")},
            )

    outsider_email, outsider_headers = account()
    profile = _profile(case["id"], "+919876543210", outsider_email)
    assert profile.other_cases == [], "a reader outside a case must not learn that it exists"

    entity = _entity(case["id"], "+919876543210")
    response = client.get(
        f"/api/v1/cases/{case['id']}/grounded/entities/{entity.id}/profile", headers=outsider_headers
    )
    assert response.status_code in {403, 404}


# --------------------------------------------------------------------------- through the API


def test_the_endpoint_returns_the_profile(client, profiled_case) -> None:
    case, headers = profiled_case
    entity = _entity(case["id"], "Yash Kumar Gupta")
    response = client.get(f"/api/v1/cases/{case['id']}/grounded/entities/{entity.id}/profile", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["label"] == "Yash Kumar Gupta"
    assert body["roles"] == ["accused"]
    assert body["alias_caveat"] and body["other_case_caveat"]
    assert "aliases" in body and "appearances" in body and "connections" in body


def test_an_entity_from_another_case_is_not_profiled(client, profiled_case, case_factory) -> None:
    case, headers = profiled_case
    other, _ = case_factory(headers)
    entity = _entity(case["id"], "Yash Kumar Gupta")
    response = client.get(f"/api/v1/cases/{other['id']}/grounded/entities/{entity.id}/profile", headers=headers)
    assert response.status_code == 404
