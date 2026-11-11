"""The negotiation engine wired for the app (D5-07 / D5-11).

The HTTP router, the mission runner and the tests all need the *same* engine state: a negotiation started by
a mission must be visible on ``GET /v1/negotiations/{id}`` and controllable from ``takeover`` / ``resume`` /
``abort``. So this module builds one process-wide arrangement:

- one store (and send logs, seller guard) shared by every engine instance;
- one transport factory pointing at the mock marketplace's threads;
- one engine per mission (the drafter is bound to a mission for the token budget);
- one short-lived ``EngineNegotiationPort`` per negotiation call, which is stateless: the store maps the
  idempotency key to the session, so a restart resumes instead of duplicating.

What is real here: the pricing ladder in ``NegotiationEngine`` (code decides every number), the guardrails,
the transcript, and the outcomes. What is dev-wired: the marketplace (mock-c) and the LLM (the OpenAI-
compatible endpoint from ``llm.roles.negotiator``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apex.agents.negotiation_params import NegotiationParamsResolver
from apex.agents.offers import OfferStore
from apex.agents.sanity_port import DomainSanityPort
from apex.common.clock import Clock
from apex.negotiation.api import NegotiationControlService
from apex.negotiation.engine import NegotiationEngine
from apex.negotiation.llm import LLMDrafter, LLMExtractor
from apex.negotiation.models import NegotiationSession, Quote, SanityBand
from apex.negotiation.node import EngineNegotiationPort
from apex.negotiation.ports import (
    ChatTransport,
    InMemoryAccountSendLog,
    InMemoryNegotiationStore,
    InMemorySellerGuard,
    InMemorySellerSendLog,
)
from apex.negotiation.sim.market import HttpMarketplace
from apex.negotiation.sim.mock_a import MockAChatTransport, PerPlatformChatTransport
from apex.negotiation.sim.transport import MarketChatTransport
from apex.tenant_config.service import TenantConfigService

__all__ = ["AppNegotiation", "build_app_negotiation"]


class _DemoAccountResolver:
    """An opaque buyer account for the mock marketplace.

    mock-c has no login, so the account id only scopes the send limits. A real tenant uses
    ``DbAccountResolver`` (an active ``ConnectedAccount`` row) once the platform requires credentials.
    """

    def __init__(self, account_id: str) -> None:
        self._account_id = account_id

    async def account_for(self, *, tenant_id: str, platform: str) -> str:
        return f"{self._account_id}:{tenant_id}:{platform}"


class OfferSanityRecheck:
    """Criterion 13: the price the seller just wrote is re-checked before the agent answers.

    Reuses DEV-3's engine through ``DomainSanityPort`` so the re-check runs against the same mission
    reference universe and the same tenant config as the first check.
    """

    def __init__(self, sanity: DomainSanityPort, offers: OfferStore) -> None:
        self._sanity = sanity
        self._offers = offers

    async def check(self, quote: Quote, *, session: NegotiationSession) -> SanityBand:
        offer = await self._offers.get(session.tenant_id, session.offer_id)
        if offer is None:
            return SanityBand.NORMAL
        payload = {
            "offer_id": offer.id,
            "mission_id": offer.mission_id,
            "category": None,
            "unit_price_eur_minor": offer.unit_price_eur_minor,
        }
        outcome = await self._sanity.check(
            payload, tenant_id=session.tenant_id, price_minor=quote.unit_price_minor
        )
        try:
            return SanityBand(outcome.band.value)
        except ValueError:
            return SanityBand.NORMAL


class AppNegotiation:
    """Process-wide negotiation collaborators, plus a factory for per-mission engines."""

    def __init__(
        self,
        *,
        gateway: Any,
        config: TenantConfigService,
        offers: OfferStore,
        sanity: DomainSanityPort,
        clock: Clock,
        marketplace_url: str,
        new_id: Callable[[], str],
        account: Any | None = None,
        flags: Any | None = None,
    ) -> None:
        self._gateway = gateway
        self._clock = clock
        self._new_id = new_id
        self._market_url = marketplace_url
        self._market: HttpMarketplace | None = None
        self._mock_a: MockAChatTransport | None = None
        self._chats: PerPlatformChatTransport | None = None
        self._sanity = sanity
        self.store = InMemoryNegotiationStore()
        self._send_log = InMemoryAccountSendLog()
        self._seller_log = InMemorySellerSendLog()
        self._seller_guard = InMemorySellerGuard()
        self.params = NegotiationParamsResolver(
            config=config,
            offers=offers,
            accounts=account or _DemoAccountResolver("demo-buyer"),
            flags=flags,
        )

    # -- transport ---------------------------------------------------------
    def _marketplace(self) -> HttpMarketplace:
        if self._market is None:
            self._market = HttpMarketplace(self._market_url)
        return self._market

    def _transport(self) -> ChatTransport:
        """One dispatcher for the process: the client that opens a chat also reads and sends on it."""
        if self._chats is None:
            self._mock_a = MockAChatTransport(self._market_url)
            self._chats = PerPlatformChatTransport(
                default=MarketChatTransport(self._marketplace()),
                overrides={"mock-a": self._mock_a},
            )
        return self._chats

    # -- engines -----------------------------------------------------------
    def engine(self, mission_id: str) -> NegotiationEngine:
        """One engine per mission: the drafter carries the mission for the token budget."""
        return NegotiationEngine(
            transport=self._transport(),
            drafter=LLMDrafter(self._gateway, mission_id=mission_id),
            extractor=LLMExtractor(self._gateway, mission_id=mission_id),
            sanity=OfferSanityRecheck(self._sanity, self.params.offers),
            store=self.store,
            send_log=self._send_log,
            seller_log=self._seller_log,
            seller_guard=self._seller_guard,
            clock=self._clock,
            new_id=self._new_id,
        )

    def port(self, mission_id: str) -> EngineNegotiationPort:
        return EngineNegotiationPort(
            self.engine(mission_id), self.store, self.params
        )

    def control(self) -> NegotiationControlService:
        """The control endpoints need no drafter: takeover/resume/abort only move session state."""
        return NegotiationControlService(self.engine(""))

    async def aclose(self) -> None:
        if self._mock_a is not None:
            await self._mock_a.aclose()
            self._mock_a = None
        self._chats = None
        if self._market is not None:
            await self._market.aclose()
            self._market = None


def build_app_negotiation(
    *,
    settings: Any,
    gateway: Any,
    config: TenantConfigService,
    offers: OfferStore,
    sanity: DomainSanityPort,
    clock: Clock,
    new_id: Callable[[], str],
    marketplace_url: str | None = None,
    account: Any | None = None,
    flags: Any | None = None,
) -> AppNegotiation | None:
    """Build the bridge, or return ``None`` when no marketplace is configured.

    ``None`` is the honest answer for a deployment without the mock marketplace: the mission stops after the
    gate instead of pretending to negotiate.
    """
    url = marketplace_url or getattr(settings, "mock_marketplace_url", "")
    if not url:
        return None
    return AppNegotiation(
        gateway=gateway,
        config=config,
        offers=offers,
        sanity=sanity,
        clock=clock,
        marketplace_url=url,
        new_id=new_id,
        account=account,
        flags=flags,
    )
