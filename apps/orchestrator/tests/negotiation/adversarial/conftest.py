from __future__ import annotations

import itertools
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

import httpx
import pytest

from apex.common.clock import FixedClock
from apex.negotiation.engine import NegotiationEngine
from apex.negotiation.ports import (
    InMemoryAccountSendLog,
    InMemoryNegotiationStore,
    InMemorySellerGuard,
    InMemorySellerSendLog,
)
from tests.negotiation.adversarial.mock_marketplace import (
    MockAChatTransport,
    MockMarketplace,
    start_mock_marketplace,
)
from tests.negotiation.fakes import NOW, BandSanity, RegexExtractor, TemplateDrafter


@pytest.fixture(scope="session")
def mock_marketplace() -> Iterator[MockMarketplace]:
    yield from start_mock_marketplace()


@dataclass
class LiveHarness:
    engine: NegotiationEngine
    transport: MockAChatTransport
    drafter: TemplateDrafter
    sanity: BandSanity
    clock: FixedClock
    market: MockMarketplace


@pytest.fixture
async def live_client(mock_marketplace: MockMarketplace) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=mock_marketplace.base_url, timeout=5.0) as client:
        yield client


def build_harness(
    market: MockMarketplace,
    client: httpx.AsyncClient,
    *,
    drafter: TemplateDrafter | None = None,
    extractor: RegexExtractor | None = None,
    sanity: BandSanity | None = None,
) -> LiveHarness:
    transport = MockAChatTransport(client)
    d = drafter or TemplateDrafter()
    s = sanity or BandSanity()
    clock = FixedClock(NOW)
    counter = itertools.count(1)
    engine = NegotiationEngine(
        transport=transport,
        drafter=d,
        extractor=extractor or RegexExtractor(),
        sanity=s,
        store=InMemoryNegotiationStore(),
        send_log=InMemoryAccountSendLog(),
        seller_log=InMemorySellerSendLog(),
        seller_guard=InMemorySellerGuard(),
        clock=clock,
        new_id=lambda: f"id-{next(counter)}",
    )
    return LiveHarness(engine, transport, d, s, clock, market)
