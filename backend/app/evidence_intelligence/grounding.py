"""Structured output validation and source grounding.

A model claim is accepted only when its quote can be found in the material the model was shown and
its citation names a region that actually exists. Anything else is dropped and counted against the
record's validation confidence — the model does not get to define reality.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.evidence_intelligence.extraction import AUTHORITATIVE_FIELDS, ExtractionUnit, RawExtraction
from app.evidence_intelligence.ocr import OCRResult
from app.evidence_intelligence.schema import (
    Readability,
    FieldProvenance,
    ObservationBasis,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

VALIDATOR_VERSION = "grounding-v1"

MATERIAL_FIELDS = (
    "event_type",
    "event_time",
    "participant_a",
    "participant_b",
    "sender",
    "receiver",
    "message_direction",
    "chat_participant_identifier",
    "transaction_reference",
    "amount",
    "location",
    "device_identifier",
)

_WHITESPACE = re.compile(r"\s+")


def _canonical(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().casefold()


# Share of a model's own words that must be traceable to the source before its reading of the
# evidence is accepted at all. Set below 1.0 so OCR noise the model drops is not treated as
# fabrication; high enough that invented sentences fail.
OBSERVED_TEXT_COVERAGE = 0.85
_WORD = re.compile(r"[0-9a-z@._+\-/]{2,}")


def _substantially_from_source(observed: str, haystack: str) -> bool:
    """Whether the model's transcription is drawn from the source rather than invented."""
    canonical = _canonical(observed)
    if canonical in haystack:
        return True

    words = _WORD.findall(canonical)
    if not words:
        return False
    found = sum(1 for word in words if word in haystack)
    return found / len(words) >= OBSERVED_TEXT_COVERAGE


def _readability(claim: dict) -> Readability:
    """What the model said it could actually read, defaulting to not-applicable.

    Only a value the model explicitly marks is treated as a readability judgement. An absent field
    means the question did not arise -- typed text in a CSV is neither readable nor unreadable in
    this sense -- and must not be recorded as though the model had assessed it.
    """
    stated = claim.get("readability")
    if isinstance(stated, str):
        try:
            return Readability(stated)
        except ValueError:
            return Readability.NOT_APPLICABLE
    return Readability.NOT_APPLICABLE


@dataclass
class GroundingResult:
    accepted: dict[str, FieldProvenance] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    ungrounded: list[str] = field(default_factory=list)
    validation_confidence: float | None = None
    observed_text: str | None = None
    normalized_summary: str | None = None
    model_confidence: float | None = None
    observation_basis: ObservationBasis = ObservationBasis.UNKNOWN
    model_requires_review: bool = True
    model_review_reason: str | None = None
    rejected_reason: str | None = None

    @property
    def rejected(self) -> bool:
        return self.rejected_reason is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator": VALIDATOR_VERSION,
            "accepted_fields": sorted(self.accepted),
            "conflicts": self.conflicts,
            "ungrounded": self.ungrounded,
            "validation_confidence": self.validation_confidence,
            "rejected_reason": self.rejected_reason,
        }


def known_locators(unit: ExtractionUnit, extraction: RawExtraction, ocr_result: OCRResult | None) -> set[str]:
    """Every source address the model was allowed to cite."""
    locators = {unit.reference.locator, "file"}
    locators.update(other.reference.locator for other in extraction.units)
    if ocr_result:
        locators.update(block.reference(unit.reference.evidence_id).locator for block in ocr_result.blocks)
    return locators


def _searchable(unit: ExtractionUnit, extraction: RawExtraction, ocr_result: OCRResult | None) -> str:
    parts = [unit.text, extraction.text]
    if ocr_result:
        parts.append(ocr_result.text)
    return _canonical("\n".join(part for part in parts if part))


# Keys the parser derives on its own and never asks the model for. The amount's `role` is read from
# the words printed beside the figure; the model is not shown that question, so its silence is not a
# disagreement — counting it as one escalated every amount to the remote provider.
PARSER_DERIVED_KEYS = {"role"}


def _value_matches(claimed: Any, authoritative: Any) -> bool:
    if isinstance(authoritative, dict) and isinstance(claimed, dict):
        return all(
            _scalar_matches(claimed.get(key), value)
            for key, value in authoritative.items()
            if value is not None and key not in PARSER_DERIVED_KEYS
        )
    if isinstance(authoritative, list):
        claimed_list = claimed if isinstance(claimed, list) else [claimed]
        return {_canonical(str(item)) for item in claimed_list} == {_canonical(str(item)) for item in authoritative}
    return _scalar_matches(claimed, authoritative)


def _scalar_matches(claimed: Any, authoritative: Any) -> bool:
    if claimed is None or authoritative is None:
        return claimed == authoritative
    if isinstance(authoritative, (int, float)) and isinstance(claimed, (int, float)):
        return abs(float(claimed) - float(authoritative)) < 0.005
    return _canonical(str(claimed)) == _canonical(str(authoritative))


