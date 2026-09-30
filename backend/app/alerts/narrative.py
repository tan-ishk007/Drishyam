"""Turning the facts behind an alert into a sequence a reader can follow and open.

An alert used to be one paragraph: a count, a threshold, and a list of file ids. A paragraph cannot
be opened. A reader who wanted to know what actually happened had to go and reconstruct it from the
records, which is exactly the work the alert existed to save them.

A sequence is the same facts in the order the sources record them, each line carrying the time, what
the source states, and the file and place it is written. Every line can be clicked through to the
page or row it came from. Nothing here is generated prose -- each statement is assembled from a
relation the extraction layer already wrote, and if a line cannot name its source it is not written.

**The line this module exists to hold.** A sequence of events reads like a story, and a story
invites a reader to supply the connective tissue: he called her *because*, they met *in order to*.
The sources record none of that. So no sentence assembled here may contain a cause, a motive, or a
relationship the source did not state -- `FORBIDDEN_IN_A_STATEMENT` is checked by the tests, and
every sequence closes with the same line saying whose job the meaning is.

The gaps are part of the sequence too. "Between these, no contact is recorded" is a fact about the
record, and one an investigator reads differently from a gap that was never mentioned. It is stated
as a fact about the record rather than about the world: nothing having been recorded is not the same
as nothing having happened, and the wording keeps that distinction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable

from app.models.entities import Entity, EntityRelation
from app.services.entity_summary import _place

NARRATIVE_VERSION = "narrative-v1"

# The one line every sequence ends on. The system orders facts; it does not read them.
SEQUENCE_CLOSING = (
    "This is what the sources record, in the order they record it. What it means is a matter for the "
    "reader; the system does not draw a conclusion from a sequence."
)

# A gap long enough to be worth stating. Below this, silence between two records is just the ordinary
# spacing of a conversation and saying so would be noise.
GAP_WORTH_STATING = timedelta(hours=6)

# Language that would put a cause, a motive or an unstated relationship into a line. Checked by the
# tests against every statement any rule produces. This list is the specification, not a filter
# applied to generated text: statements are assembled from templates that avoid these by
# construction, and the check exists to catch a template that drifts.
FORBIDDEN_IN_A_STATEMENT = (
    " because",
    " so that",
    " in order to",
    " therefore",
    " intended",
    " intent ",
    " planned",
    " arranged to",
    " conspired",
    " colluded",
    " lured",
    " orchestrated",
    " to avoid",
    " deliberately",
    " suspiciously",
    " clearly",
    " obviously",
    " proves",
    " confirms that",
)

# How one relation reads as a line of a story: active, named, and stating only what the source did.
# A type with no phrase falls back to the neutral form rather than being dropped -- a step that
# cannot be phrased is still a step that happened.
STEP_PHRASES = {
    "CALLED": "{subject} called {object}.",
    "MESSAGED": "{subject} sent a message to {object}.",
    "COMMUNICATED_WITH": "Contact is recorded between {subject} and {object}, without stating who initiated it.",
    "TRANSFERRED_TO": "{subject} sent money to {object}.",
    "REQUESTED_PAYMENT_FROM": "{subject} asked {object} for money. The source does not record that any money moved.",
    "USED_VEHICLE": "{subject} is recorded driving, riding or using {object}.",
    "LOCATED_AT": "{subject} is placed at {object}. The source does not establish when.",
    "ASSOCIATED_WITH": "{subject} and {object} are named as the parties to the same record.",
    "MENTIONED_WITH": "{subject} and {object} are named in the same record, with no relationship stated between them.",
}
NEUTRAL_PHRASE = "{subject} and {object} are recorded in the same statement."


@dataclass
class Step:
    """One line of the sequence: when, what the source states, and where to read it.

    `when` is None for a fact whose time was never established. Such a fact is kept and marked
    rather than dropped or given a position -- it belongs to the story, but not to the chronology,
    and quietly slotting it between two timed facts would invent an order nothing supports.
    """

    statement: str
    when: datetime | None = None
    evidence_id: str | None = None
    place: str | None = None
    source_reference: dict = field(default_factory=dict)
    kind: str = "fact"

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "when": self.when.isoformat() if self.when else None,
            "evidence_id": self.evidence_id,
            "place": self.place,
            "source_reference": self.source_reference,
            "kind": self.kind,
        }


def label(entities: dict[str, Entity], entity_id: str | None) -> str:
    if not entity_id:
        return "an unresolved identity"
    entity = entities.get(entity_id)
    return entity.value if entity else "an unresolved identity"


def step_from_relation(relation: EntityRelation, entities: dict[str, Entity]) -> Step:
    """One recorded relationship, as a line of the story it belongs to."""
    subject = label(entities, relation.subject_entity_id)
    object_ = label(entities, relation.object_entity_id)
    template = STEP_PHRASES.get(relation.relation_type, NEUTRAL_PHRASE)
    if not relation.directed and relation.relation_type in {"CALLED", "MESSAGED"}:
        # The source shows the two together but not who acted on whom. Naming a caller here would
        # state a direction the record does not.
        template = STEP_PHRASES["COMMUNICATED_WITH"]
    return Step(
        statement=template.format(subject=subject, object=object_),
        when=relation.observed_at,
        evidence_id=relation.source_evidence_id,
        place=_place(relation.source_reference),
        source_reference=dict(relation.source_reference or {}),
    )


def with_gaps(steps: list[Step], threshold: timedelta = GAP_WORTH_STATING) -> list[Step]:
    """Insert a stated gap wherever the record falls silent for long enough to be worth saying.

    A gap is a fact about the record, not about the world. An investigator reads "nothing was
    recorded for two days" differently from a sequence that simply skips two days without comment,
    and differently again from "nothing happened" -- which is not something the absence of a record
    can establish.
    """
    if len(steps) < 2:
        return steps

    with_silence: list[Step] = []
    for index, step in enumerate(steps):
        if index and step.when and steps[index - 1].when:
            span = step.when - steps[index - 1].when
            if span >= threshold:
                with_silence.append(Step(
                    statement=(
                        f"Then {_span_words(span)} in which no contact between them is recorded. "
                        "Nothing having been recorded is not the same as nothing having happened."
                    ),
                    kind="gap",
                ))
        with_silence.append(step)
    return with_silence


def _span_words(span: timedelta) -> str:
    hours = span.total_seconds() / 3600
    if hours < 48:
        return f"{round(hours)} hours pass"
    return f"{round(hours / 24)} days pass"


def sequence(steps: Iterable[Step], *, gaps: bool = True) -> list[dict[str, Any]]:
    """The stored form of a sequence: ordered facts, stated gaps, and the closing line.

    Facts with an established time are ordered by it. Facts without one keep their given order at
    the end, under their own marker, rather than being interleaved into a chronology they cannot
    support.
    """
    given = list(steps)
    timed = sorted([item for item in given if item.when], key=lambda item: item.when)
    untimed = [item for item in given if not item.when]

    ordered = with_gaps(timed) if gaps else timed
    # The marker is only worth writing when there is an order for these facts to be missing from.
    # A sequence in which nothing is timed asserts no chronology, so nothing is being left out of one.
    if untimed and timed:
        one = len(untimed) == 1
        ordered.append(Step(
            statement=(
                f"{len(untimed)} further record{'' if one else 's'} in this pattern "
                f"carr{'ies' if one else 'y'} no established time, so {'it is' if one else 'they are'} "
                "listed below rather than placed in the order above."
            ),
            kind="gap",
        ))
    ordered.extend(untimed)

    ordered.append(Step(statement=SEQUENCE_CLOSING, kind="closing"))
    return [item.to_dict() for item in ordered]
