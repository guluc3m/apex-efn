"""HTTP client for the ``mock-c`` marketplace of ``apps/mock-marketplace`` (D5-11).

``mock-c`` is the API-first fake platform: integer cents, seller metrics in basis points and a
threads/messages resource for the negotiation. The wire shapes are the ones served by
``apps/mock-marketplace/src/platforms/mock-c.ts`` (and mirrored in the browser worker's
``adapters/mock-c/schemas.ts``):

- ``GET  /mock-c/api/search?q=&limit=`` -> ``{query, count, items: [summary]}``
- ``GET  /mock-c/api/items/{id}`` -> item detail (summary + tiers + shipping)
- ``GET  /mock-c/api/suppliers/{id}/metrics`` -> raw seller signals
- ``POST /mock-c/api/threads`` ``{item_id}`` -> ``{thread_id, supplier_id, item_id}``
- ``POST /mock-c/api/threads/{id}/messages`` ``{body}`` -> ``{sent, received}``
- ``GET  /mock-c/api/threads/{id}/messages?after_seq=`` -> ``{thread_id, messages}``

Everything is local: no login, no scraping, no network beyond the configured URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import httpx

from apex.negotiation.sim.models import CURRENCIES

__all__ = [
    "HttpMarketplace",
    "MarketItem",
    "Marketplace",
    "MarketplaceError",
    "MarketplaceResponseError",
    "MarketplaceUnavailable",
    "SupplierMetrics",
    "ThreadMessage",
]

_API_SUFFIX = "/mock-c/api"


class MarketplaceError(RuntimeError):
    """Base class for marketplace failures."""


class MarketplaceUnavailable(MarketplaceError):
    """The marketplace cannot be reached; the CLI turns this into exit code 1."""


class MarketplaceResponseError(MarketplaceError):
    """The marketplace answered with an error or a body this client cannot read."""


@dataclass(frozen=True, slots=True)
class MarketItem:
    """An offer as the search endpoint lists it."""

    item_id: str
    title: str
    supplier_id: str
    supplier_name: str | None
    unit_price_minor: int
    currency: str
    min_order: int


@dataclass(frozen=True, slots=True)
class SupplierMetrics:
    supplier_id: str
    name: str
    rating_avg: float | None
    orders_total: int | None
    persona: str | None = None
    """The mock's persona label. The public wire does not expose it; only in-process fakes do."""


@dataclass(frozen=True, slots=True)
class ThreadMessage:
    seq: int
    author: Literal["buyer", "supplier"]
    body: str
    sent_at: datetime


class Marketplace(Protocol):
    """The slice of ``mock-c`` the simulation needs. Fakes in tests implement the same protocol."""

    async def health(self) -> None: ...

    async def search(self, query: str, *, limit: int = 20) -> list[MarketItem]: ...

    async def item(self, item_id: str) -> MarketItem: ...

    async def metrics(self, supplier_id: str) -> SupplierMetrics: ...

    async def open_thread(self, item_id: str, *, buyer_id: str = "") -> str: ...

    async def send(self, thread_id: str, body: str) -> None: ...

    async def messages(self, thread_id: str, *, after_seq: int = 0) -> list[ThreadMessage]: ...

    async def aclose(self) -> None: ...


