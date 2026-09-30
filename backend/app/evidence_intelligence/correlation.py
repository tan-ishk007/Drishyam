"""Corroboration and contradiction detection.

Deterministic exact-identifier rules run first and carry the most weight. Everything produced here
is a **candidate** for a human reviewer — this module never confirms a relationship, never resolves
a conflict, and never attributes responsibility to a person.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import combinations
from typing import Any, Iterable, Protocol

from app.evidence_intelligence.schema import RelationCandidate, RelationStatus, RelationType

CORRELATION_VERSION = "correlation-v1"

# Confidence a shared identifier lends to a candidate link, by how specific that identifier is.
IDENTIFIER_WEIGHTS = {
    "transaction_reference": 0.90,
    "device_identifier": 0.86,
    "account_identifiers": 0.85,
    "email_addresses": 0.80,
    "phone_numbers": 0.78,
}
LIST_IDENTIFIERS = ("phone_numbers", "email_addresses", "account_identifiers")
SCALAR_IDENTIFIERS = ("transaction_reference", "device_identifier")

SEMANTIC_TIME_WINDOW = timedelta(hours=6)
SEMANTIC_CONFIDENCE = 0.45
TIME_CONTRADICTION_WINDOW = timedelta(days=1)
AMOUNT_TOLERANCE = Decimal("0.01")


class CorrelatableRecord(Protocol):
    id: str
    evidence_id: str
    transaction_reference: str | None
    device_identifier: str | None
    phone_numbers: list
    email_addresses: list
    account_identifiers: list
    amount_value: Any
    amount_currency: str | None
    event_time: datetime | None
    source_type: str


@dataclass(frozen=True)
class _Pair:
    left: Any
    right: Any

    @property
    def evidence_ids(self) -> list[str]:
        return sorted({self.left.evidence_id, self.right.evidence_id})

    @property
    def record_ids(self) -> list[str]:
        return sorted([self.left.id, self.right.id])


def _key(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:48]


def _normalize(value: Any) -> str:
    return str(value).strip().casefold()


def _values(record: Any, field: str) -> set[str]:
    if field in LIST_IDENTIFIERS:
        raw = getattr(record, field, None) or []
        return {_normalize(item) for item in raw if str(item).strip()}
    value = getattr(record, field, None)
    return {_normalize(value)} if value and str(value).strip() else set()


def _amount(record: Any) -> Decimal | None:
    value = getattr(record, "amount_value", None)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def _source_references(pair: _Pair) -> list[dict[str, Any]]:
    return [
        {"record_id": pair.left.id, "evidence_id": pair.left.evidence_id, "source_type": getattr(pair.left, "source_type", None)},
        {"record_id": pair.right.id, "evidence_id": pair.right.evidence_id, "source_type": getattr(pair.right, "source_type", None)},
    ]


def _candidate(
    pair: _Pair,
    *,
    relation_type: RelationType,
    fields: list[str],
    reason: str,
    confidence: float,
    method: str,
) -> RelationCandidate:
    return RelationCandidate(
        relation_type=relation_type,
        status=RelationStatus.CANDIDATE,
        evidence_ids=pair.evidence_ids,
        record_ids=pair.record_ids,
        matching_or_conflicting_fields=fields,
        reason=reason,
        source_references=_source_references(pair),
        confidence=confidence,
        requires_human_review=True,
        idempotency_key=_key(method, relation_type.value, ",".join(fields), *pair.record_ids),
    )


def find_exact_matches(records: Iterable[Any]) -> list[RelationCandidate]:
    """Shared identifiers across two different evidence items."""
    items = list(records)
    candidates: list[RelationCandidate] = []

    for left, right in combinations(items, 2):
        if left.evidence_id == right.evidence_id:
            # Two rows from one file are not independent sources of each other.
            continue
        pair = _Pair(left, right)
        shared: dict[str, set[str]] = {}
        for field in (*SCALAR_IDENTIFIERS, *LIST_IDENTIFIERS):
            overlap = _values(left, field) & _values(right, field)
            if overlap:
                shared[field] = overlap
        if not shared:
            continue

        fields = sorted(shared)
        confidence = max(IDENTIFIER_WEIGHTS.get(field, 0.7) for field in fields)
        shown = "; ".join(f"{field}: {', '.join(sorted(values))}" for field, values in sorted(shared.items()))
        candidates.append(
            _candidate(
                pair,
                relation_type=RelationType.CORROBORATION,
                fields=fields,
                reason=(
                    f"The same identifier appears in two separate evidence items ({shown}). "
                    "This is a reviewable lead about shared identifiers, not a finding about a person or an act."
                ),
                confidence=confidence,
                method="exact_match",
            )
        )
    return candidates


def find_contradictions(records: Iterable[Any]) -> list[RelationCandidate]:
    """Records that claim the same thing but disagree about it."""
    items = list(records)
    candidates: list[RelationCandidate] = []

    for left, right in combinations(items, 2):
        if left.evidence_id == right.evidence_id:
            continue
        shared_reference = _values(left, "transaction_reference") & _values(right, "transaction_reference")
        if not shared_reference:
            continue

        pair = _Pair(left, right)
        left_amount, right_amount = _amount(left), _amount(right)
        conflicting: list[str] = []
        details: list[str] = []

        if left_amount is not None and right_amount is not None and abs(left_amount - right_amount) > AMOUNT_TOLERANCE:
            conflicting.append("amount")
            details.append(f"amounts {left_amount} and {right_amount}")
        if left.amount_currency and right.amount_currency and _normalize(left.amount_currency) != _normalize(right.amount_currency):
            conflicting.append("amount_currency")
            details.append(f"currencies {left.amount_currency} and {right.amount_currency}")
        if left.event_time and right.event_time and abs(left.event_time - right.event_time) > TIME_CONTRADICTION_WINDOW:
            conflicting.append("event_time")
            details.append(f"timestamps {left.event_time.isoformat()} and {right.event_time.isoformat()}")

        if not conflicting:
            continue

        candidates.append(
            _candidate(
                pair,
                relation_type=RelationType.CONTRADICTION,
                fields=sorted(conflicting),
                reason=(
                    f"Two evidence items share transaction reference '{sorted(shared_reference)[0]}' but report "
                    f"different {', '.join(details)}. The conflict is recorded as-is and has not been resolved."
                ),
                confidence=0.8,
                method="exact_match",
            )
        )
    return candidates


def find_semantic_candidates(records: Iterable[Any]) -> list[RelationCandidate]:
    """Same amount, close in time, no shared identifier.

    Deliberately low confidence. A request for money followed by a nearby transfer is suggestive and
    nothing more, so these always require review.
    """
    items = [record for record in records if _amount(record) is not None and record.event_time]
    candidates: list[RelationCandidate] = []

    for left, right in combinations(items, 2):
        if left.evidence_id == right.evidence_id:
            continue
        if any(_values(left, field) & _values(right, field) for field in (*SCALAR_IDENTIFIERS, *LIST_IDENTIFIERS)):
            continue  # an exact rule already covers this pair
        if abs(_amount(left) - _amount(right)) > AMOUNT_TOLERANCE:
            continue
        if abs(left.event_time - right.event_time) > SEMANTIC_TIME_WINDOW:
            continue

        pair = _Pair(left, right)
        candidates.append(
            _candidate(
                pair,
                relation_type=RelationType.CORROBORATION,
                fields=["amount", "event_time"],
                reason=(
                    f"Two evidence items record the same amount ({_amount(left)}) within "
                    f"{SEMANTIC_TIME_WINDOW.total_seconds() / 3600:.0f} hours of each other, but share no identifier. "
                    "This is a weak, semantic-only lead and requires verification before any use."
                ),
                confidence=SEMANTIC_CONFIDENCE,
                method="semantic",
            )
        )
    return candidates


def correlate(records: Iterable[Any], *, include_semantic: bool = False) -> list[RelationCandidate]:
    """Run exact rules first, then optionally the weaker semantic pass."""
    items = list(records)
    candidates = [*find_exact_matches(items), *find_contradictions(items)]
    if include_semantic:
        candidates.extend(find_semantic_candidates(items))

    unique: dict[str, RelationCandidate] = {}
    for candidate in candidates:
        unique.setdefault(candidate.idempotency_key, candidate)
    return sorted(unique.values(), key=lambda item: (-item.confidence, item.relation_type.value))
