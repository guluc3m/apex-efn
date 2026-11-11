"""Recommendation export (#379): CSV, JSON and PDF come from the ranking numbers; 501 until a provider is wired."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.api import missions as missions_api
from apex.common.errors import install_problem_handlers
from apex.contracts.generated.models import Recommendation

TENANT = "tenant-a"


def _rec() -> Recommendation:
    return Recommendation.model_validate(
        {
            "mission_id": "m1",
            "profile_id": "cheapest",
            "ranking": [
                {
                    "rank": 1,
                    "offer_id": "o1",
                    "score": 0.8,
                    "breakdown": [
                        {
                            "criterion": "landed_cost",
                            "weight": 0.5,
                            "normalized_value": 0.9,
                            "contribution": 0.45,
                        }
                    ],
                }
            ],
            "excluded": [{"offer_id": "o2", "reasons": ["budget"]}],
            "savings": {
                "vs_list_price": {"amount_minor": 1200, "currency": "EUR"},
                "vs_market_median": None,
            },
            "config_version": "7",
            "model_version": "mcda-1",
            "generated_at": datetime(2026, 11, 9, tzinfo=UTC),
        }
    )


class _Provider:
    async def recommendation(
        self, *, tenant_id: str, mission_id: str, profile_id: str
    ) -> Recommendation:
        if mission_id != "m1":
            raise LookupError(mission_id)
        return _rec()


@pytest.fixture(autouse=True)
def _tenant_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    install_problem_handlers(application)
    application.include_router(missions_api.router, prefix="/missions")
    return application


def _get(app: FastAPI, mission: str, fmt: str):  # type: ignore[no-untyped-def]
    with TestClient(app) as client:
        return client.get(
            f"/missions/{mission}/recommendation/export?profile=cheapest&format={fmt}",
            headers={"X-Tenant-Id": TENANT},
        )


def test_501_until_a_provider_is_wired(app: FastAPI) -> None:
    assert _get(app, "m1", "csv").status_code == 501


def test_exports_in_three_formats(app: FastAPI) -> None:
    app.dependency_overrides[missions_api.get_recommendation_provider] = lambda: _Provider()
    csv = _get(app, "m1", "csv")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv.headers["content-disposition"]
    assert csv.text.splitlines()[1] == "1,o1,0.8,landed_cost,0.5,0.9,0.45,"
    js = _get(app, "m1", "json")
    assert js.json()["ranking"][0]["offer_id"] == "o1" and js.json()["model_version"] == "mcda-1"
    pdf = _get(app, "m1", "pdf")
    assert pdf.content.startswith(b"%PDF") and b"mcda-1" in pdf.content


def test_unknown_mission_and_format(app: FastAPI) -> None:
    app.dependency_overrides[missions_api.get_recommendation_provider] = lambda: _Provider()
    assert _get(app, "nope", "csv").status_code == 404
    assert _get(app, "m1", "xml").status_code == 422
