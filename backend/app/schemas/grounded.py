"""Response and request contracts for the source-grounded evidence surfaces."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.evidence_intelligence.schema import RelationReviewAction, ReviewAction


class ProcessingStageResponse(BaseModel):
    stage: str
    label: str
    state: str
    attempt: int
    reached: bool
    failure_reason: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class EvidenceStagesResponse(BaseModel):
    evidence_id: str
    pipeline_version: str
    current_stage: str | None
    stages: list[ProcessingStageResponse]


class RawArtifactResponse(BaseModel):
    id: str
    layer: str
    extractor_name: str
    source_type: str
    artifact_version: str
    quality_flags: list[str]
    payload: dict[str, Any]
    created_at: datetime


class NormalizedRecordResponse(BaseModel):
    id: str
    evidence_id: str
    case_id: str
    workspace_id: str | None
    record_key: str
    source_file_name: str
    source_type: str
    observed_text: str | None
    normalized_summary: str | None
    event_type: str | None
    event_time: datetime | None
    event_time_raw: str | None
    event_time_precision: str
    participant_a: str | None
    participant_b: str | None
    sender: str | None
    receiver: str | None
    message_direction: str | None
    chat_participant_identifier: str | None
    phone_numbers: list[str]
    email_addresses: list[str]
    account_identifiers: list[str]
    vehicle_identifiers: list[str] = []
    organisation_names: list[str] = []
    person_names: list[str] = []
    location_names: list[str] = []
    transaction_reference: str | None
    amount: dict[str, Any]
    location: str | None
    device_identifier: str | None
    event_attributes: dict[str, Any]
    observation_basis: str
    field_provenance: dict[str, Any]
    model_confidence: float | None
    validation_confidence: float | None
    final_confidence_band: str
    validation_status: str
    requires_human_review: bool
    review_reason: str | None
    review_state: str
    conflict_fields: list[str]
    escalated: bool
    raw_extraction_version: str
    raw_model_output_version: str | None
    extraction_model_name: str | None
    prompt_version: str | None
    created_at: datetime
    updated_at: datetime


class NormalizedRecordPage(BaseModel):
    items: list[NormalizedRecordResponse]
    total: int
    limit: int
    offset: int


class ModelRunResponse(BaseModel):
    id: str
    record_key: str
    provider: str
    model_name: str
    prompt_version: str
    role: str
    status: str
    raw_output: str | None
    parsed_payload: dict[str, Any] | None
    grounding_report: dict[str, Any] | None
    error: dict[str, Any] | None
    latency_ms: int | None
    created_at: datetime


class RelationResponse(BaseModel):
    id: str
    relation_type: str
    status: str
    detection_method: str
    evidence_ids: list[str]
    record_ids: list[str]
    matching_or_conflicting_fields: list[str]
    reason: str
    source_references: list[dict[str, Any]]
    confidence: float
    requires_human_review: bool
    review_decision: str | None
    reviewed_at: datetime | None
    created_at: datetime


class RelationPage(BaseModel):
    items: list[RelationResponse]
    total: int
    limit: int
    offset: int


class RecordReviewRequest(BaseModel):
    action: ReviewAction
    field_name: str | None = Field(default=None, max_length=96)
    new_value: Any = None
    reason: str | None = Field(default=None, max_length=2000)


class RelationReviewRequest(BaseModel):
    action: RelationReviewAction
    reason: str | None = Field(default=None, max_length=2000)


class RecordReviewResponse(BaseModel):
    id: str
    record_id: str | None
    relation_id: str | None
    action: str
    field_name: str | None
    previous_value: Any
    new_value: Any
    reason: str | None
    reviewer_id: str
    created_at: datetime


class ReviewQueueItem(BaseModel):
    record: NormalizedRecordResponse
    evidence_name: str
    relations: list[RelationResponse]


class ReviewQueuePage(BaseModel):
    items: list[ReviewQueueItem]
    total: int
    limit: int
    offset: int


class EntityEndpointResponse(BaseModel):
    id: str
    label: str | None
    type: str | None


class EntityRelationObservation(BaseModel):
    """One record's statement of a relationship, with the place it can be read."""

    id: str
    relation_type: str
    directed: bool
    basis: str
    subject: EntityEndpointResponse
    object: EntityEndpointResponse
    source_evidence_id: str
    source_record_id: str | None
    source_reference: dict[str, Any]
    observed_at: datetime | None
    time_precision: str
    confidence: float
    verification_status: str
    review_note: str | None
    created_at: datetime


