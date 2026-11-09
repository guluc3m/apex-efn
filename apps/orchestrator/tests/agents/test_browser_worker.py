"""``HttpBrowserWorker``: the orchestrator's client for the browser worker's internal API (D5-01).

The shapes are the ones in ``contracts/internal/browser-worker.openapi.yaml``. The worker is faked with an
httpx transport, so this proves the client speaks the contract without needing the Node service.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from apex.agents.browser_worker import BrowserWorkerError, HttpBrowserWorker
from apex.agents.sourcing import PlanStep

BASE = "http://worker.test"
TOKEN = "service-token"

RAW_OFFER: dict[str, Any] = {
    "platform": "mock-a",
    "platform_offer_id": "a-gloves-01",
    "product_id": "nitrile-gloves-m-box100",
    "platform_seller_id": "a-solid-veteran",
    "seller_name": "Shenzhen Bright Gloves Co. (mock)",
    "title": "Nitrile Gloves Size M, Box of 100",
    "product_url": None,
    "unit_price": {"amount_minor": 445, "currency": "EUR"},
    "list_price": {"amount_minor": 500, "currency": "EUR"},
    "price_tiers": [],
    "moq": 500,
    "quantity_available": 2000,
    "specifications": {"material": "nitrile"},
    "certifications": ["EN 455"],
    "seller_country": "CN",
    "shipping": None,
    "incoterm": None,
    "lead_time_days": 10,
    "captured_at": "2026-11-09T12:00:00Z",
}


class _Worker:
    """A fake worker: records requests and answers a scripted sequence of job states."""

    def __init__(self, *, states: list[dict[str, Any]] | None = None, accept: int = 202) -> None:
        self.requests: list[httpx.Request] = []
        self.states = states or [
            {"job_id": "j-1", "status": "queued"},
            {"job_id": "j-1", "status": "running"},
            {
                "job_id": "j-1",
                "status": "succeeded",
                "result": {
                    "kind": "search",
                    "offers": [RAW_OFFER],
                    "skipped": [
                        {
                            "platform_offer_id": "x-1",
                            "reason": "unsupported_currency",
                            "currency_raw": "GBP",
                        }
                    ],
                    "truncated": False,
                },
            },
        ]
        self.accept = accept
        self._index = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "POST":
            if self.accept != 202:
                return httpx.Response(
                    self.accept,
                    json={"type": "about:blank", "title": "Bad request", "status": self.accept,
                          "code": "invalid_job", "detail": "payload rejected"},
                )  # fmt: skip
            return httpx.Response(
                202, json={"job_id": "j-1", "status": "queued", "deduplicated": False}
            )
        state = self.states[min(self._index, len(self.states) - 1)]
        self._index += 1
        return httpx.Response(200, json=state)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler), base_url=BASE)


@pytest.fixture
def sleeps() -> list[float]:
    return []


def _worker(worker: _Worker, sleeps: list[float], **kwargs: Any) -> HttpBrowserWorker:
    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return HttpBrowserWorker(
        base_url=BASE,
        service_token=TOKEN,
        client_factory=worker.client,
        sleep=_sleep,
        **kwargs,
    )


def _step() -> PlanStep:
    return PlanStep(platform_id="mock-a", transport="http", query="nitrile gloves")


def _body(worker: _Worker) -> dict[str, Any]:
    return json.loads(worker.requests[0].content)


# ----- the request --------------------------------------------------------------------------------


async def test_the_job_carries_the_contract_envelope(sleeps: list[float]) -> None:
    worker = _Worker()
    await _worker(worker, sleeps).search(
        tenant_id="tenant-a", mission_id="m-1", step=_step(), quantity=500
    )
    body = _body(worker)
    assert body["kind"] == "search"
    assert body["tenant_id"] == "tenant-a"
    assert body["mission_id"] == "m-1"
    assert body["platform"] == "mock-a"
    assert body["query"] == "nitrile gloves"
    assert body["quantity"] == 500
    assert body["trace_id"] == "mission:m-1"
    assert body["max_results"] == 50


def test_the_service_token_and_an_idempotency_key_are_sent(sleeps: list[float]) -> None:
    worker = _Worker()
    import asyncio

    asyncio.run(
        _worker(worker, sleeps).search(
            tenant_id="tenant-a", mission_id="m-1", step=_step(), quantity=500
        )
    )
    headers = worker.requests[0].headers
    assert headers["authorization"] == f"Bearer {TOKEN}"
    assert headers["idempotency-key"] == "m-1:mock-a:nitrile gloves"


# ----- the result ---------------------------------------------------------------------------------


async def test_a_successful_job_is_mapped_to_raw_offers(sleeps: list[float]) -> None:
    worker = _Worker()
    result = await _worker(worker, sleeps).search(
        tenant_id="tenant-a", mission_id="m-1", step=_step(), quantity=500
    )
    assert result.platform_id == "mock-a"
    assert result.truncated is False
    offer = result.offers[0]
    assert offer.platform_id == "mock-a"
    assert offer.platform_offer_id == "a-gloves-01"
    assert offer.seller_id == "a-solid-veteran"
    assert offer.product_id == "nitrile-gloves-m-box100"
    assert offer.unit_price_minor == 445
    assert offer.list_price_minor == 500
    assert offer.currency == "EUR"
    assert offer.moq == 500
    assert offer.quantity_available == 2000
    assert offer.raw_signals["certifications"] == ["EN 455"]
    assert offer.raw_signals["lead_time_days"] == 10


async def test_the_client_does_not_convert_or_score_anything(sleeps: list[float]) -> None:
    """The worker returns raw data; the EUR price is the platform's, not a converted one."""
    worker = _Worker()
    result = await _worker(worker, sleeps).search(
        tenant_id="tenant-a", mission_id="m-1", step=_step(), quantity=500
    )
    offer = result.offers[0]
    assert offer.currency == "EUR"  # straight from the payload
    assert not hasattr(offer, "band")
    assert not hasattr(offer, "score")


