"""Evidence, timeline, graph, transaction, and alert response contracts."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.entities import AlertStatus, EvidenceStatus, ProcessingState, ReviewStatus, Severity


class EvidenceResponse(BaseModel):
    id: str
    case_id: str
    original_name: str
    source_category: str
    detected_mime: str
    byte_size: int
    sha256: str
    status: EvidenceStatus
    uploaded_at: datetime
    processed_at: datetime | None
    failure_reason: str | None


class EvidenceReceiptResponse(BaseModel):
    evidence: EvidenceResponse
    integrity_receipt: dict[str, Any]


class TimelineEventResponse(BaseModel):
    id: str
    source_file_id: str
    occurred_at: datetime | None
    original_time: str | None
    time_precision: str
    event_type: str
    description: str
    amount: float | None
    currency: str | None
    confidence: float
    review_status: ReviewStatus
    entities: list[dict[str, str]]


class TransactionResponse(BaseModel):
    id: str
    event_id: str | None
    source_evidence_id: str
    amount: float
    currency: str
    occurred_at: datetime | None
    reference_id: str | None
    sender_value: str | None
    receiver_value: str | None
    source_kind: str
    confidence: float
    review_status: ReviewStatus


class AlertResponse(BaseModel):
    id: str
    rule_code: str
    severity: Severity
    status: AlertStatus
    explanation: str
    affected_evidence_ids: list[str]
    # The sourced facts behind the alert, in the order the sources record them. Null for alerts
    # raised before alerts carried one; the reader is told that rather than shown an empty story.
    sequence: list[dict] | None = None
    related_event_id: str | None
    generated_at: datetime
    reviewed_at: datetime | None


class ProcessingRunResponse(BaseModel):
    id: str
    evidence_id: str
    evidence_name: str
    pipeline_stage: str
    pipeline_version: str
    state: ProcessingState
    attempt: int
    progress: int
    warning_messages: list[Any]
    failure_reason: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class AuditLogResponse(BaseModel):
    id: str
    actor_id: str | None
    action: str
    object_type: str
    object_id: str | None
    outcome: str
    details: dict[str, Any]
    previous_hash: str | None
    event_hash: str | None
    created_at: datetime


class SearchResultResponse(BaseModel):
    kind: str
    id: str
    target: str
    title: str
    excerpt: str
    details: dict[str, Any]


class CrossCaseSourceResponse(BaseModel):
    record_type: str
    record_id: str
    source_evidence_id: str | None
    source_label: str
    review_status: str


class CrossCaseLinkedCaseResponse(BaseModel):
    id: str
    case_number: str
    title: str
    status: str


class CrossCaseLinkResponse(BaseModel):
    id: str
    signal_type: str
    signal_label: str
    normalized_value: str
    confidence: str
    review_posture: str
    current_source: CrossCaseSourceResponse
    linked_case: CrossCaseLinkedCaseResponse
    linked_source: CrossCaseSourceResponse
    explanation: str
