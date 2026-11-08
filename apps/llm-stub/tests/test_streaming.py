"""SSE streaming: data frames, [DONE] terminator, and reassembly into the non-streamed content."""

from __future__ import annotations

import json

from helpers import chat_body

from llm_stub.testing import StubClient

CHAT = "/v1/chat/completions"


def _frames(text: str) -> list[str]:
    return [line[len("data: ") :] for line in text.split("\n\n") if line.startswith("data: ")]


async def test_stream_emits_sse_and_done(llm_stub: StubClient) -> None:
    r = await llm_stub.post(
        CHAT, json=chat_body(stream=True), headers={"X-Stub-Scenario": "full-capability"}
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    frames = _frames(r.text)
    assert frames[-1] == "[DONE]"
    chunks = [json.loads(f) for f in frames[:-1]]
    assert all(c["object"] == "chat.completion.chunk" for c in chunks)


async def test_stream_reassembles_to_full_content(llm_stub: StubClient) -> None:
    body = chat_body(stream=True)
    r = await llm_stub.post(CHAT, json=body, headers={"X-Stub-Scenario": "full-capability"})
    text = "".join(
        json.loads(f)["choices"][0]["delta"].get("content", "") for f in _frames(r.text)[:-1]
    )
    full = (
        await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "full-capability"})
    ).json()["choices"][0]["message"]["content"]
    assert text == full
    assert json.loads(text) == {"result": "valid", "confidence": 0.9}


async def test_stream_final_chunk_has_finish_reason_and_usage(llm_stub: StubClient) -> None:
    r = await llm_stub.post(
        CHAT, json=chat_body(stream=True), headers={"X-Stub-Scenario": "full-capability"}
    )
    last = json.loads(_frames(r.text)[-2])
    assert last["choices"][0]["finish_reason"] == "stop"
    assert last["usage"]["total_tokens"] > 0


async def test_stream_tool_call_frame(llm_stub: StubClient) -> None:
    r = await llm_stub.post(
        CHAT,
        json=chat_body(
            stream=True, tools=[{"type": "function", "function": {"name": "emit_result"}}]
        ),
        headers={"X-Stub-Scenario": "tools-only"},
    )
    # tools-only does not declare streaming, so it must be rejected
    assert r.status_code == 400


async def test_stream_tools_when_declared(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from llm_stub.testing import mount_stub

    (tmp_path / "default.yaml").write_text(
        'name: default\ncapabilities:\n  "*":\n    supports_tools: true\n    supports_streaming: true\n'
        'response:\n  kind: tool_call\n  tool_call:\n    name: f\n    arguments: {"a": 1}\n'
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.post(
            CHAT,
            json=chat_body(stream=True, tools=[{"type": "function", "function": {"name": "f"}}]),
        )
        frames = [json.loads(f) for f in _frames(r.text)[:-1]]
        tool_frames = [f for f in frames if f["choices"][0]["delta"].get("tool_calls")]
        assert len(tool_frames) == 1
        call = tool_frames[0]["choices"][0]["delta"]["tool_calls"][0]
        assert call["function"]["name"] == "f"
        assert json.loads(call["function"]["arguments"]) == {"a": 1}
    finally:
        await client.aclose()
