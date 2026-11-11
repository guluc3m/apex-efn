"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from apex.agents.translation import MessageTranslator
from apex.api import accounts as accounts_api
from apex.api import config as config_api
from apex.api import dashboard as dashboard_api
from apex.api import gate as gate_api
from apex.api import missions as missions_api
from apex.api import negotiations as negotiations_api
from apex.api import onboarding as onboarding_api
from apex.api import router
from apex.api import sellers as sellers_api
from apex.api import sourcing as sourcing_api
from apex.api import translation as translation_api
from apex.auth.deps import current_principal
from apex.common.errors import install_problem_handlers
from apex.common.idempotency import (
    IdempotencyMiddleware,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    RedisIdempotencyStore,
)
from apex.config import Settings, settings
from apex.platform.telemetry import setup_telemetry
from apex.wiring import (
    DEV_PLATFORMS,
    AppServices,
    build_anchor_store,
    build_app_services,
    seed_demo_financials,
    seed_demo_tenants,
)

logger = structlog.get_logger(__name__)


def build_idempotency_store(cfg: Settings) -> IdempotencyStore:
    """Select the idempotency store from settings. Redis is only constructed when selected."""
    if cfg.idempotency_backend == "redis":
        return RedisIdempotencyStore(Redis.from_url(cfg.redis_url))
    return InMemoryIdempotencyStore()


def create_app(
    cfg: Settings | None = None,
    store: IdempotencyStore | None = None,
    services: AppServices | None = None,
) -> FastAPI:
    """Build the application. Tests pass their own settings, store and service graph."""
    active = cfg or settings
    active_services = services if services is not None else _safe_services(active)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Application lifespan handler."""
        # Startup: the demo tenants get their config baseline, so reads and proposals have a version.
        if active_services is not None:
            await seed_demo_tenants(active_services)
            # DEMO_MODE only: an unsigned active snapshot, so a mission can run without the passkey
            # ceremony. No-op (and never reached) outside the demo.
            await seed_demo_financials(active_services)
        yield
        # Shutdown

    application = FastAPI(
        title="APEX-EFN Orchestrator",
        description="Agent orchestration for B2B sourcing and negotiation",
        version="0.1.0",
        lifespan=lifespan,
    )

    install_problem_handlers(application)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=active.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(
        IdempotencyMiddleware,
        store=store or build_idempotency_store(active),
        ttl_seconds=active.idempotency_ttl_seconds,
        required=active.idempotency_required,
    )

    # D1-05: every versioned endpoint is authenticated, including the stubs that do not depend on the
    # tenant yet. Owning lanes add the role checks; authentication is not optional per router.
    application.include_router(router, prefix="/v1", dependencies=[Depends(current_principal)])
    if active_services is not None:
        _wire_services(application, active_services)
    setup_telemetry(application, service_name="apex-orchestrator")

    @application.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return application


def _safe_services(cfg: Settings) -> AppServices | None:
    """Build the service graph, or boot without one.

    The graph reads ``config/defaults/tenant-config.v1.json``. If that file is not where the app expects it
    (a container image built from ``apps/orchestrator`` alone, for instance), the app must still start and
    answer 501 with a reason: crashing at import would take the whole process down with no diagnosis.
    """
    try:
        return build_app_services(cfg)
    except (FileNotFoundError, KeyError, RuntimeError) as exc:
        logger.error("service graph unavailable, routes will answer 501", extra={"error": str(exc)})
        return None


def _wire_services(application: FastAPI, services: AppServices) -> None:
    """Point the DEV-4 routes at the services they need.

    Only the services that exist today are wired. Routes whose engine is still missing keep answering 501
    with the owning lane named, which is the honest answer: the alternative is inventing the numbers those
    engines own.
    """
    application.state.app_services = services
    application.state.mission_event_bus = services.mission_bus
    application.dependency_overrides[sourcing_api.get_sourcing_service] = lambda: services.sourcing
    application.dependency_overrides[sourcing_api.get_request_store] = lambda: (
        services.request_store
    )
    application.dependency_overrides[config_api.get_config_service] = lambda: services.tenant_config
    application.dependency_overrides[onboarding_api.get_onboarding] = lambda: services.onboarding
    application.dependency_overrides[dashboard_api.get_dashboard] = lambda: services.dashboard
    application.dependency_overrides[gate_api.get_gate_agent] = lambda: services.gate
    application.dependency_overrides[negotiations_api.get_negotiation_control] = lambda: (
        services.negotiation.control
    )
    application.dependency_overrides[missions_api.get_recommendation_provider] = lambda: (
        services.evaluator
    )
    application.dependency_overrides[missions_api.get_offer_reader] = lambda: services.evaluator
    application.dependency_overrides[sellers_api.get_analysis_nodes] = lambda: services.nodes
    application.dependency_overrides[translation_api.get_translator] = lambda: MessageTranslator(
        services.gateway, services.prompts
    )
    application.dependency_overrides[accounts_api.get_platform_ids] = lambda: [
        p.platform_id for p in DEV_PLATFORMS
    ]
    application.state.settings = services.settings
    application.state.anchor_store = build_anchor_store(services.settings)


app: FastAPI = create_app()
