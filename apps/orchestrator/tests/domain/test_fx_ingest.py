"""ECB ingestion (D3-03, ADR-302 §6): parsing, HTTP through a mock transport, insert-only storage."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apex.contracts.generated.models import Currency
from apex.db.session import create_engine, create_sessionmaker, system_session
from apex.domain.fx.ingest import ECB_DAILY_URL, EcbRateSource, FeedError, latest_rates, parse_ecb
from tests.db.conftest import postgres_available

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
    xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube><Cube time="2026-01-02">
    <Cube currency="USD" rate="1.0812"/><Cube currency="JPY" rate="162.31"/><Cube currency="CNY" rate="7.8123"/>
  </Cube></Cube>
</gesmes:Envelope>"""
SUMMER = FEED.replace(b"2026-01-02", b"2026-07-01")
# 16:00 Europe/Berlin: CET in winter, CEST in summer
WINTER_AS_OF = datetime(2026, 1, 2, 15, tzinfo=UTC)
SUMMER_AS_OF = datetime(2026, 7, 1, 14, tzinfo=UTC)
SLOT = datetime(2026, 1, 2, 17, tzinfo=UTC)


def test_parses_supported_currencies_at_publication_time() -> None:
    rates = parse_ecb(FEED)
    assert [(r.base, r.quote, r.rate, r.source) for r in rates] == [
        (Currency.EUR, Currency.USD, "1.0812", "ecb"),
        (Currency.EUR, Currency.CNY, "7.8123", "ecb"),
    ]
    assert rates[0].as_of == WINTER_AS_OF
    assert parse_ecb(SUMMER)[0].as_of == SUMMER_AS_OF


@pytest.mark.parametrize(
    "feed",
    [
        b"not xml",
        FEED.replace(b'rate="1.0812"', b'rate="1,0812"'),
        FEED.replace(b'rate="7.8123"', b'rate="0.0"'),
        FEED.replace(b'currency="USD"', b'currency="GBP"').replace(
            b'currency="CNY"', b'currency="CHF"'
        ),
        FEED.replace(b"</Cube></Cube>", b'</Cube><Cube time="2026-01-01"/></Cube>'),
    ],
    ids=["not-xml", "comma", "zero", "no-supported", "two-days"],
)
def test_rejects_an_unexpected_feed(feed: bytes) -> None:
    with pytest.raises(FeedError):
        parse_ecb(feed)


def _client(body: bytes, status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == ECB_DAILY_URL
        return httpx.Response(status, content=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_http_error_stores_nothing() -> None:
    async with _client(b"", 503) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await EcbRateSource(client).ingest_for(SLOT)


needs_postgres = pytest.mark.skipif(
    not postgres_available(), reason="no Postgres: set APEX_TEST_PG_ADMIN_URL or start Docker"
)


@pytest.fixture
async def factory(migrated_db: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    parts = urlsplit(migrated_db)
    engine = create_engine(urlunsplit(("postgresql+asyncpg", parts.netloc, parts.path, "", "")))
    yield create_sessionmaker(engine)
    await engine.dispose()


@pytest.mark.integration
@needs_postgres
async def test_ingestion_is_insert_only_and_idempotent(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(FEED) as client:
        source = EcbRateSource(client, factory)
        first = await source.ingest_for(SLOT)
        again = await source.ingest_for(SLOT)
    assert (first.as_of, first.inserted, first.already_present) == (SLOT, 2, 0)
    assert (again.inserted, again.already_present) == (0, 2)
    async with system_session(sessionmaker=factory) as session:
        rates = await latest_rates(session, SLOT)
        assert await latest_rates(session, WINTER_AS_OF.replace(hour=14)) == []
    assert sorted((r.quote, r.rate, r.as_of) for r in rates) == [
        (Currency.CNY, "7.8123", WINTER_AS_OF),
        (Currency.USD, "1.0812", WINTER_AS_OF),
    ]
