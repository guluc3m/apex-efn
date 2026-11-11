"""``ChatTransport`` over the mock marketplace's negotiation threads (D5-11).

The engine speaks ``open`` / ``send`` / ``read``; mock-c speaks ``POST /threads`` and
``POST/GET /threads/{id}/messages``. This adapter is the only bridge between both vocabularies:

- ``author: "supplier"`` on the wire is the engine's ``"seller"`` role; ``"buyer"`` stays ``"buyer"``.
- ``sent_at`` is epoch milliseconds; the engine's ``ChatLine`` carries no timestamp, so it is dropped.

The account id is opaque on the wire (mock-c has no login); it stays in the engine so distinct buyers use
distinct send-log scopes.
"""

from __future__ import annotations

from collections.abc import Sequence

from apex.negotiation.ports import ChatLine
from apex.negotiation.sim.market import Marketplace

__all__ = ["MarketChatTransport"]


class MarketChatTransport:
    """One transport per simulated buyer; thread ids are cached per platform/product pair."""

    def __init__(self, market: Marketplace, *, run_id: str = "") -> None:
        self._market = market
        self._threads: dict[str, str] = {}
        self._run_id = run_id

    async def open(self, *, platform: str, seller_id: str, product_id: str, account_id: str) -> str:
        key = f"{platform}:{seller_id}:{product_id}:{account_id}"
        thread_id = self._threads.get(key)
        if thread_id is None:
            buyer_id = f"{account_id}:{self._run_id}" if self._run_id else account_id
            thread_id = await self._market.open_thread(product_id, buyer_id=buyer_id)
            self._threads[key] = thread_id
        return thread_id

    async def send(self, chat_id: str, text: str) -> None:
        await self._market.send(chat_id, text)

    async def read(self, chat_id: str, *, after_seq: int) -> Sequence[ChatLine]:
        messages = await self._market.messages(chat_id, after_seq=after_seq)
        return [
            ChatLine(
                seq=message.seq,
                role="seller" if message.author == "supplier" else "buyer",
                text=message.body,
            )
            for message in messages
        ]
