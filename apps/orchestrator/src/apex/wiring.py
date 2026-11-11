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

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from apex.agents.analysis import AnalysisDeps, AnalysisNodes
from apex.agents.browser_worker import HttpBrowserWorker
from apex.agents.csv_importer import DomainCsvImporter
from apex.agents.dashboard import Dashboard
from apex.agents.finance_port import DomainFinancePort
from apex.agents.fx import DomainFxPort, InMemoryFxRateReader
from apex.agents.gate import GateAgent, GateDeps, GateRules, InMemoryGateStore
from apex.agents.header_mapping import HeaderMapper
from apex.agents.intake_chat import IntakeChatAgent
from apex.agents.mission_runner import MissionRunner, MissionRunnerDeps
from apex.agents.missions import InMemoryMissionStore, MissionEventBus
from apex.agents.offers import InMemoryOfferStore, InMemorySellerConfidenceStore
from apex.agents.onboarding import (
    InMemoryOnboardingStore,
    ObjectStore,
    OnboardingDeps,
    OnboardingService,
)
from apex.agents.recommendation import EvaluatorAgent
from apex.agents.request_store import InMemorySourcingRequestStore
from apex.agents.sanity_port import DomainSanityPort
from apex.agents.scraping import ScrapingDeps, ScrapingService
from apex.agents.signing_port import SigningDecisionPort
from apex.agents.sourcing import IntakeAgent, PlannerAgent, PlatformInfo, StaticCatalogue
from apex.agents.sourcing_service import SourcingService, SourcingServiceDeps
from apex.agents.trust_port import DomainTrustPort
from apex.audit.api import AuditEventInput
from apex.audit.api import append as audit_append
from apex.common.clock import Clock, SystemClock
from apex.common.ids import IdGenerator
from apex.config import Settings
from apex.db.models import ActorType
from apex.db.session import default_sessionmaker, tenant_session
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
from apex.signing.api import DecisionRejected, PendingSignature, SignatureInvalid, SigningService
from apex.signing.api import PendingSignature as SigningPending
from apex.tenant_config.defaults import DEFAULT_PATH, load_global_layer
from apex.tenant_config.load_defaults import DEMO_TENANTS, seed
from apex.tenant_config.ports import Decision as ConfigDecision
from apex.tenant_config.ports import PendingSignature as ConfigPendingSignature
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.resolver import content_hash
from apex.tenant_config.service import TenantConfigService
from apex.workers.ports import WorkerPorts

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

    async def sign_service_event(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "service signing is not wired yet (DEV-2 apex.signing.api pending)"
        )


class _LazySigningService:
    """``SigningService`` built on first use, so booting the app never opens a database connection."""

    def __init__(self, config: Any, clock: Clock) -> None:
        self._config, self._clock = config, clock
        self._service: SigningService | None = None

    def _get(self) -> SigningService:
        if self._service is None:
            self._service = SigningService(default_sessionmaker(), self._config, self._clock)
        return self._service

    async def create_decision(self, *args: Any, **kwargs: Any) -> Any:
        return await self._get().create_decision(*args, **kwargs)

    async def require_signed(self, *args: Any, **kwargs: Any) -> Any:
        return await self._get().require_signed(*args, **kwargs)

    async def sign_service_event(self, *args: Any, **kwargs: Any) -> Any:
        return await self._get().sign_service_event(*args, **kwargs)


def signing_port(config: Any, clock: Clock) -> SigningDecisionPort:
    """The graph's decision port over the real signing service (D2-09)."""
    return SigningDecisionPort(
        _LazySigningService(config, clock),
        pending=(PendingSignature,),
        rejected=(DecisionRejected,),
        invalid=(SignatureInvalid,),
    )


