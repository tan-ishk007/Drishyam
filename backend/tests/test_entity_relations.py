"""Typed entity-to-entity relationships, end to end over synthetic evidence.

The point of this layer is not that edges exist. It is that every edge can be opened at the source
that produced it, and that the system never states more than the source does. Both are asserted
here against the real pipeline, not against a stub.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.entities import Entity, EntityRelation
from app.services.relationship_builder import (
    ASSOCIATED_WITH,
    REQUESTED_PAYMENT_FROM,
    COMMUNICATED_WITH,
    MENTIONED_WITH,
    MESSAGED,
    TRANSFERRED_TO,
)
from scripts.generate_synthetic_evidence import generate

CATEGORIES = {
    "whatsapp": "whatsapp_chat",
    "phishing": "phishing_email",
    "bank": "bank_statement",
    "call": "call_log",
    "upi": "upi_receipt",
    "complaint": "complaint_fir",
}


@pytest.fixture
def processed_case(client, case_factory):
    """One case built from the full synthetic evidence set, processed through both pipelines."""
    case, headers = case_factory()
    for artifact in generate():
        category = next(value for key, value in CATEGORIES.items() if key in artifact.name)
        with artifact.open("rb") as stream:
            response = client.post(
                f"/api/v1/cases/{case['id']}/evidence",
                headers=headers,
                data={"source_category": category},
                files={"file": (artifact.name, stream, "application/octet-stream")},
            )
        assert response.status_code == 201, response.text
    return case, headers


def _relations(case_id: str) -> list[EntityRelation]:
    db = SessionLocal()
    try:
        return list(db.scalars(select(EntityRelation).where(EntityRelation.case_id == case_id)).all())
    finally:
        db.close()


def test_synthetic_evidence_produces_typed_relationships(processed_case) -> None:
    case, _ = processed_case
    relations = _relations(case["id"])
    assert relations, "no entity relationships were derived from six evidence files"

    types = {row.relation_type for row in relations}
    # A bank statement row is a ledger line: a declared amount between a payer and a payee column.
    assert TRANSFERRED_TO in types, f"expected a transfer edge from the bank statement; got {sorted(types)}"
    assert types <= {TRANSFERRED_TO, REQUESTED_PAYMENT_FROM, MESSAGED, COMMUNICATED_WITH, ASSOCIATED_WITH, MENTIONED_WITH}


def test_every_relationship_can_be_opened_at_its_source(processed_case) -> None:
    """Traceability Coverage is the project's headline metric; here it is enforced, not measured."""
    case, _ = processed_case
    relations = _relations(case["id"])

    without_evidence = [row.id for row in relations if not row.source_evidence_id]
    without_reference = [row.id for row in relations if not row.source_reference]
    assert not without_evidence, f"{len(without_evidence)} relationships have no source evidence"
    assert not without_reference, f"{len(without_reference)} relationships have no source reference"


def test_a_transfer_edge_is_directed_and_a_call_edge_is_not(processed_case) -> None:
    """Direction is only asserted where the source states who acted on whom.

    A bank row names a payer column and a payee column. A call-log row maps every number into one
    column, so it proves contact and not who dialled -- and must not claim otherwise.
    """
    case, _ = processed_case
    relations = _relations(case["id"])

    for row in relations:
        if row.relation_type == TRANSFERRED_TO:
            assert row.directed is True
            assert row.basis == "stated_roles"
        if row.relation_type == COMMUNICATED_WITH:
            assert row.directed is False
        if row.relation_type == REQUESTED_PAYMENT_FROM:
            # Asking for money is not moving it; the direction is who asked whom.
            assert row.directed is True
            assert row.basis == "stated_roles"
        if row.relation_type == ASSOCIATED_WITH:
            # The roles were stated even though what passed between them was not, so the order the
            # source gave is preserved.
            assert row.directed is True
            assert row.basis == "stated_roles"
        if row.relation_type == MENTIONED_WITH:
            assert row.directed is False
            assert row.basis == "co_occurrence"


