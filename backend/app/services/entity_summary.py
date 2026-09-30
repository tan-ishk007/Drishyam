"""Who is this, and why is it in the case — assembled from rows, not written by a model.

An investigator clicking a name on the network asks one question first, and until now the product
had no surface that answered it. The facts to answer it were all stored: what a source called the
person, which files they appear in, what states a relationship to them, and what does not.

Nothing here is generated. Each sentence is built from a stored value and carries the file and the
place it was read from, which makes the whole summary quotable line by line. A written summary
would be a paragraph nobody could check, produced by sending a case to somebody else's computer.

Two rules the sentences never break. Absence is stated rather than left out -- an entity connected
to nothing must say so, because a short card reads as "nothing to see" when it should read as
"nothing was recorded". And no sentence attributes intent, identity or responsibility: the role is
what a source called the person, not what they are.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Entity, EntityOccurrence, EntityRelation, EvidenceFile
from app.services.relationship_builder import RELATION_MEANING

SUMMARY_VERSION = "entity-summary-v1"

STANDING_CAVEAT = (
    "This describes what the evidence in this case records. It does not establish identity, intent "
    "or responsibility, and a name written in a source is a label rather than proof of who it names."
)

# How a stated role reads in a sentence. `named` and `relative` are deliberately not case roles --
# a form with a name field has assigned nobody anything, and a parent named for identification is
# not a party -- so both are phrased as what they are.
ROLE_SENTENCES = {
    "complainant": "is named as the complainant",
    "accused": "is named as an accused",
    "victim": "is named as the victim",
    "witness": "is named as a witness",
    "driver": "is named as the driver",
    "owner": "is named as the owner",
    "beneficiary": "is named as the beneficiary",
    "sender": "is named as the sender",
    "receiver": "is named as the receiver",
    "applicant": "is named as the applicant",
    "petitioner": "is named as the petitioner",
    "respondent": "is named as the respondent",
    "named": "appears in a name field, with no role stated",
    "relative": "is named as a relative, for identification rather than as a party",
    "self-identified": "gave this name for themselves",
}


@dataclass
class Sentence:
    """One statement and the evidence behind it."""

    text: str
    evidence: str | None = None
    place: str | None = None
    basis: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "evidence": self.evidence, "place": self.place, "basis": self.basis}


@dataclass
class EntitySummary:
    entity_id: str
    label: str
    entity_type: str
    sentences: list[Sentence] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    source_count: int = 0
    relation_count: int = 0
    caveat: str = STANDING_CAVEAT
    summary_version: str = SUMMARY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "label": self.label,
            "entity_type": self.entity_type,
            "sentences": [item.to_dict() for item in self.sentences],
            "roles": self.roles,
            "source_count": self.source_count,
            "relation_count": self.relation_count,
            "caveat": self.caveat,
            "summary_version": self.summary_version,
        }


def _place(reference: object) -> str | None:
    """Where a statement sits inside its file, in the words somebody would use to go and look."""
    if not isinstance(reference, dict):
        return None
    parts: list[str] = []
    if reference.get("page"):
        parts.append(f"page {reference['page']}")
    if reference.get("row"):
        parts.append(f"row {reference['row']}")
    if reference.get("column"):
        parts.append(f'column "{reference["column"]}"')
    if not parts and reference.get("line_start"):
        start, end = reference["line_start"], reference.get("line_end") or reference["line_start"]
        parts.append(f"line {start}" if start == end else f"lines {start}-{end}")
    return ", ".join(parts) or None


def _label(entity: Entity | None) -> str:
    return entity.value if entity is not None else "an unresolved identity"


def build(db: Session, case_id: str, entity_id: str) -> EntitySummary | None:
    """Four sentences about one identity, each carrying the evidence it was read from."""
    entity = db.scalar(select(Entity).where(Entity.id == entity_id, Entity.case_id == case_id))
    if entity is None:
        return None

    files = {item.id: item.original_name for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id))}
    occurrences = list(db.scalars(select(EntityOccurrence).where(EntityOccurrence.entity_id == entity.id)))
    relations = list(
        db.scalars(
            select(EntityRelation).where(
                EntityRelation.case_id == case_id,
                (EntityRelation.subject_entity_id == entity.id) | (EntityRelation.object_entity_id == entity.id),
            )
        )
    )
    labels = {item.id: item for item in db.scalars(select(Entity).where(Entity.case_id == case_id))}

    sources = {item.evidence_id for item in occurrences} | (
        {item.source_evidence_id for item in relations} | ({entity.source_evidence_id} if entity.source_evidence_id else set())
    )
    sources.discard(None)

    summary = EntitySummary(
        entity_id=entity.id,
        label=entity.value,
        entity_type=entity.entity_type,
        source_count=len(sources),
        relation_count=len(relations),
    )

    # ------------------------------------------------------------------ what a source calls it
    roled = [item for item in occurrences if item.stated_role]
    summary.roles = sorted({item.stated_role for item in roled})
    if roled:
        # Every distinct reading, because two sources calling one person two things is a fact the
        # investigator needs rather than a conflict to resolve silently.
        for role in summary.roles:
            first = next(item for item in roled if item.stated_role == role)
            summary.sentences.append(Sentence(
                text=f"{entity.value} {ROLE_SENTENCES.get(role, f'is described as {role}')} in this case.",
                evidence=files.get(first.evidence_id),
                place=_place(first.source_reference),
                basis="stated role",
            ))
        if len(summary.roles) > 1:
            summary.sentences.append(Sentence(
                text="Different sources describe this person differently. Both readings are kept; neither has been preferred.",
                basis="conflict",
            ))
    elif entity.entity_type == "person":
        summary.sentences.append(Sentence(
            text=f"No source in this case states a role for {entity.value}. The name is recorded; what they are to the case is not.",
            basis="absence",
        ))

    # ------------------------------------------------------------------ where it was found
    if sources:
        named = sorted({files[item] for item in sources if item in files})
        listed = ", ".join(named[:3]) + (f" and {len(named) - 3} more" if len(named) > 3 else "")
        summary.sentences.append(Sentence(
            text=f"Found in {len(sources)} evidence file{'' if len(sources) == 1 else 's'}"
                 + (f": {listed}." if named else "."),
            basis="occurrence",
        ))
    else:
        summary.sentences.append(Sentence(
            text="No evidence file in this case records where this identity came from.",
            basis="absence",
        ))

    # ------------------------------------------------------------------ what it connects to
    if relations:
        kinds = Counter(item.relation_type for item in relations)
        strongest = relations[0]
        for item in relations:
            if float(item.confidence or 0) > float(strongest.confidence or 0):
                strongest = item
        other = labels.get(
            strongest.object_entity_id if strongest.subject_entity_id == entity.id else strongest.subject_entity_id
        )
        summary.sentences.append(Sentence(
            text=f"Connected to {len({item.subject_entity_id for item in relations} | {item.object_entity_id for item in relations}) - 1} "
                 f"other identit{'y' if len(relations) == 1 else 'ies'} through {len(relations)} recorded observation"
                 f"{'' if len(relations) == 1 else 's'}: "
                 + ", ".join(f"{kind.replace('_', ' ').lower()} ({count})" for kind, count in kinds.most_common(3))
                 + ".",
            basis="relationship",
        ))
        summary.sentences.append(Sentence(
            text=f"The strongest of these: {_label(labels.get(strongest.subject_entity_id))} "
                 f"{strongest.relation_type.replace('_', ' ').lower()} {_label(labels.get(strongest.object_entity_id))}. "
                 + RELATION_MEANING.get(strongest.relation_type, "The source names both in the same record."),
            evidence=files.get(strongest.source_evidence_id),
            place=_place(strongest.source_reference),
            basis="relationship",
        ))
        _ = other  # the pair is named in full in the sentence above
    else:
        summary.sentences.append(Sentence(
            text="Nothing in this case states a relationship between this identity and any other. That is an absence of "
                 "recorded evidence, not evidence that no relationship exists.",
            basis="absence",
        ))

    # ------------------------------------------------------------------ what it does not connect to
    if relations:
        touched = {item.subject_entity_id for item in relations} | {item.object_entity_id for item in relations}
        touched.discard(entity.id)
        connected_classes = {labels[item].entity_type for item in touched if item in labels}
        present_classes = {item.entity_type for item in labels.values() if item.id != entity.id}
        # Only a class this identity reaches none of, and only one the case actually holds. The
        # first version listed any class with an unconnected member in it, so a vehicle connected
        # to one place was told it connected to no location -- contradicting the sentence above it.
        classes = sorted(
            {"person", "vehicle", "location", "organisation"} & present_classes - connected_classes
        )
        if classes:
            summary.sentences.append(Sentence(
                text="No recorded relationship connects this identity to any "
                     + ", ".join(classes[:-1]) + (" or " if len(classes) > 1 else "") + classes[-1]
                     + " in this case.",
                basis="absence",
            ))

    # ------------------------------------------------------------------ whether a person checked
    unreviewed = sum(1 for item in relations if str(item.verification_status or "").startswith("machine"))
    if relations:
        summary.sentences.append(Sentence(
            text=f"{unreviewed} of {len(relations)} observation{'' if len(relations) == 1 else 's'} "
                 f"{'has' if unreviewed == 1 else 'have'} not yet been confirmed by a person."
            if unreviewed
            else "Every observation about this identity has been reviewed by a person.",
            basis="review",
        ))

    return summary
