"""seed echo control and vLLM guided_json / llama.cpp grammar schema validation paths."""

from __future__ import annotations

from pathlib import Path

from helpers import chat_body, mount_stub

CHAT = "/v1/chat/completions"


async def test_seed_not_echoed_when_disabled(tmp_path: Path) -> None:
    (tmp_path / "default.yaml").write_text(
        "name: default\nbehaviour:\n  echo_seed: false\n"
        'capabilities:\n  "*":\n    supports_seed: true\n'
        "response:\n  kind: text\n  content: ok\n"
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.post(CHAT, json=chat_body(seed=5))
        assert "system_fingerprint" not in r.json()
    finally:
        await client.aclose()


async def test_no_seed_no_fingerprint(llm_stub) -> None:  # type: ignore[no-untyped-def]
    r = await llm_stub.post(CHAT, json=chat_body(), headers={"X-Stub-Scenario": "full-capability"})
    assert "system_fingerprint" not in r.json()


async def test_guided_json_capability_allows_request(tmp_path: Path) -> None:
    (tmp_path / "default.yaml").write_text(
        'name: default\ncapabilities:\n  "*":\n    supports_guided: true\n'
        'response:\n  kind: json\n  content: {"a": "x"}\n'
    )
    client = mount_stub(tmp_path)
    try:
        r = await client.post(CHAT, json=chat_body(guided_json={"type": "object"}))
        assert r.status_code == 200
    finally:
        await client.aclose()