class DbAuditPort:
    """``AuditPort`` over the hash-chained audit log (D2-10). One transaction per event."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    async def append(self, event: Mapping[str, Any], *, tenant_id: str) -> None:
        name = str(event.get("event", "agent_event"))
        async with tenant_session(tenant_id, sessionmaker=default_sessionmaker()) as session:
            await audit_append(
                session,
                AuditEventInput(
                    tenant_id=tenant_id,
                    actor_type=ActorType.SERVICE,
                    actor_id="orchestrator",
                    event_type=name,
                    subject_ref=str(event.get("seller_id") or event.get("offer_id") or tenant_id),
                    payload=dict(event),
                ),
                clock=self._clock,
            )


class ConfigDecisionPort:
    """Tenant config's ``DecisionPort`` (no tenant argument) over the signing service.

    The tenant is read from the payload on create and remembered per decision id for ``require_signed``.
    """

    def __init__(self, signing: _LazySigningService) -> None:
        self._signing = signing
        self._tenants: dict[str, str] = {}

    async def create_decision(
        self, type: str, subject_ref: str, payload: Mapping[str, Any]
    ) -> ConfigDecision:
        tenant_id = str(payload["tenant_id"])
        ref = await self._signing.create_decision(type, subject_ref, payload, tenant_id=tenant_id)
        self._tenants[ref.id] = tenant_id
        return ConfigDecision(
            id=ref.id,
            type=type,
            subject_ref=subject_ref,
            status=ref.status.value,
            payload=dict(payload),
        )

    async def require_signed(self, decision_id: str) -> ConfigDecision:
        tenant_id = self._tenants.get(decision_id)
        if tenant_id is None:
            raise ConfigPendingSignature(decision_id)  # unknown here: cannot be treated as signed
        try:
            signed = await self._signing.require_signed(decision_id, tenant_id=tenant_id)
        except SigningPending as exc:
            raise ConfigPendingSignature(decision_id) from exc
        return ConfigDecision(
            id=signed.id,
            type=signed.type.value,
            subject_ref=signed.subject_ref,
            status="signed",
            payload=dict(signed.payload),
        )


class S3ObjectStore:
    """Original financial CSVs in the ``apex-csv`` bucket (RustFS in dev). Returns ``s3://bucket/key``."""

    def __init__(self, cfg: Settings) -> None:
        import boto3  # type: ignore[import-untyped]

        self._bucket = cfg.s3_bucket_csv
        self._client = boto3.client(
            "s3",
            endpoint_url=cfg.s3_endpoint,
            aws_access_key_id=cfg.s3_access_key,
            aws_secret_access_key=cfg.s3_secret_key,
        )

    async def put(self, key: str, content: bytes, *, content_type: str) -> str:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return f"s3://{self._bucket}/{key}"


