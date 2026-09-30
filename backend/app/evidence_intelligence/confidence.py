"""Explainable confidence scoring and mandatory-review classification.

A single opaque score is never produced. Model self-assessment and independent source agreement are
scored separately and combined into a band that a reviewer can argue with.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.evidence_intelligence.schema import (
    ConfidenceBand,
    NormalizedRecordDraft,
    ObservationBasis,
    ValidationStatus,
)

HIGH_BAND_FLOOR = 0.85
MEDIUM_BAND_FLOOR = 0.60

IDENTITY_FIELDS = ("sender", "receiver", "participant_a", "participant_b", "chat_participant_identifier")
KEY_FINDING_FIELDS = ("amount", "transaction_reference", "account_identifiers", "event_time")

SENSITIVE_MARKERS = (
    "threat",
    "kill",
    "blackmail",
    "extort",
    "fraud",
    "scam",
    "cheat",
    "police",
    "fir",
    "arrest",
    "aadhaar",
    "aadhar",
    "pan card",
    "otp",
    "password",
    "dhamki",
    "jaan se",
)

AMBIGUOUS_SOURCE_MARKERS = ("cropped", "blurry", "incomplete", "low_quality", "partial", "ambiguous", "truncated")


@dataclass
class ConfidenceOutcome:
    model_confidence: float | None
    validation_confidence: float | None
    band: ConfidenceBand
    validation_status: ValidationStatus
    requires_human_review: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def review_reason(self) -> str | None:
        return "; ".join(self.reasons) if self.reasons else None


def band_for(score: float | None) -> ConfidenceBand:
    if score is None:
        return ConfidenceBand.UNKNOWN
    if score >= HIGH_BAND_FLOOR:
        return ConfidenceBand.HIGH
    if score >= MEDIUM_BAND_FLOOR:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def _combined(model_confidence: float | None, validation_confidence: float | None) -> float | None:
    """Agreement with the source is weighted above the model's opinion of itself."""
    if model_confidence is None and validation_confidence is None:
        return None
    if model_confidence is None:
        return validation_confidence
    if validation_confidence is None:
        return model_confidence * 0.75
    return round((model_confidence * 0.4) + (validation_confidence * 0.6), 4)


def _mentions_sensitive_content(record: NormalizedRecordDraft) -> bool:
    haystack = " ".join(filter(None, [record.observed_text, record.normalized_summary, record.event_type])).lower()
    return any(marker in haystack for marker in SENSITIVE_MARKERS)


def classify(
    record: NormalizedRecordDraft,
    *,
    validation_confidence: float | None,
    conflicts: list[str] | None = None,
    source_quality_flags: list[str] | None = None,
) -> ConfidenceOutcome:
    """Score a record and decide whether a human must look at it before it can be relied on."""
    conflicts = conflicts or []
    quality_flags = source_quality_flags or []
    reasons: list[str] = []

    combined = _combined(record.model_confidence, validation_confidence)
    band = band_for(combined)

    if conflicts:
        status = ValidationStatus.MISMATCH
        reasons.append(
            f"Conflicting readings were preserved for: {', '.join(sorted(set(conflicts)))}. "
            "Both values are kept and no automatic resolution was applied."
        )
    elif validation_confidence is None:
        status = ValidationStatus.UNVALIDATED
    elif validation_confidence >= MEDIUM_BAND_FLOOR:
        status = ValidationStatus.VALIDATED
    else:
        status = ValidationStatus.MISMATCH
        reasons.append("Claimed values could not be located in the raw extraction with sufficient agreement.")

    if combined is None or combined < HIGH_BAND_FLOOR:
        reasons.append(f"Combined confidence is below the {HIGH_BAND_FLOOR} review threshold.")

    inferred_identity = [
        name
        for name in IDENTITY_FIELDS
        if (provenance := record.field_provenance.get(name))
        and provenance.value is not None
        and provenance.basis in {ObservationBasis.INFERRED, ObservationBasis.UNKNOWN}
    ]
    if inferred_identity:
        reasons.append(f"Identity or role is inferred rather than directly supported for: {', '.join(inferred_identity)}.")

    key_findings = [
        name
        for name in KEY_FINDING_FIELDS
        if (provenance := record.field_provenance.get(name)) and provenance.value not in (None, [], {})
    ]
    if key_findings:
        reasons.append(f"Record carries key findings that affect case conclusions: {', '.join(key_findings)}.")

    if _mentions_sensitive_content(record):
        reasons.append("Source text contains sensitive, threatening or allegation-like content.")

    ambiguous = [flag for flag in quality_flags if flag in AMBIGUOUS_SOURCE_MARKERS]
    if ambiguous:
        reasons.append(f"Source quality is degraded or incomplete: {', '.join(sorted(set(ambiguous)))}.")

    if record.observation_basis in {ObservationBasis.INFERRED, ObservationBasis.UNKNOWN}:
        reasons.append("Record meaning is contextual rather than directly represented in the source.")

    return ConfidenceOutcome(
        model_confidence=record.model_confidence,
        validation_confidence=validation_confidence,
        band=band,
        validation_status=status,
        requires_human_review=bool(reasons),
        reasons=reasons,
    )


def apply(
    record: NormalizedRecordDraft,
    *,
    validation_confidence: float | None,
    conflicts: list[str] | None = None,
    source_quality_flags: list[str] | None = None,
) -> NormalizedRecordDraft:
    outcome = classify(
        record,
        validation_confidence=validation_confidence,
        conflicts=conflicts,
        source_quality_flags=source_quality_flags,
    )
    record.validation_confidence = outcome.validation_confidence
    record.final_confidence_band = outcome.band
    record.validation_status = outcome.validation_status
    record.requires_human_review = outcome.requires_human_review
    record.review_reason = outcome.review_reason
    return record
