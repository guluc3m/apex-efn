"""Negotiation wiring for the app (D5-07 engine, D4-06 path): one shared engine, real ports.

What this module connects:

* **Chat** through the browser worker's internal API (``/internal/v1/chats``), which drives the platform's
  chat (the mock marketplace in dev). Credentials never pass through here: the account id is opaque.
* **Drafting and extraction** through ``LLMGateway`` (role ``negotiator``), scoped to the negotiation's
  mission so the token budget applies. The engine falls back to its deterministic templates when the model
  answers off-plan, so the prices are always the playbook's.
* **Sanity re-check** of every quote with DEV-3's engine against the mission's other offers (criterion 13).
* **Starting**: :class:`NegotiationStarter` opens a negotiation for an offer that cleared trust, sanity and
  finance (the runner calls it only for offers with no gate item, criterion 12). Phase 1 is semi-automatic:
  the opening message waits for a human approval.
* **Following the seller**: :class:`LiveNegotiationControl` reads the seller's reply right after an approved
  send and whenever the negotiation is read while it waits for the seller, so the UI sees the next draft
  without a background poller.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import httpx

from apex.agents.offers import Offer
from apex.agents.sanity_port import DomainSanityPort
from apex.common.clock import Clock
from apex.common.ids import IdGenerator
from apex.contracts.generated.models import Negotiation
from apex.negotiation.api import NegotiationControlService, to_contract
from apex.negotiation.engine import NegotiationEngine
from apex.negotiation.llm import GatewayLike, LLMDrafter, LLMExtractor
from apex.negotiation.models import (
    NegotiationOutcome,
    NegotiationSession,
    Plan,
    Quote,
    SanityBand,
)
from apex.negotiation.node import EngineNegotiationPort, NegotiationResult, ParamsResolver
from apex.negotiation.ports import (
    ChatLine,
    Draft,
    Extraction,
    InMemoryAccountSendLog,
    InMemoryNegotiationStore,
    InMemorySellerGuard,
    InMemorySellerSendLog,
)

logger = logging.getLogger(__name__)

CHATS_PATH = "/internal/v1/chats"

_OPENING: ContextVar[Mapping[str, str] | None] = ContextVar("negotiation_opening", default=None)
"""Who is opening the chat. The engine's ``open`` carries only the platform ids, but the worker's
``OpenChatRequest`` also wants the tenant, mission, trace and negotiation reference. The starter sets them
for the duration of the call; nothing else reads them."""


def negotiation_key(offer_id: str) -> str:
    """Idempotency key of the first negotiation of an offer (``negotiate:<subject>:<attempt>``)."""
    return f"negotiate:{offer_id}:1"


class WorkerChatTransport:
    """``ChatTransport`` over the browser worker's chat API."""

    def __init__(
        self,
        *,
        base_url: str,
        service_token: str,
        client_factory: Callable[[], httpx.AsyncClient],
    ) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {service_token}"}
        self._client_factory = client_factory

    async def open(self, *, platform: str, seller_id: str, product_id: str, account_id: str) -> str:
        ctx = _OPENING.get() or {}
        reference = ctx.get("negotiation_id") or f"{platform}:{seller_id}:{product_id}"
        body = {
            "tenant_id": ctx.get("tenant_id", "unknown"),
            "mission_id": ctx.get("mission_id") or "none",
            "trace_id": ctx.get("trace_id") or "none",
            "negotiation_id": reference,
            "platform": platform,
            "account_id": account_id,
            "platform_seller_id": seller_id,
            "product_id": product_id,
        }
        data = await self._request("POST", CHATS_PATH, json=body, key=f"open:{reference}")
        return str(data["chat_id"])

    async def send(self, chat_id: str, text: str) -> None:
        # ponytail: a random key sends at most once per call; a retried call could send twice.
        await self._request(
            "POST",
            f"{CHATS_PATH}/{chat_id}/messages",
            json={"text": text, "sender": "agent"},
            key=str(uuid.uuid4()),
        )

    async def read(self, chat_id: str, *, after_seq: int) -> Sequence[ChatLine]:
        data = await self._request(
            "GET", f"{CHATS_PATH}/{chat_id}/messages", params={"after_seq": str(after_seq)}
        )
        return [
            ChatLine(seq=int(m["seq"]), role=m["role"], text=str(m["text"]))
            for m in data["messages"]
        ]

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
        key: str | None = None,
    ) -> dict[str, Any]:
        headers = dict(self._headers)
        if key is not None:
            headers["Idempotency-Key"] = key
        async with self._client_factory() as client:
            response = await client.request(
                method, f"{self._base}{path}", json=json, params=params, headers=headers
            )
        if response.status_code >= 400:
            raise RuntimeError(f"browser worker chat {method} {path}: HTTP {response.status_code}")
        body: dict[str, Any] = response.json()
        return body


class MissionDrafter:
    """``LLMDrafter`` scoped to the negotiation's mission, so its tokens count against that mission."""

    def __init__(self, gateway: GatewayLike) -> None:
        self._gateway = gateway

    async def draft(
        self, plan: Plan, session: NegotiationSession, seller_text: str | None
    ) -> Draft:
        drafter = LLMDrafter(self._gateway, mission_id=session.mission_id or session.id)
        return await drafter.draft(plan, session, seller_text)