class EntityRelationSummary(BaseModel):
    """A distinct relationship, and how many independent records support it."""

    relation_type: str
    meaning: str
    directed: bool
    subject: EntityEndpointResponse
    object: EntityEndpointResponse
    observation_ids: list[str]
    observation_count: int
    evidence_ids: list[str]
    supporting_evidence_count: int
    bases: list[str]
    confidence: float
    verification_status: str
    first_observed_at: datetime | None
    last_observed_at: datetime | None


class EntityRelationPage(BaseModel):
    items: list[EntityRelationObservation]
    total: int
    limit: int
    offset: int


class EntityRelationReviewRequest(BaseModel):
    action: Literal["confirm_relationship", "reject_relationship"]
    reason: str | None = None


class ImportantEntityResponse(BaseModel):
    """A ranked entity, and the countable reason it ranked there.

    `why` and `caveat` are not decoration. A bare centrality score invites an investigator to read
    it as a measure of criminality, which is the single most damaging misreading this system can
    produce, so the sentence travels with the number everywhere.
    """

    entity_id: str
    label: str
    entity_type: str
    metric: str
    score: float
    rank: int
    connections: int
    supporting_evidence_count: int
    communities_linked: int
    is_bridge: bool
    why: str
    caveat: str


class NetworkNodeResponse(BaseModel):
    id: str
    label: str
    entity_type: str


class NetworkEdgeResponse(BaseModel):
    subject_entity_id: str
    object_entity_id: str
    relation_types: list[str]
    confidence: float
    observations: int
    supporting_evidence_count: int


class BridgeRelationshipResponse(BaseModel):
    subject: dict[str, Any]
    object: dict[str, Any]
    relation_types: list[str]
    confidence: float
    observations: int
    supporting_evidence_count: int
    why: str
    caveat: str


class CommunityResponse(BaseModel):
    community_id: int
    size: int
    supporting_evidence_count: int
    members: list[dict[str, Any]]
    caveat: str


class NetworkPathResponse(BaseModel):
    found: bool
    reason: str | None = None
    nodes: list[dict[str, Any]] = []
    edges: list[NetworkEdgeResponse] = []
    weakest_link_confidence: float | None = None
    caveat: str | None = None


class NetworkSubgraphResponse(BaseModel):
    center: str | None = None
    hops: int | None = None
    nodes: list[NetworkNodeResponse] = []
    edges: list[NetworkEdgeResponse] = []
    truncated: bool = False


class NetworkOverviewResponse(BaseModel):
    entities: int
    relationships: int
    communities: int
    bridges: int
    isolated_entities: int
    analytics_version: str


class CaseChronologyResponse(BaseModel):
    """How the case's contact record sits around the declared incident window."""

    incident_window_declared: bool
    incident_start: datetime | None
    incident_end: datetime | None
    contacts_placed: dict[str, int]
    contacts_without_established_time: bool
    temporal_version: str


class TemporalFindingResponse(BaseModel):
    subject: EntityEndpointResponse
    object: EntityEndpointResponse
    contacts: int
    first: datetime
    last: datetime
    evidence_ids: list[str]
    relation_ids: list[str]
    detail: str
    # The span itself, so a caller can rank or filter without re-parsing the sentence. Only one is
    # meaningful per finding: a burst has a duration, a pre-incident finding has a lead time.
    minutes: int | None = None
    hours_before: float | None = None


class AssistantFinding(BaseModel):
    """One statement the assistant makes, and the evidence it read it from."""

    statement: str
    evidence_ids: list[str] = []
    source_reference: dict[str, Any] | None = None
    verification_status: str | None = None
    # Words copied from an uploaded file. Marked as a quotation because uploaded text is
    # attacker-controlled: it is shown to the reader, never acted on.
    quoted_source_text: str | None = None


class CaseAssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=600)


class CaseAssistantResponse(BaseModel):
    question: str
    intent: str
    answer: str
    findings: list[AssistantFinding]
    entities_understood: list[dict[str, str]]
    unresolved_terms: list[str]
    caveat: str
    assistant_version: str