def test_nothing_is_confirmed_without_a_reviewer(processed_case) -> None:
    case, _ = processed_case
    statuses = {row.verification_status for row in _relations(case["id"])}
    assert statuses == {"machine_extracted"}


def test_no_relationship_points_at_itself(processed_case) -> None:
    """An account appearing in both the payer and payee column is a parse artefact, not a finding."""
    case, _ = processed_case
    assert not [row.id for row in _relations(case["id"]) if row.subject_entity_id == row.object_entity_id]


def test_both_ends_of_every_edge_are_resolved_entities_in_this_case(processed_case) -> None:
    """An edge to a node that identity resolution never registered would be unopenable."""
    case, _ = processed_case
    db = SessionLocal()
    try:
        known = {entity.id for entity in db.scalars(select(Entity).where(Entity.case_id == case["id"])).all()}
    finally:
        db.close()
    for row in _relations(case["id"]):
        assert row.subject_entity_id in known
        assert row.object_entity_id in known


def test_reprocessing_does_not_duplicate_relationships(processed_case, client) -> None:
    """A worker retry must not turn one stated transfer into two."""
    case, headers = processed_case
    before = len(_relations(case["id"]))

    evidence = client.get(f"/api/v1/cases/{case['id']}/evidence", headers=headers).json()
    for item in evidence:
        client.post(f"/api/v1/cases/{case['id']}/evidence/{item['id']}/process", headers=headers)

    assert len(_relations(case["id"])) == before


def test_relations_endpoint_returns_openable_observations(processed_case, client) -> None:
    case, headers = processed_case
    response = client.get(f"/api/v1/cases/{case['id']}/grounded/entity-relations", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] >= 1

    item = body["items"][0]
    assert item["source_evidence_id"]
    assert item["source_reference"]
    assert item["subject"]["label"] and item["object"]["label"]
    assert item["verification_status"] == "machine_extracted"


def test_summary_counts_independent_sources_not_repeat_mentions(processed_case, client) -> None:
    case, headers = processed_case
    response = client.get(f"/api/v1/cases/{case['id']}/grounded/entity-relations/summary", headers=headers)
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary

    for entry in summary:
        assert entry["meaning"], "a relationship must carry a plain-language meaning"
        assert entry["observation_count"] >= entry["supporting_evidence_count"] >= 1
        assert len(entry["evidence_ids"]) == entry["supporting_evidence_count"]

    ranked = [entry["supporting_evidence_count"] for entry in summary]
    assert ranked == sorted(ranked, reverse=True), "corroborated relationships must rank first"


def test_a_reviewer_decision_is_recorded_on_the_observation(processed_case, client) -> None:
    case, headers = processed_case
    relation_id = client.get(
        f"/api/v1/cases/{case['id']}/grounded/entity-relations", headers=headers
    ).json()["items"][0]["id"]

    response = client.post(
        f"/api/v1/cases/{case['id']}/grounded/entity-relations/{relation_id}/review",
        headers=headers,
        json={"action": "confirm_relationship", "reason": "Matches the statement column in the source row."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == "human_verified"
    assert response.json()["review_note"]

    # The observation is annotated, never removed: the original machine reading stays auditable.
    assert any(row.id == relation_id for row in _relations(case["id"]))


def test_another_case_cannot_read_or_review_these_relationships(processed_case, client, case_factory) -> None:
    case, headers = processed_case
    relation_id = client.get(
        f"/api/v1/cases/{case['id']}/grounded/entity-relations", headers=headers
    ).json()["items"][0]["id"]

    other_case, other_headers = case_factory()
    leaked = client.get(f"/api/v1/cases/{other_case['id']}/grounded/entity-relations", headers=other_headers)
    assert leaked.status_code == 200
    assert leaked.json()["total"] == 0

    # A relationship id from another case must not be reviewable through this case.
    forged = client.post(
        f"/api/v1/cases/{other_case['id']}/grounded/entity-relations/{relation_id}/review",
        headers=other_headers,
        json={"action": "reject_relationship"},
    )
    assert forged.status_code == 404
