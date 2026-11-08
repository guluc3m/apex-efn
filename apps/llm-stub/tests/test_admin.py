"""Admin surface under /_stub: reset, scenarios, call log that lets gateway tests assert what was sent."""

from __future__ import annotations

from helpers import chat_body

from llm_stub.testing import StubClient

CHAT = "/v1/chat/completions"


async def test_call_log_records_request_body_and_headers(llm_stub: StubClient) -> None:
    body = chat_body(model="gpt-x", response_format={"type": "json_object"})
    await llm_stub.post(
        CHAT, json=body, headers={"X-Stub-Scenario": "json-object-only", "X-Trace": "abc"}
    )
    calls = await llm_stub.calls()
    assert len(calls) == 1
    call = calls[0]
    assert call["path"] == CHAT
    assert call["scenario"] == "json-object-only"
    assert call["status"] == 200
    assert call["body"]["response_format"] == {"type": "json_object"}
    assert call["headers"]["x-trace"] == "abc"
    assert "authorization" not in call["headers"]


async def test_call_log_proves_response_format_not_sent(llm_stub: StubClient) -> None:
    """Gateway assertion pattern: when the capability is absent, the gateway must not send it."""
    await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "plain-text-only"})
    calls = await llm_stub.calls()
    assert "response_format" not in calls[-1]["body"]


async def test_call_log_records_rejected_calls_with_status(llm_stub: StubClient) -> None:
    await llm_stub.post(
        CHAT,
        json=chat_body(
            response_format={"type": "json_schema", "json_schema": {"name": "x", "schema": {}}}
        ),
        headers={"X-Stub-Scenario": "no-json-schema"},
    )
    calls = await llm_stub.calls()
    assert calls[-1]["status"] == 400


async def test_call_log_records_fail_injected_calls(llm_stub: StubClient) -> None:
    await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "flaky-5xx"})
    calls = await llm_stub.calls()
    assert calls[-1]["status"] == 503


async def test_clear_calls(llm_stub: StubClient) -> None:
    await llm_stub.post(CHAT, json=chat_body())
    await llm_stub.clear_calls()
    assert await llm_stub.calls() == []


async def test_reset_clears_call_log_and_counters(llm_stub: StubClient) -> None:
    await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "flaky-5xx"})
    await llm_stub.reset()
    assert await llm_stub.calls() == []
    r = await llm_stub.get("/_stub/scenarios")
    flaky = next(s for s in r.json()["scenarios"] if s["name"] == "flaky-5xx")
    assert flaky["calls"] == 0


async def test_scenarios_admin_reports_capabilities(llm_stub: StubClient) -> None:
    r = await llm_stub.get("/_stub/scenarios")
    full = next(s for s in r.json()["scenarios"] if s["name"] == "full-capability")
    assert full["capabilities"]["*"]["supports_json_schema"] is True


async def test_call_log_is_bounded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from llm_stub.app import CALL_LOG_LIMIT
    from llm_stub.testing import mount_stub

    (tmp_path / "default.yaml").write_text(
        "name: default\nresponse:\n  kind: text\n  content: ok\n"
    )
    client = mount_stub(tmp_path)
    try:
        for _ in range(CALL_LOG_LIMIT + 5):
            await client.post(CHAT, json=chat_body())
        calls = (await client.get("/_stub/calls")).json()["calls"]
        assert len(calls) == CALL_LOG_LIMIT
    finally:
        await client.aclose()
