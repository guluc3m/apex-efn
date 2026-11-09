"""``apex.db.session``: tenant-scoped SQLAlchemy sessions on top of RLS (D2-04)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apex.db.session import create_engine, create_sessionmaker, system_session, tenant_session
from tests.db.conftest import postgres_available

T0 = datetime(2026, 1, 1, tzinfo=UTC)
TENANTS = ("tenant-session-a", "tenant-session-b")

integration = pytest.mark.integration
needs_postgres = pytest.mark.skipif(
    not postgres_available(), reason="no Postgres: set APEX_TEST_PG_ADMIN_URL or start Docker"
)


def _asyncpg(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, "", ""))


@pytest.fixture(scope="module")
def seeded_app_db(migrated_db: str, app_db: str) -> str:
    with psycopg.connect(migrated_db, autocommit=True) as admin:
        for tenant in TENANTS:
            admin.execute(
                "INSERT INTO tenants (id, name, country, base_currency, created_at, updated_at) "
                "VALUES (%s, %s, 'ES', 'EUR', %s, %s)",
                [tenant, tenant, T0, T0],
            )
    return app_db


@pytest.fixture
async def factory(seeded_app_db: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # One pooled connection, so every session reuses it and a leaked tenant setting would show.
    engine = create_engine(_asyncpg(seeded_app_db), pool_size=1, max_overflow=0)
    try:
        yield create_sessionmaker(engine)
    finally:
        await engine.dispose()


async def _visible_tenants(session: AsyncSession) -> list[str]:
    return list((await session.execute(text("SELECT id FROM tenants ORDER BY id"))).scalars())


async def test_empty_tenant_is_rejected() -> None:
    for tenant in ("", "  "):
        with pytest.raises(ValueError, match="non-empty"):
            async with tenant_session(tenant, sessionmaker=async_sessionmaker()):
                pass


@integration
@needs_postgres
async def test_session_sees_only_its_tenant(factory: async_sessionmaker[AsyncSession]) -> None:
    async with tenant_session(TENANTS[0], sessionmaker=factory) as session:
        assert await _visible_tenants(session) == [TENANTS[0]]
    async with tenant_session(TENANTS[1], sessionmaker=factory) as session:
        assert await _visible_tenants(session) == [TENANTS[1]]


@integration
@needs_postgres
async def test_tenant_survives_a_commit_inside_the_session(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with tenant_session(TENANTS[0], sessionmaker=factory) as session:
        await session.commit()
        assert await _visible_tenants(session) == [TENANTS[0]]


@integration
@needs_postgres
async def test_tenant_does_not_leak_to_the_next_session(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with tenant_session(TENANTS[0], sessionmaker=factory) as session:
        assert await _visible_tenants(session) == [TENANTS[0]]
    async with system_session(sessionmaker=factory) as session:
        assert await _visible_tenants(session) == []
        setting = await session.execute(text("SELECT current_setting('app.tenant_id', true)"))
        assert setting.scalar_one() in (None, "")


@integration
@needs_postgres
async def test_writes_for_another_tenant_are_refused_and_rolled_back(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_session(TENANTS[0], sessionmaker=factory) as session:
            await session.execute(
                text("UPDATE tenants SET name = 'renamed' WHERE id = :id"), {"id": TENANTS[0]}
            )
            await session.execute(
                text(
                    "INSERT INTO tenants (id, name, country, base_currency, created_at, updated_at) "
                    "VALUES (:id, 'x', 'ES', 'EUR', :t, :t)"
                ),
                {"id": "tenant-session-forged", "t": T0},
            )
    async with tenant_session(TENANTS[0], sessionmaker=factory) as session:
        name = await session.execute(
            text("SELECT name FROM tenants WHERE id = :id"), {"id": TENANTS[0]}
        )
        assert name.scalar_one() == TENANTS[0]
