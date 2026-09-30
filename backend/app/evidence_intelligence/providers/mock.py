"""Deterministic stand-in adapters used by tests and by `LLM_ROUTING_MODE=mock`.

Ollama may not be installed and Groq is disabled by default, so provider behaviour still has to be
exercisable. These adapters return canned output; they never reach the network.
"""

from __future__ import annotations

import json
from typing import Any

from app.evidence_intelligence.providers.base import (
    ProviderError,
    ProviderErrorKind,
    VLMRequest,
    VLMResponse,
)


class ScriptedVLMAdapter:
    """Replays a fixed payload, or raises a fixed error, for every request."""

    supports_images = True

    def __init__(
        self,
        *,
        name: str = "mock",
        model: str = "mock-vlm",
        payload: dict[str, Any] | None = None,
        raw_text: str | None = None,
        error: ProviderError | None = None,
        is_available: bool = True,
    ) -> None:
        self.name = name
        self.model = model
        self.payload = payload
        self.raw_text = raw_text
        self.error = error
        self.is_available = is_available
        self.calls: list[VLMRequest] = []

    def available(self) -> bool:
        return self.is_available

    def generate(self, request: VLMRequest) -> VLMResponse:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        raw = self.raw_text if self.raw_text is not None else json.dumps(self.payload or {})
        parsed: dict[str, Any] | None
        try:
            candidate = json.loads(raw)
            parsed = candidate if isinstance(candidate, dict) else None
        except json.JSONDecodeError:
            parsed = None
        return VLMResponse(
            provider=self.name,
            model=self.model,
            prompt_version=request.prompt_version,
            raw_text=raw,
            payload=parsed,
            latency_ms=1,
        )


def unavailable_adapter(name: str = "mock", model: str = "mock-vlm") -> ScriptedVLMAdapter:
    return ScriptedVLMAdapter(
        name=name,
        model=model,
        error=ProviderError(ProviderErrorKind.UNAVAILABLE, f"{name} host is unreachable", retryable=True),
        is_available=False,
    )


def invalid_json_adapter(name: str = "mock", model: str = "mock-vlm") -> ScriptedVLMAdapter:
    return ScriptedVLMAdapter(name=name, model=model, raw_text="not json at all {{{")
