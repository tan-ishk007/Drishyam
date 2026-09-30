"""The connection graph: which evidence items are tied together, and by what.

The older projection drew provenance — evidence produced an event which produced a transaction.
That answers "where did this row come from", which nobody asks. The question an investigator asks
is "what do these two files have in common", so this graph puts **evidence on one side, shared
identifiers in the middle**, and reports the bridge between them.

A link is only interesting when the identifier is seen in more than one evidence item, so a bridge
is exactly an identifier whose occurrence count spans two or more files.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Entity, EntityOccurrence, EvidenceFile, RecordRelation

# How much a shared identifier is worth, by how hard it is to coincide. Two people can share a
# first name; they do not share a UTR.
IDENTIFIER_WEIGHT = {
    "reference": 1.00,
    "device": 0.95,
    "account": 0.92,
    "vehicle": 0.90,  # a registration plate is issued once
    "ifsc": 0.90,
    "upi": 0.90,
    "email": 0.88,
    "phone": 0.85,
    "organisation": 0.50,  # a trading name is shared and often abbreviated
    "party": 0.45,
    "person": 0.40,  # two people share a name far more often than an account
    "location": 0.25,  # thousands of unrelated people share a place
}
DEFAULT_WEIGHT = 0.6

STRENGTH_BANDS = ((0.85, "strong"), (0.60, "moderate"))

# What a shared identifier of each kind actually proves. A named thing is not
# an identifier: the same name appearing twice is a lead to check, not a link
# that has been established.
_CAVEATS = {
    "party": "A shared name is weak evidence of a shared person and needs confirmation.",
    "person": "A shared name is weak evidence of a shared person. Two people can have the same name; confirm identity before treating this as a link.",
    "organisation": "Organisation names are abbreviated and reused. Confirm this is the same entity before relying on the link.",
    "location": "A shared location links the records to a place, not to each other. Thousands of unrelated people share a place.",
    "vehicle": "This is an exact registration match. It links the records to one vehicle, not to whoever was driving it.",
}


@dataclass
class Bridge:
    """One identifier seen in more than one evidence item."""

    entity_id: str
    entity_type: str
    label: str
    canonical: str
    evidence_ids: list[str] = field(default_factory=list)
    occurrences: int = 0
    confidence: float = 0.0

    @property
    def strength(self) -> float:
        """Distinct files matter; repeat mentions inside one file barely do.

        Ranking by raw mention count promoted whatever appeared most often in a single chat. What
        makes a link investigable is the identifier turning up in *separate* sources.
        """
        weight = IDENTIFIER_WEIGHT.get(self.entity_type, DEFAULT_WEIGHT)
        spread = min(len(self.evidence_ids), 4) / 4
        return round(weight * (0.6 + 0.4 * spread) * max(self.confidence, 0.5), 4)

    @property
    def band(self) -> str:
        for floor, name in STRENGTH_BANDS:
            if self.strength >= floor:
                return name
        return "weak"


def _bridges(db: Session, case_id: str) -> list[Bridge]:
    rows = db.execute(
        select(EntityOccurrence, Entity)
        .join(Entity, Entity.id == EntityOccurrence.entity_id)
        .where(EntityOccurrence.case_id == case_id)
    ).all()

    grouped: dict[str, Bridge] = {}
    for occurrence, entity in rows:
        bridge = grouped.get(entity.id)
        if bridge is None:
            bridge = Bridge(
                entity_id=entity.id,
                entity_type=entity.entity_type,
                label=entity.value,
                canonical=entity.normalized_value,
            )
            grouped[entity.id] = bridge
        if occurrence.evidence_id not in bridge.evidence_ids:
            bridge.evidence_ids.append(occurrence.evidence_id)
        bridge.occurrences += 1
        bridge.confidence = max(bridge.confidence, float(occurrence.confidence))

    return sorted(
        (bridge for bridge in grouped.values() if len(bridge.evidence_ids) > 1),
        key=lambda item: (-item.strength, -len(item.evidence_ids), item.label),
    )


def _isolated(db: Session, case_id: str, linked: set[str]) -> list[EvidenceFile]:
    files = db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)).all()
    return [item for item in files if item.id not in linked]


def build_connection_graph(db: Session, case_id: str, *, min_evidence: int = 2) -> dict[str, Any]:
    """Evidence nodes, shared-identifier nodes, and the edges that bridge them."""
    files = {item.id: item for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)).all()}
    bridges = [item for item in _bridges(db, case_id) if len(item.evidence_ids) >= min_evidence]

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    linked_evidence: set[str] = set()

    for bridge in bridges:
        nodes.append(
            {
                "id": f"identifier:{bridge.entity_id}",
                "kind": "identifier",
                "identifier_type": bridge.entity_type,
                "label": bridge.label,
                "canonical": bridge.canonical,
                "evidence_count": len(bridge.evidence_ids),
                "occurrences": bridge.occurrences,
                "strength": bridge.strength,
                "strength_band": bridge.band,
                "confidence": round(bridge.confidence, 4),
            }
        )
        for evidence_id in bridge.evidence_ids:
            linked_evidence.add(evidence_id)
            edges.append(
                {
                    "id": f"{bridge.entity_id}|{evidence_id}",
                    "source": f"identifier:{bridge.entity_id}",
                    "target": f"evidence:{evidence_id}",
                    "relationship": "appears_in",
                    "link_style": "solid",
                    "basis": "exact_identifier_match",
                    "strength": bridge.strength,
                    "strength_band": bridge.band,
                }
            )

    for evidence_id, item in files.items():
        nodes.append(
            {
                "id": f"evidence:{evidence_id}",
                "kind": "evidence",
                "label": item.original_name,
                "source_category": item.source_category,
                "status": item.status.value,
                "connected": evidence_id in linked_evidence,
                "bridge_count": sum(1 for bridge in bridges if evidence_id in bridge.evidence_ids),
            }
        )

    # Candidate semantic links are drawn dashed so an inferred connection never looks like a proven
    # one, per the reporting rules.
    for relation in db.scalars(
        select(RecordRelation).where(RecordRelation.case_id == case_id, RecordRelation.detection_method == "semantic")
    ).all():
        evidence_ids = list(relation.evidence_ids or [])
        for left, right in zip(evidence_ids, evidence_ids[1:]):
            edges.append(
                {
                    "id": f"relation:{relation.id}",
                    "source": f"evidence:{left}",
                    "target": f"evidence:{right}",
                    "relationship": relation.relation_type,
                    "link_style": "dashed",
                    "basis": "semantic_candidate",
                    "strength": float(relation.confidence),
                    "strength_band": "weak",
                    "review_status": relation.status,
                }
            )

    isolated = _isolated(db, case_id, linked_evidence)
    return {
        "case_id": case_id,
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "evidence_count": len(files),
            "connected_evidence": len(linked_evidence),
            "isolated_evidence": [{"id": item.id, "label": item.original_name} for item in isolated],
            "bridge_count": len(bridges),
            "strongest": [
                {
                    "label": bridge.label,
                    "identifier_type": bridge.entity_type,
                    "evidence_count": len(bridge.evidence_ids),
                    "strength_band": bridge.band,
                }
                for bridge in bridges[:5]
            ],
        },
    }


def describe_connections(db: Session, case_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Plain-language sentences a reader can act on, one per bridge."""
    files = {item.id: item.original_name for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id)).all()}
    described = []
    for bridge in _bridges(db, case_id)[:limit]:
        names = [files.get(item, "unknown file") for item in bridge.evidence_ids]
        label = {
            "phone": "phone number",
            "email": "email address",
            "upi": "UPI handle",
            "account": "account identifier",
            "ifsc": "bank branch code",
            "reference": "transaction reference",
            "device": "device identifier",
            "vehicle": "vehicle registration",
            "organisation": "organisation name",
            "person": "person name",
            "location": "location",
            "party": "name",
        }.get(bridge.entity_type, bridge.entity_type)
        described.append(
            {
                "identifier": bridge.label,
                "identifier_label": label,
                "evidence_names": names,
                "evidence_count": len(names),
                "strength_band": bridge.band,
                "sentence": (
                    f"The {label} {bridge.label} appears in {len(names)} evidence items: "
                    f"{', '.join(names)}."
                ),
                "caveat": _CAVEATS.get(
                    bridge.entity_type,
                    "This is an exact identifier match. It links the files, not the people behind them.",
                ),
            }
        )
    return described
