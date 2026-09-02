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
    related_event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[Case] = relationship("Case", back_populates="alerts")
    __table_args__ = (Index("ix_alerts_case_status_severity", "case_id", "status", "severity"),)


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
    storage_key: Mapped[str | None] = mapped_column(String(1024), unique=True)
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