class UnwiredBrowserWorker:
    """D5-01. Named so a mission that needs it fails with the owner instead of hanging."""

    async def search(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("browser worker is not wired yet (owner: DEV-5, D5-01)")


class UnwiredFx:
    async def to_eur_unit(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("FX is not wired yet (owner: DEV-3, D3-03)")


class UnwiredAudit:
    async def append(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("audit chain is not wired yet (owner: DEV-2, D2-10)")


class _AnalysisConfig:
    """``AnalysisConfig`` over the defaults: the config version and the snapshot max age."""

    def __init__(self, config_version: Callable[[str], str]) -> None:
        self._config_version = config_version
        _, values = load_global_layer(DEFAULT_PATH)
        self._snapshot_max_age_days = int(values["seller"]["snapshot_max_age_days"])

    def config_version(self, tenant_id: str) -> str:
        return self._config_version(tenant_id)

    def seller_snapshot_max_age_days(self, tenant_id: str) -> int:
        return self._snapshot_max_age_days


def _browser_worker(
    cfg: Settings, http_client_factory: Callable[[RoleEndpointConfig], httpx.AsyncClient] | None
) -> Any:
    """The real worker client when a URL is configured, otherwise the port that names its owner.

    The factory is reused for the worker's own clients when a test provides one, so a test can point both
    the LLM gateway and the worker at fakes without a second injection point.
    """
    if not cfg.browser_worker_url:
        return UnwiredBrowserWorker()
    if http_client_factory is not None:
        client_factory = lambda: http_client_factory(  # noqa: E731
            RoleEndpointConfig(
                endpoint_id="browser-worker", base_url=cfg.browser_worker_url, model="worker"
            )
        )
    else:
        client_factory = lambda: httpx.AsyncClient(  # noqa: E731
            base_url=cfg.browser_worker_url, timeout=30.0
        )
    return HttpBrowserWorker(
        base_url=cfg.browser_worker_url,
        service_token=cfg.browser_worker_token,
        client_factory=client_factory,
        max_results=cfg.browser_worker_max_results,
        max_polls=cfg.browser_worker_max_polls,
        poll_interval_s=cfg.browser_worker_poll_interval_s,
    )


def _gate_rules() -> GateRules:
    """``GateRules`` from the versioned defaults. ``approval.threshold`` is unset by default (Q7).

    An unset threshold means "no stretch gate": the value is a business number the tenant must supply, and
    inventing one here would be exactly what rule 0.6 forbids. The gate queue still catches every other
    cause.
    """
    _, values = load_global_layer(DEFAULT_PATH)
    threshold = values["approval"]["threshold"]
    stretch = int(threshold["amount_minor"]) if isinstance(threshold, dict) else 0
    return GateRules(
        sla_hours=int(values["gate"]["sla_hours"]),
        max_renegotiations=int(values["gate"]["max_renegotiations"]),
        stretch_gate_threshold_eur_minor=stretch,
    )


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

    settings: Settings
    tenant_config: TenantConfigService
    gateway: LLMGateway
    prompts: PromptRegistry
    sourcing: SourcingService
    mission_bus: MissionEventBus
    mission_store: InMemoryMissionStore
    flags: FlagProvider
    config_repository: InMemoryConfigRepository
    request_store: InMemorySourcingRequestStore
    onboarding: OnboardingService
    nodes: AnalysisNodes
    gate: GateAgent
    dashboard: Dashboard
    evaluator: EvaluatorAgent
    """Recommendation (D4-12) and the mission's offers, over the same offer store the runner fills."""
    runner: MissionRunner
    """Ready to advance a planned mission. Only invoked automatically when ``mission_autorun`` is on."""


def build_app_services(
    cfg: Settings,
    *,
    clock: Clock | None = None,
    http_client_factory: Callable[[RoleEndpointConfig], httpx.AsyncClient] | None = None,
    flags: FlagProvider | None = None,
    catalogue: StaticCatalogue | None = None,
    fx_rates: Any = None,
    objects: ObjectStore | None = None,
) -> AppServices:
    """Build the service graph. Synchronous on purpose: ``create_app`` is a sync factory."""
    active_clock = clock or SystemClock()
    config_repository = InMemoryConfigRepository()
    signing = _LazySigningService(None, active_clock)
    tenant_config = TenantConfigService(
        config_repository, ConfigDecisionPort(signing), active_clock
    )
    signing._config = tenant_config
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
    request_store = InMemorySourcingRequestStore()
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
    offer_store = InMemoryOfferStore()
    # FX is wired: EUR offers pass through untouched, other currencies go through DEV-3's engine. The rate
    # history is empty until D3-03's ingestion persists it, so a non-EUR offer fails with `rate_unavailable`
    # rather than `not_wired` — an honest "no rate yet", not a missing engine.
    fx_port: Any = DomainFxPort(
        rates=fx_rates or InMemoryFxRateReader(), config=tenant_config, clock=active_clock
    )
    onboarding = OnboardingService(
        OnboardingDeps(
            store=InMemoryOnboardingStore(),
            importer=DomainCsvImporter(
                rates=fx_rates or InMemoryFxRateReader(), config=tenant_config
            ),
            objects=objects or S3ObjectStore(cfg),
            decisions=signing_port(tenant_config, active_clock),
            clock=active_clock,
            ids=IdGenerator(active_clock),
            stale_after_days=_finance_stale_after_days(),
            config_version=_default_config_version(),
            intake=IntakeChatAgent(gateway, prompts),
            mapper=HeaderMapper(gateway, prompts),
        )
    )
    gate_store = InMemoryGateStore()
    rules = _gate_rules()
    nodes = AnalysisNodes(
        AnalysisDeps(
            trust=DomainTrustPort(config=tenant_config, clock=active_clock),
            sanity=DomainSanityPort(config=tenant_config, offers=offer_store, clock=active_clock),
            finance=DomainFinancePort(
                config=tenant_config, onboarding=onboarding, clock=active_clock
            ),
            offers=offer_store,
            confidence=InMemorySellerConfidenceStore(),
            audit=DbAuditPort(active_clock),
            config=_AnalysisConfig(_default_config_version()),
            clock=active_clock,
        )
    )
    gate = GateAgent(
        GateDeps(
            store=gate_store,
            decisions=signing_port(tenant_config, active_clock),
            clock=active_clock,
            ids=IdGenerator(active_clock),
        )
    )
    runner = MissionRunner(
        MissionRunnerDeps(
            scraping=ScrapingService(
                ScrapingDeps(
                    worker=_browser_worker(cfg, http_client_factory),
                    fx=fx_port,
                    offers=offer_store,
                    bus=mission_bus,
                    clock=active_clock,
                )
            ),
            nodes=nodes,
            gate=gate,
            store=mission_store,
            bus=mission_bus,
            clock=active_clock,
            rules_for=lambda tenant_id: rules,
            mission_cost_minor=gateway.mission_cost_minor,
        )
    )
    dashboard = Dashboard(
        offers=offer_store,
        missions=mission_store,
        gate_store=gate_store,
        gate=gate,
        rules_for=lambda tenant_id: rules,
    )
    return AppServices(
        settings=cfg,
        tenant_config=tenant_config,
        gateway=gateway,
        prompts=prompts,
        sourcing=sourcing,
        mission_bus=mission_bus,
        mission_store=mission_store,
        flags=active_flags,
        config_repository=config_repository,
        request_store=request_store,
        onboarding=onboarding,
        nodes=nodes,
        gate=gate,
        dashboard=dashboard,
        evaluator=EvaluatorAgent(
            offers=offer_store,
            missions=mission_store,
            config=tenant_config,
            gateway=gateway,
            prompts=prompts,
            clock=active_clock,
        ),
        runner=runner,
    )


def _finance_stale_after_days() -> int:
    """``finance.stale_after_days`` from the versioned defaults (spec §3.5). Read, never hardcoded."""
    _, values = load_global_layer(DEFAULT_PATH)
    entry = values["finance"]["stale_after_days"]
    return int(entry)


async def seed_demo_tenants(services: AppServices) -> list[str]:
    """Seed the demo tenants' config baseline so proposals and reads have a version to work from.

    Uses the same ``load_defaults`` path as ``pnpm dev:reset`` (ADR-900 Q7 demo values). Idempotent.
    """
    written = await seed(sorted(DEMO_TENANTS), services.config_repository, demo_values=True)
    return [record.tenant_id for record in written]


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
    "UnwiredBrowserWorker",
    "UnwiredFx",
    "S3ObjectStore",
    "UnwiredDecisionPort",
    "build_app_services",
    "seed_demo_tenants",
]


def build_anchor_store(cfg: Settings) -> Any:
    """S3 Object Lock store for audit anchors (ADR-211). Building the client does not open a connection."""
    import boto3

    from apex.audit.anchor import Boto3AnchorStore

    client = boto3.client(
        "s3",
        endpoint_url=cfg.s3_endpoint,
        aws_access_key_id=cfg.s3_access_key,
        aws_secret_access_key=cfg.s3_secret_key,
    )
    return Boto3AnchorStore(client, cfg.s3_bucket_audit)


def build_worker_ports(cfg: Settings, clock: Clock | None = None) -> WorkerPorts:
    """Worker ports with the audit job wired. The other ports stay unwired until their owners land."""
    from dataclasses import replace

    from apex.audit.service import build_audit_chain_service

    return replace(
        WorkerPorts.unwired(), audit=build_audit_chain_service(cfg, clock or SystemClock())
    )
