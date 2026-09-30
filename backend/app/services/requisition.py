"""Drafting what to request next, from what the case already records.

An investigator finishes reading the network and then writes a requisition by hand: which numbers,
which date ranges, and a paragraph justifying each. The facts they need for that are already in the
case -- which identifiers appear, which relationships rest on a single observation, when the
contact around the incident happened. This assembles them into a draft.

**The system drafts; it does not submit.** What comes back is text an officer reads, edits and
sends under their own name. Nothing here is addressed, signed, or transmitted anywhere, and a
requisition is a legal instrument that must carry a person's judgement rather than a system's
output.

Every number in a draft traces to a stated relationship or a recorded occurrence in this case, and
the draft says which. A request that cannot say why it is asking is a fishing expedition, and an
officer should not be handed one with their name at the bottom.

No sentence here states intent, involvement, or that anybody did anything. The basis is always of
the form "this case records X, so the period around X is what is being asked for".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import analytics
from app.models.entities import Entity, EntityRelation, EvidenceFile
from app.services import temporal

REQUISITION_VERSION = "requisition-v1"

# How far either side of the recorded contact to ask for. Wide enough to catch what sits around it,
# narrow enough that the request is proportionate to what the case actually records.
MARGIN = timedelta(days=2)

# A request naming more identifiers than this stops being a request and becomes a trawl.
MAX_SUBJECTS = 12

CLOSING = (
    "This draft was assembled from what this case records. It is not a submission: read it, correct it, and send "
    "it under your own name. Every period requested is derived from a recorded observation, which is stated "
    "beside it."
)

NOT_ESTABLISHED = (
    "This case records no established time for any contact involving this identifier, so no period is proposed. "
    "A range chosen without one would be a request this case cannot justify."
)


@dataclass
class Subject:
    """One identifier the draft asks about, and the recorded basis for asking."""

    value: str
    entity_type: str
    basis: str
    period_from: str | None = None
    period_to: str | None = None
    evidence: list[str] = field(default_factory=list)
    load_bearing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "entity_type": self.entity_type,
            "basis": self.basis,
            "period_from": self.period_from,
            "period_to": self.period_to,
            "evidence": self.evidence,
            "load_bearing": self.load_bearing,
        }


@dataclass
class Draft:
    case_number: str
    subjects: list[Subject] = field(default_factory=list)
    text: str = ""
    closing: str = CLOSING
    version: str = REQUISITION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_number": self.case_number,
            "subjects": [item.to_dict() for item in self.subjects],
            "text": self.text,
            "closing": self.closing,
            "version": self.version,
        }


REQUESTABLE = {"phone", "upi", "account", "email", "device", "vehicle"}


def _window(relations: list[EntityRelation]) -> tuple[str | None, str | None]:
    """The period around what this case actually recorded, or nothing at all.

    A relationship whose time was never established contributes no period. Widening a request to
    cover a range nobody observed is how a proportionate ask becomes a general one.
    """
    timed = [item.observed_at for item in relations if item.observed_at]
    if not timed:
        return None, None
    return (min(timed) - MARGIN).date().isoformat(), (max(timed) + MARGIN).date().isoformat()


def build(db: Session, case_id: str, case_number: str) -> Draft:
    """Assemble the draft. Nothing is invented; everything traces to a row in this case."""
    entities = {item.id: item for item in db.scalars(select(Entity).where(Entity.case_id == case_id))}
    files = {item.id: item.original_name for item in db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id))}
    relations = list(db.scalars(select(EntityRelation).where(EntityRelation.case_id == case_id)))

    # A relationship that is the only link between two parts of the network is the one worth
    # confirming with the operator's own records before anything else rests on it.
    fragile: set[frozenset[str]] = set()
    for bridge in analytics.bridge_relationships(db, case_id):
        fragile.add(frozenset(((bridge.get("subject") or {}).get("id"), (bridge.get("object") or {}).get("id"))))

    touching: dict[str, list[EntityRelation]] = {}
    for relation in relations:
        for side in (relation.subject_entity_id, relation.object_entity_id):
            touching.setdefault(side, []).append(relation)

    draft = Draft(case_number=case_number)
    for entity_id, involved in touching.items():
        entity = entities.get(entity_id)
        if entity is None or entity.entity_type not in REQUESTABLE:
            continue

        opens, closes = _window(involved)
        on_a_bridge = any(
            frozenset((item.subject_entity_id, item.object_entity_id)) in fragile for item in involved
        )
        evidence = sorted({files.get(item.source_evidence_id, "an evidence file") for item in involved})
        kinds = sorted({str(item.relation_type).replace("_", " ").lower() for item in involved})

        basis = (
            f"This case records {len(involved)} observation(s) of this identifier "
            f"({', '.join(kinds)}) across {len(evidence)} evidence file(s)."
        )
        if on_a_bridge:
            basis += (
                " One of them is the only recorded link between two parts of this network, so it is the first thing "
                "worth confirming against the holder's own records."
            )
        if opens is None:
            basis += " " + NOT_ESTABLISHED

        draft.subjects.append(Subject(
            value=entity.value,
            entity_type=entity.entity_type,
            basis=basis,
            period_from=opens,
            period_to=closes,
            evidence=evidence,
            load_bearing=on_a_bridge,
        ))

    # Fragile links first, then the identifiers the case records most about.
    draft.subjects.sort(key=lambda item: (not item.load_bearing, -len(item.evidence), item.value))
    draft.subjects = draft.subjects[:MAX_SUBJECTS]
    draft.text = _render(draft, db, case_id)
    return draft


def _render(draft: Draft, db: Session, case_id: str) -> str:
    """The draft as text an officer can edit and send.

    Written as a request for records over a stated period, with the reason beside each. It does not
    say what anybody did, because this case does not know that and a requisition does not need it.
    """
    window = temporal.incident_window(db, case_id)
    lines = [
        f"Subject: Request for records - case {draft.case_number}",
        "",
        f"This request is made in connection with case {draft.case_number}.",
    ]
    if window.is_set:
        lines.append(
            f"The case records an incident window beginning {window.start.isoformat()}"
            + (f" and ending {window.end.isoformat()}" if window.end else "")
            + "."
        )
    else:
        lines.append(
            "No incident window has been declared in this case, so the periods below are derived from the times "
            "recorded in the evidence rather than from a declared incident."
        )
    lines.append("")

    if not draft.subjects:
        lines.append(
            "This case does not yet record any identifier with a stated relationship behind it, so there is nothing "
            "to request. Nothing has been proposed on its own."
        )
        return "\n".join(lines)

    lines.append("The following records are requested:")
    lines.append("")
    for index, subject in enumerate(draft.subjects, start=1):
        period = (
            f"for the period {subject.period_from} to {subject.period_to}"
            if subject.period_from
            else "with no period proposed"
        )
        lines.append(f"{index}. {subject.entity_type.upper()} {subject.value} - {period}.")
        lines.append(f"   Basis: {subject.basis}")
        lines.append(f"   Read from: {', '.join(subject.evidence)}")
        lines.append("")

    lines.append(
        "Nothing in this request states that any person named or reachable at these identifiers has done anything. "
        "The records are sought to establish what this case has so far only read from other sources."
    )
    return "\n".join(lines)
