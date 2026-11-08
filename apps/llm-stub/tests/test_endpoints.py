from __future__ import annotations

import json

import httpx
from helpers import chat_body, mount_stub

CHAT = "/v1/chat/completions"


async def test_health(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_chat_non_streaming_shape(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.post(CHAT, json=chat_body(model="m"))
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "m"
    assert body["id"].startswith("chatcmpl-stub-")
    choice = body["choices"][0]
    assert choice["index"] == 0
    assert choice["message"]["role"] == "assistant"
    assert choice["finish_reason"] == "stop"
    assert json.loads(choice["message"]["content"]) == {"status": "ok", "stub": True}


async def test_usage_is_deterministic_and_consistent(llm_stub: httpx.AsyncClient) -> None:
    body = chat_body(content="x" * 40)
    r1 = (await llm_stub.post(CHAT, json=body)).json()["usage"]
    r2 = (await llm_stub.post(CHAT, json=body)).json()["usage"]
    assert r1["prompt_tokens"] == r2["prompt_tokens"]
    assert r1["total_tokens"] == r1["prompt_tokens"] + r1["completion_tokens"]
    # 4 overhead + ceil(40/4)=10
    assert r1["prompt_tokens"] == 14


async def test_text_scenario_returns_plain_text(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "plain-text-only"})
    assert r.status_code == 200
    assert "price looks fine" in r.json()["choices"][0]["message"]["content"]


async def test_unknown_scenario_header_returns_400(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "nope"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "scenario_not_found"


async def test_models_listing(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.get("/v1/models")
    assert r.status_code == 200
    assert r.json()["object"] == "list"
    assert isinstance(r.json()["data"], list)


async def test_models_listing_includes_declared_models(tmp_path) -> None:  # type: ignore[no-untyped-def]

    (tmp_path / "default.yaml").write_text(
        "name: default\nmodels: [gpt-a, gpt-b]\nresponse:\n  kind: text\n  content: a\n"
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.get("/v1/models")
        ids = [m["id"] for m in r.json()["data"]]
        assert ids == ["gpt-a", "gpt-b"]
    finally:
        await client.aclose()


async def test_embeddings_are_deterministic(llm_stub: httpx.AsyncClient) -> None:
    body = {"model": "emb", "input": ["alpha", "beta"]}
    a = (await llm_stub.post("/v1/embeddings", json=body)).json()
    b = (await llm_stub.post("/v1/embeddings", json=body)).json()
    assert a == b
    assert len(a["data"]) == 2
    assert a["data"][0]["index"] == 0 and a["data"][1]["index"] == 1
    assert len(a["data"][0]["embedding"]) == 64
    assert a["usage"]["prompt_tokens"] > 0


async def test_embeddings_string_input_and_unit_norm(llm_stub: httpx.AsyncClient) -> None:
    import math

    r = await llm_stub.post("/v1/embeddings", json={"model": "emb", "input": "single"})
    vec = r.json()["data"][0]["embedding"]
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-5


async def test_embeddings_differ_per_input(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.post("/v1/embeddings", json={"model": "emb", "input": ["a", "b"]})
    d = r.json()["data"]
    assert d[0]["embedding"] != d[1]["embedding"]
