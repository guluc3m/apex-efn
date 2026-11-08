"""Gateway tests against the D4-02 LLM stub (``llm_stub.testing``).

Skipped automatically when ``llm_stub`` is not importable (it becomes importable once D4-02 is merged and the
uv path source resolves). The local fakes in ``fakes.py`` cover the same behaviour without the stub.

Scenario selection: the stub picks a scenario per request from the ``X-Stub-Scenario`` header. The gateway's
transport owns the request, so the header is injected through a scenario-scoped httpx client that forwards
to the stub's ASGI-mounted client.
"""

from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

if importlib.util.find_spec("llm_stub") is None:  # pragma: no cover - depends on D4-02 merge
    pytest.skip("llm_stub not importable (D4-02 not merged yet)", allow_module_level=True)

pytest_plugins = ["llm_stub.testing"]

from apex.common.clock import FixedClock  # noqa: E402
from apex.llm.accounting import InMemorySink  # noqa: E402
from apex.llm.budget import InMemoryBudgetStore, TokenBudget  # noqa: E402
from apex.llm.config import CapabilityProfile, LLMRole  # noqa: E402
from apex.llm.gateway import LLMGateway  # noqa: E402
from apex.llm.structured import LadderStep, StructuredOutputError  # noqa: E402

from .fakes import endpoint_cfg, provider, roles_config, secrets  # noqa: E402

T0 = datetime(2026, 1, 1, tzinfo=UTC)
MESSAGES = [{"role": "user", "content": "extract the invoice"}]


class Invoice(BaseModel):
    vendor: str
    total_minor: int


def _scoped(client: httpx.AsyncClient, scenario: str) -> httpx.AsyncClient:
    """Return an AsyncClient whose requests all carry ``X-Stub-Scenario`` and reach the stub transport."""

    class _ScenarioTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            request.headers["X-Stub-Scenario"] = scenario
            return await client._transport.handle_async_request(request)  # type: ignore[attr-defined]

    return httpx.AsyncClient(transport=_ScenarioTransport(), base_url=str(client.base_url))


def _gateway(
    stub: Any,
    caps: CapabilityProfile,
    scenario: str,
) -> tuple[LLMGateway, InMemorySink]:
    primary = endpoint_cfg(base_url="http://llm-stub", caps=caps, model="stub-model")
    sink = InMemorySink()
    gw = LLMGateway(
        config_provider=provider(roles_config(primary)),
        secrets=secrets(),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=1_000_000),
        sink=sink,
        clock=FixedClock(T0),
        http_client_factory=lambda cfg: _scoped(stub.http, scenario),
    )
    return gw, sink


async def test_no_response_format_sent_without_capability(llm_stub: Any) -> None:
    gw, _ = _gateway(llm_stub, CapabilityProfile(), "default")
    await gw.chat_structured(
        LLMRole.EXTRACTOR, MESSAGES, Invoice, mission_id="m", tenant_id="t", prompt_version="v"
    )
    for call in await llm_stub.calls():
        assert "response_format" not in call["body"]


async def test_no_response_format_sent_to_no_json_schema_scenario(llm_stub: Any) -> None:
    gw, _ = _gateway(llm_stub, CapabilityProfile(), "no-json-schema")
    await gw.chat_structured(
        LLMRole.EXTRACTOR, MESSAGES, Invoice, mission_id="m", tenant_id="t", prompt_version="v"
    )
    for call in await llm_stub.calls():
        assert "response_format" not in call["body"] or (
            call["body"]["response_format"].get("type") != "json_schema"
        )


async def test_full_capability_uses_json_schema_step(llm_stub: Any) -> None:
    caps = CapabilityProfile(supports_json_schema=True, supports_json_object=True)
    gw, sink = _gateway(llm_stub, caps, "full-capability")
    await gw.chat_structured(
        LLMRole.EXTRACTOR, MESSAGES, Invoice, mission_id="m", tenant_id="t", prompt_version="v"
    )
    assert sink.events[-1].ladder_step == LadderStep.JSON_SCHEMA.value


async def test_malformed_then_valid_repairs_within_bound(llm_stub: Any) -> None:
    gw, sink = _gateway(llm_stub, CapabilityProfile(), "malformed-then-valid")
    await gw.chat_structured(
        LLMRole.EXTRACTOR, MESSAGES, Invoice, mission_id="m", tenant_id="t", prompt_version="v"
    )
    assert 1 <= sink.events[-1].repair_attempts <= 2


async def test_always_malformed_fails_loudly_after_two_repairs(llm_stub: Any) -> None:
    gw, _ = _gateway(llm_stub, CapabilityProfile(), "always-malformed")
    with pytest.raises(StructuredOutputError):
        await gw.chat_structured(
            LLMRole.EXTRACTOR, MESSAGES, Invoice, mission_id="m", tenant_id="t", prompt_version="v"
        )
    assert len(await llm_stub.calls()) == 3  # 1 initial + exactly 2 repairs


async def test_timeout_scenario_is_bounded_by_caller_deadline(llm_stub: Any) -> None:
    gw, _ = _gateway(llm_stub, CapabilityProfile(), "timeout")
    # ASGITransport does not enforce httpx timeouts; the caller deadline is emulated explicitly.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            gw.chat(LLMRole.EXTRACTOR, MESSAGES, mission_id="m", tenant_id="t", prompt_version="v"),
            timeout=0.2,
        )
