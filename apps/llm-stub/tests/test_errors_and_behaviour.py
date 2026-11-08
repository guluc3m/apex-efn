"""5xx/429 with Retry-After, fail-N-times counters, latency, timeouts, usage override, error kinds."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from helpers import chat_body, mount_stub

CHAT = "/v1/chat/completions"


async def test_flaky_5xx_fails_twice_then_succeeds(llm_stub: httpx.AsyncClient) -> None:
    hdr = {"X-Stub-Scenario": "flaky-5xx"}
    r1 = await llm_stub.post(CHAT, json=chat_body(), headers=hdr)
    r2 = await llm_stub.post(CHAT, json=chat_body(), headers=hdr)
    r3 = await llm_stub.post(CHAT, json=chat_body(), headers=hdr)
    assert r1.status_code == 503
    assert r2.status_code == 503
    assert r3.status_code == 200
    assert r1.json()["error"]["type"] == "server_error"


async def test_fresh_app_restores_fail_counter(scenarios_dir) -> None:  # type: ignore[no-untyped-def]
    hdr = {"X-Stub-Scenario": "flaky-5xx"}
    first = mount_stub(scenarios_dir)
    try:
        await first.post(CHAT, json=chat_body(), headers=hdr)
        await first.post(CHAT, json=chat_body(), headers=hdr)
        assert (await first.post(CHAT, json=chat_body(), headers=hdr)).status_code == 200
    finally:
        await first.aclose()
    fresh = mount_stub(scenarios_dir)
    try:
        assert (await fresh.post(CHAT, json=chat_body(), headers=hdr)).status_code == 503
    finally:
        await fresh.aclose()


async def test_fresh_app_restores_sequence(scenarios_dir) -> None:  # type: ignore[no-untyped-def]
    hdr = {"X-Stub-Scenario": "malformed-then-valid"}
    first = mount_stub(scenarios_dir)
    try:
        await first.post(CHAT, json=chat_body(), headers=hdr)
        await first.post(CHAT, json=chat_body(), headers=hdr)
    finally:
        await first.aclose()
    fresh = mount_stub(scenarios_dir)
    try:
        r = (await fresh.post(CHAT, json=chat_body(), headers=hdr)).json()
        assert r["choices"][0]["message"]["content"] == '{"result": "val'
    finally:
        await fresh.aclose()


async def test_counters_are_per_scenario(llm_stub: httpx.AsyncClient) -> None:
    await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "flaky-5xx"})
    # a different scenario is unaffected by flaky-5xx's counter
    r = await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "full-capability"})
    assert r.status_code == 200


async def test_rate_limited_429_with_retry_after(llm_stub: httpx.AsyncClient) -> None:
    hdr = {"X-Stub-Scenario": "rate-limited"}
    r = await llm_stub.post(CHAT, json=chat_body(), headers=hdr)
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "2"
    assert r.json()["error"]["type"] == "rate_limit_error"
    assert (await llm_stub.post(CHAT, json=chat_body(), headers=hdr)).status_code == 200


async def test_scripted_error_response(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "default.yaml").write_text(
        "name: default\nresponse:\n  kind: error\n  error:\n    status: 502\n    message: bad gateway\n"
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.post(CHAT, json=chat_body())
        assert r.status_code == 502
        assert r.json()["error"]["message"] == "bad gateway"
    finally:
        await client.aclose()


async def test_fail_with_retry_after_absent_when_unset(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "default.yaml").write_text(
        "name: default\nbehaviour:\n  fail_times: 1\n  fail_with:\n    status: 500\n"
        "response:\n  kind: text\n  content: ok\n"
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.post(CHAT, json=chat_body())
        assert r.status_code == 500
        assert "Retry-After" not in r.headers
    finally:
        await client.aclose()


async def test_latency_is_applied(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "default.yaml").write_text(
        "name: default\nresponse:\n  kind: text\n  content: ok\n  delay_ms: 150\n"
    )
    client = mount_stub(tmp_path)
    try:
        start = time.monotonic()
        r = await client.post(CHAT, json=chat_body())
        elapsed = time.monotonic() - start
        assert r.status_code == 200
        assert elapsed >= 0.14
    finally:
        await client.aclose()


async def test_slow_scenario_bundled_delay(llm_stub: httpx.AsyncClient) -> None:
    start = time.monotonic()
    r = await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "slow"})
    assert r.status_code == 200
    assert time.monotonic() - start >= 1.4


async def test_timeout_scenario_is_slower_than_caller_budget(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """In-process ASGI transport cannot enforce an httpx timeout, so the caller's budget is
    emulated with ``asyncio.wait_for``. The scenario must not answer inside that budget."""
    (tmp_path / "default.yaml").write_text(
        "name: default\nbehaviour:\n  timeout_sleep_ms: 2000\n"
        "response:\n  kind: text\n  content: late\n"
    )
    client = mount_stub(tmp_path)
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(client.post(CHAT, json=chat_body()), timeout=0.2)
    finally:
        await client.aclose()


async def test_bundled_timeout_scenario_exceeds_budget(scenarios_dir) -> None:  # type: ignore[no-untyped-def]
    # Bundled "timeout" sleeps 60 s; we only prove it does not answer within a 0.3 s budget.
    client = mount_stub(scenarios_dir)
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                client.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "timeout"}),
                timeout=0.3,
            )
    finally:
        await client.aclose()


async def test_usage_override_per_scenario(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "huge-usage"})
    usage = r.json()["usage"]
    assert usage["prompt_tokens"] == 900000
    assert usage["completion_tokens"] == 100000
    assert usage["total_tokens"] == 1000000


async def test_usage_override_per_response(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "default.yaml").write_text(
        "name: default\nresponse:\n  kind: text\n  content: ok\n  usage:\n    prompt_tokens: 5\n    completion_tokens: 7\n"
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.post(CHAT, json=chat_body())
        assert r.json()["usage"] == {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}
    finally:
        await client.aclose()


async def test_concurrent_requests_all_counted(llm_stub: httpx.AsyncClient) -> None:
    hdr = {"X-Stub-Scenario": "flaky-5xx"}
    results = await asyncio.gather(
        *[llm_stub.post(CHAT, json=chat_body(), headers=hdr) for _ in range(4)]
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 200, 503, 503]


async def test_unknown_embedding_scenario_header(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.post(
        "/v1/embeddings", json={"model": "e", "input": "x"}, headers={"X-Stub-Scenario": "missing"}
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "scenario_not_found"
