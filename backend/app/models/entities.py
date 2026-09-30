"""SQLAlchemy data model for the independent DRISHYAM backend MVP."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.security import utcnow


def new_id() -> str:
    return str(uuid4())


class Role(str, Enum):
    INVESTIGATOR = "investigator"
    REVIEWER = "reviewer"
    BANK_ANALYST = "bank_analyst"
    ADMIN = "admin"


class AccountStatus(str, Enum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    DISABLED = "disabled"


class CaseStatus(str, Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    CLOSED = "closed"
    ARCHIVED = "archived"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceStatus(str, Enum):
    UPLOADED = "uploaded"
    VALIDATING = "validating"
    HASHING = "hashing"
    QUEUED = "queued"
    PROCESSING = "processing"
    OCR = "ocr"
    EXTRACTING = "extracting"
    NORMALIZING = "normalizing"
    BUILDING_GRAPH = "building_graph"
    EVALUATING_ALERTS = "evaluating_alerts"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    # Grounded-pipeline stage vocabulary. These are additive: `EvidenceFile.status` still moves only
    # through the legacy values above, because the frontend pins those as a closed union. The
    # granular lifecycle is served from the evidence stages endpoint instead.
    RECEIVED = "received"
    TYPE_DETECTED = "type_detected"
    OCR_COMPLETED = "ocr_completed"
    LOCAL_MODEL_COMPLETED = "local_model_completed"
    GROQ_ESCALATED = "groq_escalated"
    VALIDATED = "validated"
    REVIEW_REQUIRED = "review_required"
    READY = "ready"
    PARTIALLY_PROCESSED = "partially_processed"


class ProcessingState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ReviewStatus(str, Enum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class AlertStatus(str, Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


class ClaimStatus(str, Enum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    CORROBORATED = "corroborated"
    CHALLENGED = "challenged"
    ARCHIVED = "archived"


class SourceRelationship(str, Enum):
    SUPPORTS = "supports"
    CHALLENGES = "challenges"
    CONTEXT = "context"


class ContradictionStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class NotificationLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ACTION = "action"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[Role] = mapped_column(SAEnum(Role, name="role"), nullable=False, default=Role.INVESTIGATOR)
    status: Mapped[AccountStatus] = mapped_column(
        SAEnum(AccountStatus, name="account_status"), nullable=False, default=AccountStatus.PENDING_VERIFICATION
    )
    auth_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="password")
    google_subject: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    owned_cases: Mapped[list[Case]] = relationship("Case", back_populates="owner", foreign_keys="Case.owner_id")
    memberships: Mapped[list[CaseMembership]] = relationship("CaseMembership", back_populates="user")
    notifications: Mapped[list[Notification]] = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    notification_preferences: Mapped[list[NotificationPreference]] = relationship("NotificationPreference", back_populates="user", cascade="all, delete-orphan")
    account_settings: Mapped[AccountSettings | None] = relationship("AccountSettings", back_populates="user", cascade="all, delete-orphan", uselist=False)
    account_sessions: Mapped[list[AccountSession]] = relationship("AccountSession", back_populates="user", cascade="all, delete-orphan")


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False, default="signup_verification")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AccountSettings(Base):
    """Explicitly saved, non-authorization profile and presentation settings for one user."""

    __tablename__ = "account_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    language: Mapped[str | None] = mapped_column(String(80))
    timezone: Mapped[str | None] = mapped_column(String(80))
    date_format: Mapped[str | None] = mapped_column(String(40))
    time_format: Mapped[str | None] = mapped_column(String(40))
    items_per_page: Mapped[int | None] = mapped_column(Integer)
    theme: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="account_settings")


class AccountSession(Base):
    """Server-side metadata for an issued bearer session; raw tokens are never stored."""

    __tablename__ = "account_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    device_label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship("User", back_populates="account_sessions")


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    crime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    fir_number: Mapped[str | None] = mapped_column(String(120))
    victim_alias: Mapped[str | None] = mapped_column(String(160))
    date_range_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_range_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CaseStatus] = mapped_column(SAEnum(CaseStatus, name="case_status"), nullable=False, default=CaseStatus.OPEN)
    priority: Mapped[Priority] = mapped_column(SAEnum(Priority, name="priority"), nullable=False, default=Priority.MEDIUM)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship("User", back_populates="owned_cases", foreign_keys=[owner_id])
    memberships: Mapped[list[CaseMembership]] = relationship("CaseMembership", back_populates="case", cascade="all, delete-orphan")
    evidence_files: Mapped[list[EvidenceFile]] = relationship("EvidenceFile", back_populates="case", cascade="all, delete-orphan")
    entities: Mapped[list[Entity]] = relationship("Entity", back_populates="case", cascade="all, delete-orphan")
    events: Mapped[list[Event]] = relationship("Event", back_populates="case", cascade="all, delete-orphan")
    transactions: Mapped[list[Transaction]] = relationship("Transaction", back_populates="case", cascade="all, delete-orphan")
    alerts: Mapped[list[Alert]] = relationship("Alert", back_populates="case", cascade="all, delete-orphan")
    claims: Mapped[list[Claim]] = relationship("Claim", back_populates="case", cascade="all, delete-orphan")
    contradictions: Mapped[list[Contradiction]] = relationship("Contradiction", back_populates="case", cascade="all, delete-orphan")
    notifications: Mapped[list[Notification]] = relationship("Notification", back_populates="case")

    __table_args__ = (Index("ix_cases_status_updated", "status", "updated_at"),)


class CaseMembership(Base):
    __tablename__ = "case_memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    case_role: Mapped[Role] = mapped_column(SAEnum(Role, name="case_role"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    case: Mapped[Case] = relationship("Case", back_populates="memberships")
    user: Mapped[User] = relationship("User", back_populates="memberships")

    __table_args__ = (UniqueConstraint("case_id", "user_id", name="uq_case_membership"),)


class EvidenceFile(Base):
    __tablename__ = "evidence_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    source_category: Mapped[str] = mapped_column(String(64), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    declared_mime: Mapped[str | None] = mapped_column(String(128))
    detected_mime: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[EvidenceStatus] = mapped_column(
        SAEnum(EvidenceStatus, name="evidence_status"), nullable=False, default=EvidenceStatus.UPLOADED
    )
    uploader_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    case: Mapped[Case] = relationship("Case", back_populates="evidence_files")
    extracted_texts: Mapped[list[ExtractedText]] = relationship("ExtractedText", back_populates="evidence_file", cascade="all, delete-orphan")
    processing_runs: Mapped[list[ProcessingRun]] = relationship("ProcessingRun", back_populates="evidence_file", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("case_id", "sha256", "version", name="uq_evidence_case_hash_version"),
        Index("ix_evidence_case_status_uploaded", "case_id", "status", "uploaded_at"),
        Index("ix_evidence_sha256_case", "sha256", "case_id"),
    )


class ExtractedText(Base):
    __tablename__ = "extracted_text"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id", ondelete="CASCADE"), index=True, nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False, default="mvp-v1")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=1.0)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    evidence_file: Mapped[EvidenceFile] = relationship("EvidenceFile", back_populates="extracted_texts")
    __table_args__ = (UniqueConstraint("evidence_id", "pipeline_version", name="uq_extracted_text_version"),)


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    source_evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id", ondelete="RESTRICT"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(512), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    review_status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(ReviewStatus, name="entity_review_status"), nullable=False, default=ReviewStatus.UNREVIEWED
    )
    first_seen_event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    case: Mapped[Case] = relationship("Case", back_populates="entities")
    event_links: Mapped[list[EventEntity]] = relationship("EventEntity", back_populates="entity", foreign_keys="EventEntity.entity_id")
    __table_args__ = (
        Index("ix_entities_case_type_normalized", "case_id", "entity_type", "normalized_value"),
        Index("ix_entities_type_normalized_case", "entity_type", "normalized_value", "case_id"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id", ondelete="RESTRICT"), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    original_time: Mapped[str | None] = mapped_column(String(128))
    time_precision: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(8), default="INR")
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.5)
    review_status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(ReviewStatus, name="event_review_status"), nullable=False, default=ReviewStatus.UNREVIEWED
    )
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    case: Mapped[Case] = relationship("Case", back_populates="events")
    entity_links: Mapped[list[EventEntity]] = relationship("EventEntity", back_populates="event", cascade="all, delete-orphan")
    __table_args__ = (Index("ix_events_case_time", "case_id", "occurred_at"),)


class EventEntity(Base):
    __tablename__ = "event_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False, default="mentioned_in")
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=1.0)

    event: Mapped[Event] = relationship("Event", back_populates="entity_links")
    entity: Mapped[Entity] = relationship("Entity", back_populates="event_links", foreign_keys=[entity_id])
    __table_args__ = (UniqueConstraint("event_id", "entity_id", "relationship_type", name="uq_event_entity_relation"),)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    source_evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id", ondelete="RESTRICT"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    reference_id: Mapped[str | None] = mapped_column(String(160), index=True)
    sender_value: Mapped[str | None] = mapped_column(String(256))
    receiver_value: Mapped[str | None] = mapped_column(String(256))
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.5)
    review_status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(ReviewStatus, name="transaction_review_status"), nullable=False, default=ReviewStatus.UNREVIEWED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    case: Mapped[Case] = relationship("Case", back_populates="transactions")
    __table_args__ = (
        Index("ix_transactions_case_time", "case_id", "occurred_at"),
        Index("ix_transactions_reference_case", "reference_id", "case_id"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    rule_code: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity, name="alert_severity"), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(SAEnum(AlertStatus, name="alert_status"), nullable=False, default=AlertStatus.OPEN)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    affected_evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # The sourced facts behind this alert, in the order the sources record them. Each step names the
    # file and place it was read from, so a reader can open any line of the story rather than being
    # handed a conclusion and a pile of file ids. Null means the alert predates the column and has
    # no sequence -- which is not the same as a sequence in which nothing happened.
    sequence: Mapped[list | None] = mapped_column(JSON)
    related_event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[Case] = relationship("Case", back_populates="alerts")
    __table_args__ = (Index("ix_alerts_case_status_severity", "case_id", "status", "severity"),)


class CaseVisit(Base):
    """When one user last opened one case.

    Per user rather than per case: what is new to an investigator returning after a week is not new
    to the colleague who uploaded it yesterday, and a single shared timestamp would be wrong for
    everybody except the last person through the door.

    It records that somebody opened the case, which the audit log also records. This is not a
    duplicate of that: the audit log is the account of who did what, and reading it backwards to
    find one user's previous visit on every case open would be a query over the whole history to
    answer a question one row can hold.
    """

    __tablename__ = "case_visits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    last_opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("case_id", "user_id", name="uq_case_visit"),)


class CaseNote(Base):
    """Something an investigator knows, kept beside what the system read.

    An investigator holds things no evidence file states: what a witness said on the doorstep, which
    of two spellings is the same person, why a lead was dropped. That belongs in the case, not in a
    notebook that leaves with them.

    **It is never mixed into extracted facts.** A note lives in its own table, is returned through
    its own endpoint, and is marked as investigator commentary everywhere it is shown, including in
    the report. The whole extraction layer is built on the line between what a source states and
    what somebody concluded; a note that could be mistaken for the former would erase it.

    Deletion is recorded rather than performed. A note that shaped an investigation and then
    vanished without trace is exactly the kind of gap a defence should be able to see.
    """

    __tablename__ = "case_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    # What the note is about: an entity, a relation, or the case itself.
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (Index("ix_case_notes_subject", "case_id", "subject_type", "subject_id"),)


class PriorRecord(Base):
    """One entry in the national record of registered cases, as this deployment holds it.

    This is a different source from the shared ledger and answers a different question. The ledger
    says another force is working a live case that touches this identity, and deliberately holds
    nothing else. This says a case involving this identity was registered before, and comes from an
    authoritative record that is entitled to hold the details -- an NCRB or CCTNS extract in a real
    deployment, and a synthetic dataset here.

    **Disposal is not optional.** A record store that showed convictions and quietly omitted
    acquittals and closures would be a lie told by arithmetic, and it is the lie that turns a
    lookup into an accusation. Every row carries what actually happened to the case.

    Nothing here is evidence in the case a reader is working. Under section 46 of the Bharatiya
    Sakshya Adhiniyam a person's previous bad character is generally not relevant, and "he did it
    before" is precisely the reasoning the rest of this product refuses to make. The record is here
    so an investigator can find the officer who dealt with it, not so a case can lean on it.
    """

    __tablename__ = "prior_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # The canonical form the resolver produces, so a number written four ways still matches.
    identifier_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    subject_name: Mapped[str | None] = mapped_column(String(160))
    record_reference: Mapped[str] = mapped_column(String(96), nullable=False)
    police_station: Mapped[str] = mapped_column(String(160), nullable=False)
    district: Mapped[str | None] = mapped_column(String(160))
    sections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    registered_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # What became of it: under_investigation, chargesheeted, convicted, acquitted, closed, quashed.
    disposal: Mapped[str] = mapped_column(String(32), nullable=False)
    disposal_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_officer: Mapped[str | None] = mapped_column(String(320))
    source: Mapped[str] = mapped_column(String(96), nullable=False, default="synthetic-national-dataset")

    __table_args__ = (
        Index("ix_prior_records_identifier", "identifier_type", "identifier_value"),
        UniqueConstraint("record_reference", "identifier_type", "identifier_value", name="uq_prior_record_identity"),
    )


class LedgerEntry(Base):
    """One identifier published to the shared ledger, as a hash and nothing else.

    This is the only store in this product that several forces read and write. Everywhere else a
    local hash chain is the honest answer, because there is one party and it is trusted; here the
    parties are different districts who must be able to find a shared identifier without either
    being able to read the other's case, or to quietly remove an entry once it is written.

    **What is here and what is deliberately not.** The identifier itself never is: only a keyed
    digest of it, which two districts sharing the key both compute to the same value. The case
    reference and a contact are here, because the entire point is that somebody can pick up a phone.
    No evidence, no names, no statement about what the case contains.

    Chained like the audit log, so an entry cannot be removed or backdated by whoever holds the
    store -- which is the property a shared ledger has to have and a plain table does not.
    """

    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # HMAC-SHA256 over "type:canonical value", keyed with the secret the participating districts
    # share. A plain digest would not do: the space of phone numbers is small enough to enumerate,
    # so an unkeyed hash of one is the number itself with extra steps.
    identifier_digest: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    case_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    contact: Mapped[str] = mapped_column(String(320), nullable=False)
    published_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # The case this was published from. Local bookkeeping so a case can withdraw what it published
    # and can be told what it already has out there; never returned to another district.
    source_case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"), index=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        # One district publishing the same identifier for the same case twice adds nothing and
        # would make the ledger's own counts meaningless.
        UniqueConstraint("identifier_digest", "case_reference", name="uq_ledger_digest_case"),
        Index("ix_ledger_published_at", "published_at"),
    )


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decision: Mapped[ReviewStatus] = mapped_column(SAEnum(ReviewStatus, name="review_decision_status"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id", ondelete="CASCADE"), index=True, nullable=False)
    pipeline_stage: Mapped[str] = mapped_column(String(80), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False, default="mvp-v1")
    state: Mapped[ProcessingState] = mapped_column(
        SAEnum(ProcessingState, name="processing_state"), nullable=False, default=ProcessingState.PENDING
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(128), index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_messages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    evidence_file: Mapped[EvidenceFile] = relationship("EvidenceFile", back_populates="processing_runs")
    __table_args__ = (UniqueConstraint("evidence_id", "pipeline_stage", "pipeline_version", name="uq_processing_stage_version"),)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="RESTRICT"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ProcessingState] = mapped_column(
        SAEnum(ProcessingState, name="report_state"), nullable=False, default=ProcessingState.PENDING
    )
    review_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    redaction_profile: Mapped[str] = mapped_column(String(64), nullable=False, default="standard")
    # Who this report is for. Redaction says what to hide from a reader; the profile says what that
    # reader is being handed at all.
    profile: Mapped[str] = mapped_column(String(32), nullable=False, default="case_file")
    storage_key: Mapped[str | None] = mapped_column(String(1024), unique=True)
    # The numbered findings exactly as this report printed them, each keeping the evidence file and
    # the place inside it. Kept rather than recomputed: a relationship added or reviewed since would
    # renumber the list, and F-07 in a filed document would come to mean a different statement.
    findings: Mapped[list | None] = mapped_column(JSON)
    generated_by_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("case_id", "version", name="uq_report_case_version"),)


class TrustifyReceipt(Base):
    __tablename__ = "trustify_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="RESTRICT"), index=True, nullable=False)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), unique=True, nullable=False)
    verification_id: Mapped[str] = mapped_column(String(96), unique=True, index=True, nullable=False)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_chain_hash: Mapped[str | None] = mapped_column(String(64))
    # One value standing for the whole set of evidence this report covered, and the leaves it was
    # built from. The leaves are kept so an inclusion proof can be produced later for any one file
    # without rebuilding the set from a case that has moved on since.
    merkle_root: Mapped[str | None] = mapped_column(String(64))
    merkle_leaves: Mapped[list | None] = mapped_column(JSON)
    review_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(64), nullable=False, default="trustify-v1")
    manifest_storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_audit_case_created", "case_id", "created_at"),)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ClaimStatus] = mapped_column(SAEnum(ClaimStatus, name="claim_status"), nullable=False, default=ClaimStatus.DRAFT)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    case: Mapped[Case] = relationship("Case", back_populates="claims")
    source_links: Mapped[list[ClaimSourceLink]] = relationship("ClaimSourceLink", back_populates="claim", cascade="all, delete-orphan")
    __table_args__ = (Index("ix_claims_case_status_created", "case_id", "status", "created_at"),)


class ClaimSourceLink(Base):
    __tablename__ = "claim_source_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    relationship_type: Mapped[SourceRelationship] = mapped_column("relationship", SAEnum(SourceRelationship, name="source_relationship"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    claim: Mapped[Claim] = relationship("Claim", back_populates="source_links")
    __table_args__ = (UniqueConstraint("claim_id", "source_type", "source_id", "relationship", name="uq_claim_source_link"),)


class Contradiction(Base):
    __tablename__ = "contradictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ContradictionStatus] = mapped_column(SAEnum(ContradictionStatus, name="contradiction_status"), nullable=False, default=ContradictionStatus.OPEN)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    case: Mapped[Case] = relationship("Case", back_populates="contradictions")
    source_links: Mapped[list[ContradictionSourceLink]] = relationship("ContradictionSourceLink", back_populates="contradiction", cascade="all, delete-orphan")
    __table_args__ = (Index("ix_contradictions_case_status_created", "case_id", "status", "created_at"),)


class ContradictionSourceLink(Base):
    __tablename__ = "contradiction_source_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contradiction_id: Mapped[str] = mapped_column(ForeignKey("contradictions.id", ondelete="CASCADE"), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    relationship_type: Mapped[SourceRelationship] = mapped_column("relationship", SAEnum(SourceRelationship, name="source_relationship"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    contradiction: Mapped[Contradiction] = relationship("Contradiction", back_populates="source_links")
    __table_args__ = (UniqueConstraint("contradiction_id", "source_type", "source_id", "relationship", name="uq_contradiction_source_link"),)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="notification_preferences")
    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_notification_preference_user_category"),)


class RawExtractionArtifact(Base):
    """One versioned, immutable layer of deterministic extraction for a piece of evidence.

    Written and committed before any model runs, so a provider outage can never destroy extraction
    that already succeeded.
    """

    __tablename__ = "raw_extraction_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    artifact_version: Mapped[str] = mapped_column(String(64), nullable=False)
    layer: Mapped[str] = mapped_column(String(48), nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(96), nullable=False)
    source_type: Mapped[str] = mapped_column(String(48), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    quality_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("evidence_id", "artifact_version", "layer", name="uq_raw_artifact_version_layer"),
        Index("ix_raw_artifacts_case_evidence", "case_id", "evidence_id"),
    )


class ModelInferenceRun(Base):
    """One provider call. Raw model output is preserved verbatim, including when models disagree."""

    __tablename__ = "model_inference_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    record_key: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(48), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="local")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    raw_output: Mapped[str | None] = mapped_column(Text)
    parsed_payload: Mapped[dict | None] = mapped_column(JSON)
    grounding_report: Mapped[dict | None] = mapped_column(JSON)
    error_json: Mapped[dict | None] = mapped_column(JSON)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("evidence_id", "record_key", "cache_key", name="uq_inference_run_cache"),
        Index("ix_inference_case_evidence", "case_id", "evidence_id"),
    )


class NormalizedRecord(Base):
    """A source-grounded observation. `null` is a meaningful, deliberate value in every column."""

    __tablename__ = "normalized_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36))
    record_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(48), nullable=False)
    observed_text: Mapped[str | None] = mapped_column(Text)
    normalized_summary: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(String(120))
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    event_time_raw: Mapped[str | None] = mapped_column(String(160))
    event_time_precision: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    participant_a: Mapped[str | None] = mapped_column(String(255))
    participant_b: Mapped[str | None] = mapped_column(String(255))
    sender: Mapped[str | None] = mapped_column(String(255))
    receiver: Mapped[str | None] = mapped_column(String(255))
    message_direction: Mapped[str | None] = mapped_column(String(16))
    chat_participant_identifier: Mapped[str | None] = mapped_column(String(255))
    phone_numbers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    email_addresses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    account_identifiers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # SIH26189 entity classes. JSON lists to match the identifier columns above.
    vehicle_identifiers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    organisation_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    person_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # What this record called each person: {name: role}. A role belongs to a reading, not to
    # a person -- the same individual can be a witness in one source and a suspect in another.
    person_roles: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    location_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    transaction_reference: Mapped[str | None] = mapped_column(String(160), index=True)
    amount_value: Mapped[float | None] = mapped_column(Numeric(16, 2))
    amount_currency: Mapped[str | None] = mapped_column(String(8))
    # What the figure is — a payment, a request, a fee, or a balance. A balance is a position, not a
    # transfer, so it must never be projected into the transaction trail.
    amount_role: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown", server_default="unknown")
    location: Mapped[str | None] = mapped_column(String(255))
    device_identifier: Mapped[str | None] = mapped_column(String(160))
    event_attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    observation_basis: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    field_provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    model_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    validation_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    final_confidence_band: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    validation_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unvalidated")
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    review_reason: Mapped[str | None] = mapped_column(Text)
    review_state: Mapped[str] = mapped_column(String(24), nullable=False, default="unreviewed")
    conflict_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_extraction_version: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_model_output_version: Mapped[str | None] = mapped_column(String(64))
    extraction_model_name: Mapped[str | None] = mapped_column(String(160))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("evidence_id", "record_key", "raw_extraction_version", name="uq_normalized_record_version"),
        Index("ix_normalized_case_review", "case_id", "requires_human_review", "final_confidence_band"),
        Index("ix_normalized_case_created", "case_id", "created_at"),
    )


class RecordRelation(Base):
    """A candidate corroboration or contradiction. Never an automatic conclusion."""

    __tablename__ = "record_relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    relation_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="candidate")
    detection_method: Mapped[str] = mapped_column(String(32), nullable=False, default="exact_match")
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    record_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    matching_or_conflicting_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_references: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.0)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    review_decision: Mapped[str | None] = mapped_column(String(32))
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_record_relations_case_type_status", "case_id", "relation_type", "status"),)


class EntityOccurrence(Base):
    """Every place one identifier was seen.

    `Entity.source_evidence_id` can only name the file the identifier was *first* seen in, so a UPI
    handle appearing in a chat, a receipt and a bank statement still looked like it belonged to one
    file. Cross-evidence linking is the product's whole purpose, so where an identifier appears is
    modelled as its own many-to-many fact rather than inferred by walking events.
    """

    __tablename__ = "entity_occurrences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id", ondelete="CASCADE"), index=True, nullable=False)
    record_id: Mapped[str | None] = mapped_column(ForeignKey("normalized_records.id", ondelete="SET NULL"))
    field_name: Mapped[str | None] = mapped_column(String(64))
    observed_value: Mapped[str] = mapped_column(String(512), nullable=False)
    source_reference: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    detection_method: Mapped[str] = mapped_column(String(64), nullable=False, default="grounded_pipeline")
    # The role this source stated for this identity, where it stated one. Null is correct and
    # common: most occurrences are of a number or a handle, which no source gives a role to.
    stated_role: Mapped[str | None] = mapped_column(String(48))
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("entity_id", "evidence_id", "field_name", name="uq_entity_occurrence"),
        Index("ix_entity_occurrence_case_entity", "case_id", "entity_id"),
        Index("ix_entity_occurrence_case_evidence", "case_id", "evidence_id"),
    )


class EntityRelation(Base):
    """One observation of a relationship between two resolved entities.

    This is the criminal-network edge SIH26189 asks for. `EntityOccurrence` says an identifier was
    seen in a file; this says two entities stand in a stated relation to each other.

    **One row is one observation, not one relationship.** If three records show the same pair, that
    is three rows. Collapsing them into a single edge with a counter would leave the edge pointing
    at one arbitrary source, and an investigator who clicks it would be shown evidence that is not
    the whole basis for the claim. Aggregation belongs to the read side; the write side keeps
    provenance exact.

    **Invariant:** `source_evidence_id` and `source_reference` are NOT NULL. An edge with no source
    is not investigative intelligence, and refusing to write one is what keeps traceability
    coverage at 100% by construction rather than by audit.
    """

    __tablename__ = "entity_relations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)

    subject_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False)
    object_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True, nullable=False)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # False means the source shows the two parties together but not who acted on whom. A call log
    # that lists both numbers in one column proves contact, not who dialled. Such rows are stored
    # once in a canonical order rather than twice in both directions.
    directed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    source_evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_files.id", ondelete="CASCADE"), index=True, nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(ForeignKey("normalized_records.id", ondelete="SET NULL"))
    source_reference: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # How the relation was established: stated_roles, table_row, or co_occurrence. It is shown to
    # the reviewer, because "the source named both" is a far weaker claim than "the source states
    # one paid the other".
    basis: Mapped[str] = mapped_column(String(32), nullable=False, default="co_occurrence")

    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    time_precision: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")

    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False, default=0.0)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="machine_extracted")
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_entity_relations_case_type", "case_id", "relation_type"),
        Index("ix_entity_relations_subject", "case_id", "subject_entity_id"),
        Index("ix_entity_relations_object", "case_id", "object_entity_id"),
        Index("ix_entity_relations_case_time", "case_id", "observed_at"),
        Index("ix_entity_relations_review", "case_id", "verification_status"),
    )


class RecordReview(Base):
    """Append-only reviewer decisions. Original evidence and raw model output are never overwritten."""

    __tablename__ = "record_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False)
    record_id: Mapped[str | None] = mapped_column(ForeignKey("normalized_records.id", ondelete="CASCADE"), index=True)
    relation_id: Mapped[str | None] = mapped_column(ForeignKey("record_relations.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(96))
    previous_value: Mapped[dict | None] = mapped_column(JSON)
    new_value: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    audit_log_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_record_reviews_case_created", "case_id", "created_at"),)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"), index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[NotificationLevel] = mapped_column(SAEnum(NotificationLevel, name="notification_level"), nullable=False, default=NotificationLevel.INFO)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="notifications")
    case: Mapped[Case | None] = relationship("Case", back_populates="notifications")
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)
