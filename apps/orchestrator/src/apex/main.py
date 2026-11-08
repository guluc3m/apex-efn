"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from apex.api import router
from apex.common.errors import install_problem_handlers
from apex.common.idempotency import (
    IdempotencyMiddleware,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    RedisIdempotencyStore,
)
from apex.config import Settings, settings


def build_idempotency_store(cfg: Settings) -> IdempotencyStore:
    """Select the idempotency store from settings. Redis is only constructed when selected."""
    if cfg.idempotency_backend == "redis":
        return RedisIdempotencyStore(Redis.from_url(cfg.redis_url))
    return InMemoryIdempotencyStore()


def create_app(cfg: Settings | None = None, store: IdempotencyStore | None = None) -> FastAPI:
    """Build the application. Tests pass their own settings and an in-memory store."""
    active = cfg or settings

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

    @application.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return application


app: FastAPI = create_app()
