"""Application wiring: build the DEV-4 services the HTTP layer depends on (D4-01/D4-08).

Until D2-05 (data layer) and the DEV-3 engines land, the app runs on in-memory stores and the LLM stub.
This module is the single place that decides which implementation a dependency gets, so a route module
never builds its own collaborators and tests override exactly one seam.

What is wired today:

* **Tenant config** from the versioned defaults (in-memory repository). Reads work without a baseline;
  a tenant with no stored version resolves to the global defaults at version 1.
* **LLM gateway** with per-role endpoints taken from ``llm.roles`` in that config (ADR-900 Q7 option B
  points every role at the LLM stub in dev).
* **Sourcing**: the prompt registry, the platform catalogue and the feature flags, so
  ``POST /v1/sourcing-requests`` and ``POST /v1/missions`` answer for real.
* **Mission store and event bus**, so missions persist for the process lifetime and SSE works.

What is *not* wired: signing (D2-09), the DEV-3 engines (trust, sanity, finance, MCDA, FX, CSV import) and
the browser worker (D5-01). The routes that need them keep answering 501 with the owner named, which is
honest: the alternative would be inventing the numbers those engines own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from apex.agents.missions import InMemoryMissionStore, MissionEventBus
from apex.agents.sourcing import IntakeAgent, PlannerAgent, PlatformInfo, StaticCatalogue
from apex.agents.sourcing_service import SourcingService, SourcingServiceDeps
from apex.common.clock import Clock, SystemClock
from apex.common.ids import IdGenerator
from apex.config import Settings
from apex.llm.accounting import InMemorySink
from apex.llm.budget import InMemoryBudgetStore, TokenBudget
from apex.llm.config import (
    CapabilityProfile,
    LLMRole,
    LLMRolesConfig,
    RoleEndpointConfig,
    StaticSecretResolver,
)
from apex.llm.gateway import LLMGateway
from apex.llm.prompts import PromptRegistry
from apex.platform.flags import FlagProvider, StaticFlags
from apex.tenant_config.defaults import DEFAULT_PATH, load_global_layer
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.resolver import content_hash
from apex.tenant_config.service import TenantConfigService

DEV_PLATFORMS: tuple[PlatformInfo, ...] = (
    PlatformInfo(platform_id="mock-a", transport="http", regions=("EU", "CN")),
    PlatformInfo(platform_id="mock-b", transport="browser", regions=("EU",)),
)
"""The two platforms the mock marketplace serves (D5-04). Real adapters replace this catalogue."""


class UnwiredDecisionPort:
    """Refuses to create decisions until DEV-2's ``apex.signing.api`` is merged (D2-09)."""

    async def create_decision(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("signing is not wired yet (DEV-2 apex.signing.api pending)")

    async def require_signed(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("signing is not wired yet (DEV-2 apex.signing.api pending)")


class DefaultRoleConfigProvider:
    """``RoleConfigProvider`` reading ``llm.roles`` from the versioned defaults.

    The gateway calls this synchronously from async code, so it reads the **global** layer, which is what
    ``/config/defaults`` ships (ADR-900 Q7 option B: every role points at the LLM stub in dev). A tenant
    override needs the config repository, which arrives with D2-05; until then a per-tenant override would
    have to be applied here explicitly rather than silently ignored.
    """

    def __init__(self, defaults_path: Path | None = None) -> None:
        self._version, values = load_global_layer(defaults_path or DEFAULT_PATH)
        self._roles = _roles_from(values)

    def llm_roles(self, tenant_id: str) -> LLMRolesConfig:
        return self._roles


def _roles_from(values: dict[str, Any]) -> LLMRolesConfig:
    """Build the gateway's role configuration from the ``llm.roles`` block. Loud on anything unknown."""
    raw = values.get("llm", {}).get("roles")
    if not raw:
        raise RuntimeError(
            "llm.roles is unset in /config/defaults; the gateway has no endpoint to call (ADR-900 Q7)"
        )
    endpoints: dict[str, RoleEndpointConfig] = {}
    by_role: dict[LLMRole, RoleEndpointConfig] = {}
    for name, role in raw.items():
        try:
            llm_role = LLMRole(name)
        except ValueError as exc:
            raise RuntimeError(f"unknown llm role {name!r} in config") from exc
        endpoint = RoleEndpointConfig(
            endpoint_id=f"default-{name}",
            base_url=str(role["base_url"]),
            model=str(role["model"]),
            capabilities=_capabilities(tuple(role.get("capabilities", ()))),
        )
        endpoints[endpoint.endpoint_id] = endpoint
        by_role[llm_role] = endpoint
    return LLMRolesConfig(roles=by_role, endpoints=endpoints)


def _capabilities(declared: tuple[str, ...]) -> CapabilityProfile:
    """Capabilities are declared, never assumed: an unknown name is a configuration error."""
    known = {
        "json_schema": "supports_json_schema",
        "json_object": "supports_json_object",
        "tools": "supports_tools",
        "streaming": "supports_streaming",
        "seed": "supports_seed",
    }
    flags: dict[str, Any] = {}
    for name in declared:
        if name not in known:
            raise RuntimeError(f"unknown LLM capability {name!r}; see spec §5.6")
        flags[known[name]] = True
    return CapabilityProfile(**flags)


@dataclass(frozen=True)
class AppServices:
    """Everything the HTTP layer needs, built once per app."""

    tenant_config: TenantConfigService
    gateway: LLMGateway
    prompts: PromptRegistry
    sourcing: SourcingService
    mission_bus: MissionEventBus
    mission_store: InMemoryMissionStore
    flags: FlagProvider


def build_app_services(
    cfg: Settings,
    *,
    clock: Clock | None = None,
    http_client_factory: Callable[[RoleEndpointConfig], httpx.AsyncClient] | None = None,
    flags: FlagProvider | None = None,
    catalogue: StaticCatalogue | None = None,
) -> AppServices:
    """Build the service graph. Synchronous on purpose: ``create_app`` is a sync factory."""
    active_clock = clock or SystemClock()
    tenant_config = TenantConfigService(
        InMemoryConfigRepository(),
        UnwiredDecisionPort(),
        active_clock,
    )
    gateway = LLMGateway(
        config_provider=DefaultRoleConfigProvider(),
        secrets=StaticSecretResolver({}),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=cfg.llm_mission_token_budget),
        sink=InMemorySink(),
        clock=active_clock,
        http_client_factory=http_client_factory,
    )
    prompts = PromptRegistry()
    active_flags = flags or StaticFlags(
        {f"platform.{p.platform_id}.enabled": True for p in DEV_PLATFORMS}
    )
    mission_bus = MissionEventBus()
    mission_store = InMemoryMissionStore()
    sourcing = SourcingService(
        SourcingServiceDeps(
            intake=IntakeAgent(gateway, prompts, active_clock),
            planner=PlannerAgent(
                gateway, prompts, catalogue or StaticCatalogue(list(DEV_PLATFORMS)), active_flags
            ),
            store=mission_store,
            bus=mission_bus,
            clock=active_clock,
            ids=IdGenerator(active_clock),
            config_version=_default_config_version(),
        )
    )
    return AppServices(
        tenant_config=tenant_config,
        gateway=gateway,
        prompts=prompts,
        sourcing=sourcing,
        mission_bus=mission_bus,
        mission_store=mission_store,
        flags=active_flags,
    )


def _default_config_version() -> Callable[[str], str]:
    """``tenant_id -> config_version`` for the defaults the services resolved.

    Synchronous for the same reason as :class:`DefaultRoleConfigProvider`: the sourcing service calls it from
    async code and the repository that would hold a tenant version arrives with D2-05.
    """
    version, values = load_global_layer(DEFAULT_PATH)
    digest = content_hash(_plain_defaults(values))

    def resolve(tenant_id: str) -> str:
        return f"v{version}:{digest[:12]}"

    return resolve


def _plain_defaults(values: dict[str, Any]) -> dict[str, Any]:
    """The hashed view: the defaults as they are, without the per-category block (none here)."""
    return {key: value for key, value in values.items() if key != "categories"}


__all__ = [
    "DEV_PLATFORMS",
    "AppServices",
    "DefaultRoleConfigProvider",
    "UnwiredDecisionPort",
    "build_app_services",
]
