"""The repair for entity nodes two extraction generations split apart.

This script runs against real case data, so the properties that matter are that it loses nothing,
touches nothing it has no business touching, and does the same thing when run twice.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import Entity, Event, EventEntity
from scripts import merge_split_entities


@pytest.fixture
def case(client, case_factory):
    """A case with one real evidence file, because an event and an entity must both name one.

    That every row points at the evidence it came from is enforced in the schema, not merely by
    convention, so these fixtures cannot fabricate rows without it.
    """
    created, headers = case_factory()
    response = client.post(
        f"/api/v1/cases/{created['id']}/evidence",
        headers=headers,
        data={"source_category": "other"},
        files={"file": ("synthetic-merge.txt", b"SYNTHETIC TEST ONLY.", "text/plain")},
    )
    assert response.status_code == 201, response.text
    return created["id"], response.json()["evidence"]["id"]


def _event(db, case_id: str, evidence_id: str, label: str) -> Event:
    event = Event(
        case_id=case_id,
        source_file_id=evidence_id,
        event_type="observed_record",
        description="Synthetic row for the merge repair test.",
        raw_text_reference=f"synthetic:{label}",
        confidence=0.8,
    )
    db.add(event)
    db.flush()
    return event


def _entity(db, case_id: str, evidence_id: str, *, entity_type: str, value: str, normalized: str, method: str) -> Entity:
    entity = Entity(
        case_id=case_id,
        source_evidence_id=evidence_id,
        entity_type=entity_type,
        value=value,
        normalized_value=normalized,
        source_reference="synthetic",
        extraction_method=method,
        confidence=0.8,
    )
    db.add(entity)
    db.flush()
    return entity


def _run(apply: bool) -> None:
    argv = ["--apply"] if apply else []
    import sys

    original = sys.argv
    sys.argv = ["merge_split_entities", *argv]
    try:
        merge_split_entities.main()
    finally:
        sys.argv = original


def test_three_duplicates_merge_into_one_node(case) -> None:
    """Three rows for one email, each linked to the same events under the same relationship.

    Repointing them a loser at a time re-read the survivor's links for each, and the session does
    not autoflush, so the second loser did not see the first one's repoints and claimed a slot that
    was already taken. The whole merge then rolled back on the unique constraint.
    """
    case_id, evidence_id = case
    db = SessionLocal()
    try:
        shared = _event(db, case_id, evidence_id, "shared")
        rows = [
            _entity(db, case_id, evidence_id, entity_type="email", value=written, normalized=written, method="regex_normalizer")
            for written in ("Advisor@Example.test", "advisor@example.test", "ADVISOR@EXAMPLE.TEST")
        ]
        for row in rows:
            db.add(EventEntity(event_id=shared.id, entity_id=row.id, relationship_type="mentioned_in", confidence=0.8))
        db.commit()
    finally:
        db.close()

    _run(apply=True)

    db = SessionLocal()
    try:
        remaining = list(db.scalars(select(Entity).where(Entity.case_id == case_id, Entity.entity_type == "email")))
        assert len(remaining) == 1, [item.normalized_value for item in remaining]
        assert remaining[0].normalized_value == "advisor@example.test"
        links = list(db.scalars(select(EventEntity).where(EventEntity.entity_id == remaining[0].id)))
        assert len(links) == 1, "the duplicate links should have collapsed, not multiplied"
    finally:
        db.close()


def test_distinct_links_are_carried_over_not_dropped(case) -> None:
    """Collapsing duplicates must not lose an event only one of them was attached to."""
    case_id, evidence_id = case
    db = SessionLocal()
    try:
        first, second = _event(db, case_id, evidence_id, "one"), _event(db, case_id, evidence_id, "two")
        keeper = _entity(db, case_id, evidence_id, entity_type="email", value="a@b.test", normalized="a@b.test", method="grounded_pipeline")
        loser = _entity(db, case_id, evidence_id, entity_type="email", value="A@B.test", normalized="A@B.test", method="regex_normalizer")
        db.add(EventEntity(event_id=first.id, entity_id=keeper.id, relationship_type="mentioned_in", confidence=0.8))
        db.add(EventEntity(event_id=second.id, entity_id=loser.id, relationship_type="mentioned_in", confidence=0.8))
        db.commit()
        keeper_id = keeper.id
    finally:
        db.close()

    _run(apply=True)

    db = SessionLocal()
    try:
        links = list(db.scalars(select(EventEntity).where(EventEntity.entity_id == keeper_id)))
        assert len(links) == 2, "an event reached only through the merged row was lost"
    finally:
        db.close()


def test_a_row_that_is_not_an_identity_is_left_exactly_as_it_is(case) -> None:
    """An `amount` is not an identity. Re-deriving its key from the display value read "59,000"."""
    case_id, evidence_id = case
    db = SessionLocal()
    try:
        _entity(db, case_id, evidence_id, entity_type="amount", value="59,000", normalized="59000", method="regex_normalizer")
        _entity(db, case_id, evidence_id, entity_type="url", value="http://Example.test/a", normalized="http://example.test/a", method="regex_normalizer")
        db.commit()
    finally:
        db.close()

    _run(apply=True)

    db = SessionLocal()
    try:
        amount = db.scalar(select(Entity).where(Entity.case_id == case_id, Entity.entity_type == "amount"))
        url = db.scalar(select(Entity).where(Entity.case_id == case_id, Entity.entity_type == "url"))
        assert amount is not None and amount.normalized_value == "59000"
        assert url is not None and url.normalized_value == "http://example.test/a"
    finally:
        db.close()


def test_running_it_again_changes_nothing(case) -> None:
    case_id, evidence_id = case
    db = SessionLocal()
    try:
        event = _event(db, case_id, evidence_id, "again")
        for written in ("+919876543210", "9876543210"):
            row = _entity(db, case_id, evidence_id, entity_type="phone", value=written, normalized=written, method="regex_normalizer")
            db.add(EventEntity(event_id=event.id, entity_id=row.id, relationship_type="mentioned_in", confidence=0.8))
        db.commit()
    finally:
        db.close()

    _run(apply=True)

    db = SessionLocal()
    try:
        before = sorted((item.entity_type, item.normalized_value) for item in db.scalars(select(Entity).where(Entity.case_id == case_id)))
    finally:
        db.close()

    _run(apply=True)

    db = SessionLocal()
    try:
        after = sorted((item.entity_type, item.normalized_value) for item in db.scalars(select(Entity).where(Entity.case_id == case_id)))
    finally:
        db.close()

    assert before == after
    assert len(after) == 1, f"one number stayed several nodes: {after}"
