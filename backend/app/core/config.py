"""Central configuration for the isolated DRISHYAM backend."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Drishyam Backend"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    secret_key: SecretStr = SecretStr("development-only-secret-change-me")
    access_token_expire_minutes: int = 30
    database_url: str = "postgresql+psycopg://drishyam:drishyam@localhost:5432/drishyam"
    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False
    storage_backend: Literal["filesystem", "supabase"] = "filesystem"
    storage_root: Path = Path("./data/private_storage")
    generated_reports_root: Path = Path("./generated_reports")
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_storage_bucket: str | None = None
    max_upload_size_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    email_provider: str = "console"
    allow_local_console_email: bool = False
    gmail_smtp_email: str | None = None
    gmail_app_password: SecretStr | None = None
    gmail_api_client_id: str | None = None
    gmail_api_client_secret: SecretStr | None = None
    gmail_api_sender: str | None = None
    gmail_api_token_file: Path = Path("/var/lib/drishyam-oauth/gmail_api_token.json")
    gmail_api_redirect_uri: str = "http://127.0.0.1:8000/api/v1/system/gmail-api/callback"
    otp_pepper: SecretStr = SecretStr("development-otp-pepper-change-me")
    otp_expire_minutes: int = 10
    otp_max_attempts: int = 5
    otp_request_cooldown_seconds: int = Field(default=60, ge=15, le=3600)
    google_client_id: str | None = None
    google_allowed_workspace_domain: str | None = None
    allowed_origins: str = "http://localhost:5173"
    assistant_llm_base_url: str | None = Field(default=None, validation_alias=AliasChoices("ASSISTANT_LLM_BASE_URL", "OPENAI_API_BASE"))
    assistant_llm_api_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices("ASSISTANT_LLM_API_KEY", "OPENAI_API_KEY"))
    assistant_llm_model: str = Field(default="gpt-5-mini", validation_alias=AliasChoices("ASSISTANT_LLM_MODEL", "OPENAI_MODEL"))

    # --- Evidence intelligence: local-first VLM with opt-in Groq escalation ---------------------
    # Deliberately separate from the ASSISTANT_LLM_* block above. Trace Orb is a website help
    # assistant that must never reach case data; sharing one credential knob would erase that line.
    evidence_intelligence_enabled: bool = True
    llm_routing_mode: Literal["local_first", "local_only", "groq_only", "mock", "disabled"] = "local_first"
    ollama_base_url: str = "http://localhost:11434"
    ollama_vision_model: str = "qwen2.5vl:7b"
    ollama_timeout_seconds: float = Field(default=120.0, gt=0)
    # Ollama defaults every model to a 4096-token window regardless of what the model supports. A
    # full-resolution phone screenshot plus its OCR blocks runs past 8000 tokens and is rejected
    # outright, so the window is set explicitly.
    ollama_num_ctx: int = Field(default=16384, ge=2048, le=131072)
    groq_enabled: bool = False
    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "qwen/qwen3.8-27b"
    groq_escalate_below_confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    groq_max_retries: int = Field(default=1, ge=0, le=5)
    groq_timeout_seconds: float = Field(default=60.0, gt=0)
    external_evidence_transmission: Literal["disabled", "enabled"] = "disabled"
    semantic_correlation_enabled: bool = False

    # The shared identifier ledger. Off by default and behind the same two independent switches the
    # external-model gate uses, because publishing is the one action in this product that puts
    # anything derived from a case outside it.
    ledger_enabled: bool = False
    ledger_publication: Literal["disabled", "enabled"] = "disabled"
    # The key the participating districts share. Without it there is no ledger: an unkeyed digest of
    # a phone number can be enumerated in an afternoon, so publishing one would be publishing the
    # number. Absence of this key is treated as the gate being shut, not as a reason to fall back.
    ledger_key: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=(".env", ".env.trace-orb"), env_file_encoding="utf-8", extra="ignore")

    @property
    def ledger_publication_allowed(self) -> bool:
        """Identifiers leave this case only when both switches are on and a shared key exists."""
        return self.ledger_enabled and self.ledger_publication == "enabled" and bool(self.ledger_key)

    @property
    def groq_transmission_allowed(self) -> bool:
        """Evidence leaves this machine only when both independent switches are on."""
        return self.groq_enabled and self.external_evidence_transmission == "enabled" and bool(self.groq_api_key)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    def validate_private_storage(self) -> None:
        if self.storage_backend != "supabase":
            return
        missing = [
            name
            for name, value in {
                "SUPABASE_URL": self.supabase_url,
                "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_role_key,
                "SUPABASE_STORAGE_BUCKET": self.supabase_storage_bucket,
            }.items()
            if not value or (isinstance(value, SecretStr) and not value.get_secret_value())
        ]
        if missing:
            raise RuntimeError(f"Supabase private storage is selected but missing: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_private_storage()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.generated_reports_root.mkdir(parents=True, exist_ok=True)
    return settings
