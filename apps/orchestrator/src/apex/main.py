"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from apex.api import missions as missions_api
from apex.api import router
from apex.api import sourcing as sourcing_api
from apex.common.errors import install_problem_handlers
from apex.common.idempotency import (
    IdempotencyMiddleware,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    RedisIdempotencyStore,
)
from apex.config import Settings, settings
from apex.platform.telemetry import setup_telemetry
from apex.wiring import AppServices, build_app_services


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
    active_services = services or build_app_services(active)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Application lifespan handler."""
        # Startup
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

    application.include_router(router, prefix="/v1")
    _wire_services(application, active_services)
    setup_telemetry(application, service_name="apex-orchestrator")

    @application.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return application


def _wire_services(application: FastAPI, services: AppServices) -> None:
    """Point the DEV-4 routes at the services they need.

    Only the services that exist today are wired. Routes whose engine is still missing keep answering 501
    with the owning lane named, which is the honest answer: the alternative is inventing the numbers those
    engines own.
    """
    application.state.app_services = services
    application.state.mission_event_bus = services.mission_bus
    application.dependency_overrides[sourcing_api.get_sourcing_service] = lambda: services.sourcing
    application.dependency_overrides[missions_api.get_sourcing_service] = lambda: services.sourcing


app: FastAPI = create_app()
