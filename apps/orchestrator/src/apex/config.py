"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(default="postgresql+asyncpg://apex:apex@localhost:5432/apex")
    database_pool_size: int = Field(default=10)

    # Redis
    redis_url: str = Field(default="redis://localhost:6379")

    # S3
    s3_endpoint: str = Field(default="http://localhost:9000")
    s3_access_key: str = Field(default="apex-dev")
    s3_secret_key: str = Field(default="apex-dev-secret")
    s3_bucket_audit: str = Field(default="apex-audit")
    s3_bucket_csv: str = Field(default="apex-csv")
    # Object Lock COMPLIANCE retention of audit anchors (ADR-211): 6 years. It cannot be shortened once written.
    audit_anchor_retention_days: int = Field(default=2192, ge=1)

    # LLM Gateway (OpenAI-compatible)
    llm_gateway_url: str = Field(default="http://localhost:8001/v1")
    llm_gateway_api_key: str = Field(default="")
    # Deployment override for every ``llm.roles.*.base_url`` of the config defaults. The defaults point at
    # http://localhost:8001/v1 (the stub seen from the host); a container reaches it at http://llm-stub:8001/v1.
    llm_base_url_override: str = Field(default="")

    # Browser worker internal API (D5-01). Empty means "not wired": a mission that needs to scrape fails
    # with the owner named instead of calling a service that is not there.
    browser_worker_url: str = Field(default="")
    browser_worker_token: str = Field(default="")
    browser_worker_max_results: int = Field(default=50, ge=1, le=200)
    browser_worker_max_polls: int = Field(default=60, ge=1)
    browser_worker_poll_interval_s: float = Field(default=0.5, gt=0)

    # Mock marketplace base URL (D5-04/D5-11). Empty means "no negotiation": a mission stops after the gate
    # instead of opening a chat with a seller that is not there.
    mock_marketplace_url: str = Field(default="")
    # Demo mode (hackathon). On top of the demo tenant config, startup leaves an **unsigned** active
    # financial snapshot for tenant-a/tenant-b, so a mission can be launched without the passkey ceremony.
    # Never enable outside a demo: it skips the signature that criterion 17/21 requires.
    demo_mode: bool = Field(default=False)
    # Phase 1 is semi-automatic on purpose: every drafted message waits for a person (spec §3.6 step 5).
    # A demo flips this so the conversation runs while the audience watches; it is the same flag Unleash
    # exposes, read statically here until the flag client is wired into the orchestrator.
    negotiation_autonomous_send: bool = Field(default=False)
    # Pause between negotiation rounds. Zero is the honest default for tests and CI; a demo sets it so the
    # transcript arrives one message at a time instead of all at once.
    negotiation_step_delay_s: float = Field(default=0.0, ge=0.0)

    # Run a mission in the background as soon as it is created; progress streams on the SSE route. A port
    # that is not configured (no BROWSER_WORKER_URL, for instance) fails the mission with the reason, which
    # is the honest answer. Set MISSION_AUTORUN=false to only plan missions.
    mission_autorun: bool = Field(default=True)

    # LLM token budget per mission (criterion 28). An operator limit, not a business threshold: the
    # business limits live in tenant config. Kept here until tenant config carries it.
    llm_mission_token_budget: int = Field(default=200_000, ge=1)

    # LLM Models by role
    llm_planner_model: str = Field(default="gpt-4o")
    llm_negotiator_model: str = Field(default="gpt-4o")
    llm_extractor_model: str = Field(default="gpt-4o-mini")
    llm_narrator_model: str = Field(default="gpt-4o-mini")
    llm_embedder_model: str = Field(default="text-embedding-3-small")

    # Signing
    signing_session_minutes: int = Field(default=15)
    signing_max_decisions_per_session: int = Field(default=10)

    # Observability
    otel_exporter_endpoint: str = Field(default="http://localhost:4318")
    log_level: str = Field(default="INFO")

    # HTTP API: idempotency (technical settings, not business defaults)
    idempotency_required: bool = Field(default=False)
    idempotency_backend: Literal["memory", "redis"] = Field(default="memory")
    idempotency_ttl_seconds: int = Field(default=86400, ge=1)

    # HTTP API: pagination (technical limits)
    pagination_default_limit: int = Field(default=50, ge=1)
    pagination_max_limit: int = Field(default=200, ge=1)

    # CORS
    cors_origins: list[str] = Field(default=["http://localhost:3000"])


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
