"""HTTP client for the browser worker's internal API (D5-01).

The orchestrator never touches a marketplace: it enqueues a job and reads the result. The wire shapes come
from ``contracts/internal/browser-worker.openapi.yaml`` and are validated here with the generated Pydantic
models, so a change in the contract fails loudly instead of silently producing a wrong offer.

Two rules from that contract are enforced by construction:

* **The worker returns raw data.** No EUR conversion, no bands, no scores: this module maps the raw payload
  into :class:`~apex.agents.scraping.RawOffer` and nothing more. Normalisation and scoring are the
  orchestrator's job (D4-09) and DEV-3's.
* **Credentials never cross this API.** The client sends a service bearer token and opaque ids only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apex.agents.scraping import RawOffer, SkippedListing, WorkerSearchResult
from apex.agents.sourcing import PlanStep

JOBS_PATH = "/internal/v1/jobs"
DEFAULT_MAX_RESULTS = 50
DEFAULT_MAX_POLLS = 60
DEFAULT_POLL_INTERVAL_S = 0.5


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Money(_Model):
    amount_minor: int
    currency: str


class _RawOffer(_Model):
    """One listing as the worker returns it (contract ``RawOffer``)."""

    platform: str
    platform_offer_id: str
    product_id: str
    platform_seller_id: str
    title: str = ""
    unit_price: _Money
    list_price: _Money | None = None
    moq: int = Field(default=1, ge=1)
    quantity_available: int | None = None
    specifications: dict[str, str] = Field(default_factory=dict)
    certifications: list[str] = Field(default_factory=list)
    seller_country: str | None = None
    lead_time_days: int | None = None
    captured_at: str | None = None


class _SkippedListing(_Model):
    platform_offer_id: str
    reason: str
    currency_raw: str | None = None


class _SearchJobResult(_Model):
    kind: str
    offers: list[_RawOffer]
    skipped: list[_SkippedListing] = Field(default_factory=list)
    truncated: bool = False


class _JobError(_Model):
    """Contract ``JobError``: a closed code, a message and whether a retry could help."""

    code: str
    message: str = ""
    retryable: bool = False


class _JobState(_Model):
    """Contract ``JobState``. Only the fields this client acts on are declared; the rest are ignored."""

    job_id: str
    status: str
    result: Mapping[str, Any] | None = None
    error: _JobError | None = None


class _JobAccepted(_Model):
    job_id: str
    status: str
    deduplicated: bool = False


class BrowserWorkerError(Exception):
    """The worker refused the job, failed it, or never finished. ``code`` is the contract's closed code."""

    def __init__(self, code: str, detail: str = "", *, retryable: bool = False) -> None:
        super().__init__(f"browser worker: {code}{': ' + detail if detail else ''}")
        self.code = code
        self.detail = detail
        self.retryable = retryable


class HttpClientFactory(Protocol):
    def __call__(self) -> httpx.AsyncClient: ...


