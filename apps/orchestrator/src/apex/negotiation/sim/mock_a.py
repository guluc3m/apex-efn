"""``ChatTransport`` over the mock marketplace's mock-a conversations API (D5-05 in mock form).

The negotiation engine is platform-agnostic: it opens a chat, sends text and reads replies. The mock
marketplace publishes that surface twice — mock-c's ``threads`` and mock-a's ``conversations`` — because
criterion 3 wants offers from more than one platform. A mission that discovers an offer on mock-a must haggle
on mock-a, not open a thread on a platform that never listed the item (that used to fail every negotiation
with ``unknown_item``). mock-b's chat is form-driven HTML and stays behind the browser worker (D5-02).

Wire shapes come from ``apps/mock-marketplace/src/platforms/mock-a.ts``:

- ``POST /mock-a/api/conversations`` ``{vendor_id, listing_id}`` -> ``{conversation_id}``
- ``POST /mock-a/api/conversations/{id}/messages`` ``{body}`` -> ``{message}``
- ``GET  /mock-a/api/conversations/{id}/messages?after=`` -> ``{messages}``

Everything is local: no login, no scraping, no network beyond the configured marketplace URL.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from apex.negotiation.ports import ChatLine, ChatTransport
from apex.negotiation.sim.market import MarketplaceResponseError, MarketplaceUnavailable

__all__ = ["MockAChatTransport", "PerPlatformChatTransport"]

_API_SUFFIX = "/mock-a/api"


class MockAChatTransport:
    """One ``httpx`` client per instance. The mock has no login, so the account id only scopes sends."""

    def __init__(self, base_url: str, *, timeout: float = 15.0) -> None:
        root = base_url.rstrip("/")
        for suffix in (_API_SUFFIX, "/mock-c/api"):
            if root.endswith(suffix):
                root = root[: -len(suffix)]
        if not root:
            raise ValueError("marketplace_url must include a host")
        self._client = httpx.AsyncClient(base_url=f"{root}{_API_SUFFIX}", timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def open(self, *, platform: str, seller_id: str, product_id: str, account_id: str) -> str:
        payload = await self._post(
            "/conversations", json={"vendor_id": seller_id, "listing_id": product_id}
        )
        conversation = payload.get("conversation_id")
        if not isinstance(conversation, str) or not conversation:
            raise MarketplaceResponseError("conversation: 'conversation_id' is not a string")
        return conversation

    async def send(self, chat_id: str, text: str) -> None:
        await self._post(f"/conversations/{chat_id}/messages", json={"body": text})

    async def read(self, chat_id: str, *, after_seq: int) -> Sequence[ChatLine]:
        payload = await self._get(
            f"/conversations/{chat_id}/messages", params={"after": str(after_seq)}
        )
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise MarketplaceResponseError("conversation messages: 'messages' is not a list")
        lines: list[ChatLine] = []
        for entry in messages:
            if not isinstance(entry, Mapping):
                raise MarketplaceResponseError("conversation message: expected an object")
            seq, body, author = entry.get("id"), entry.get("body"), entry.get("from")
            if not isinstance(seq, int) or isinstance(seq, bool):
                raise MarketplaceResponseError("conversation message: 'id' is not an integer")
            if not isinstance(body, str):
                raise MarketplaceResponseError("conversation message: 'body' is not a string")
            lines.append(
                ChatLine(seq=seq, role="buyer" if author == "buyer" else "seller", text=body)
            )
        return lines

    async def _get(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise MarketplaceUnavailable(f"GET {path} failed: {exc}") from exc
        return self._decode(response, f"GET {path}")

    async def _post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, json=json)
        except httpx.HTTPError as exc:
            raise MarketplaceUnavailable(f"POST {path} failed: {exc}") from exc
        return self._decode(response, f"POST {path}")

    def _decode(self, response: httpx.Response, what: str) -> dict[str, Any]:
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise MarketplaceResponseError(f"{what}: body is not JSON") from exc
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise MarketplaceResponseError(f"{what}: HTTP {response.status_code}: {payload}")
        if not isinstance(payload, dict):
            raise MarketplaceResponseError(f"{what}: expected an object")
        return payload


class PerPlatformChatTransport:
    """Routes each conversation to the platform that published the offer.

    A platform without an override uses ``default`` (mock-c's threads). A platform with no chat surface at
    all (mock-b, HTML forms) must be given an override before it is enabled for negotiation; otherwise the
    error names the platform instead of failing with a 404 from another platform's API.

    Chat ids are ``chat-<platform>-<n>`` on both surfaces, so send/read route by the id itself. That keeps the
    mapping stateless: a negotiation resumed after a restart still reaches the right marketplace.
    """

    def __init__(self, *, default: ChatTransport, overrides: Mapping[str, ChatTransport]) -> None:
        self._default = default
        self._overrides = dict(overrides)

    async def open(self, *, platform: str, seller_id: str, product_id: str, account_id: str) -> str:
        return await self._overrides.get(platform, self._default).open(
            platform=platform,
            seller_id=seller_id,
            product_id=product_id,
            account_id=account_id,
        )

    async def send(self, chat_id: str, text: str) -> None:
        await self._owner(chat_id).send(chat_id, text)

    async def read(self, chat_id: str, *, after_seq: int) -> Sequence[ChatLine]:
        return await self._owner(chat_id).read(chat_id, after_seq=after_seq)

    def _owner(self, chat_id: str) -> ChatTransport:
        for platform, transport in self._overrides.items():
            if chat_id.startswith(f"chat-{platform}-"):
                return transport
        return self._default
