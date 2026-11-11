"""``HttpMarketplace`` forwards the session's provider configuration to the mock marketplace.

The marketplace rephrases the scripted seller replies with the same OpenAI-compatible endpoint, so every
request carries the per-session URL, key and model. The key is only ever a header: it must not show up in
a URL, a body or a repr.
"""

from __future__ import annotations

import httpx

from apex.negotiation.sim.market import HttpMarketplace


def _capture() -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"items": []})

    return seen, httpx.MockTransport(handler)


async def test_every_request_carries_the_provider_headers() -> None:
    seen, transport = _capture()
    market = HttpMarketplace(
        "http://market.test",
        llm_url="https://api.deepseek.com",
        llm_api_key="sk-session-secret",
        llm_model="deepseek-chat",
        transport=transport,
    )

    await market.health()
    await market.search("nitrile gloves")

    assert len(seen) == 2
    for request in seen:
        assert request.headers["x-sim-llm-url"] == "https://api.deepseek.com"
        assert request.headers["x-sim-llm-key"] == "sk-session-secret"
        assert request.headers["x-sim-llm-model"] == "deepseek-chat"
        assert "sk-session-secret" not in str(request.url)
    assert "sk-session-secret" not in repr(market)
    await market.aclose()


async def test_empty_provider_values_omit_the_headers() -> None:
    seen, transport = _capture()
    market = HttpMarketplace(
        "http://market.test",
        llm_url="",
        llm_api_key="",
        llm_model=None,
        transport=transport,
    )

    await market.health()

    headers = seen[0].headers
    assert "x-sim-llm-url" not in headers
    assert "x-sim-llm-key" not in headers
    assert "x-sim-llm-model" not in headers
    await market.aclose()
