"""The simulation's LLM client: stub locally, real provider when a key is configured.

The point of these tests is the contract between the demo and whatever answers on ``SIM_LLM_URL``: the key is a
bearer header (never in the payload), the stub scenario header only goes to the stub, and `seed` — which real
providers may reject — is only sent in stub mode.
"""

from __future__ import annotations

import json

import httpx
import pytest

from apex.negotiation.sim.stub_llm import OpenAICompatGateway, build_gateway


def _capture() -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": "whatever",
                "choices": [{"message": {"content": "Understood."}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
        )

    return seen, httpx.MockTransport(handler)


async def _chat(gateway: OpenAICompatGateway) -> None:
    await gateway.chat(
        "negotiator",  # type: ignore[arg-type]
        [{"role": "user", "content": "Propose EUR 4.10"}],
        mission_id="m1",
        tenant_id="t1",
        prompt_version="v1",
        seed=7,
        max_tokens=100,
    )


async def test_stub_mode_sends_its_scenario_and_seed() -> None:
    seen, transport = _capture()
    gateway = OpenAICompatGateway("http://stub.test", model="negotiator", transport=transport)

    await _chat(gateway)

    headers = seen[0].headers
    assert headers["x-stub-scenario"] == "sim-negotiation"
    assert "authorization" not in headers
    payload = json.loads(seen[0].content)
    assert payload["model"] == "negotiator"
    assert payload["seed"] == 7
    await gateway.aclose()


async def test_a_real_provider_gets_the_key_and_no_stub_parameters() -> None:
    seen, transport = _capture()
    gateway = OpenAICompatGateway(
        "https://api.deepseek.com",
        model="deepseek-chat",
        api_key="sk-secret",
        scenario=None,
        transport=transport,
    )

    await _chat(gateway)

    headers = seen[0].headers
    assert headers["authorization"] == "Bearer sk-secret"
    assert "x-stub-scenario" not in headers
    payload = json.loads(seen[0].content)
    assert payload["model"] == "deepseek-chat"
    assert "seed" not in payload  # providers may reject it; the demo does not need it
    # The key never leaks into the payload or into the endpoint id.
    assert "sk-secret" not in seen[0].content.decode()
    await gateway.aclose()


async def test_the_url_is_normalised_for_both_provider_styles() -> None:
    seen, transport = _capture()
    plain = OpenAICompatGateway("https://api.deepseek.com", transport=transport)
    with_v1 = OpenAICompatGateway("https://api.deepseek.com/v1/", transport=transport)

    await _chat(plain)
    await _chat(with_v1)

    assert str(seen[0].url) == "https://api.deepseek.com/v1/chat/completions"
    assert str(seen[1].url) == "https://api.deepseek.com/v1/chat/completions"
    await plain.aclose()
    await with_v1.aclose()


async def test_without_a_url_the_gateway_is_null(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIM_LLM_API_KEY", raising=False)
    gateway = build_gateway(None)
    with pytest.raises(Exception, match="no llm_url"):
        await _chat(gateway)  # type: ignore[arg-type]
