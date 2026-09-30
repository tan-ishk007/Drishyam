"""Vision-language provider adapters and the router that chooses between them."""

from app.evidence_intelligence.providers.base import (
    ImageAttachment,
    ProviderError,
    ProviderErrorKind,
    VLMAdapter,
    VLMRequest,
    VLMResponse,
)
from app.evidence_intelligence.providers.prompts import PROMPT_VERSION, RESPONSE_SCHEMA, SYSTEM_PROMPT
from app.evidence_intelligence.providers.router import (
    InferenceAttempt,
    ModelRouter,
    RoutingOutcome,
    build_deterministic_record,
)

__all__ = [
    "PROMPT_VERSION",
    "RESPONSE_SCHEMA",
    "SYSTEM_PROMPT",
    "ImageAttachment",
    "InferenceAttempt",
    "ModelRouter",
    "ProviderError",
    "ProviderErrorKind",
    "RoutingOutcome",
    "VLMAdapter",
    "VLMRequest",
    "VLMResponse",
    "build_deterministic_record",
]