def validate(
    payload: dict[str, Any] | None,
    *,
    unit: ExtractionUnit,
    extraction: RawExtraction,
    ocr_result: OCRResult | None = None,
) -> GroundingResult:
    """Check a model payload against the source and the deterministic parser."""
    if not isinstance(payload, dict):
        return GroundingResult(rejected_reason="Model output was not a JSON object")

    result = GroundingResult()
    haystack = _searchable(unit, extraction, ocr_result)
    allowed = known_locators(unit, extraction, ocr_result)

    observed = payload.get("observed_text")
    if isinstance(observed, str) and observed.strip():
        # The model must reproduce the source rather than invent it — but OCR of a real screenshot
        # carries junk ("= L) e") and broken line wrapping that a model sensibly drops. Demanding an
        # exact substring rejected the entire output for tidying up, so coverage is measured
        # instead: nearly every word must come from the source, while omission and reflow are fine.
        if not _substantially_from_source(observed, haystack):
            return GroundingResult(rejected_reason="observed_text is not supported by the source text")
        result.observed_text = observed

    summary = payload.get("normalized_summary")
    result.normalized_summary = summary if isinstance(summary, str) and summary.strip() else None

    raw_confidence = payload.get("model_confidence")
    if isinstance(raw_confidence, (int, float)) and 0.0 <= float(raw_confidence) <= 1.0:
        result.model_confidence = float(raw_confidence)

    basis = payload.get("observation_basis")
    if isinstance(basis, str) and basis in {item.value for item in ObservationBasis}:
        result.observation_basis = ObservationBasis(basis)

    result.model_requires_review = bool(payload.get("requires_human_review", True))
    reason = payload.get("review_reason")
    result.model_review_reason = reason if isinstance(reason, str) and reason.strip() else None

    checked = 0
    grounded = 0

    for name in MATERIAL_FIELDS:
        claim = payload.get(name)
        if not isinstance(claim, dict):
            continue
        value = claim.get("value")

        if value in (None, "", [], {}):
            result.accepted.setdefault(
                name,
                FieldProvenance(
                    value=None,
                    basis=ObservationBasis.UNKNOWN,
                    reason=str(claim.get("reason") or "The source does not establish this field."),
                    validation_status=ValidationStatus.UNVALIDATED,
                    readability=_readability(claim),
                    # A partially readable value keeps its visible characters here even though the
                    # value itself stays null. The fragment is what was observed; completing it
                    # would be the invention this whole layer exists to refuse.
                    literal_transcription=(
                        str(claim["literal_transcription"]) if isinstance(claim.get("literal_transcription"), str) else None
                    ),
                ),
            )
            continue

        authoritative = unit.facts.get(name)
        if name in AUTHORITATIVE_FIELDS and authoritative and authoritative.basis is ObservationBasis.DIRECT and authoritative.value is not None:
            checked += 1
            if not _value_matches(value, authoritative.value):
                # The parser wins. The disagreement is recorded rather than silently dropped.
                result.conflicts.append(name)
                continue
            grounded += 1
            continue

        claimed_basis = claim.get("basis")
        field_basis = ObservationBasis(claimed_basis) if claimed_basis in {item.value for item in ObservationBasis} else ObservationBasis.INFERRED

        quote = claim.get("quote")
        citation = claim.get("source_reference")

        if field_basis in {ObservationBasis.DIRECT, ObservationBasis.DIRECT_VISUAL}:
            # Only claims that assert direct observation can be checked against the source, so only
            # they belong in the grounding ratio. Counting honest `inferred` claims in the
            # denominator would punish a model for correctly flagging its own uncertainty.
            checked += 1
            if not isinstance(quote, str) or not quote.strip() or _canonical(quote) not in haystack:
                result.ungrounded.append(name)
                continue
            if isinstance(citation, str) and citation.strip() and citation not in allowed:
                result.ungrounded.append(name)
                continue
            grounded += 1
            status = ValidationStatus.VALIDATED
        else:
            # Inferred claims cannot be grounded by definition; they are kept but never validated.
            status = ValidationStatus.UNVALIDATED

        confidence = claim.get("confidence")
        result.accepted[name] = FieldProvenance(
            value=value,
            basis=field_basis,
            quote=quote if isinstance(quote, str) else None,
            source_reference=_reference_for(citation, unit),
            confidence=float(confidence) if isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0 else None,
            validation_status=status,
            reason=str(claim["reason"]) if isinstance(claim.get("reason"), str) else None,
            readability=_readability(claim),
            literal_transcription=(
                str(claim["literal_transcription"]) if isinstance(claim.get("literal_transcription"), str) else None
            ),
        )

    for list_field in ("phone_numbers", "email_addresses", "account_identifiers"):
        values = payload.get(list_field)
        if not isinstance(values, list):
            continue
        supported = [str(item) for item in values if isinstance(item, (str, int)) and _canonical(str(item)) in haystack]
        if supported:
            result.accepted[list_field] = FieldProvenance(
                value=sorted(set(supported)),
                basis=ObservationBasis.DIRECT,
                quote=", ".join(sorted(set(supported))),
                source_reference=unit.reference.to_dict(),
                confidence=0.9,
                validation_status=ValidationStatus.VALIDATED,
            )

    result.validation_confidence = round(grounded / checked, 4) if checked else None
    return result


def _reference_for(citation: Any, unit: ExtractionUnit) -> dict[str, Any]:
    if isinstance(citation, dict):
        return citation
    reference = unit.reference.to_dict()
    if isinstance(citation, str) and citation.strip():
        reference["locator"] = citation
    return reference