async def test_a_missing_quantity_available_falls_back_to_the_moq(sleeps: list[float]) -> None:
    raw = {**RAW_OFFER, "quantity_available": None}
    worker = _Worker(
        states=[{"job_id": "j-1", "status": "succeeded",
                 "result": {"kind": "search", "offers": [raw], "skipped": [], "truncated": True}}]
    )  # fmt: skip
    result = await _worker(worker, sleeps).search(
        tenant_id="tenant-a", mission_id="m-1", step=_step(), quantity=500
    )
    assert result.offers[0].quantity_available == 500
    assert result.truncated is True


async def test_the_client_polls_until_the_job_is_terminal(sleeps: list[float]) -> None:
    worker = _Worker()
    await _worker(worker, sleeps).search(
        tenant_id="tenant-a", mission_id="m-1", step=_step(), quantity=500
    )
    gets = [r for r in worker.requests if r.method == "GET"]
    assert len(gets) == 3  # queued, running, succeeded
    assert sleeps == [0.5, 0.5]  # it waited between polls, and only then


# ----- failures -----------------------------------------------------------------------------------


async def test_a_rejected_job_raises_with_the_contract_code(sleeps: list[float]) -> None:
    worker = _Worker(accept=422)
    with pytest.raises(BrowserWorkerError) as caught:
        await _worker(worker, sleeps).search(
            tenant_id="tenant-a", mission_id="m-1", step=_step(), quantity=500
        )
    assert caught.value.code == "invalid_job"


@pytest.mark.parametrize("status", ["failed", "dead_lettered"])
async def test_a_failed_job_raises_with_its_error_code(status: str, sleeps: list[float]) -> None:
    worker = _Worker(
        states=[
            {"job_id": "j-1", "status": status, "error_code": "captcha", "error_message": "blocked"}
        ]
    )
    with pytest.raises(BrowserWorkerError) as caught:
        await _worker(worker, sleeps).search(
            tenant_id="tenant-a", mission_id="m-1", step=_step(), quantity=500
        )
    assert caught.value.code == "captcha"


async def test_a_job_that_never_finishes_times_out_instead_of_hanging(sleeps: list[float]) -> None:
    worker = _Worker(states=[{"job_id": "j-1", "status": "running"}])
    with pytest.raises(BrowserWorkerError) as caught:
        await _worker(worker, sleeps, max_polls=3).search(
            tenant_id="tenant-a", mission_id="m-1", step=_step(), quantity=500
        )
    assert caught.value.code == "timeout"


async def test_a_result_that_does_not_match_the_contract_fails_loudly(sleeps: list[float]) -> None:
    worker = _Worker(
        states=[
            {"job_id": "j-1", "status": "succeeded", "result": {"kind": "search", "offers": "nope"}}
        ]
    )
    with pytest.raises(BrowserWorkerError) as caught:
        await _worker(worker, sleeps).search(
            tenant_id="tenant-a", mission_id="m-1", step=_step(), quantity=500
        )
    assert caught.value.code == "invalid_result"
