"""``apex.db.models``: the SQLAlchemy mapping of the Prisma schema (D2-05, ADR-207).

Two drift checks run against a freshly migrated database: the generator output must match the committed
``generated.py``, and an independent reflection of the catalog must match ``Base.metadata`` (tables, columns,
types, nullability, primary keys, foreign keys and indexes). Then a round trip through ``tenant_session`` as the
application role checks the types that need care: bigint money, Decimal FX rates, enums and enum arrays,
pgvector and timezone-aware timestamps.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.types import TypeEngine

from apex.db import codegen
from apex.db.base import Base
from apex.db.models import (
    ActorType,
    Currency,
    FxRate,
    GateQueueItem,
    GateReason,
    GateStatus,
    Mission,
    MissionState,
    ProductEmbedding,
    SourcingRequest,
    SourcingRequestStatus,
    Tenant,
    TenantConfigVersion,
)
from apex.db.session import create_engine as create_async_engine
from apex.db.session import create_sessionmaker, system_session, tenant_session
from apex.db.types import Vector
from tests.db.conftest import postgres_available

T0 = datetime(2026, 1, 1, 12, 30, tzinfo=UTC)
TENANT = "tenant-models-a"
OTHER = "tenant-models-b"

integration = pytest.mark.integration
needs_postgres = pytest.mark.skipif(
    not postgres_available(), reason="no Postgres: set APEX_TEST_PG_ADMIN_URL or start Docker"
)


def _driver(url: str, driver: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((f"postgresql+{driver}", parts.netloc, parts.path, "", ""))


# --- static checks ---------------------------------------------------------------------------------------------


def test_every_prisma_model_is_mapped() -> None:
    names = codegen.prisma_model_names(codegen.PRISMA_SCHEMA.read_text(encoding="utf-8"))
    assert set(Base.metadata.tables) == set(names)
    mapped = {mapper.class_.__name__: mapper.local_table.name for mapper in Base.registry.mappers}
    assert mapped == {model: table for table, model in names.items()}


def test_metadata_never_creates_tables() -> None:
    # Prisma owns DDL (ADR-201): enum types are declared create_type=False so nothing here emits CREATE TYPE.
    enums = [
        column.type
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, postgresql.ENUM)
    ]
    assert enums
    assert all(not enum.create_type for enum in enums)


# --- drift against a migrated database -------------------------------------------------------------------------


@integration
@needs_postgres
def test_generated_models_match_the_migrations(migrated_db: str) -> None:
    expected = codegen.generate(migrated_db)
    assert codegen.OUTPUT.read_text(encoding="utf-8") == expected, (
        "apex/db/models/generated.py is stale: run python -m apex.db.codegen --database-url <migrated db>"
    )


def _type_key(type_: TypeEngine[object]) -> str:
    if isinstance(type_, Vector):
        return "VECTOR"
    if isinstance(type_, postgresql.ARRAY):
        return f"ARRAY({_type_key(type_.item_type)})"
    if isinstance(type_, postgresql.ENUM):
        return f"ENUM({type_.name})"
    compiled = type_.compile(dialect=postgresql.dialect())
    return re.sub(r"\s+", " ", compiled)


def _reflected_type_key(type_: TypeEngine[object], raw: str | None) -> str:
    if raw == "vector":
        return "VECTOR"
    return _type_key(type_)


@integration
@needs_postgres
def test_reflection_matches_the_metadata(migrated_db: str) -> None:
    engine = create_engine(_driver(migrated_db, "psycopg"))
    try:
        with engine.connect() as conn:
            vector_columns = {
                (table, column)
                for table, column in conn.exec_driver_sql(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND udt_name = 'vector'"
                )
            }
            inspector = inspect(conn)
            reflected_tables = set(inspector.get_table_names()) - codegen.EXCLUDED_TABLES
            assert reflected_tables == set(Base.metadata.tables)
            problems: list[str] = []
            for name, table in Base.metadata.tables.items():
                with warnings.catch_warnings():
                    # SQLAlchemy does not know pgvector and warns; the vector columns are compared by name.
                    warnings.simplefilter("ignore")
                    columns = inspector.get_columns(name)
                reflected = {
                    c["name"]: (
                        _reflected_type_key(
                            c["type"], "vector" if (name, c["name"]) in vector_columns else None
                        ),
                        c["nullable"],
                    )
                    for c in columns
                }
                mapped = {c.name: (_type_key(c.type), c.nullable) for c in table.columns}
                if reflected != mapped:
                    problems.append(
                        f"{name} columns: {sorted(set(reflected.items()) ^ set(mapped.items()))}"
                    )
                pk = inspector.get_pk_constraint(name)["constrained_columns"]
                if pk != [c.name for c in table.primary_key.columns]:
                    problems.append(f"{name} primary key: {pk}")
                fks = {
                    (
                        fk["name"],
                        tuple(fk["constrained_columns"]),
                        fk["referred_table"],
                        tuple(fk["referred_columns"]),
                    )
                    for fk in inspector.get_foreign_keys(name)
                }
                mapped_fks = {
                    (
                        fk.name,
                        tuple(c.name for c in fk.columns),
                        fk.referred_table.name,
                        tuple(e.column.name for e in fk.elements),
                    )
                    for fk in table.foreign_key_constraints
                }
                if fks != mapped_fks:
                    problems.append(f"{name} foreign keys: {sorted(map(str, fks ^ mapped_fks))}")
                indexes = {
                    (i["name"], tuple(i["column_names"]), bool(i["unique"]))
                    for i in inspector.get_indexes(name)
                }
                mapped_indexes = {
                    (i.name, tuple(c.name for c in i.columns), bool(i.unique))
                    for i in table.indexes
                }
                if indexes != mapped_indexes:
                    problems.append(f"{name} indexes: {sorted(map(str, indexes ^ mapped_indexes))}")
            assert problems == []
    finally:
        engine.dispose()


# --- ORM round trip as the application role --------------------------------------------------------------------


@pytest.fixture
async def factory(migrated_db: str, app_db: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    with psycopg.connect(migrated_db, autocommit=True) as admin:
        for tenant in (TENANT, OTHER):
            admin.execute(
                "INSERT INTO tenants (id, name, country, base_currency, created_at, updated_at) "
                "VALUES (%s, %s, 'ES', 'EUR', %s, %s) ON CONFLICT DO NOTHING",
                [tenant, tenant, T0, T0],
            )
    engine = create_async_engine(_driver(app_db, "asyncpg"), pool_size=1, max_overflow=0)
    try:
        yield create_sessionmaker(engine)
    finally:
        await engine.dispose()


@integration
@needs_postgres
async def test_orm_round_trip_through_tenant_session(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    token_budget = 2**40 + 7  # above int32: money and counters are int64 (ADR-205)
    async with tenant_session(TENANT, sessionmaker=factory) as session:
        session.add(
            TenantConfigVersion(
                id="cfg-models-1",
                tenant_id=TENANT,
                config_version=1,
                content_hash="0" * 64,
                values={"sanity": {"z_gate": "3.5"}},
                created_by_type=ActorType.SERVICE,
                created_by_id="load-defaults",
                created_at=T0,
            )
        )
        session.add(
            SourcingRequest(
                id="req-models-1",
                tenant_id=TENANT,
                created_by_id="user-buyer-a",
                status=SourcingRequestStatus.NORMALIZED,
                spec={"product": "nitrile gloves"},
                quantity_tiers=[{"quantity": 10000}],
                max_budget_minor=token_budget,
                max_budget_currency=Currency.CNY,
                delivery_country="ES",
                created_at=T0,
            )
        )
        await session.flush()
        session.add(
            Mission(
                id="mission-models-1",
                tenant_id=TENANT,
                request_id="req-models-1",
                state=MissionState.CREATED,
                config_version=1,
                offers_discovered=0,
                offers_negotiated=0,
                offers_in_gate=0,
                tokens_used=0,
                token_budget=token_budget,
                started_at=T0,
            )
        )
        await session.flush()
        session.add(
            GateQueueItem(
                id="gate-models-1",
                tenant_id=TENANT,
                mission_id="mission-models-1",
                causes=[GateReason.PRICE_ATYPICAL, GateReason.SELLER_LOW],
                status=GateStatus.OPEN,
                sla_due_at=T0 + timedelta(hours=24),
                created_at=T0,
            )
        )
        session.add(
            ProductEmbedding(
                id="emb-models-1",
                tenant_id=TENANT,
                product_key="nitrile-gloves-m",
                model="stub-embed",
                dimensions=3,
                embedding=[0.25, -1.5, 3.0],
                created_at=T0,
            )
        )

    async with tenant_session(TENANT, sessionmaker=factory) as session:
        tenants = (await session.scalars(select(Tenant))).all()
        assert [t.id for t in tenants] == [TENANT]
        assert tenants[0].base_currency is Currency.EUR

        request = await session.get_one(SourcingRequest, "req-models-1")
        assert request.max_budget_minor == token_budget
        assert request.max_budget_currency is Currency.CNY
        assert request.quantity_tiers == [{"quantity": 10000}]

        mission = await session.get_one(Mission, "mission-models-1")
        assert mission.token_budget == token_budget
        assert mission.state is MissionState.CREATED
        assert mission.started_at == T0
        assert mission.started_at.tzinfo is not None

        item = await session.get_one(GateQueueItem, "gate-models-1")
        assert item.causes == [GateReason.PRICE_ATYPICAL, GateReason.SELLER_LOW]
        assert all(isinstance(cause, GateReason) for cause in item.causes or [])

        embedding = await session.get_one(ProductEmbedding, "emb-models-1")
        assert embedding.embedding == [0.25, -1.5, 3.0]

    async with tenant_session(OTHER, sessionmaker=factory) as session:
        assert await session.get(Mission, "mission-models-1") is None
        assert (await session.scalars(select(GateQueueItem))).all() == []


@integration
@needs_postgres
async def test_fx_rates_keep_every_decimal_place(factory: async_sessionmaker[AsyncSession]) -> None:
    rate = Decimal("7.812345678901")
    async with system_session(sessionmaker=factory) as session:
        session.add(
            FxRate(
                id="fx-models-1",
                base=Currency.EUR,
                quote=Currency.CNY,
                rate=rate,
                as_of=T0,
                source="ecb",
                ingested_at=T0 + timedelta(minutes=5),
            )
        )
    async with tenant_session(TENANT, sessionmaker=factory) as session:
        stored = await session.get_one(FxRate, "fx-models-1")
        assert stored.rate == rate
        assert isinstance(stored.rate, Decimal)
        assert (stored.base, stored.quote) == (Currency.EUR, Currency.CNY)
        assert stored.as_of == T0
