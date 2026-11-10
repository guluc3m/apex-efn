"""Daily ECB euro reference rates into the insert-only ``fx_rates`` history (D3-03, ADR-302 §6).

The worker job (DEV-4, ``apex.workers.jobs.ingest_fx_rates``) calls ``EcbRateSource.ingest_for(slot)``.
``ingested_at`` is the database's ``CURRENT_TIMESTAMP``, so this module never reads the clock (ADR-300).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apex.contracts.generated.models import Currency, FxRate
from apex.db.models.generated import FxRate as FxRateRow
from apex.db.session import system_session
from apex.domain.fx import PIVOT
from apex.workers.ports import FxIngestResult

ECB_DAILY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
SOURCE = "ecb"
# The ECB publishes the reference rates at about 16:00 CET on each TARGET business day
PUBLISHED_AT = time(16, 0, tzinfo=ZoneInfo("Europe/Berlin"))
_RATE = re.compile(r"[0-9]+(\.[0-9]+)?")
_NS = "{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}"


class FeedError(ValueError):
    """The ECB file is not what ADR-302 expects. Nothing is stored."""

    code = "fx_feed_invalid"


def parse_ecb(xml: bytes) -> list[FxRate]:
    """``EUR→<currency>`` rates for every supported currency in the ECB daily file."""
    try:
        root = ElementTree.fromstring(xml)  # expat >= 2.4.1 refuses entity expansion bombs
    except ElementTree.ParseError as exc:
        raise FeedError(f"ECB feed is not XML: {exc}") from None
    days = root.findall(f"./{_NS}Cube/{_NS}Cube[@time]")
    if len(days) != 1:
        raise FeedError(f"Expected one reference day, found {len(days)}")
    as_of = datetime.combine(date.fromisoformat(days[0].attrib["time"]), PUBLISHED_AT)
    rates = []
    for cube in days[0].findall(f"{_NS}Cube"):
        code, rate = cube.attrib.get("currency", ""), cube.attrib.get("rate", "")
        if code not in Currency.__members__ or code == PIVOT:
            continue
        if not _RATE.fullmatch(rate) or not rate.strip("0."):
            raise FeedError(f"Invalid {code} rate {rate!r}")
        rates.append(
            FxRate(base=PIVOT, quote=Currency(code), rate=rate, as_of=as_of, source=SOURCE)
        )
    if not rates:
        raise FeedError("No supported currency in the ECB feed")
    return rates


async def store(session: AsyncSession, rates: list[FxRate]) -> int:
    """Insert-only; a row already present for (base, quote, as_of, source) is left untouched."""
    rows = [
        {
            "id": f"{r.source}:{r.base.value}:{r.quote.value}:{r.as_of.isoformat()}",
            "base": r.base,
            "quote": r.quote,
            "rate": Decimal(r.rate),
            "as_of": r.as_of,
            "source": r.source,
            "ingested_at": func.current_timestamp(),
        }
        for r in rates
    ]
    stmt = (
        insert(FxRateRow)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["base", "quote", "as_of", "source"])
        .returning(FxRateRow.id)
    )
    return len((await session.execute(stmt)).all())


async def latest_rates(session: AsyncSession, now: datetime) -> list[FxRate]:
    """The newest rate per (base, quote, source) at ``now``: the input of ``apex.domain.fx.convert``."""
    stmt = (
        select(FxRateRow)
        .where(FxRateRow.as_of <= now)
        .order_by(FxRateRow.base, FxRateRow.quote, FxRateRow.source, FxRateRow.as_of.desc())
        .distinct(FxRateRow.base, FxRateRow.quote, FxRateRow.source)
    )
    return [
        FxRate(
            base=Currency(r.base.value),
            quote=Currency(r.quote.value),
            rate=_plain(r.rate),
            as_of=r.as_of,
            source=r.source,
        )
        for r in (await session.execute(stmt)).scalars()
    ]


def _plain(value: object) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


class EcbRateSource:
    """``apex.workers.ports.FxRateSource`` backed by the ECB daily file."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
        url: str = ECB_DAILY_URL,
    ) -> None:
        self._client, self._sessionmaker, self._url = client, sessionmaker, url

    async def ingest_for(self, as_of: datetime) -> FxIngestResult:
        response = await self._client.get(self._url)
        response.raise_for_status()
        rates = parse_ecb(response.content)
        async with system_session(sessionmaker=self._sessionmaker) as session:
            inserted = await store(session, rates)
        return FxIngestResult(as_of=as_of, inserted=inserted, already_present=len(rates) - inserted)
