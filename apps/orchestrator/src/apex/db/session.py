"""Tenant-scoped database sessions (D2-04, ADR-206).

Row-level security reads the tenant from the transaction-local setting ``app.tenant_id``. ``tenant_session``
opens a session whose every transaction sets it, so code that commits halfway and keeps going stays inside the
same tenant. Without the setting, tenant rows are invisible and cannot be written.

The application must connect as a member of the ``apex_app`` role, never as the migrator or a superuser: those
bypass RLS. ``system_session`` is for global data only (FX rates, service keys) and sets no tenant.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction

from apex.config import get_settings

TENANT_SETTING = "app.tenant_id"
_TENANT_INFO_KEY = "apex.tenant_id"
_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")


def create_engine(url: str | None = None, **kwargs: Any) -> AsyncEngine:
    """An async engine for ``url``, or for ``Settings.database_url`` when no URL is given."""
    settings = get_settings()
    options: dict[str, Any] = {"pool_size": settings.database_pool_size, "pool_pre_ping": True}
    options.update(kwargs)
    return create_async_engine(url or settings.database_url, **options)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@lru_cache
def default_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return create_sessionmaker(create_engine())


def _apply_tenant(
    session: Session, _transaction: SessionTransaction, connection: Connection
) -> None:
    tenant_id = session.info.get(_TENANT_INFO_KEY)
    if tenant_id:
        connection.execute(_SET_TENANT, {"tenant_id": tenant_id})


@asynccontextmanager
async def _committing(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    # Autobegin instead of session.begin(), so callers may commit halfway; each new transaction re-runs
    # _apply_tenant through the after_begin event.
    try:
        yield session
    except BaseException:
        await session.rollback()
        raise
    await session.commit()


@asynccontextmanager
async def tenant_session(
    tenant_id: str, *, sessionmaker: async_sessionmaker[AsyncSession] | None = None
) -> AsyncIterator[AsyncSession]:
    """A session bound to ``tenant_id``. Commits on normal exit and rolls back on error."""
    if not tenant_id or not tenant_id.strip():
        raise ValueError("tenant_session needs a non-empty tenant_id")
    factory = sessionmaker or default_sessionmaker()
    async with factory() as session:
        session.info[_TENANT_INFO_KEY] = tenant_id
        event.listen(session.sync_session, "after_begin", _apply_tenant)
        async with _committing(session):
            yield session


@asynccontextmanager
async def system_session(
    *, sessionmaker: async_sessionmaker[AsyncSession] | None = None
) -> AsyncIterator[AsyncSession]:
    """A session with no tenant: it sees global tables only. Commits on normal exit and rolls back on error."""
    factory = sessionmaker or default_sessionmaker()
    async with factory() as session, _committing(session):
        yield session


__all__ = [
    "TENANT_SETTING",
    "create_engine",
    "create_sessionmaker",
    "default_sessionmaker",
    "system_session",
    "tenant_session",
]