class MissionExtractor:
    def __init__(self, gateway: GatewayLike) -> None:
        self._gateway = gateway

    async def extract(self, seller_text: str, session: NegotiationSession) -> Extraction:
        extractor = LLMExtractor(self._gateway, mission_id=session.mission_id or session.id)
        return await extractor.extract(seller_text, session)


@dataclass(frozen=True)
class QuoteSanity:
    """``SanityRecheck`` over DEV-3's engine: the quote against the mission's other offers."""

    sanity: DomainSanityPort

    async def check(self, quote: Quote, *, session: NegotiationSession) -> SanityBand:
        outcome = await self.sanity.check(
            {"offer_id": session.offer_id, "mission_id": session.mission_id, "category": None},
            tenant_id=session.tenant_id,
            price_minor=quote.unit_price_minor,
        )
        return SanityBand(outcome.band.value)


class LiveNegotiationControl(NegotiationControlService):
    """The HTTP control service, advancing the chat when the seller may have answered.

    The mock seller answers synchronously, so reading right after an approved send shows its reply and the
    next draft. A read while the negotiation waits for the seller tries once more.
    """

    _WAITING = frozenset({NegotiationOutcome.AWAITING_SELLER, NegotiationOutcome.IN_PROGRESS})

    def __init__(self, engine: NegotiationEngine) -> None:
        super().__init__(engine)
        self._live_engine = engine

    async def get(self, negotiation_id: str, *, tenant_id: str) -> NegotiationSession:
        session = await super().get(negotiation_id, tenant_id=tenant_id)
        if session.status in self._WAITING and session.pending is None and not session.terminal:
            return await self._advance(session, tenant_id)
        return session

    async def approve(
        self, negotiation_id: str, draft_id: str, *, approver: str, tenant_id: str
    ) -> NegotiationSession:
        session = await super().approve(
            negotiation_id, draft_id, approver=approver, tenant_id=tenant_id
        )
        return await self._advance(session, tenant_id)

    async def _advance(self, session: NegotiationSession, tenant_id: str) -> NegotiationSession:
        try:
            return await self._live_engine.advance(session.id, tenant_id=tenant_id)
        except Exception:
            # Reading the seller is best effort: the send already happened, the next read tries again.
            logger.exception("negotiation advance failed", extra={"negotiation_id": session.id})
            return session


@dataclass(frozen=True)
class NegotiationStarter:
    """Opens the negotiation of a cleared offer through the graph's port (idempotent per offer)."""

    port: EngineNegotiationPort
    platforms: frozenset[str]
    """Platforms whose chat the worker can drive. Offers elsewhere stay as deals without a negotiation."""

    async def start(self, offer: Offer) -> NegotiationResult | None:
        if offer.platform_id not in self.platforms:
            return None
        key = negotiation_key(offer.id)
        token = _OPENING.set(
            {
                "tenant_id": offer.tenant_id,
                "mission_id": offer.mission_id,
                "trace_id": f"mission:{offer.mission_id}",
                "negotiation_id": key,
            }
        )
        try:
            return await self.port.negotiate(
                {
                    "offer_id": offer.id,
                    "platform": offer.platform_id,
                    "seller_id": offer.seller_id,
                    "platform_offer_id": offer.product_id,
                    "mission_id": offer.mission_id,
                    "trace_id": f"mission:{offer.mission_id}",
                },
                tenant_id=offer.tenant_id,
                idempotency_key=key,
            )
        finally:
            _OPENING.reset(token)


@dataclass(frozen=True)
class NegotiationServices:
    engine: NegotiationEngine
    store: InMemoryNegotiationStore
    control: LiveNegotiationControl
    starter: NegotiationStarter

    async def contract_for(self, tenant_id: str, offer_id: str) -> Negotiation | None:
        """The contract view of the offer's negotiation, for the dashboard. ``None`` when none was opened."""
        session = await self.store.find_by_key(negotiation_key(offer_id))
        if session is None or session.tenant_id != tenant_id:
            return None
        return to_contract(session)


def build_negotiation(
    *,
    transport: Any,
    gateway: GatewayLike,
    sanity: DomainSanityPort,
    resolve: ParamsResolver,
    clock: Clock,
    platforms: frozenset[str],
) -> NegotiationServices:
    store = InMemoryNegotiationStore()
    engine = NegotiationEngine(
        transport=transport,
        drafter=MissionDrafter(gateway),
        extractor=MissionExtractor(gateway),
        sanity=QuoteSanity(sanity),
        store=store,
        send_log=InMemoryAccountSendLog(),
        seller_log=InMemorySellerSendLog(),
        seller_guard=InMemorySellerGuard(),
        clock=clock,
        new_id=IdGenerator(clock).new_id,
    )
    return NegotiationServices(
        engine=engine,
        store=store,
        control=LiveNegotiationControl(engine),
        starter=NegotiationStarter(EngineNegotiationPort(engine, store, resolve), platforms),
    )


__all__ = [
    "LiveNegotiationControl",
    "NegotiationServices",
    "NegotiationStarter",
    "WorkerChatTransport",
    "build_negotiation",
    "negotiation_key",
]
