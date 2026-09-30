"""The card that answers "who is this", and the four things it may never do.

An investigator clicking a name asks that before anything else, and the product had no surface for
it. The facts were all stored; nothing surfaced them.

The card is assembled from rows rather than written, which is what makes these tests possible at
all: every sentence has a source that can be checked, and a generated paragraph would have neither.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import Entity, EntityRelation
from app.services import entity_summary
from scripts import benchmark_case


@pytest.fixture
def summarised_case(client, case_factory):
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


def _summary(case_id: str, label: str):
    db = SessionLocal()
    try:
        return entity_summary.build(db, case_id, _entity(case_id, label).id)
    finally:
        db.close()


# --------------------------------------------------------------------------- it answers the question


def test_the_role_a_source_states_is_the_first_thing_said(summarised_case) -> None:
    case, _ = summarised_case
    summary = _summary(case["id"], "Yash Kumar Gupta")

    assert summary.roles == ["accused"]
    first = summary.sentences[0]
    assert "accused" in first.text
    assert first.evidence, "the role must name the file that states it"


def test_a_weaker_basis_is_worded_as_the_weaker_thing_it_is(summarised_case) -> None:
    """"Identifying himself as" is not a report assigning a role, and must not read like one."""
    case, _ = summarised_case
    summary = _summary(case["id"], "Yash Kumar Gupt")

    assert summary.roles == ["self-identified"]
    assert "gave this name for themselves" in summary.sentences[0].text


def test_it_says_how_many_files_carry_the_identity(summarised_case) -> None:
    case, _ = summarised_case
    summary = _summary(case["id"], "+919876543210")
    assert summary.source_count >= 2
    assert any("evidence file" in sentence.text for sentence in summary.sentences)


# --------------------------------------------------------------------------- it never leaves a gap


def test_an_identity_connected_to_nothing_says_so(summarised_case) -> None:
    """A short card reads as “nothing to see”. It has to read as “nothing was recorded”."""
    case, _ = summarised_case
    summary = _summary(case["id"], "Yash Kumar Gupt")

    assert summary.relation_count == 0
    text = " ".join(sentence.text for sentence in summary.sentences)
    assert "absence of recorded evidence, not evidence that no relationship exists" in text


def test_a_person_with_no_stated_role_says_the_role_was_not_stated(summarised_case) -> None:
    case, _ = summarised_case
    db = SessionLocal()
    try:
        people = [
            item for item in db.scalars(select(Entity).where(Entity.case_id == case["id"], Entity.entity_type == "person"))
        ]
    finally:
        db.close()

    unroled = [item for item in people if not _summary(case["id"], item.value).roles]
    if not unroled:
        pytest.skip("every person in this case carries a stated role")
    summary = _summary(case["id"], unroled[0].value)
    assert any("does not" in s.text or "No source" in s.text for s in summary.sentences)


def test_it_never_claims_an_absence_that_contradicts_its_own_sentences(summarised_case) -> None:
    """The first version told a vehicle connected to a place that it connected to no location.

    A card that argues with itself is worse than one that says less.
    """
    case, _ = summarised_case
    db = SessionLocal()
    try:
        entities = {item.id: item for item in db.scalars(select(Entity).where(Entity.case_id == case["id"]))}
        relations = list(db.scalars(select(EntityRelation).where(EntityRelation.case_id == case["id"])))
    finally:
        db.close()

    for entity in entities.values():
        summary = _summary(case["id"], entity.value)
        denial = next((s.text for s in summary.sentences if s.text.startswith("No recorded relationship connects")), None)
        if denial is None:
            continue
        connected = {
            entities[other].entity_type
            for relation in relations
            for this, other in ((relation.subject_entity_id, relation.object_entity_id),
                                (relation.object_entity_id, relation.subject_entity_id))
            if this == entity.id and other in entities
        }
        for kind in connected:
            assert kind not in denial, f"{entity.value} is connected to a {kind} and the card denies it"


# --------------------------------------------------------------------------- it never overstates


def test_every_sentence_that_states_a_source_names_it(summarised_case) -> None:
    case, _ = summarised_case
    for label in ("Yash Kumar Gupta", "MH12DE1433", "+919876543210"):
        for sentence in _summary(case["id"], label).sentences:
            if sentence.basis in {"stated role", "relationship"} and sentence.evidence is None:
                assert "Connected to" in sentence.text, f"a sourced claim with no source: {sentence.text}"


def test_no_sentence_asserts_guilt_or_identity(summarised_case) -> None:
    case, _ = summarised_case
    db = SessionLocal()
    try:
        labels = [item.value for item in db.scalars(select(Entity).where(Entity.case_id == case["id"]))]
    finally:
        db.close()

    for label in labels:
        summary = _summary(case["id"], label)
        text = " ".join(sentence.text for sentence in summary.sentences).lower()
        for claim in ("is guilty", "is the culprit", "committed", "is responsible for", "is a criminal"):
            assert claim not in text, f"{label}: {claim}"
        assert summary.caveat


def test_the_caveat_travels_with_every_summary(summarised_case) -> None:
    case, _ = summarised_case
    assert _summary(case["id"], "Yash Kumar Gupta").caveat == entity_summary.STANDING_CAVEAT


# --------------------------------------------------------------------------- through the API


def test_the_endpoint_returns_the_summary(client, summarised_case) -> None:
    case, headers = summarised_case
    entity = _entity(case["id"], "Yash Kumar Gupta")
    response = client.get(f"/api/v1/cases/{case['id']}/grounded/entities/{entity.id}/summary", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["label"] == "Yash Kumar Gupta"
    assert body["roles"] == ["accused"]
    assert body["sentences"] and body["caveat"]


def test_another_users_case_is_refused(client, summarised_case, account) -> None:
    case, _ = summarised_case
    entity = _entity(case["id"], "Yash Kumar Gupta")
    _, outsider = account()
    response = client.get(
        f"/api/v1/cases/{case['id']}/grounded/entities/{entity.id}/summary", headers=outsider
    )
    assert response.status_code in {403, 404}
    assert "Yash" not in response.text


def test_an_entity_from_another_case_is_not_summarised(client, summarised_case, case_factory) -> None:
    """Scoping is by case, so an entity id from elsewhere must not resolve here."""
    case, headers = summarised_case
    other, _ = case_factory(headers)
    entity = _entity(case["id"], "Yash Kumar Gupta")
    response = client.get(f"/api/v1/cases/{other['id']}/grounded/entities/{entity.id}/summary", headers=headers)
    assert response.status_code == 404
