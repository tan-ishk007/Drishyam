"""Everything one case records about one identity, in the order an investigator asks for it.

The summary card answers "who is this" in five sentences. This is the page behind it: every way the
identity was written and which file wrote it that way, every place it was seen, every relationship
stated about it, its own chronology, and whether it is known to another case the reader can already
open.

The distinction this page must never blur is between an alias and a merge. Two spellings recorded
here are two spellings recorded here -- listing them together says the case wrote the identity
these ways, not that the system has decided they are one person. Whether they are is a review
decision, and one this page deliberately does not take.

Nothing is assembled by a model. Every row carries the file and the exact place it was read from,
so the page can be checked line by line and the case never leaves the machine to produce it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Case,
    CaseMembership,
    Entity,
    EntityOccurrence,
    EntityRelation,
    EvidenceFile,
    NormalizedRecord,
    Role,
    User,
)
from app.services.entity_summary import _place
from app.services.relationship_builder import RELATION_MEANING

PROFILE_VERSION = "entity-profile-v1"

ALIAS_CAVEAT = (
    "These are the ways this case wrote the identity down. Listing them together records how it was "
    "written; it does not decide that they are the same person, which is a review decision."
)

OTHER_CASE_CAVEAT = (
    "Only cases you can already open are listed. The same identifier appearing in two cases is a "
    "lead to follow with the officer who holds the other one, never a finding that they are linked."
)


@dataclass
class Alias:
    """One way the identity was written, and where it was written that way."""

    value: str
    evidence: str | None
    field_name: str | None
    stated_role: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "evidence": self.evidence, "field_name": self.field_name, "stated_role": self.stated_role}


@dataclass
class Appearance:
    occurrence_id: str
    evidence_id: str
    evidence: str | None
    place: str | None
    observed_value: str
    field_name: str | None
    stated_role: str | None
    confidence: float
    source_reference: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "occurrence_id": self.occurrence_id,
            "evidence_id": self.evidence_id,
            "evidence": self.evidence,
            "place": self.place,
            "observed_value": self.observed_value,
            "field_name": self.field_name,
            "stated_role": self.stated_role,
            "confidence": self.confidence,
            "source_reference": self.source_reference,
        }


@dataclass
class Connection:
    relation_id: str
    relation_type: str
    meaning: str
    directed: bool
    outgoing: bool
    other_id: str
    other_label: str
    other_type: str
    evidence_id: str
    evidence: str | None
    place: str | None
    observed_at: str | None
    time_precision: str
    confidence: float
    verification_status: str
    source_reference: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "relation_type": self.relation_type,
            "meaning": self.meaning,
            "directed": self.directed,
            "outgoing": self.outgoing,
            "other_id": self.other_id,
            "other_label": self.other_label,
            "other_type": self.other_type,
            "evidence_id": self.evidence_id,
            "evidence": self.evidence,
            "place": self.place,
            "observed_at": self.observed_at,
            "time_precision": self.time_precision,
            "confidence": self.confidence,
            "verification_status": self.verification_status,
            "source_reference": self.source_reference,
        }


@dataclass
class Moment:
    when: str
    precision: str
    statement: str
    evidence_id: str
    evidence: str | None
    place: str | None
    source_reference: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "when": self.when,
            "precision": self.precision,
            "statement": self.statement,
            "evidence_id": self.evidence_id,
            "evidence": self.evidence,
            "place": self.place,
            "source_reference": self.source_reference,
        }


@dataclass
class OtherCase:
    case_id: str
    case_number: str
    title: str
    status: str
    written_as: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_number": self.case_number,
            "title": self.title,
            "status": self.status,
            "written_as": self.written_as,
        }


@dataclass
class EntityProfile:
    entity_id: str
    label: str
    entity_type: str
    normalized_value: str
    aliases: list[Alias] = field(default_factory=list)
    appearances: list[Appearance] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    timeline: list[Moment] = field(default_factory=list)
    other_cases: list[OtherCase] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    unreviewed: int = 0
    alias_caveat: str = ALIAS_CAVEAT
    other_case_caveat: str = OTHER_CASE_CAVEAT
    profile_version: str = PROFILE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "label": self.label,
            "entity_type": self.entity_type,
            "normalized_value": self.normalized_value,
            "aliases": [item.to_dict() for item in self.aliases],
            "appearances": [item.to_dict() for item in self.appearances],
            "connections": [item.to_dict() for item in self.connections],
            "timeline": [item.to_dict() for item in self.timeline],
            "other_cases": [item.to_dict() for item in self.other_cases],
            "roles": self.roles,
            "unreviewed": self.unreviewed,
            "alias_caveat": self.alias_caveat,
            "other_case_caveat": self.other_case_caveat,
            "profile_version": self.profile_version,
        }


def _authorized_case_ids(db: Session, user: User) -> set[str]:
    """Cases this reader can already open. Nothing outside them is described here at all."""
    if user.role == Role.ADMIN:
        return set(db.scalars(select(Case.id)).all())
    owned = set(db.scalars(select(Case.id).where(Case.owner_id == user.id)).all())
    member = set(db.scalars(select(CaseMembership.case_id).where(CaseMembership.user_id == user.id)).all())
    return owned | member


def build(db: Session, case_id: str, entity_id: str, viewer: User) -> EntityProfile | None:
    entity = db.scalar(select(Entity).where(Entity.id == entity_id, Entity.case_id == case_id))
    if entity is None:
        return None

    files = {item.id: item.original_name for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id))}
    labels = {item.id: item for item in db.scalars(select(Entity).where(Entity.case_id == case_id))}
    occurrences = list(
        db.scalars(
            select(EntityOccurrence)
            .where(EntityOccurrence.entity_id == entity.id)
            .order_by(EntityOccurrence.created_at)
        )
    )
    relations = list(
        db.scalars(
            select(EntityRelation)
            .where(
                EntityRelation.case_id == case_id,
                (EntityRelation.subject_entity_id == entity.id) | (EntityRelation.object_entity_id == entity.id),
            )
            .order_by(EntityRelation.confidence.desc())
        )
    )

    profile = EntityProfile(
        entity_id=entity.id,
        label=entity.value,
        entity_type=entity.entity_type,
        normalized_value=entity.normalized_value,
        roles=sorted({item.stated_role for item in occurrences if item.stated_role}),
        unreviewed=sum(1 for item in relations if str(item.verification_status or "").startswith("machine")),
    )

    # ------------------------------------------------------------------ how it was written
    seen: set[str] = set()
    for occurrence in occurrences:
        written = (occurrence.observed_value or "").strip()
        if not written or written.casefold() in seen:
            continue
        seen.add(written.casefold())
        profile.aliases.append(Alias(
            value=written,
            evidence=files.get(occurrence.evidence_id),
            field_name=occurrence.field_name,
            stated_role=occurrence.stated_role,
        ))
    if entity.value.strip().casefold() not in seen:
        profile.aliases.insert(0, Alias(value=entity.value, evidence=None, field_name=None, stated_role=None))

    # ------------------------------------------------------------------ where it was seen
    for occurrence in occurrences:
        profile.appearances.append(Appearance(
            occurrence_id=occurrence.id,
            evidence_id=occurrence.evidence_id,
            evidence=files.get(occurrence.evidence_id),
            place=_place(occurrence.source_reference),
            observed_value=occurrence.observed_value,
            field_name=occurrence.field_name,
            stated_role=occurrence.stated_role,
            confidence=float(occurrence.confidence or 0),
            source_reference=dict(occurrence.source_reference or {}),
        ))

    # ------------------------------------------------------------------ what states a relationship
    for relation in relations:
        outgoing = relation.subject_entity_id == entity.id
        other = labels.get(relation.object_entity_id if outgoing else relation.subject_entity_id)
        profile.connections.append(Connection(
            relation_id=relation.id,
            relation_type=relation.relation_type,
            meaning=RELATION_MEANING.get(relation.relation_type, "The source names both in the same record."),
            directed=bool(relation.directed),
            outgoing=outgoing,
            other_id=other.id if other else "",
            other_label=other.value if other else "an unresolved identity",
            other_type=other.entity_type if other else "unknown",
            evidence_id=relation.source_evidence_id,
            evidence=files.get(relation.source_evidence_id),
            place=_place(relation.source_reference),
            observed_at=relation.observed_at.isoformat() if relation.observed_at else None,
            time_precision=relation.time_precision,
            confidence=float(relation.confidence or 0),
            verification_status=relation.verification_status,
            source_reference=dict(relation.source_reference or {}),
        ))

    # ------------------------------------------------------------------ its own chronology
    # Only what a source timed. A relationship whose time was never established is real and stays
    # out of the chronology rather than being given a position it does not have.
    for relation in relations:
        if relation.observed_at is None:
            continue
        outgoing = relation.subject_entity_id == entity.id
        other = labels.get(relation.object_entity_id if outgoing else relation.subject_entity_id)
        subject = entity.value if outgoing else (other.value if other else "an unresolved identity")
        target = (other.value if other else "an unresolved identity") if outgoing else entity.value
        profile.timeline.append(Moment(
            when=relation.observed_at.isoformat(),
            precision=relation.time_precision,
            statement=f"{subject} {relation.relation_type.replace('_', ' ').lower()} {target}",
            evidence_id=relation.source_evidence_id,
            evidence=files.get(relation.source_evidence_id),
            place=_place(relation.source_reference),
            source_reference=dict(relation.source_reference or {}),
        ))

    records = {
        item.id: item
        for item in db.scalars(
            select(NormalizedRecord).where(
                NormalizedRecord.id.in_([item.record_id for item in occurrences if item.record_id] or [""])
            )
        )
    }
    for occurrence in occurrences:
        record = records.get(occurrence.record_id or "")
        if record is None or record.event_time is None:
            continue
        profile.timeline.append(Moment(
            when=record.event_time.isoformat(),
            precision=record.event_time_precision or "unknown",
            statement=record.normalized_summary or f"Recorded in {files.get(occurrence.evidence_id, 'an evidence file')}",
            evidence_id=occurrence.evidence_id,
            evidence=files.get(occurrence.evidence_id),
            place=_place(occurrence.source_reference),
            source_reference=dict(occurrence.source_reference or {}),
        ))

    profile.timeline.sort(key=lambda item: item.when)

    # ------------------------------------------------------------------ known to another case
    allowed = _authorized_case_ids(db, viewer) - {case_id}
    if allowed:
        matches = db.scalars(
            select(Entity).where(
                Entity.case_id.in_(allowed),
                Entity.entity_type == entity.entity_type,
                Entity.normalized_value == entity.normalized_value,
            )
        ).all()
        cases = {item.id: item for item in db.scalars(select(Case).where(Case.id.in_({item.case_id for item in matches} or {""})))}
        for match in matches:
            other_case = cases.get(match.case_id)
            if other_case is None:
                continue
            profile.other_cases.append(OtherCase(
                case_id=other_case.id,
                case_number=other_case.case_number,
                title=other_case.title,
                status=other_case.status.value,
                written_as=match.value,
            ))
        profile.other_cases.sort(key=lambda item: item.case_number)

    return profile
