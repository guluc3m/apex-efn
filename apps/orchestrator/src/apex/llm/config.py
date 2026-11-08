"""Per-role LLM endpoint configuration (spec §5.6).

The source of truth is the tenant configuration ``llm.roles.*`` (DEV-4, D4-03). This module does not
import ``apex.tenant_config``; it consumes any object satisfying :class:`RoleConfigProvider`.

Capabilities are conservative: every flag defaults to ``False`` and the guided-decoding engine to
``none``. The gateway never assumes a capability that has not been declared.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LLMRole(StrEnum):
    """Agent roles, each with its own endpoint configuration."""

    PLANNER = "planner"
    NEGOTIATOR = "negotiator"
    EXTRACTOR = "extractor"
    NARRATOR = "narrator"
    EMBEDDER = "embedder"


class GuidedDecoding(StrEnum):
    """Guided-decoding mechanism exposed by the engine, if any."""

    NONE = "none"
    VLLM_GUIDED_JSON = "vllm_guided_json"
    LLAMACPP_GRAMMAR = "llamacpp_grammar"


class CapabilityProfile(BaseModel):
    """Capabilities declared by an endpoint. Undeclared means unsupported."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supports_json_schema: bool = False
    supports_json_object: bool = False
    supports_tools: bool = False
    supports_streaming: bool = False
    supports_seed: bool = False
    supports_guided: GuidedDecoding = GuidedDecoding.NONE
    context_window: int = Field(default=0, ge=0)
    tokenizer: str = ""


class RoleEndpointConfig(BaseModel):
    """Endpoint + model + limits used by one role.

    ``api_key_ref`` is an opaque reference resolved through a :class:`SecretResolver`; raw keys never
    belong in this model. ``fallback`` lists other endpoint ids (keys of the endpoint registry) to try in
    order when this endpoint is unavailable or its budget policy degrades.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoint_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    api_key_ref: str | None = None
    model: str = Field(min_length=1)
    capabilities: CapabilityProfile = Field(default_factory=CapabilityProfile)
    timeout_s: float = Field(default=60.0, gt=0)
    max_output_tokens: int = Field(default=1024, gt=0)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int | None = None
    fallback: list[str] = Field(default_factory=list)
    cost_per_1k_prompt_minor: int | None = Field(default=None, ge=0)
    cost_per_1k_completion_minor: int | None = Field(default=None, ge=0)
    gpu_seconds_per_1k_tokens: float | None = Field(default=None, ge=0)


class ResilienceConfig(BaseModel):
    """Retry, backoff and circuit-breaker thresholds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_retries: int = Field(default=2, ge=0)
    backoff_base_s: float = Field(default=0.5, ge=0)
    backoff_cap_s: float = Field(default=10.0, ge=0)
    breaker_failure_threshold: int = Field(default=5, ge=1)
    breaker_open_seconds: float = Field(default=30.0, gt=0)


class LLMRolesConfig(BaseModel):
    """Mapping role -> endpoint configuration, plus the shared endpoint registry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    roles: dict[LLMRole, RoleEndpointConfig]
    endpoints: dict[str, RoleEndpointConfig] = Field(default_factory=dict)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)

    def endpoint_for(self, role: LLMRole) -> RoleEndpointConfig:
        if role not in self.roles:
            raise KeyError(f"no endpoint configured for role {role.value}")
        return self.roles[role]


@runtime_checkable
class RoleConfigProvider(Protocol):
    """Anything that can produce the effective roles configuration (tenant config, tests, ...)."""

    def llm_roles(self, tenant_id: str) -> LLMRolesConfig: ...


@runtime_checkable
class SecretResolver(Protocol):
    """Resolves an opaque ``api_key_ref`` into a secret. Vault client arrives with DEV-1."""

    def resolve(self, ref: str) -> SecretStr: ...


class StaticRoleConfigProvider:
    """Trivial provider for tests and local wiring."""

    def __init__(self, config: LLMRolesConfig) -> None:
        self._config = config

    def llm_roles(self, tenant_id: str) -> LLMRolesConfig:
        return self._config


class StaticSecretResolver:
    """In-memory resolver for tests only."""

    def __init__(self, secrets: dict[str, str]) -> None:
        self._secrets = {k: SecretStr(v) for k, v in secrets.items()}

    def resolve(self, ref: str) -> SecretStr:
        try:
            return self._secrets[ref]
        except KeyError as exc:
            raise KeyError(f"unknown secret reference: {ref}") from exc


__all__ = [
    "CapabilityProfile",
    "GuidedDecoding",
    "LLMRole",
    "LLMRolesConfig",
    "ResilienceConfig",
    "RoleConfigProvider",
    "RoleEndpointConfig",
    "SecretResolver",
    "StaticRoleConfigProvider",
    "StaticSecretResolver",
]
