"""Provider-neutral contract for vision-language adapters.

Business logic imports only from this module. Nothing outside `ollama.py` and `groq.py` may know
which vendor is in use, so swapping or removing a provider stays a configuration change.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class ProviderErrorKind(str, Enum):
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    INVALID_JSON = "invalid_json"
    SCHEMA_VIOLATION = "schema_violation"
    MODEL_NOT_FOUND = "model_not_found"
    AUTHENTICATION = "authentication"
    DISABLED = "disabled"
    UNSUPPORTED = "unsupported"


class ProviderError(RuntimeError):
    """A structured, classifiable provider failure.

    Every provider failure is non-fatal by contract: the caller keeps the deterministic extraction
    and marks the record for review rather than failing the evidence.
    """

    def __init__(self, kind: ProviderErrorKind, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "message": str(self), "retryable": self.retryable}


@dataclass
class ImageAttachment:
    """An image handed to a vision model, carried as bytes rather than a URL.

    Private evidence URLs must never leave the process, so attachments are always inlined.
    """

    data: bytes
    mime: str = "image/png"

    @classmethod
    def from_path(cls, path: Path) -> ImageAttachment:
        suffix = path.suffix.lower()
        mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
        return cls(data=path.read_bytes(), mime=mime)

    @property
    def base64_data(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    @property
    def data_url(self) -> str:
        return f"data:{self.mime};base64,{self.base64_data}"


@dataclass
class VLMRequest:
    system_prompt: str
    user_prompt: str
    prompt_version: str
    json_schema: dict[str, Any] | None = None
    images: list[ImageAttachment] = field(default_factory=list)
    temperature: float = 0.0
    max_output_tokens: int = 1600

    def cache_key(self, *, evidence_sha256: str, parser_version: str, provider: str, model: str) -> str:
        """Deterministic key so identical work is never paid for twice."""
        digest = hashlib.sha256()
        for part in (evidence_sha256, parser_version, provider, model, self.prompt_version, self.user_prompt):
            digest.update(part.encode("utf-8"))
            digest.update(b"\x1f")
        for image in self.images:
            digest.update(hashlib.sha256(image.data).digest())
        return digest.hexdigest()


@dataclass
class VLMResponse:
    provider: str
    model: str
    prompt_version: str
    raw_text: str
    payload: dict[str, Any] | None = None
    latency_ms: int | None = None
    supports_images: bool = True
    usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "raw_text": self.raw_text,
            "payload": self.payload,
            "latency_ms": self.latency_ms,
            "usage": self.usage,
        }


class VLMAdapter(Protocol):
    name: str
    model: str
    supports_images: bool

    def available(self) -> bool: ...

    def generate(self, request: VLMRequest) -> VLMResponse: ...
