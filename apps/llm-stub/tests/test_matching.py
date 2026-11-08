from __future__ import annotations

from pathlib import Path

import pytest

from llm_stub.models import ChatMessage, Response, Scenario
from llm_stub.scenarios import ScenarioError, prompt_sha256, select_scenario


def _s(name: str, **kw: object) -> Scenario:
    return Scenario(name=name, response=Response(kind="text", content=name), **kw)  # type: ignore[arg-type]


MSGS = [ChatMessage(role="user", content="hello")]


def test_header_beats_everything() -> None:
    scenarios = {
        "default": _s("default"),
        "by-model": _s("by-model", models=["m1"]),
        "forced": _s("forced"),
    }
    chosen = select_scenario(scenarios, header_name="forced", model="m1", messages=MSGS)
    assert chosen.name == "forced"


def test_unknown_header_raises() -> None:
    with pytest.raises(ScenarioError, match="unknown scenario"):
        select_scenario({"default": _s("default")}, header_name="nope", model="m", messages=MSGS)


def test_model_match() -> None:
    scenarios = {"default": _s("default"), "m1-only": _s("m1-only", models=["m1"])}
    assert select_scenario(scenarios, header_name=None, model="m1", messages=MSGS).name == "m1-only"
    assert (
        select_scenario(scenarios, header_name=None, model="other", messages=MSGS).name == "default"
    )


def test_role_match_from_system_marker() -> None:
    scenarios = {"default": _s("default"), "planner": _s("planner", role="planner")}
    msgs = [
        ChatMessage(role="system", content="role: planner"),
        ChatMessage(role="user", content="go"),
    ]
    assert select_scenario(scenarios, header_name=None, model="x", messages=msgs).name == "planner"


def test_prompt_hash_match() -> None:
    digest = prompt_sha256(MSGS)
    scenarios = {"default": _s("default"), "hashed": _s("hashed", prompt_sha256=digest)}
    assert select_scenario(scenarios, header_name=None, model="x", messages=MSGS).name == "hashed"
    other = [ChatMessage(role="user", content="different")]
    assert select_scenario(scenarios, header_name=None, model="x", messages=other).name == "default"


def test_more_specific_match_wins() -> None:
    digest = prompt_sha256(MSGS)
    scenarios = {
        "default": _s("default"),
        "model-only": _s("model-only", models=["m1"]),
        "model-and-hash": _s("model-and-hash", models=["m1"], prompt_sha256=digest),
    }
    assert (
        select_scenario(scenarios, header_name=None, model="m1", messages=MSGS).name
        == "model-and-hash"
    )


def test_partial_criteria_must_all_hold() -> None:
    scenarios = {
        "default": _s("default"),
        "m1-planner": _s("m1-planner", models=["m1"], role="planner"),
    }
    # model matches but no planner marker -> falls back to default
    assert select_scenario(scenarios, header_name=None, model="m1", messages=MSGS).name == "default"


def test_default_used_when_nothing_matches() -> None:
    scenarios = {"default": _s("default"), "x": _s("x", models=["zzz"])}
    assert select_scenario(scenarios, header_name=None, model="a", messages=MSGS).name == "default"


@pytest.mark.parametrize("header", ["full-capability", "flaky-5xx"])
def test_bundled_header_selection(scenarios_dir: Path, header: str) -> None:
    from llm_stub.scenarios import load_scenarios

    scenarios = load_scenarios(scenarios_dir)
    assert select_scenario(scenarios, header_name=header, model="x", messages=MSGS).name == header
