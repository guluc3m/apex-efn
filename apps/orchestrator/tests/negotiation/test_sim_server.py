"""The simulation page: it renders, and it returns the report the pipeline produced."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from apex.negotiation.sim import server
from apex.negotiation.sim.models import BuyerRun, ScenarioReport, Step, TranscriptLine


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
    assert "simulated marketplace" in response.text
    assert "AI buyers" in response.text


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
