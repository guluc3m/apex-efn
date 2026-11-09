"""Ports the negotiation engine depends on (D5-07b).

Collaborators owned by other tasks or lanes are reached through these protocols, so the engine is
testable without a browser, an LLM or a database:

- ``ChatTransport``: the seller chat, through the browser worker (D5-01/D5-03) or the mock marketplace.
- ``Drafter`` / ``Extractor``: the LLM (role ``negotiator``, D4-04), see ``apex.negotiation.llm``.
- ``SanityRecheck``: DEV-3's ``sanity.check`` on the negotiated price in EUR (criterion 13).
- ``NegotiationStore`` / ``AccountSendLog`` / ``SellerSendLog``: persistence (D2-05). In-memory versions
  live here.
- ``SellerGuard``: one active negotiation per seller across missions (D5-08 anti-abuse).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from apex.negotiation.models import NegotiationSession, Plan, Quote, SanityBand


@dataclass(frozen=True, slots=True)
class ChatLine:
    seq: int
    role: Literal["buyer", "seller"]
    text: str


class ChatTransport(Protocol):
    async def open(
        self, *, platform: str, seller_id: str, product_id: str, account_id: str
    ) -> str: ...

    async def send(self, chat_id: str, text: str) -> None: ...

    async def read(self, chat_id: str, *, after_seq: int) -> Sequence[ChatLine]: ...


@dataclass(frozen=True, slots=True)
class Draft:
    text: str
    tokens: int


class Drafter(Protocol):
    async def draft(
        self, plan: Plan, session: NegotiationSession, seller_text: str | None
    ) -> Draft: ...


@dataclass(frozen=True, slots=True)
class Extraction:
    unit_price_minor: int | None
    currency: str | None
    tokens: int


class Extractor(Protocol):
    async def extract(self, seller_text: str, session: NegotiationSession) -> Extraction: ...


class SanityRecheck(Protocol):
    async def check(self, quote: Quote, *, session: NegotiationSession) -> SanityBand: ...


class NegotiationStore(Protocol):
    async def get(self, negotiation_id: str) -> NegotiationSession | None: ...

    async def find_by_key(self, idempotency_key: str) -> NegotiationSession | None: ...

    async def save(
        self, session: NegotiationSession, *, idempotency_key: str | None = None
    ) -> None: ...


class AccountSendLog(Protocol):
    async def sends(self, account_id: str) -> Sequence[datetime]: ...

    async def record(self, account_id: str, at: datetime) -> None: ...


class SellerGuard(Protocol):
    """One active negotiation per seller, across missions (D5-08 anti-abuse).

    ``claim`` is the admission test: it returns ``False`` when another non-terminal negotiation of the same
    tenant is already talking to that seller on that platform, and the engine then refuses to open a chat.
    ``claim`` is idempotent for the negotiation that already holds the seller, so a resumed start keeps
    working. The holder must ``release`` when it reaches a terminal outcome.
    """

    async def claim(
        self, *, tenant_id: str, platform: str, seller_id: str, negotiation_id: str
    ) -> bool: ...

    async def release(
        self, *, tenant_id: str, platform: str, seller_id: str, negotiation_id: str
    ) -> None: ...

    async def holder(self, *, tenant_id: str, platform: str, seller_id: str) -> str | None: ...


class SellerSendLog(Protocol):
    """Agent messages already sent to one seller account, across missions (D5-08 rate limit)."""

    async def sends(
        self, *, tenant_id: str, platform: str, seller_id: str
    ) -> Sequence[datetime]: ...

    async def record(
        self, *, tenant_id: str, platform: str, seller_id: str, at: datetime
    ) -> None: ...


class InMemoryNegotiationStore:
    def __init__(self) -> None:
        self._items: dict[str, NegotiationSession] = {}
        self._keys: dict[str, str] = {}

    async def get(self, negotiation_id: str) -> NegotiationSession | None:
        item = self._items.get(negotiation_id)
        return item.model_copy(deep=True) if item else None

    async def find_by_key(self, idempotency_key: str) -> NegotiationSession | None:
        nid = self._keys.get(idempotency_key)
        return await self.get(nid) if nid else None

    async def save(
        self, session: NegotiationSession, *, idempotency_key: str | None = None
    ) -> None:
        self._items[session.id] = session.model_copy(deep=True)
        if idempotency_key is not None:
            self._keys[idempotency_key] = session.id


class InMemoryAccountSendLog:
    def __init__(self) -> None:
        self._sends: dict[str, list[datetime]] = defaultdict(list)

    async def sends(self, account_id: str) -> Sequence[datetime]:
        return tuple(self._sends[account_id])

    async def record(self, account_id: str, at: datetime) -> None:
        self._sends[account_id].append(at)


class InMemorySellerGuard:
    """Process-local seller lease. Production needs Redis or a DB constraint (D2-05, multi-worker)."""

    def __init__(self) -> None:
        self._holders: dict[tuple[str, str, str], str] = {}

    async def claim(
        self, *, tenant_id: str, platform: str, seller_id: str, negotiation_id: str
    ) -> bool:
        key = (tenant_id, platform, seller_id)
        holder = self._holders.get(key)
        if holder is None or holder == negotiation_id:
            self._holders[key] = negotiation_id
            return True
        return False

    async def release(
        self, *, tenant_id: str, platform: str, seller_id: str, negotiation_id: str
    ) -> None:
        key = (tenant_id, platform, seller_id)
        if self._holders.get(key) == negotiation_id:
            del self._holders[key]

    async def holder(self, *, tenant_id: str, platform: str, seller_id: str) -> str | None:
        return self._holders.get((tenant_id, platform, seller_id))


class InMemorySellerSendLog:
    def __init__(self) -> None:
        self._sends: dict[tuple[str, str, str], list[datetime]] = defaultdict(list)

    async def sends(self, *, tenant_id: str, platform: str, seller_id: str) -> Sequence[datetime]:
        return tuple(self._sends[(tenant_id, platform, seller_id)])

    async def record(self, *, tenant_id: str, platform: str, seller_id: str, at: datetime) -> None:
        self._sends[(tenant_id, platform, seller_id)].append(at)