@dataclass(frozen=True)
class HttpBrowserWorker:
    """``BrowserWorkerPort`` over the worker's HTTP API.

    ``sleep`` is injected so tests never wait: the poll loop is the only place this client spends time.
    """

    base_url: str
    service_token: str
    client_factory: HttpClientFactory
    trace_id_for: Callable[[str], str] = lambda mission_id: f"mission:{mission_id}"
    max_results: int = DEFAULT_MAX_RESULTS
    max_polls: int = DEFAULT_MAX_POLLS
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    async def search(
        self, *, tenant_id: str, mission_id: str, step: PlanStep, quantity: int
    ) -> WorkerSearchResult:
        """Enqueue a search job, wait for it and map its raw offers."""
        body = {
            "kind": "search",
            "tenant_id": tenant_id,
            "mission_id": mission_id,
            "trace_id": self.trace_id_for(mission_id),
            "platform": step.platform_id,
            "query": step.query,
            "quantity": quantity,
            "max_results": self.max_results,
        }
        async with self.client_factory() as client:
            accepted = await self._post(
                client, body, idempotency_key=f"{mission_id}:{step.platform_id}:{step.query}"
            )
            state = await self._wait(client, accepted.job_id)
        return self._to_search_result(step.platform_id, state)

    async def _post(
        self, client: httpx.AsyncClient, body: Mapping[str, Any], *, idempotency_key: str
    ) -> _JobAccepted:
        response = await client.post(
            f"{self.base_url}{JOBS_PATH}",
            json=body,
            headers={
                "Authorization": f"Bearer {self.service_token}",
                "Idempotency-Key": idempotency_key,
            },
        )
        if response.status_code == 202:
            try:
                return _JobAccepted.model_validate(response.json())
            except ValidationError as exc:
                raise BrowserWorkerError("invalid_response", str(exc)) from exc
        raise _problem(response)

    async def _wait(self, client: httpx.AsyncClient, job_id: str) -> _JobState:
        """Poll until the job is terminal. Bounded: a job that never finishes is an error, never a hang."""
        for _ in range(self.max_polls):
            response = await client.get(
                f"{self.base_url}{JOBS_PATH}/{job_id}",
                headers={"Authorization": f"Bearer {self.service_token}"},
            )
            if response.status_code != 200:
                raise _problem(response)
            try:
                state = _JobState.model_validate(response.json())
            except ValidationError as exc:
                raise BrowserWorkerError("invalid_response", str(exc)) from exc
            if state.status in {"succeeded", "failed", "dead_lettered"}:
                if state.status != "succeeded":
                    error = state.error
                    raise BrowserWorkerError(
                        error.code if error else state.status,
                        error.message if error else "",
                        retryable=error.retryable if error else False,
                    )
                return state
            await self.sleep(self.poll_interval_s)
        raise BrowserWorkerError(
            "timeout", f"job {job_id} did not finish in {self.max_polls} polls"
        )

    def _to_search_result(self, platform_id: str, state: _JobState) -> WorkerSearchResult:
        if state.result is None:
            raise BrowserWorkerError(
                "missing_result", f"job {state.job_id} succeeded without a result"
            )
        try:
            result = _SearchJobResult.model_validate(state.result)
        except ValidationError as exc:
            raise BrowserWorkerError("invalid_result", str(exc)) from exc
        return WorkerSearchResult(
            platform_id=platform_id,
            offers=[_to_raw_offer(offer) for offer in result.offers],
            skipped=[
                SkippedListing(
                    platform_id=platform_id,
                    platform_offer_id=skipped.platform_offer_id,
                    reason=skipped.reason,
                    currency_raw=skipped.currency_raw,
                )
                for skipped in result.skipped
            ],
            truncated=result.truncated,
        )


def _to_raw_offer(offer: _RawOffer) -> RawOffer:
    """Contract ``RawOffer`` -> the orchestrator's raw shape. No conversion, no judgement."""
    return RawOffer(
        platform_id=offer.platform,
        platform_offer_id=offer.platform_offer_id,
        seller_id=offer.platform_seller_id,
        product_id=offer.product_id,
        title=offer.title,
        unit_price_minor=offer.unit_price.amount_minor,
        list_price_minor=offer.list_price.amount_minor if offer.list_price else None,
        currency=offer.unit_price.currency,
        quantity_available=max(1, offer.quantity_available or offer.moq),
        moq=offer.moq,
        raw_signals={
            "specifications": dict(offer.specifications),
            "certifications": list(offer.certifications),
            "seller_country": offer.seller_country,
            "lead_time_days": offer.lead_time_days,
            "captured_at": offer.captured_at,
        },
    )


def _problem(response: httpx.Response) -> BrowserWorkerError:
    """Map the worker's RFC 9457 problem to an error with its closed code."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    code = str(body.get("code") or body.get("error") or f"http_{response.status_code}")
    detail = str(body.get("detail") or body.get("title") or "")
    return BrowserWorkerError(code, detail)


__all__ = ["BrowserWorkerError", "HttpBrowserWorker"]
