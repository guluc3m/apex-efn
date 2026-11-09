"""Ports the negotiation engine depends on (D5-07b).

Collaborators owned by other tasks or lanes are reached through these protocols, so the engine is
testable without a browser, an LLM or a database:

- ``ChatTransport``: the seller chat, through the browser worker (D5-01/D5-03) or the mock marketplace.
- ``Drafter`` / ``Extractor``: the LLM (role ``negotiator``, D4-04), see ``apex.negotiation.llm``.
- ``SanityRecheck``: DEV-3's ``sanity.check`` on the negotiated price in EUR (criterion 13).
- ``NegotiationStore`` / ``AccountSendLog``: persistence (D2-05). In-memory versions live here.
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
