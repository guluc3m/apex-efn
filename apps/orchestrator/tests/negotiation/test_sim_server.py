"""The simulation page: it renders, and it returns the report the pipeline produced."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from apex.negotiation.sim import server
from apex.negotiation.sim.models import (
    BuyerRun,
    ScenarioConfig,
    ScenarioReport,
    Step,
    TranscriptLine,
)


def report() -> ScenarioReport:
    now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    return ScenarioReport(
        started_at=now,
        finished_at=now,
        marketplace_url="http://127.0.0.1:8002",
        llm_url="http://127.0.0.1:8001",
        items=[
            {
                "item_id": "c-gloves-01",
                "title": "Nitrile Examination Gloves M",
                "supplier_id": "c-solid-supplier",
                "supplier_name": "Ningbo Harbour Glove Works",
                "unit_price": {"amount_minor": 432, "currency": "EUR"},
                "moq": 1000,
            }
        ],
        sellers=[
            {
                "supplier_id": "c-solid-supplier",
                "name": "Ningbo Harbour Glove Works",
                "rating_avg": 4.8,
                "orders_total": 14200,
                "persona": "cooperative",
            }
        ],
        buyers=[
            BuyerRun(
                buyer_id="buyer-a",
                name="Ana",
                chosen={
                    "item_id": "c-gloves-01",
                    "supplier_id": "c-solid-supplier",
                    "supplier_name": "Ningbo Harbour Glove Works",
                    "asking_price": {"amount_minor": 432, "currency": "EUR"},
                },
                steps=[Step(kind="search", at=now, detail="3 offers", price=None)],
                transcript=[TranscriptLine(seq=1, role="buyer", text="Hello", at=now)],
                outcome="agreed",
                final_price={"amount_minor": 402, "currency": "EUR"},
                reason=None,
            )
        ],
    )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://sim") as http:
        yield http


async def test_the_page_is_served(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    # The page is in Spanish like the rest of the demo docs; assert on structure, not on a translated string.
    assert "mercado simulado" in response.text
    assert 'id="run-buyers"' in response.text


async def test_the_config_endpoint_describes_the_demo(client: AsyncClient) -> None:
    body = (await client.get("/api/config")).json()
    assert body["marketplace_url"].startswith("http")
    assert len(body["buyers"]) >= 1


async def test_the_scenario_endpoint_returns_the_report(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_run(_scenario: object) -> ScenarioReport:
        return report()

    monkeypatch.setattr(server, "run_scenario", fake_run)

    response = await client.post("/api/scenario", json={"buyer_count": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["buyers"][0]["outcome"] == "agreed"
    assert body["items"][0]["unit_price"] == {"amount_minor": 432, "currency": "EUR"}
    assert body["buyers"][0]["transcript"][0]["text"] == "Hello"


@pytest.fixture
def provider_spy(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace the session collaborators so ``POST /api/session`` can be inspected without HTTP."""
    captured: dict[str, Any] = {}

    class FakeMarketplace:
        def __init__(self, base_url: str, **kwargs: Any) -> None:
            captured["marketplace_url"] = base_url
            captured["marketplace_kwargs"] = kwargs

        async def aclose(self) -> None:
            return

    class FakeSession:
        def __init__(
            self,
            config: ScenarioConfig,
            marketplace: object,
            ctx: object,
            factory: object,
            run_id: str,
            *,
            owns_marketplace: bool,
        ) -> None:
            captured["config"] = config
            captured["owns_marketplace"] = owns_marketplace

        async def start(self) -> None:
            return

        async def close(self) -> None:
            return

        async def view(self) -> dict[str, Any]:
            return {"run_id": "fake", "buyers": []}

    def fake_build_gateway(
        llm_url: str | None, *, api_key: str | None = None, model: str | None = None
    ) -> object:
        captured["gateway"] = (llm_url, api_key, model)
        return object()

    monkeypatch.setattr(server, "_sessions", {})
    monkeypatch.setattr(server, "HttpMarketplace", FakeMarketplace)
    monkeypatch.setattr(server, "SimSession", FakeSession)
    monkeypatch.setattr(server, "build_gateway", fake_build_gateway)
    for name in (
        "SIM_LLM_URL",
        "SIM_LLM_API_KEY",
        "DEEPSEEK_API_KEY",
        "SIM_LLM_MODEL",
        "SIM_MARKETPLACE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    return captured


async def test_a_session_passes_the_provider_config_to_the_gateway_and_the_marketplace(
    client: AsyncClient, provider_spy: dict[str, Any]
) -> None:
    response = await client.post(
        "/api/session",
        json={
            "llm_url": "https://api.deepseek.com",
            "llm_api_key": "sk-session-secret",
            "llm_model": "deepseek-reasoner",
            "buyer_count": 1,
        },
    )

    assert response.status_code == 200
    assert provider_spy["gateway"] == (
        "https://api.deepseek.com",
        "sk-session-secret",
        "deepseek-reasoner",
    )
    assert provider_spy["marketplace_kwargs"] == {
        "llm_url": "https://api.deepseek.com",
        "llm_api_key": "sk-session-secret",
        "llm_model": "deepseek-reasoner",
    }
    # The key is a header for the marketplace, never part of the response the page renders.
    assert "sk-session-secret" not in response.text


async def test_a_session_without_provider_fields_falls_back_to_the_environment(
    client: AsyncClient, provider_spy: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIM_LLM_API_KEY", "sk-env")
    monkeypatch.setenv("SIM_LLM_MODEL", "env-model")

    response = await client.post("/api/session", json={"buyer_count": 1})

    assert response.status_code == 200
    assert provider_spy["gateway"] == (server.DEFAULT_LLM_URL, "sk-env", "env-model")
    assert provider_spy["marketplace_kwargs"] == {
        "llm_url": server.DEFAULT_LLM_URL,
        "llm_api_key": "sk-env",
        "llm_model": "env-model",
    }
