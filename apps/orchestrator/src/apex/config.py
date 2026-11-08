"""Application configuration using pydantic-settings."""

from functools import lru_cache

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
    s3_access_key: str = Field(default="minioadmin")
    s3_secret_key: str = Field(default="minioadmin")
    s3_bucket_audit: str = Field(default="apex-audit")

    # LLM Gateway (OpenAI-compatible)
    llm_gateway_url: str = Field(default="http://localhost:8001/v1")
    llm_gateway_api_key: str = Field(default="")

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
