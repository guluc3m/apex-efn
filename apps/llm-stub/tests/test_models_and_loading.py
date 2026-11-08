from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_stub.models import ChatMessage, Response, Scenario
from llm_stub.scenarios import ScenarioError, load_scenarios, prompt_sha256, role_marker


def test_bundled_scenarios_load(scenarios_dir: Path) -> None:
    scenarios = load_scenarios(scenarios_dir)
    for name in [
        "default",
        "full-capability",
        "no-json-schema",
        "json-object-only",
        "tools-only",
        "plain-text-only",
        "malformed-then-valid",
        "always-malformed",
        "flaky-5xx",
        "rate-limited",
        "slow",
        "huge-usage",
        "timeout",
    ]:
        assert name in scenarios


def test_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="does not exist"):
        load_scenarios(tmp_path / "nope")


def test_missing_default_raises(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text(
        json.dumps({"name": "other", "response": {"kind": "text", "content": "a"}})
    )
    with pytest.raises(ScenarioError, match="no 'default'"):
        load_scenarios(tmp_path)


def test_duplicate_name_raises(tmp_path: Path) -> None:
    item = {"name": "default", "response": {"kind": "text", "content": "a"}}
    (tmp_path / "a.json").write_text(json.dumps(item))
    (tmp_path / "b.json").write_text(json.dumps(item))
    with pytest.raises(ScenarioError, match="duplicate"):
        load_scenarios(tmp_path)


def test_invalid_scenario_reports_file(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("scenarios:\n  - name: default\n    bogus_field: 1\n")
    with pytest.raises(ScenarioError, match="bad.yaml"):
        load_scenarios(tmp_path)


def test_yaml_and_json_and_list_forms(tmp_path: Path) -> None:
    (tmp_path / "default.yaml").write_text("name: default\nresponse:\n  kind: text\n  content: a\n")
    (tmp_path / "many.json").write_text(
        json.dumps({"scenarios": [{"name": "one", "response": {"kind": "text", "content": "1"}}]})
    )
    (tmp_path / "list.yml").write_text(
        "- name: two\n  response:\n    kind: text\n    content: '2'\n"
    )
    (tmp_path / "ignored.txt").write_text("not a scenario")
    loaded = load_scenarios(tmp_path)
    assert set(loaded) == {"default", "one", "two"}


def test_response_validation_requires_payload() -> None:
    with pytest.raises(ValueError, match="requires"):
        Response(kind="error")
    with pytest.raises(ValueError, match="requires"):
        Response(kind="tool_call")
    with pytest.raises(ValueError, match="requires"):
        Response(kind="text")


def test_scenario_requires_responses() -> None:
    with pytest.raises(ValueError, match="needs"):
        Scenario(name="empty")


def test_sequence_repeats_last_element() -> None:
    s = Scenario(
        name="seq",
        sequence=[
            Response(kind="text", content="a"),
            Response(kind="text", content="b"),
        ],
    )
    assert s.response_for_call(0).content == "a"
    assert s.response_for_call(1).content == "b"
    assert s.response_for_call(50).content == "b"


def test_caps_fall_back_to_wildcard_then_empty() -> None:
    from llm_stub.models import Capabilities

    s = Scenario(
        name="caps",
        response=Response(kind="text", content="x"),
        capabilities={
            "exact": Capabilities(supports_tools=True),
            "*": Capabilities(supports_seed=True),
        },
    )
    assert s.caps_for("exact").supports_tools is True
    assert s.caps_for("other").supports_seed is True
    empty = Scenario(name="none", response=Response(kind="text", content="x"))
    assert empty.caps_for("anything") == Capabilities()


def test_role_marker_detection() -> None:
    msgs = [
        ChatMessage(role="system", content="You are the role: negotiator agent"),
        ChatMessage(role="user", content="hi"),
    ]
    assert role_marker(msgs) == "negotiator"
    assert role_marker([ChatMessage(role="user", content="role: planner")]) is None
    assert role_marker([ChatMessage(role="system", content="nothing here")]) is None


def test_prompt_sha256_is_stable_and_order_sensitive() -> None:
    a = [ChatMessage(role="user", content="x")]
    b = [ChatMessage(role="user", content="x")]
    c = [ChatMessage(role="user", content="y")]
    assert prompt_sha256(a) == prompt_sha256(b)
    assert prompt_sha256(a) != prompt_sha256(c)
