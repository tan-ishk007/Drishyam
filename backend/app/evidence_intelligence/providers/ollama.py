"""Ollama adapter — the local first-pass vision-language model.

Local inference keeps evidence on the machine, so this is the default path. A missing or stopped
Ollama host is an ordinary, expected condition and raises a classified `ProviderError`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
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

CONNECT_TIMEOUT_SECONDS = 3.0
# Ollama answers 5xx while a model is still being loaded into memory. On a cold 7B vision model
# that window is a minute or more, and treating it as a dead host would drop the model pass for the
# whole evidence item.
COLD_START_RETRIES = 2
COLD_START_BACKOFF_SECONDS = 5.0

# One local GPU serves one vision request at a time. When three screenshots were uploaded together
# the worker dialled Ollama three times at once; the daemon queued them, but each client was
# already counting against its own timeout while waiting its turn, so a job that needed 100 seconds
# of GPU could burn the whole budget queueing and be recorded as a timeout. Taking the turn here
# instead means the request timeout measures generation, not the queue.
_GENERATION_LOCK_PATH = os.path.join(tempfile.gettempdir(), "drishyam-local-vlm.lock")
_thread_lock = threading.Lock()


@contextlib.contextmanager
def _generation_turn():
    """Hold the local model to one caller at a time, across threads and worker processes."""
    with _thread_lock:
        handle = None
        try:
            handle = open(_GENERATION_LOCK_PATH, "w")
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (OSError, ImportError):
            # No cross-process lock available (Windows, or an unwritable temp dir). The in-process
            # lock above still serializes this worker, which is where the contention comes from.
            if handle is not None:
                handle.close()
            handle = None
        try:
            yield
        finally:
            if handle is not None:
                with contextlib.suppress(OSError):
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()


class OllamaVLMAdapter:
    """Talks to a local Ollama daemon over its native /api/chat endpoint."""

    name = "ollama"
    supports_images = True

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_vision_model
        self.timeout = timeout or settings.ollama_timeout_seconds
        self.num_ctx = settings.ollama_num_ctx

    def available(self) -> bool:
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                installed = {str(item.get("name", "")) for item in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            return False
        # Ollama reports "qwen2.5vl:7b"; a bare "qwen2.5vl" request resolves to :latest.
        return any(name == self.model or name.split(":")[0] == self.model.split(":")[0] for name in installed)

    def generate(self, request: VLMRequest) -> VLMResponse:
        message: dict[str, Any] = {"role": "user", "content": request.user_prompt}
        if request.images:
            message["images"] = [image.base64_data for image in request.images]

        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": request.system_prompt}, message],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens,
                "num_ctx": self.num_ctx,
            },
        }

        started = time.perf_counter()
        response = None
        with _generation_turn():
            response, started = self._post(payload, started)
        return self._read(response, request, started)

    def _post(self, payload: dict[str, Any], started: float) -> tuple[httpx.Response, float]:
        # The clock restarts once this caller actually holds the model, so time spent waiting for
        # another screenshot to finish is not charged to this request.
        started = time.perf_counter()
        response = None
        for attempt in range(COLD_START_RETRIES + 1):
            try:
                # Generation is slow and deserves the full budget; reaching a local port is not, so
                # a missing Ollama host fails in seconds instead of holding the worker for minutes.
                timeout = httpx.Timeout(self.timeout, connect=CONNECT_TIMEOUT_SECONDS)
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(f"{self.base_url}/api/chat", json=payload)
            except httpx.TimeoutException as exc:
                raise ProviderError(ProviderErrorKind.TIMEOUT, "Local model timed out", retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(ProviderErrorKind.UNAVAILABLE, "Local model host is unreachable", retryable=True) from exc

            if response.status_code < 500 or attempt >= COLD_START_RETRIES:
                break
            logger.info("Local model host is busy loading; retrying (attempt %d)", attempt + 1)
            time.sleep(COLD_START_BACKOFF_SECONDS)
        return response, started

    def _read(self, response: httpx.Response, request: VLMRequest, started: float) -> VLMResponse:
        if response.status_code == 404:
            raise ProviderError(ProviderErrorKind.MODEL_NOT_FOUND, f"Local model '{self.model}' is not installed")
        if response.status_code >= 500:
            raise ProviderError(ProviderErrorKind.UNAVAILABLE, "Local model host returned a server error", retryable=True)
        if response.status_code >= 400:
            raise ProviderError(ProviderErrorKind.UNSUPPORTED, f"Local model rejected the request ({_reason(response)})")

        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(ProviderErrorKind.INVALID_JSON, "Local model returned a non-JSON envelope") from exc

        raw_text = str(body.get("message", {}).get("content") or "").strip()
        if not raw_text:
            raise ProviderError(ProviderErrorKind.INVALID_JSON, "Local model returned an empty response")

        return VLMResponse(
            provider=self.name,
            model=self.model,
            prompt_version=request.prompt_version,
            raw_text=raw_text,
            payload=_loads(raw_text),
            latency_ms=latency_ms,
            usage={
                "prompt_eval_count": body.get("prompt_eval_count"),
                "eval_count": body.get("eval_count"),
            },
        )


def _loads(raw_text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _reason(response: httpx.Response) -> str:
    """Ollama's own error classifier, without echoing any prompt content back into logs."""
    try:
        body = response.json()
    except ValueError:
        return f"http {response.status_code}"
    error = body.get("error")
    if isinstance(error, str):
        try:
            error = json.loads(error).get("error", {})
        except (json.JSONDecodeError, AttributeError):
            return f"http {response.status_code}"
    if isinstance(error, dict) and error.get("type"):
        return str(error["type"])
    return f"http {response.status_code}"
