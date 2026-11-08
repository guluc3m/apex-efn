"""The golden suite runs through the real gateway and ladder against the local stub (no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from llm_stub.testing import DEFAULT_SCENARIOS_DIR, mount_stub

from apex.agents.schemas import SCHEMAS
from apex.llm.config import CapabilityProfile, RoleEndpointConfig
from apex.llm.prompts import PromptRegistry
from evals.checks import run_check
from evals.runner import (
    GoldenCase,
    build_stub_scenarios,
    endpoint_from_json,
    format_report,
    load_golden,
    run_suite,
)

CAPS = CapabilityProfile(supports_json_schema=True, supports_json_object=True)


def _endpoint(endpoint_id: str = "stub") -> RoleEndpointConfig:
    return RoleEndpointConfig(
        endpoint_id=endpoint_id, base_url="http://llm-stub", model="m", capabilities=CAPS
    )


async def _run(cases: list[GoldenCase], tmp: Path) -> Any:
    registry = PromptRegistry()
    build_stub_scenarios(cases, registry, DEFAULT_SCENARIOS_DIR, tmp)
    client = mount_stub(tmp)
    try:
        return await run_suite([(_endpoint(), "")], cases, registry, http_client=client)
    finally:
        await client.aclose()


def test_every_prompt_has_a_golden_set_and_every_golden_set_a_prompt() -> None:
    golden = {(c.prompt, c.version) for c in load_golden()}
    shipped = {(s.name, s.version) for s in PromptRegistry().specs()}
    assert golden == shipped


def test_every_golden_case_names_a_known_schema_and_has_checks() -> None:
    for case in load_golden():
        assert case.schema in SCHEMAS
        assert case.expect, case.case_id
        assert case.stub_response is not None, case.case_id


async def test_full_suite_passes_against_the_stub(tmp_path: Path) -> None:
    report = await _run(load_golden(), tmp_path)
    assert report.ok, format_report(report)
    assert len(report.results) == len(load_golden())


async def test_a_failing_endpoint_fails_the_whole_suite(tmp_path: Path) -> None:
    """Editing a golden expectation without the prompt satisfying it must turn the suite red."""
    cases = load_golden()
    broken = GoldenCase(
        **{**cases[0].__dict__, "expect": [{"equals": {"destination_country": "FR"}}]}
    )
    report = await _run([broken, *cases[1:]], tmp_path)
    assert not report.ok
    assert [r.case for r in report.failures] == [f"{broken.prompt}/{broken.case_id}"]
    assert "destination_country" in report.failures[0].failure


async def test_prompt_edit_without_golden_update_is_detected(tmp_path: Path) -> None:
    """Scenarios pin the sha256 of the rendered prompt: a prompt edit makes the stub miss its case."""
    cases = load_golden()
    registry = PromptRegistry()
    build_stub_scenarios(cases, registry, DEFAULT_SCENARIOS_DIR, tmp_path)
    pinned = yaml.safe_load((tmp_path / "eval-cases.yaml").read_text(encoding="utf-8"))
    for scenario in pinned["scenarios"]:
        scenario["prompt_sha256"] = "0" * 64  # pretend the prompt text changed
    (tmp_path / "eval-cases.yaml").write_text(yaml.safe_dump(pinned), encoding="utf-8")
    client = mount_stub(tmp_path)
    try:
        report = await run_suite([(_endpoint(), "")], cases, registry, http_client=client)
    finally:
        await client.aclose()
    assert not report.ok  # default scenario answers with the wrong shape for every case


async def test_each_endpoint_is_run_independently(tmp_path: Path) -> None:
    cases = load_golden()[:2]
    registry = PromptRegistry()
    build_stub_scenarios(cases, registry, DEFAULT_SCENARIOS_DIR, tmp_path)
    client = mount_stub(tmp_path)
    try:
        report = await run_suite(
            [(_endpoint("a"), ""), (_endpoint("b"), "")], cases, registry, http_client=client
        )
    finally:
        await client.aclose()
    assert {r.endpoint_id for r in report.results} == {"a", "b"}
    assert len(report.results) == 4


def test_endpoint_from_json_reads_key_from_environment_only() -> None:
    raw = {
        "endpoint_id": "e",
        "base_url": "http://x",
        "model": "m",
        "api_key_env": "K",
        "capabilities": {"supports_json_object": True},
    }
    cfg, key = endpoint_from_json(raw, {"K": "secret"})
    assert key == "secret"
    assert cfg.api_key_ref == "eval/key"
    assert "secret" not in cfg.model_dump_json()
    cfg2, key2 = endpoint_from_json({**raw, "api_key_env": None}, {})
    assert key2 == "" and cfg2.api_key_ref is None


@pytest.mark.parametrize(
    ("kind", "arg", "output", "ok"),
    [
        ("equals", {"a": 1}, {"a": 1}, True),
        ("equals", {"a": 1}, {"a": 2}, False),
        ("is_null", ["a"], {"a": None}, True),
        ("is_null", ["a"], {"a": 0}, False),
        ("contains_all", {"a": ["x"]}, {"a": ["x", "y"]}, True),
        ("contains_all", {"a": ["z"]}, {"a": ["x"]}, False),
        ("list_subset_of", {"s": ["p"]}, {"s": [{"platform_id": "p"}]}, True),
        ("list_subset_of", {"s": ["p"]}, {"s": [{"platform_id": "q"}]}, False),
        ("min_len", {"a": 2}, {"a": [1, 2]}, True),
        ("min_len", {"a": 2}, {"a": [1]}, False),
        ("max_len", {"a": 1}, {"a": [1, 2]}, False),
        ("numbers_in_input", ["t"], {"t": "pay 412 now"}, True),
        ("numbers_in_input", ["t"], {"t": "pay 999 now"}, False),
        ("mentions_all", ["o-1"], {"a": "x o-1"}, True),
        ("mentions_all", ["o-9"], {"a": "x o-1"}, False),
        ("nonsense", None, {}, False),
    ],
)
def test_checks(kind: str, arg: Any, output: dict[str, Any], ok: bool) -> None:
    reason = run_check(kind, arg, output, "pay 412 units")
    assert (reason is None) is ok
