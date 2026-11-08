"""Capability enforcement: undeclared features are rejected with an OpenAI-style 400."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from helpers import chat_body, mount_stub

CHAT = "/v1/chat/completions"
JSON_SCHEMA_RF = {
    "type": "json_schema",
    "json_schema": {
        "name": "r",
        "schema": {"type": "object", "properties": {"result": {"type": "string"}}},
    },
}
TOOLS = [{"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}]


def _assert_400(r: httpx.Response, fragment: str) -> None:
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["type"] == "invalid_request_error"
    assert fragment in err["message"]


# (scenario, request extras, message fragment) for every feature a scenario does not declare.
REJECTED = [
    ("no-json-schema", {"response_format": JSON_SCHEMA_RF}, "json_schema"),
    ("plain-text-only", {"response_format": {"type": "json_object"}}, "json_object"),
    ("plain-text-only", {"tools": TOOLS}, "tools"),
    ("plain-text-only", {"stream": True}, "streaming"),
    ("plain-text-only", {"seed": 3}, "seed"),
    ("json-object-only", {"guided_json": {"type": "object"}}, "guided_json"),
    ("json-object-only", {"grammar": "root ::= 'x'"}, "grammar"),
]


@pytest.mark.parametrize(("scenario", "extra", "fragment"), REJECTED)
async def test_undeclared_feature_is_rejected(
    llm_stub: httpx.AsyncClient, scenario: str, extra: dict[str, Any], fragment: str
) -> None:
    r = await llm_stub.post(CHAT, json=chat_body(**extra), headers={"X-Stub-Scenario": scenario})
    _assert_400(r, fragment)


# Declared features are accepted.
ACCEPTED = [
    ("no-json-schema", {"response_format": {"type": "json_object"}}),
    (
        "full-capability",
        {
            "response_format": JSON_SCHEMA_RF,
            "tools": TOOLS,
            "seed": 1,
            "guided_json": {"type": "object"},
        },
    ),
]


@pytest.mark.parametrize(("scenario", "extra"), ACCEPTED)
async def test_declared_feature_is_accepted(
    llm_stub: httpx.AsyncClient, scenario: str, extra: dict[str, Any]
) -> None:
    r = await llm_stub.post(CHAT, json=chat_body(**extra), headers={"X-Stub-Scenario": scenario})
    assert r.status_code == 200


async def test_json_schema_rejected_on_no_json_schema_model(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.post(
        CHAT,
        json=chat_body(response_format=JSON_SCHEMA_RF),
        headers={"X-Stub-Scenario": "no-json-schema"},
    )
    _assert_400(r, "json_schema")


async def test_seed_is_echoed_when_declared(llm_stub: httpx.AsyncClient) -> None:
    r = await llm_stub.post(
        CHAT, json=chat_body(seed=42), headers={"X-Stub-Scenario": "full-capability"}
    )
    assert r.status_code == 200
    assert r.json()["system_fingerprint"] == "stub-seed-42"


async def test_capabilities_are_per_model(tmp_path: Path) -> None:
    """A model declared with json_schema is accepted while an unlisted model is rejected."""
    (tmp_path / "default.yaml").write_text(
        "name: default\n"
        "capabilities:\n"
        "  strong:\n"
        "    supports_json_schema: true\n"
        '  "*": {}\n'
        'response:\n  kind: json\n  content: {"a": 1}\n'
    )
    client = mount_stub(tmp_path)
    try:
        ok = await client.post(CHAT, json=chat_body(model="strong", response_format=JSON_SCHEMA_RF))
        assert ok.status_code == 200
        bad = await client.post(CHAT, json=chat_body(model="weak", response_format=JSON_SCHEMA_RF))
        _assert_400(bad, "json_schema")
    finally:
        await client.aclose()
