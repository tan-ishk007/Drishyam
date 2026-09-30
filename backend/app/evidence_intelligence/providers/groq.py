"""Groq adapter — escalation only, never the default and never the source of truth.

Calling this sends evidence off the machine, so it is gated behind two independent switches and
refuses to run unless both are set. It is a second opinion for difficult evidence.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.evidence_intelligence.providers.base import (
    ProviderError,
    ProviderErrorKind,
    VLMRequest,
    VLMResponse,
)

logger = logging.getLogger(__name__)


class GroqVLMAdapter:
    """OpenAI-compatible chat completions against Groq."""

    name = "groq"
    supports_images = True

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.groq_base_url).rstrip("/")
        self.model = model or settings.groq_model
        self.timeout = timeout or settings.groq_timeout_seconds
        self.max_retries = settings.groq_max_retries

    def available(self) -> bool:
        return get_settings().groq_transmission_allowed

    def _api_key(self) -> str:
        settings = get_settings()
        if not settings.groq_transmission_allowed:
            raise ProviderError(
                ProviderErrorKind.DISABLED,
                "External evidence transmission is disabled; enable GROQ_ENABLED and "
                "EXTERNAL_EVIDENCE_TRANSMISSION and supply a key to escalate",
            )
        return settings.groq_api_key.get_secret_value()

    def generate(self, request: VLMRequest) -> VLMResponse:
        key = self._api_key()
        content: list[dict[str, Any]] = [{"type": "text", "text": request.user_prompt}]
        for image in request.images:
            content.append({"type": "image_url", "image_url": {"url": image.data_url}})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": content if request.images else request.user_prompt},
            ],
            "temperature": request.temperature,
            "max_completion_tokens": request.max_output_tokens,
            "response_format": {"type": "json_object"},
        }

        last_error: ProviderError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._call(payload, key, request)
            except ProviderError as error:
                last_error = error
                if not error.retryable or attempt >= self.max_retries:
                    raise
                time.sleep(min(2**attempt, 8))
        raise last_error or ProviderError(ProviderErrorKind.UNAVAILABLE, "Escalation provider produced no result")

    def _call(self, payload: dict[str, Any], key: str, request: VLMRequest) -> VLMResponse:
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(ProviderErrorKind.TIMEOUT, "Escalation provider timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(ProviderErrorKind.UNAVAILABLE, "Escalation provider is unreachable", retryable=True) from exc

        if response.status_code in {401, 403}:
            raise ProviderError(ProviderErrorKind.AUTHENTICATION, "Escalation provider rejected the credential")
        if response.status_code == 404:
            raise ProviderError(ProviderErrorKind.MODEL_NOT_FOUND, f"Escalation model '{self.model}' is not available")
        if response.status_code == 429:
            raise ProviderError(ProviderErrorKind.RATE_LIMITED, "Escalation provider rate limit reached", retryable=True)
        if response.status_code >= 500:
            raise ProviderError(ProviderErrorKind.UNAVAILABLE, "Escalation provider returned a server error", retryable=True)
        if response.status_code >= 400:
            # The body can echo the prompt, so only the status is surfaced.
            raise ProviderError(ProviderErrorKind.UNSUPPORTED, f"Escalation provider rejected the request ({response.status_code})")

        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(ProviderErrorKind.INVALID_JSON, "Escalation provider returned a non-JSON envelope") from exc

        raw_text = str(body.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not raw_text:
            raise ProviderError(ProviderErrorKind.INVALID_JSON, "Escalation provider returned an empty response")

        return VLMResponse(
            provider=self.name,
            model=self.model,
            prompt_version=request.prompt_version,
            raw_text=raw_text,
            payload=_loads(raw_text),
            latency_ms=latency_ms,
            usage=body.get("usage") or {},
        )


def _loads(raw_text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