def _as_dict(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MarketplaceResponseError(f"{what}: expected an object")
    return value


def _as_int(value: Any, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise MarketplaceResponseError(f"{what}: expected an integer")
    return value


def _as_str(value: Any, what: str) -> str:
    if not isinstance(value, str):
        raise MarketplaceResponseError(f"{what}: expected a string")
    return value


def _wire_money(payload: Any, what: str) -> tuple[int, str]:
    body = _as_dict(payload, what)
    cents = _as_int(body.get("cents"), f"{what}.cents")
    currency = _as_str(body.get("currency"), f"{what}.currency").upper()
    if currency not in CURRENCIES:
        raise MarketplaceResponseError(f"{what}: unsupported currency {currency!r}")
    return cents, currency


def _wire_item(payload: Any) -> MarketItem:
    body = _as_dict(payload, "item")
    minor, currency = _wire_money(body.get("unit_price"), "item.unit_price")
    supplier_name = body.get("supplier_name")
    return MarketItem(
        item_id=_as_str(body.get("item_id"), "item.item_id"),
        title=_as_str(body.get("title"), "item.title"),
        supplier_id=_as_str(body.get("supplier_id"), "item.supplier_id"),
        supplier_name=supplier_name if isinstance(supplier_name, str) else None,
        unit_price_minor=minor,
        currency=currency,
        min_order=_as_int(body.get("min_order"), "item.min_order"),
    )


def _wire_message(payload: Any) -> ThreadMessage:
    body = _as_dict(payload, "message")
    author = _as_str(body.get("author"), "message.author")
    if author not in ("buyer", "supplier"):
        raise MarketplaceResponseError(f"message.author: unknown value {author!r}")
    return ThreadMessage(
        seq=_as_int(body.get("seq"), "message.seq"),
        author=author,  # type: ignore[arg-type]
        body=_as_str(body.get("body"), "message.body"),
        sent_at=datetime.fromtimestamp(
            _as_int(body.get("sent_at"), "message.sent_at") / 1000, tz=UTC
        ),
    )


class HttpMarketplace:
    """``httpx`` client over the mock marketplace. One instance per simulation run."""

    def __init__(self, base_url: str, *, timeout: float = 15.0) -> None:
        root = base_url.rstrip("/")
        if root.endswith(_API_SUFFIX):
            root = root[: -len(_API_SUFFIX)]
        if not root:
            raise ValueError("marketplace_url must include a host")
        self._root = root
        self._api = f"{root}{_API_SUFFIX}"
        self._client = httpx.AsyncClient(base_url=self._api, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> None:
        try:
            response = await self._client.get(f"{self._root}/healthz")
        except httpx.HTTPError as exc:
            raise MarketplaceUnavailable(f"cannot reach the marketplace: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise MarketplaceUnavailable(
                f"marketplace health check returned {response.status_code}"
            )

    async def search(self, query: str, *, limit: int = 20) -> list[MarketItem]:
        payload = await self._get("/search", params={"q": query, "limit": str(limit)})
        items = payload.get("items")
        if not isinstance(items, list):
            raise MarketplaceResponseError("search: 'items' is not a list")
        return [_wire_item(entry) for entry in items]

    async def item(self, item_id: str) -> MarketItem:
        return _wire_item(await self._get(f"/items/{item_id}"))

    async def metrics(self, supplier_id: str) -> SupplierMetrics:
        payload = await self._get(f"/suppliers/{supplier_id}/metrics")
        orders = payload.get("orders")
        reviews = payload.get("reviews")
        rating = _as_dict(reviews, "metrics.reviews").get("avg") if reviews is not None else None
        total = _as_dict(orders, "metrics.orders").get("total") if orders is not None else None
        name = _as_str(payload.get("name", supplier_id), "metrics.name")
        return SupplierMetrics(
            supplier_id=_as_str(payload.get("supplier_id"), "metrics.supplier_id"),
            name=name,
            rating_avg=float(rating) if isinstance(rating, (int, float)) else None,
            orders_total=total if isinstance(total, int) and not isinstance(total, bool) else None,
        )

    async def open_thread(self, item_id: str, *, buyer_id: str = "") -> str:
        body: dict[str, Any] = {"item_id": item_id}
        if buyer_id:
            body["buyer_id"] = buyer_id
        payload = await self._post("/threads", json=body)
        return _as_str(payload.get("thread_id"), "thread.thread_id")

    async def send(self, thread_id: str, body: str) -> None:
        await self._post(f"/threads/{thread_id}/messages", json={"body": body})

    async def messages(self, thread_id: str, *, after_seq: int = 0) -> list[ThreadMessage]:
        payload = await self._get(
            f"/threads/{thread_id}/messages", params={"after_seq": str(after_seq)}
        )
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise MarketplaceResponseError("thread messages: 'messages' is not a list")
        return [_wire_message(entry) for entry in messages]

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
        return _as_dict(payload, what)
