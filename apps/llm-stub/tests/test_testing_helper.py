"""The public llm_stub.testing API used by D4-04 (orchestrator) tests."""

from __future__ import annotations

from pathlib import Path

import httpx
from helpers import chat_body

from llm_stub.testing import StubClient, mount_stub


async def test_mount_stub_returns_async_client(scenarios_dir: Path) -> None:
    client = mount_stub(scenarios_dir)
    try:
        assert isinstance(client, httpx.AsyncClient)
        r = await client.get("/health")
        assert r.status_code == 200
    finally:
        await client.aclose()


async def test_fixture_exposes_client_and_base_url(llm_stub: StubClient) -> None:
    assert llm_stub.base_url == "http://llm-stub"
    assert isinstance(llm_stub.http, httpx.AsyncClient)
    r = await llm_stub.post("/v1/chat/completions", json=chat_body())
    assert r.status_code == 200


async def test_fixture_counters_are_fresh_per_test(llm_stub: StubClient) -> None:
    # The flaky scenario has fail_times=2; a fresh app per test means the first call fails.
    r = await llm_stub.post(
        "/v1/chat/completions", json=chat_body(), headers={"X-Stub-Scenario": "flaky-5xx"}
    )
    assert r.status_code == 503
