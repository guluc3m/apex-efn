"""The app's negotiation wiring: start a cleared offer, approve, follow the seller, read it on the dashboard."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from apex.agents.negotiation_params import DevPlatformAccountResolver
from apex.agents.negotiation_wiring import (
    WorkerChatTransport,
    build_negotiation,
    negotiation_key,
)
from apex.agents.offers import Offer
from apex.agents.ports import PriceBand, SanityOutcome
from apex.common.clock import FixedClock
from apex.negotiation.models import NegotiationOutcome, NegotiationParams
from apex.negotiation.node import OfferInput

from ..negotiation.fakes import NOW, ScriptedChat, cooperative_seller, params

TENANT = "tenant-a"


class _Gateway:
    """The model is down: the engine must fall back to its deterministic templates and extraction."""

    async def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("llm down")

    async def chat_structured(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("llm down")


class _NormalSanity:
    async def check(self, offer: Any, *, tenant_id: str, price_minor: int | None) -> SanityOutcome:
        return SanityOutcome(band=PriceBand.NORMAL, config_version="v1")


async def _resolve(offer: OfferInput, tenant_id: str) -> tuple[NegotiationParams, str, str]:
    return params(), "v1", "dev-account:mock-a"


def _offer(platform: str = "mock-a") -> Offer:
    return Offer(
        id=f"{platform}:a-1",
        tenant_id=TENANT,
        mission_id="m-1",
        platform_id=platform,
        seller_id="s-1",
        product_id="a-1",
        unit_price_eur_minor=465,
        currency="EUR",
        quantity=5000,
        collected_at=NOW,
    )


def _services(chat: ScriptedChat) -> Any:
    return build_negotiation(
        transport=chat,
        gateway=_Gateway(),
        sanity=_NormalSanity(),  # type: ignore[arg-type]
        resolve=_resolve,
        clock=FixedClock(NOW),
        platforms=frozenset({"mock-a"}),
    )


async def test_a_cleared_offer_opens_a_negotiation_that_waits_for_approval() -> None:
    chat = ScriptedChat(cooperative_seller())
    services = _services(chat)
    result = await services.starter.start(_offer())
    assert result is not None
    assert result.outcome is NegotiationOutcome.AWAITING_HUMAN_APPROVAL  # Phase 1: semi-automatic
    assert chat.opened[0]["product_id"] == "a-1" and chat.sent == []  # nothing sent before approval
    view = await services.contract_for(TENANT, _offer().id)
    assert view is not None and view.pending_draft is not None
    assert view.offer_id == _offer().id and view.mission_id == "m-1"


async def test_approving_sends_and_reads_the_sellers_reply_into_the_next_draft() -> None:
    chat = ScriptedChat(cooperative_seller())
    services = _services(chat)
    result = await services.starter.start(_offer())
    assert result is not None
    first = await services.control.get(result.negotiation_id, tenant_id=TENANT)
    assert first.pending is not None
    after = await services.control.approve(
        result.negotiation_id, first.pending.id, approver="u-1", tenant_id=TENANT
    )
    assert len(chat.sent) == 1  # the approved opening
    assert any(m.role == "seller" for m in after.transcript)  # the reply was read right away
    assert after.pending is not None and after.pending.id != first.pending.id  # next draft waits


async def test_starting_twice_is_idempotent_per_offer() -> None:
    chat = ScriptedChat(cooperative_seller())
    services = _services(chat)
    first = await services.starter.start(_offer())
    second = await services.starter.start(_offer())
    assert first is not None and second is not None
    assert first.negotiation_id == second.negotiation_id
    assert len(chat.opened) == 1


async def test_a_platform_without_chat_is_not_negotiated() -> None:
    services = _services(ScriptedChat(cooperative_seller()))
    assert await services.starter.start(_offer("mock-b")) is None
    assert await services.contract_for(TENANT, _offer("mock-b").id) is None


async def test_another_tenant_never_sees_the_negotiation() -> None:
    services = _services(ScriptedChat(cooperative_seller()))
    await services.starter.start(_offer())
    assert await services.contract_for("tenant-b", _offer().id) is None
    assert await services.store.find_by_key(negotiation_key(_offer().id)) is not None


# ----- the browser worker chat transport ------------------------------------------------------------


async def test_the_worker_transport_speaks_the_internal_chat_api() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST" and request.url.path == "/internal/v1/chats":
            return httpx.Response(201, json={"chat_id": "c-1"})
        if request.method == "POST":
            return httpx.Response(201, json={"seq": 1})
        return httpx.Response(
            200,
            json={
                "chat_id": "c-1",
                "last_seq": 2,
                "messages": [
                    {"seq": 1, "role": "buyer", "text": "hi", "at": "x", "sent_by": "agent"},
                    {"seq": 2, "role": "seller", "text": "EUR 4.40", "at": "x", "sent_by": None},
                ],
            },
        )

    transport = WorkerChatTransport(
        base_url="http://worker.test",
        service_token="tok",
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    chat_id = await transport.open(
        platform="mock-a", seller_id="s-1", product_id="a-1", account_id="dev-account:mock-a"
    )
    await transport.send(chat_id, "hello")
    lines = await transport.read(chat_id, after_seq=0)
    assert chat_id == "c-1"
    assert [line.role for line in lines] == ["buyer", "seller"]
    opened = json.loads(calls[0].content)
    assert opened["platform_seller_id"] == "s-1" and opened["product_id"] == "a-1"
    assert json.loads(calls[1].content) == {"text": "hello", "sender": "agent"}
    assert all(c.headers["Authorization"] == "Bearer tok" for c in calls)
    assert "Idempotency-Key" in calls[0].headers and "Idempotency-Key" in calls[1].headers
    assert calls[2].url.params["after_seq"] == "0"


async def test_a_worker_error_is_loud() -> None:
    transport = WorkerChatTransport(
        base_url="http://worker.test",
        service_token="tok",
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(422, json={}))
        ),
    )
    with pytest.raises(RuntimeError, match="422"):
        await transport.open(platform="mock-b", seller_id="s", product_id="p", account_id="a")


# ----- accounts -------------------------------------------------------------------------------------


async def test_dev_platforms_get_an_opaque_account_and_others_go_to_the_connected_accounts() -> (
    None
):
    class _Db:
        async def account_for(self, *, tenant_id: str, platform: str) -> str:
            return f"db:{platform}"

    resolver = DevPlatformAccountResolver(frozenset({"mock-a"}), _Db())
    assert await resolver.account_for(tenant_id=TENANT, platform="mock-a") == "dev-account:mock-a"
    assert await resolver.account_for(tenant_id=TENANT, platform="alibaba") == "db:alibaba"
