"""The simulation's LLM client: stub locally, real provider when a key is configured.

The point of these tests is the contract between the demo and whatever answers on ``SIM_LLM_URL``: the key is a
bearer header (never in the payload), the stub scenario header only goes to the stub, and `seed` — which real
providers may reject — is only sent in stub mode.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from apex.negotiation.sim import stub_llm
from apex.negotiation.sim.models import ScenarioConfig
from apex.negotiation.sim.stub_llm import OpenAICompatGateway, SimGateway, build_gateway


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


async def _chat(gateway: SimGateway) -> None:
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
        await _chat(gateway)


def _capture_build(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace the real client with a spy so ``build_gateway`` precedence is visible without HTTP."""
    captured: dict[str, Any] = {}

    class Spy:
        def __init__(self, base_url: str, **kwargs: Any) -> None:
            captured["base_url"] = base_url
            captured.update(kwargs)

        async def aclose(self) -> None:
            return

    monkeypatch.setattr(stub_llm, "OpenAICompatGateway", Spy)
    return captured


def test_explicit_key_and_model_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_LLM_API_KEY", "sk-env")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-env")
    monkeypatch.setenv("SIM_LLM_MODEL", "env-model")
    monkeypatch.setenv("SIM_LLM_SCENARIO", "env-scenario")
    captured = _capture_build(monkeypatch)

    build_gateway("https://api.deepseek.com", api_key="sk-explicit", model="explicit-model")

    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["api_key"] == "sk-explicit"
    assert captured["model"] == "explicit-model"
    # A real provider never gets the stub header, even if stub-mode variables are still exported.
    assert captured["scenario"] is None


def test_a_key_from_the_environment_defaults_to_deepseek_and_no_stub_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SIM_LLM_API_KEY", "sk-env")
    monkeypatch.delenv("SIM_LLM_MODEL", raising=False)
    monkeypatch.setenv("SIM_LLM_SCENARIO", "env-scenario")
    captured = _capture_build(monkeypatch)

    build_gateway("https://api.deepseek.com")

    assert captured["api_key"] == "sk-env"
    assert captured["model"] == "deepseek-chat"
    assert captured["scenario"] is None


def test_without_a_key_the_stub_defaults_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SIM_LLM_API_KEY", "DEEPSEEK_API_KEY", "SIM_LLM_MODEL", "SIM_LLM_SCENARIO"):
        monkeypatch.delenv(name, raising=False)
    captured = _capture_build(monkeypatch)

    build_gateway("http://127.0.0.1:8001")

    assert captured["api_key"] is None
    assert captured["model"] == "negotiator"
    assert captured["scenario"] == "sim-negotiation"


async def test_a_gateway_built_with_a_key_sends_no_stub_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen, transport = _capture()
    real_client = stub_llm.OpenAICompatGateway

    def with_transport(base_url: str, **kwargs: Any) -> OpenAICompatGateway:
        return real_client(base_url, transport=transport, **kwargs)

    monkeypatch.setattr(stub_llm, "OpenAICompatGateway", with_transport)
    monkeypatch.setenv("SIM_LLM_SCENARIO", "env-scenario")
    monkeypatch.delenv("SIM_LLM_MODEL", raising=False)

    gateway = build_gateway("https://api.deepseek.com", api_key="sk-explicit")
    await _chat(gateway)

    headers = seen[0].headers
    assert headers["authorization"] == "Bearer sk-explicit"
    assert "x-stub-scenario" not in headers
    payload = json.loads(seen[0].content)
    assert payload["model"] == "deepseek-chat"
    assert "seed" not in payload
    await gateway.aclose()


async def test_the_key_is_hidden_from_reprs_and_serialisation() -> None:
    config = ScenarioConfig(marketplace_url="http://market.test", llm_api_key="sk-secret")
    gateway = OpenAICompatGateway("https://api.deepseek.com", api_key="sk-secret")

    assert "sk-secret" not in repr(config)
    assert "llm_api_key" not in config.model_dump()
    assert "sk-secret" not in repr(gateway)
    await gateway.aclose()
