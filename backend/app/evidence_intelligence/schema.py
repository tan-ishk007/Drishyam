"""Canonical source-grounded record schema.

`null` is a first-class, meaningful value here. A field is never filled from common sense: if the
source does not establish it, the value stays `None` and carries a reason.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.evidence_intelligence.references import SourceReference

RAW_EXTRACTION_VERSION = "grounded-v1"


class ObservationBasis(str, Enum):
    DIRECT = "direct"
    DIRECT_VISUAL = "direct_visual"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class ValidationStatus(str, Enum):
    VALIDATED = "validated"
    MISMATCH = "mismatch"
    UNVALIDATED = "unvalidated"
    REJECTED = "rejected"


class ConfidenceBand(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class Readability(str, Enum):
    """How much of a written value could actually be read.

    `PARTIALLY_READABLE` is the one that matters. A half-read phone number must keep its visible
    fragment and must never be completed into a whole number -- the fragment is an observation, the
    completion would be an invention.
    """

    READABLE = "readable"
    PARTIALLY_READABLE = "partially_readable"
    UNREADABLE = "unreadable"
    NOT_APPLICABLE = "not_applicable"


class MessageDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    UNKNOWN = "unknown"


class SourceType(str, Enum):
    SCREENSHOT = "screenshot"
    CHAT_EXPORT = "chat_export"
    EMAIL = "email"
    PDF = "pdf"
    CSV = "csv"
    BANK_RECORD = "bank_record"
    CALL_LOG = "call_log"
    IMAGE = "image"
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    # The sources SIH26189 names. They parse like a table or a document, but naming them lets the
    # extractor read the structure each one actually has -- an A-party and B-party column in a CDR,
    # a report header and stated roles in an FIR or a surveillance note.
    CDR = "cdr"
    FIR = "fir"
    POLICE_REPORT = "police_report"
    SURVEILLANCE = "surveillance"
    SOCIAL_MEDIA = "social_media"
    UNKNOWN = "unknown"


class TimePrecision(str, Enum):
    EXACT = "exact"
    DATE_ONLY = "date_only"
    # The clock reading is observed but the calendar day is not stated anywhere in the source.
    TIME_ONLY = "time_only"
    APPROXIMATE = "approximate"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class FieldProvenance(BaseModel):
    """Why one field holds the value it holds, and where that value can be seen."""

    model_config = ConfigDict(extra="forbid")

    value: Any = None
    basis: ObservationBasis = ObservationBasis.UNKNOWN
    quote: str | None = None
    source_reference: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED
    reason: str | None = None
    # For handwritten and degraded sources: what was legible, and the characters as printed before
    # any normalisation. A partially readable value keeps `literal_transcription` and leaves
    # `value` null rather than guessing the rest.
    readability: Readability = Readability.NOT_APPLICABLE
    literal_transcription: str | None = None

    @classmethod
    def observed(cls, value: Any, *, quote: str, reference: SourceReference, confidence: float) -> FieldProvenance:
        return cls(
            value=value,
            basis=ObservationBasis.DIRECT,
            quote=quote,
            source_reference=reference.to_dict(),
            confidence=confidence,
            validation_status=ValidationStatus.VALIDATED,
        )

    @classmethod
    def unestablished(cls, reason: str) -> FieldProvenance:
        return cls(value=None, basis=ObservationBasis.UNKNOWN, reason=reason, validation_status=ValidationStatus.UNVALIDATED)


class AmountRole(str, Enum):
    """What a figure is, judged from the words printed beside it.

    Only `PAYMENT`, `REQUEST` and `FEE` describe money that moved or was asked for. A `BALANCE` is a
    position, not a transfer, and listing one in a transaction trail asserts a movement the evidence
    never recorded.
    """

    PAYMENT = "payment"
    REQUEST = "request"
    FEE = "fee"
    BALANCE = "balance"
    UNKNOWN = "unknown"


class Amount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | None = None
    currency: str | None = None
    role: AmountRole = AmountRole.UNKNOWN


class NormalizedRecordDraft(BaseModel):
    """One reviewable observation derived from one piece of evidence.

    Material identity fields default to None on purpose. A header phone number becomes
    `chat_participant_identifier`, never `sender` or `receiver`, unless the source proves the role.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    record_key: str
    source_type: SourceType = SourceType.UNKNOWN
    observed_text: str | None = None
    normalized_summary: str | None = None
    event_type: str | None = None
    event_time: str | None = None
    event_time_precision: TimePrecision = TimePrecision.UNKNOWN
    participant_a: str | None = None
    participant_b: str | None = None
    sender: str | None = None
    receiver: str | None = None
    message_direction: MessageDirection | None = None
    chat_participant_identifier: str | None = None
    phone_numbers: list[str] = Field(default_factory=list)
    email_addresses: list[str] = Field(default_factory=list)
    account_identifiers: list[str] = Field(default_factory=list)
    # SIH26189 asks for people, locations, vehicles, phone numbers and
    # organisations. These carry the three classes the identifier fields above
    # cannot express. `location` stays as the record's single free-text place;
    # `location_names` holds the marked places that may become graph nodes.
    vehicle_identifiers: list[str] = Field(default_factory=list)
    organisation_names: list[str] = Field(default_factory=list)
    person_names: list[str] = Field(default_factory=list)
    person_roles: dict[str, str] = Field(default_factory=dict)
    location_names: list[str] = Field(default_factory=list)
    transaction_reference: str | None = None
    amount: Amount = Field(default_factory=Amount)
    location: str | None = None
    device_identifier: str | None = None
    event_attributes: dict[str, Any] = Field(default_factory=dict)
    observation_basis: ObservationBasis = ObservationBasis.UNKNOWN
    field_provenance: dict[str, FieldProvenance] = Field(default_factory=dict)
    model_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    validation_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    final_confidence_band: ConfidenceBand = ConfidenceBand.UNKNOWN
    validation_status: ValidationStatus = ValidationStatus.UNVALIDATED
    requires_human_review: bool = True
    review_reason: str | None = None
    raw_extraction_version: str = RAW_EXTRACTION_VERSION
    raw_model_output_version: str | None = None
    extraction_model_name: str | None = None
    prompt_version: str | None = None

    @field_validator("event_type")
    @classmethod
    def _reject_legal_conclusions(cls, value: str | None) -> str | None:
        """A model may describe an event; it may never adjudicate one."""
        if value and value.lower().replace(" ", "_") in FORBIDDEN_EVENT_TYPES:
            raise ValueError("Event type asserts a legal or criminal conclusion")
        return value


FORBIDDEN_EVENT_TYPES = {
    "fraud",
    "fraud_committed",
    "crime",
    "criminal_act",
    "guilt",
    "guilty",
    "culprit_identified",
    "money_laundering",
    "theft",
    "extortion",
    "criminal_conspiracy",
    "legal_violation",
}


class RelationType(str, Enum):
    CORROBORATION = "corroboration"
    CONTRADICTION = "contradiction"


class RelationStatus(str, Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class RelationCandidate(BaseModel):
    """A candidate link between records. Never an automatic conclusion."""

    model_config = ConfigDict(extra="forbid")

    relation_type: RelationType
    status: RelationStatus = RelationStatus.CANDIDATE
    evidence_ids: list[str] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)
    matching_or_conflicting_fields: list[str] = Field(default_factory=list)
    reason: str
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_human_review: bool = True
    review_decision: str | None = None
    idempotency_key: str = ""


class ReviewAction(str, Enum):
    CONFIRM = "confirm"
    EDIT = "edit"
    REJECT = "reject"
    MARK_UNKNOWN = "mark_unknown"


class RelationReviewAction(str, Enum):
    CONFIRM_RELATIONSHIP = "confirm_relationship"
    REJECT_RELATIONSHIP = "reject_relationship"
