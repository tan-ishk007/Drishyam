"""Model routing: deterministic base, local first pass, Groq escalation only when justified.

The router never decides that a cloud answer is right because it came from the cloud. When two
models disagree, both outputs are kept, the field is marked conflicting, and a human decides.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.core.config import get_settings
from app.evidence_intelligence import confidence as confidence_engine
from app.evidence_intelligence import grounding
from app.evidence_intelligence.extraction import AUTHORITATIVE_FIELDS, ExtractionUnit, RawExtraction
from app.evidence_intelligence.ocr import OCRResult
from app.evidence_intelligence.providers import prompts
from app.evidence_intelligence.providers.base import (
    ImageAttachment,
    ProviderError,
    ProviderErrorKind,
    VLMAdapter,
    VLMRequest,
    VLMResponse,
)
from app.evidence_intelligence.schema import (
    Amount,
    AmountRole,
    FieldProvenance,
    MessageDirection,
    NormalizedRecordDraft,
    ObservationBasis,
    SourceType,
    TimePrecision,
)

logger = logging.getLogger(__name__)

ROUTER_VERSION = "model-router-v1"

# Structured sources whose parser output is authoritative; a model may only add narrative around it.
STRUCTURED_SOURCE_TYPES = {
    SourceType.BANK_RECORD,
    SourceType.CALL_LOG,
    SourceType.CSV,
    SourceType.SPREADSHEET,
    SourceType.EMAIL,
}
VISUAL_SOURCE_TYPES = {SourceType.SCREENSHOT, SourceType.IMAGE}
DEGRADED_FLAGS = {"blurry", "cropped", "incomplete", "low_quality", "ambiguous"}

LIST_FIELDS = (
    "phone_numbers",
    "email_addresses",
    "account_identifiers",
    "vehicle_identifiers",
    "organisation_names",
    "person_names",
    "location_names",
)

# Fields whose value is a mapping rather than a list or a scalar. Only the deterministic
# extractor produces these; no model is asked for them.
MAPPING_FIELDS = ("person_roles",)

# Distinguishes "caller passed nothing, build from config" from "caller explicitly wants no model".
_UNSET: Any = object()

# Failures that describe the provider itself rather than one request. Retrying these for every
# remaining unit of the same evidence item only wastes time.
TRIPPING_ERRORS = {
    ProviderErrorKind.UNAVAILABLE,
    ProviderErrorKind.TIMEOUT,
    ProviderErrorKind.MODEL_NOT_FOUND,
    ProviderErrorKind.AUTHENTICATION,
    ProviderErrorKind.DISABLED,
    ProviderErrorKind.RATE_LIMITED,
}


@dataclass
class InferenceAttempt:
    provider: str
    model: str
    prompt_version: str
    status: str
    cache_key: str
    raw_output: str | None = None
    payload: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    grounding_report: dict[str, Any] | None = None
    latency_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "status": self.status,
            "cache_key": self.cache_key,
            "raw_output": self.raw_output,
            "payload": self.payload,
            "error": self.error,
            "grounding": self.grounding_report,
            "latency_ms": self.latency_ms,
        }


@dataclass
class CachedResponse:
    """A model answer already on record for an identical request."""

    raw_output: str | None
    payload: dict[str, Any] | None


@dataclass
class RoutingOutcome:
    record: NormalizedRecordDraft
    attempts: list[InferenceAttempt] = field(default_factory=list)
    escalated: bool = False
    escalation_reasons: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    router_version: str = ROUTER_VERSION


def build_deterministic_record(unit: ExtractionUnit, extraction: RawExtraction) -> NormalizedRecordDraft:
    """The record that exists even if every model provider is down."""
    record = NormalizedRecordDraft(
        record_key=unit.unit_key,
        source_type=extraction.source_type,
        observed_text=unit.text or None,
        raw_extraction_version=extraction.version,
    )
    for name, provenance in unit.facts.items():
        _apply_field(record, name, provenance)
    record.observation_basis = ObservationBasis.DIRECT if unit.facts else ObservationBasis.UNKNOWN
    return record


def _apply_field(record: NormalizedRecordDraft, name: str, provenance: FieldProvenance) -> None:
    """Write one provenance entry onto the record, keeping the typed field and the audit trail in step."""
    record.field_provenance[name] = provenance
    value = provenance.value

    if name == "amount":
        if isinstance(value, dict):
            role = value.get("role")
            record.amount = Amount(
                value=value.get("value"),
                currency=value.get("currency"),
                role=AmountRole(role) if role in {item.value for item in AmountRole} else AmountRole.UNKNOWN,
            )
        return
    if name == "event_time_precision":
        if isinstance(value, str) and value in {item.value for item in TimePrecision}:
            record.event_time_precision = TimePrecision(value)
        return
    if name == "message_direction":
        if isinstance(value, str) and value in {item.value for item in MessageDirection}:
            record.message_direction = MessageDirection(value)
        return
    if name in LIST_FIELDS:
        if isinstance(value, list):
            setattr(record, name, [str(item) for item in value])
        return
    # A mapping field. Without this the fallback below would stringify the whole dict onto
    # the record, and "{'Yash Kumar Gupta': 'accused'}" is not a role.
    if name in MAPPING_FIELDS:
        if isinstance(value, dict):
            setattr(record, name, {str(key): str(item) for key, item in value.items()})
        return
    if name in {"media_content", "narration", "duration", "cell_site", "fir_number", "fir_sections", "police_station", "stated_vehicle_use", "stated_presence", "stated_vehicle_presence"}:
        if value is not None:
            record.event_attributes[name] = value
        return
    if hasattr(record, name):
        setattr(record, name, str(value) if value is not None and not isinstance(value, (str, type(None))) else value)


def authoritative_summary(unit: ExtractionUnit) -> dict[str, Any]:
    """Parser-derived values shown to the model as fixed."""
    return {
        name: provenance.value
        for name, provenance in unit.facts.items()
        if name in AUTHORITATIVE_FIELDS and provenance.basis is ObservationBasis.DIRECT and provenance.value is not None
    }


class ModelRouter:
    """Chooses which models see an evidence unit, and reconciles what they return."""

    version = ROUTER_VERSION

    def __init__(
        self,
        local: VLMAdapter | None = _UNSET,
        escalation: VLMAdapter | None = _UNSET,
        cache_lookup: Callable[[str], CachedResponse | None] | None = None,
    ) -> None:
        # Injected rather than looked up here: this layer must not know a database exists. The
        # caller that owns a session supplies the reader; without one the router simply always
        # calls the provider, which is the previous behaviour.
        self._cache_lookup = cache_lookup or (lambda _key: None)
        # `_UNSET` means "build from configuration"; an explicit None means "no provider on this
        # leg", which is how tests and the deterministic-only path disable a model.
        self._local = local
        self._escalation = escalation
        self._settings = get_settings()
        # One router handles every unit of one evidence item. A provider that is down for the first
        # unit is down for the rest, so it is tripped out instead of being dialled once per unit —
        # a 300-row bank statement must not mean 300 connection timeouts.
        self._unreachable: dict[str, dict[str, Any]] = {}

    @property
    def local(self) -> VLMAdapter | None:
        if self._local is _UNSET:
            self._local = None
            if self._settings.llm_routing_mode in {"local_first", "local_only"}:
                from app.evidence_intelligence.providers.ollama import OllamaVLMAdapter

                self._local = OllamaVLMAdapter()
        return self._local

    @property
    def escalation(self) -> VLMAdapter | None:
        if self._escalation is _UNSET:
            self._escalation = None
            if self._settings.llm_routing_mode in {"local_first", "groq_only"} and self._settings.groq_transmission_allowed:
                from app.evidence_intelligence.providers.groq import GroqVLMAdapter

                self._escalation = GroqVLMAdapter()
        return self._escalation

    def normalize(
        self,
        unit: ExtractionUnit,
        extraction: RawExtraction,
        *,
        evidence_sha256: str,
        image_path: Path | None = None,
        ocr_result: OCRResult | None = None,
        force_escalation: bool = False,
    ) -> RoutingOutcome:
        record = build_deterministic_record(unit, extraction)
        outcome = RoutingOutcome(record=record)

        if not self._settings.evidence_intelligence_enabled or self._settings.llm_routing_mode == "disabled":
            return self._finalize(outcome, extraction, validation_confidence=None)

        request = self._build_request(unit, extraction, ocr_result=ocr_result, image_path=image_path)

        local_result: grounding.GroundingResult | None = None
        local_attempt = self._attempt(self.local, request, evidence_sha256=evidence_sha256, unit=unit, extraction=extraction, ocr_result=ocr_result)
        if local_attempt:
            outcome.attempts.append(local_attempt)
            local_result = _grounding_of(local_attempt)

        reasons = self._escalation_reasons(local_attempt, local_result, extraction, force_escalation=force_escalation)
        escalation_result: grounding.GroundingResult | None = None
        if reasons and self.escalation is not None:
            escalation_attempt = self._attempt(
                self.escalation, request, evidence_sha256=evidence_sha256, unit=unit, extraction=extraction, ocr_result=ocr_result
            )
            if escalation_attempt:
                outcome.attempts.append(escalation_attempt)
                escalation_result = _grounding_of(escalation_attempt)
                outcome.escalated = escalation_attempt.status == "succeeded"
                outcome.escalation_reasons = reasons

        chosen, conflicts = self._reconcile(local_result, escalation_result)
        outcome.conflicts = conflicts

        validation_confidence = chosen.validation_confidence if chosen else None
        if chosen:
            self._merge(record, chosen, unit)
            outcome.conflicts.extend(name for name in chosen.conflicts if name not in outcome.conflicts)

        return self._finalize(outcome, extraction, validation_confidence=validation_confidence)

    # ------------------------------------------------------------------ internals

    def _build_request(
        self,
        unit: ExtractionUnit,
        extraction: RawExtraction,
        *,
        ocr_result: OCRResult | None,
        image_path: Path | None,
    ) -> VLMRequest:
        images: list[ImageAttachment] = []
        if image_path and extraction.source_type in VISUAL_SOURCE_TYPES and image_path.is_file():
            images.append(ImageAttachment.from_path(image_path))

        return VLMRequest(
            system_prompt=prompts.SYSTEM_PROMPT,
            user_prompt=prompts.build_user_prompt(
                unit,
                extraction,
                ocr_result=ocr_result,
                authoritative=authoritative_summary(unit) if extraction.source_type in STRUCTURED_SOURCE_TYPES or unit.facts else None,
            ),
            prompt_version=prompts.PROMPT_VERSION,
            json_schema=prompts.RESPONSE_SCHEMA,
            images=images,
        )

    def _attempt(
        self,
        adapter: VLMAdapter | None,
        request: VLMRequest,
        *,
        evidence_sha256: str,
        unit: ExtractionUnit,
        extraction: RawExtraction,
        ocr_result: OCRResult | None,
    ) -> InferenceAttempt | None:
        if adapter is None:
            return None

        cache_key = request.cache_key(
            evidence_sha256=evidence_sha256,
            parser_version=extraction.version,
            provider=adapter.name,
            model=adapter.model,
        )
        attempt = InferenceAttempt(
            provider=adapter.name,
            model=adapter.model,
            prompt_version=request.prompt_version,
            status="skipped",
            cache_key=cache_key,
        )

        if tripped := self._unreachable.get(adapter.name):
            attempt.status = "failed"
            attempt.error = tripped
            return attempt

        if (cached := self._cache_lookup(cache_key)) is not None:
            # The key already covered evidence hash, parser version, provider, model, prompt version
            # and the images, and its docstring promised identical work would never be paid for
            # twice. Only the audit row was deduplicated, though -- the model was still called on
            # every reprocess, which on a local vision model is tens of seconds per image for an
            # answer already known.
            attempt.status = "cached"
            attempt.raw_output = cached.raw_output
            attempt.payload = cached.payload
            attempt.latency_ms = 0
            return attempt

        try:
            response: VLMResponse = adapter.generate(request)
        except ProviderError as error:
            attempt.status = "failed"
            attempt.error = error.to_dict()
            if error.kind in TRIPPING_ERRORS:
                self._unreachable[adapter.name] = attempt.error
            logger.info("Model provider unavailable for an evidence unit: %s", error.kind.value)
            return attempt
        except Exception:  # a provider bug must never take the evidence down with it
            attempt.status = "failed"
            attempt.error = {"kind": ProviderErrorKind.UNAVAILABLE.value, "message": "Provider adapter raised an unexpected error"}
            self._unreachable[adapter.name] = attempt.error
            logger.exception("Model provider adapter raised while normalizing an evidence unit")
            return attempt

        attempt.raw_output = response.raw_text
        attempt.payload = response.payload
        attempt.latency_ms = response.latency_ms

        report = grounding.validate(response.payload, unit=unit, extraction=extraction, ocr_result=ocr_result)
        attempt.grounding_report = report.to_dict()
        attempt.status = "rejected" if report.rejected else "succeeded"
        attempt.grounding_report["_result"] = report
        return attempt

    def _escalation_reasons(
        self,
        local_attempt: InferenceAttempt | None,
        local_result: grounding.GroundingResult | None,
        extraction: RawExtraction,
        *,
        force_escalation: bool,
    ) -> list[str]:
        reasons: list[str] = []
        if force_escalation:
            reasons.append("A reviewer requested re-analysis of this evidence.")
        if self._settings.llm_routing_mode == "groq_only":
            reasons.append("Routing mode sends this evidence directly to the escalation provider.")
        if local_attempt is None:
            reasons.append("No local model is configured for the first pass.")
        elif local_attempt.status == "failed":
            reasons.append("The local model was unavailable or returned an error.")
        elif local_attempt.status == "rejected":
            reasons.append("The local model returned output that failed schema or grounding validation.")

        if local_result:
            if local_result.validation_confidence is None:
                reasons.append("The local result could not be validated against the source.")
            elif local_result.validation_confidence < self._settings.groq_escalate_below_confidence:
                reasons.append(
                    f"Local validation confidence {local_result.validation_confidence:.2f} is below the "
                    f"{self._settings.groq_escalate_below_confidence:.2f} escalation threshold."
                )
            if local_result.conflicts:
                reasons.append(f"The local model conflicts with parser values for: {', '.join(local_result.conflicts)}.")
            if local_result.ungrounded:
                reasons.append(f"The local model cited unsupported values for: {', '.join(local_result.ungrounded)}.")

        if degraded := sorted(set(extraction.quality_flags) & DEGRADED_FLAGS):
            reasons.append(f"The source is visually degraded: {', '.join(degraded)}.")

        return reasons

    def _reconcile(
        self,
        local_result: grounding.GroundingResult | None,
        escalation_result: grounding.GroundingResult | None,
    ) -> tuple[grounding.GroundingResult | None, list[str]]:
        """Compare both model outputs field by field. Disagreement is preserved, never resolved."""
        if escalation_result is None or escalation_result.rejected:
            return (None if local_result and local_result.rejected else local_result), []
        if local_result is None or local_result.rejected:
            return escalation_result, []

        conflicts: list[str] = []
        for name, local_field in local_result.accepted.items():
            other = escalation_result.accepted.get(name)
            if other is None or local_field.value is None or other.value is None:
                continue
            if not grounding._value_matches(other.value, local_field.value):
                conflicts.append(name)

        local_score = local_result.validation_confidence or 0.0
        escalation_score = escalation_result.validation_confidence or 0.0
        # Ties go to the local result: the cloud does not win by default.
        chosen = escalation_result if escalation_score > local_score else local_result
        return chosen, conflicts

    def _merge(self, record: NormalizedRecordDraft, result: grounding.GroundingResult, unit: ExtractionUnit) -> None:
        """Layer model interpretation over deterministic facts without ever overwriting them."""
        for name, provenance in result.accepted.items():
            existing = unit.facts.get(name)
            if existing and existing.basis is ObservationBasis.DIRECT and existing.value is not None:
                continue
            if provenance.value is None and name in record.field_provenance and record.field_provenance[name].value is not None:
                continue
            _apply_field(record, name, provenance)

        if result.normalized_summary:
            record.normalized_summary = result.normalized_summary
        if result.model_confidence is not None:
            record.model_confidence = result.model_confidence
        if result.observation_basis is not ObservationBasis.UNKNOWN:
            record.observation_basis = result.observation_basis

    def _finalize(self, outcome: RoutingOutcome, extraction: RawExtraction, *, validation_confidence: float | None) -> RoutingOutcome:
        record = outcome.record
        succeeded = [attempt for attempt in outcome.attempts if attempt.status == "succeeded"]
        if succeeded:
            last = succeeded[-1]
            record.extraction_model_name = f"{last.provider}:{last.model}"
            record.prompt_version = last.prompt_version
            record.raw_model_output_version = last.cache_key[:16]

        confidence_engine.apply(
            record,
            validation_confidence=validation_confidence,
            conflicts=outcome.conflicts,
            source_quality_flags=extraction.quality_flags,
        )
        if outcome.escalation_reasons and outcome.escalated:
            record.review_reason = "; ".join(filter(None, [record.review_reason, "Escalated for a second opinion: " + outcome.escalation_reasons[0]]))
        return outcome


def _grounding_of(attempt: InferenceAttempt) -> grounding.GroundingResult | None:
    if not attempt.grounding_report:
        return None
    return attempt.grounding_report.pop("_result", None)
