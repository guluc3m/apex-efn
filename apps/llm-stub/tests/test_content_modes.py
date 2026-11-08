"""Content shapes: valid JSON, malformed JSON, fenced JSON, schema violations, tool calls, sequences."""

from __future__ import annotations

import json

import httpx
from helpers import chat_body, mount_stub

CHAT = "/v1/chat/completions"


async def test_malformed_then_valid_sequence(llm_stub: httpx.AsyncClient) -> None:
    hdr = {"X-Stub-Scenario": "malformed-then-valid"}
    first = (await llm_stub.post(CHAT, json=chat_body(), headers=hdr)).json()
    content1 = first["choices"][0]["message"]["content"]
    assert content1 == '{"result": "val'
    try:
        json.loads(content1)
        raise AssertionError("expected malformed JSON")
    except json.JSONDecodeError:
        pass
    second = (await llm_stub.post(CHAT, json=chat_body(), headers=hdr)).json()
    assert json.loads(second["choices"][0]["message"]["content"]) == {"result": "valid"}
    # sequence is sticky on the last element
    third = (await llm_stub.post(CHAT, json=chat_body(), headers=hdr)).json()
    assert json.loads(third["choices"][0]["message"]["content"]) == {"result": "valid"}


async def test_always_malformed_covers_all_shapes(llm_stub: httpx.AsyncClient) -> None:
    hdr = {"X-Stub-Scenario": "always-malformed"}
    c1 = (await llm_stub.post(CHAT, json=chat_body(), headers=hdr)).json()["choices"][0]["message"][
        "content"
    ]
    c2 = (await llm_stub.post(CHAT, json=chat_body(), headers=hdr)).json()["choices"][0]["message"][
        "content"
    ]
    c3 = (await llm_stub.post(CHAT, json=chat_body(), headers=hdr)).json()["choices"][0]["message"][
        "content"
    ]
    # trailing prose
    try:
        json.loads(c1)
        raise AssertionError
    except json.JSONDecodeError:
        pass
    # markdown fences
    assert c2.startswith("```json")
    # valid JSON but wrong shape
    assert json.loads(c3) == {"wrong_field": 1}


async def test_tool_call_response(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.post(
        CHAT,
        json=chat_body(tools=[{"type": "function", "function": {"name": "emit_result"}}]),
        headers={"X-Stub-Scenario": "tools-only"},
    )
    assert r.status_code == 200
    choice = r.json()["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["content"] is None
    call = choice["message"]["tool_calls"][0]
    assert call["type"] == "function"
    assert call["function"]["name"] == "emit_result"
    # arguments must be a JSON *string*, as in the OpenAI wire format
    assert isinstance(call["function"]["arguments"], str)
    assert json.loads(call["function"]["arguments"]) == {"result": "valid"}


async def test_tool_call_string_arguments_passed_through(tmp_path) -> None:  # type: ignore[no-untyped-def]

    (tmp_path / "default.yaml").write_text(
        "name: default\nresponse:\n  kind: tool_call\n  tool_call:\n    name: f\n    arguments: '{\"raw\": true}'\n"
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.post(CHAT, json=chat_body())
        assert (
            r.json()["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
            == '{"raw": true}'
        )
    finally:
        await client.aclose()


async def test_finish_reason_override(tmp_path) -> None:  # type: ignore[no-untyped-def]

    (tmp_path / "default.yaml").write_text(
        "name: default\nresponse:\n  kind: text\n  content: cut\n  finish_reason: length\n"
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.post(CHAT, json=chat_body())
        assert r.json()["choices"][0]["finish_reason"] == "length"
    finally:
        await client.aclose()


async def test_json_scalar_content_is_serialized(tmp_path) -> None:  # type: ignore[no-untyped-def]

    (tmp_path / "default.yaml").write_text(
        "name: default\nresponse:\n  kind: json\n  content: [1, 2]\n"
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.post(CHAT, json=chat_body())
        assert r.json()["choices"][0]["message"]["content"] == "[1, 2]"
    finally:
        await client.aclose()
