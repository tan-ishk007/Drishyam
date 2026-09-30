"""Confidence scoring, review classification and the correlation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.evidence_intelligence import confidence, correlation
from app.evidence_intelligence.schema import (
    Amount,
    ConfidenceBand,
    FieldProvenance,
    NormalizedRecordDraft,
    ObservationBasis,
    RelationStatus,
    RelationType,
    SourceType,
    ValidationStatus,
)

BASE_TIME = datetime(2024, 3, 12, 21, 15, tzinfo=timezone.utc)


@dataclass
class FakeRecord:
    """Stands in for a persisted `NormalizedRecord` row."""

    id: str
    evidence_id: str
    transaction_reference: str | None = None
    device_identifier: str | None = None
    phone_numbers: list = field(default_factory=list)
    email_addresses: list = field(default_factory=list)
    account_identifiers: list = field(default_factory=list)
    amount_value: float | None = None
    amount_currency: str | None = None
    event_time: datetime | None = None
    source_type: str = "chat_export"


# ------------------------------------------------------------------------------- confidence


def test_bands_follow_the_published_thresholds():
    assert confidence.band_for(0.95) is ConfidenceBand.HIGH
    assert confidence.band_for(0.85) is ConfidenceBand.HIGH
    assert confidence.band_for(0.84) is ConfidenceBand.MEDIUM
    assert confidence.band_for(0.60) is ConfidenceBand.MEDIUM
    assert confidence.band_for(0.59) is ConfidenceBand.LOW
    assert confidence.band_for(None) is ConfidenceBand.UNKNOWN


def _record(**overrides) -> NormalizedRecordDraft:
    draft = NormalizedRecordDraft(record_key="unit:1", source_type=SourceType.SCREENSHOT, observed_text="hello")
    for key, value in overrides.items():
        setattr(draft, key, value)
    return draft


def test_conflicting_values_are_never_silently_resolved():
    outcome = confidence.classify(_record(model_confidence=0.95), validation_confidence=0.95, conflicts=["amount"])

    assert outcome.validation_status is ValidationStatus.MISMATCH
    assert outcome.requires_human_review is True
    assert "amount" in outcome.review_reason
    assert "no automatic resolution" in outcome.review_reason


def test_inferred_identity_forces_review():
    draft = _record(model_confidence=0.99)
    draft.field_provenance["sender"] = FieldProvenance(value="Someone", basis=ObservationBasis.INFERRED)
    outcome = confidence.classify(draft, validation_confidence=0.99)

    assert outcome.requires_human_review is True
    assert "inferred" in outcome.review_reason


def test_degraded_source_forces_review():
    outcome = confidence.classify(_record(model_confidence=0.99), validation_confidence=1.0, source_quality_flags=["cropped"])

    assert outcome.requires_human_review is True
    assert "cropped" in outcome.review_reason


def test_sensitive_content_forces_review():
    outcome = confidence.classify(
        _record(model_confidence=0.99, observed_text="paise do warna dhamki dunga"),
        validation_confidence=1.0,
    )
    assert outcome.requires_human_review is True


def test_source_agreement_outweighs_model_self_assessment():
    # A model that is sure of itself but cannot be checked against the source must not outrank one
    # that is less sure but verifiable.
    confident_but_ungrounded = confidence.classify(_record(model_confidence=1.0), validation_confidence=0.2)
    modest_but_grounded = confidence.classify(_record(model_confidence=0.6), validation_confidence=1.0)

    assert confident_but_ungrounded.band is ConfidenceBand.LOW
    assert modest_but_grounded.band is ConfidenceBand.MEDIUM


def test_only_full_agreement_reaches_the_high_band():
    assert confidence.classify(_record(model_confidence=0.9), validation_confidence=1.0).band is ConfidenceBand.HIGH
    assert confidence.classify(_record(model_confidence=0.6), validation_confidence=1.0).band is ConfidenceBand.MEDIUM


def test_apply_writes_the_scores_onto_the_record():
    draft = _record(model_confidence=0.9, amount=Amount(value=25000.0, currency="INR"))
    confidence.apply(draft, validation_confidence=1.0)

    assert draft.validation_confidence == 1.0
    assert draft.final_confidence_band is ConfidenceBand.HIGH
    assert draft.requires_human_review is True  # a key amount always gets a second pair of eyes


# ------------------------------------------------------------------------------ correlation


def test_shared_transaction_reference_creates_a_corroboration_candidate():
    records = [
        FakeRecord("r1", "ev1", transaction_reference="HDFC0012345678", amount_value=25000.0, event_time=BASE_TIME),
        FakeRecord("r2", "ev2", transaction_reference="HDFC0012345678", amount_value=25000.0, event_time=BASE_TIME),
    ]
    candidates = correlation.correlate(records)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.relation_type is RelationType.CORROBORATION
    assert candidate.status is RelationStatus.CANDIDATE
    assert candidate.requires_human_review is True
    assert candidate.evidence_ids == ["ev1", "ev2"]
    assert "not a finding about a person" in candidate.reason


def test_same_reference_with_different_amount_is_a_contradiction():
    records = [
        FakeRecord("r1", "ev1", transaction_reference="UTR1", amount_value=25000.0),
        FakeRecord("r2", "ev2", transaction_reference="UTR1", amount_value=20000.0),
    ]
    contradictions = [c for c in correlation.correlate(records) if c.relation_type is RelationType.CONTRADICTION]

    assert len(contradictions) == 1
    assert "amount" in contradictions[0].matching_or_conflicting_fields
    assert "has not been resolved" in contradictions[0].reason


def test_incompatible_dates_for_one_reference_are_a_contradiction():
    records = [
        FakeRecord("r1", "ev1", transaction_reference="UTR1", event_time=BASE_TIME),
        FakeRecord("r2", "ev2", transaction_reference="UTR1", event_time=BASE_TIME + timedelta(days=5)),
    ]
    contradictions = [c for c in correlation.correlate(records) if c.relation_type is RelationType.CONTRADICTION]

    assert contradictions and "event_time" in contradictions[0].matching_or_conflicting_fields


def test_rows_from_one_evidence_item_do_not_corroborate_each_other():
    records = [
        FakeRecord("r1", "ev1", phone_numbers=["+919876543210"]),
        FakeRecord("r2", "ev1", phone_numbers=["+919876543210"]),
    ]
    assert correlation.correlate(records) == []


def test_shared_phone_between_chat_and_call_log_is_a_candidate():
    records = [
        FakeRecord("r1", "ev-chat", phone_numbers=["+919876500011"], source_type="chat_export"),
        FakeRecord("r2", "ev-calls", phone_numbers=["+919876500011"], source_type="call_log"),
    ]
    candidates = correlation.correlate(records)

    assert len(candidates) == 1
    assert candidates[0].matching_or_conflicting_fields == ["phone_numbers"]


def test_semantic_candidates_are_opt_in_and_weakly_scored():
    records = [
        FakeRecord("r1", "ev-chat", amount_value=25000.0, event_time=BASE_TIME),
        FakeRecord("r2", "ev-bank", amount_value=25000.0, event_time=BASE_TIME + timedelta(hours=1)),
    ]
    assert correlation.correlate(records) == []

    candidates = correlation.correlate(records, include_semantic=True)
    assert len(candidates) == 1
    assert candidates[0].confidence <= correlation.SEMANTIC_CONFIDENCE
    assert candidates[0].requires_human_review is True
    assert "requires verification" in candidates[0].reason


def test_identifier_specificity_orders_confidence():
    reference_pair = correlation.correlate(
        [FakeRecord("r1", "ev1", transaction_reference="UTR1"), FakeRecord("r2", "ev2", transaction_reference="UTR1")]
    )
    phone_pair = correlation.correlate(
        [FakeRecord("r3", "ev3", phone_numbers=["+919876543210"]), FakeRecord("r4", "ev4", phone_numbers=["+919876543210"])]
    )
    assert reference_pair[0].confidence > phone_pair[0].confidence


def test_correlation_is_idempotent_across_runs():
    records = [
        FakeRecord("r1", "ev1", transaction_reference="UTR1"),
        FakeRecord("r2", "ev2", transaction_reference="UTR1"),
    ]
    first = correlation.correlate(records)
    second = correlation.correlate(records)

    assert [c.idempotency_key for c in first] == [c.idempotency_key for c in second]
