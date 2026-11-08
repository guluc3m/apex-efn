"""Golden-set eval runner (D4-05, spec §5.6 "portabilidad de prompts").

Every golden case renders a versioned prompt, sends it through ``LLMGateway.chat_structured`` to one
endpoint, validates the output with the Pydantic draft schema and then runs deterministic checks. The same
suite runs against *every* configured endpoint; a prompt change cannot merge if any endpoint fails.

Two modes:

- **stub** (default, CI, no network): each case becomes a scenario of the local LLM stub pinned to the
  exact rendered prompt, answering with the case's ``stub_response``. This proves rendering, the structured
  ladder, schema validation and checks work end to end, and fails when a prompt or schema is edited without
  updating its golden set.
- **live**: endpoints come from a JSON file (``--endpoints``); no case ``stub_response`` is used. Run it
  against self-hosted engines (vLLM, llama.cpp, Ollama ``/v1``) before promoting a model or a prompt.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel, ValidationError

from apex.agents.schemas import SCHEMAS
from apex.common.clock import FixedClock
from apex.llm.accounting import InMemorySink
from apex.llm.budget import InMemoryBudgetStore, TokenBudget
from apex.llm.config import (
    CapabilityProfile,
    LLMRole,
    LLMRolesConfig,
    RoleEndpointConfig,
    StaticRoleConfigProvider,
    StaticSecretResolver,
)
from apex.llm.gateway import LLMGateway
from apex.llm.prompts import PromptRegistry
from apex.llm.structured import StructuredOutputError
from evals.checks import run_check

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
EVAL_NOW = datetime(2026, 1, 1, tzinfo=UTC)
TENANT = "eval-tenant"
MISSION_LIMIT = 10_000_000


@dataclass(frozen=True)
class GoldenCase:
    prompt: str
    version: int
    schema: str
    case_id: str
    variables: dict[str, Any]
    expect: list[dict[str, Any]]
    stub_response: dict[str, Any] | None


@dataclass
class CaseResult:
    endpoint_id: str
    case: str
    passed: bool
    failure: str = ""


@dataclass
class SuiteReport:
    results: list[CaseResult] = field(default_factory=list)

    @property
    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]

    @property
    def ok(self) -> bool:
        return bool(self.results) and not self.failures


def load_golden(directory: Path = GOLDEN_DIR) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for path in sorted(directory.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for raw in doc["cases"]:
            cases.append(
                GoldenCase(
                    prompt=doc["prompt"],
                    version=int(doc["version"]),
                    schema=doc["schema"],
                    case_id=raw["id"],
                    variables=raw["variables"],
                    expect=raw.get("expect", []),
                    stub_response=raw.get("stub_response"),
                )
            )
    return cases


def _canonical(messages: list[dict[str, Any]]) -> str:
    payload = [{"role": m["role"], "content": m["content"]} for m in messages]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_stub_scenarios(
    cases: list[GoldenCase], registry: PromptRegistry, stub_scenarios_dir: Path, out_dir: Path
) -> None:
    """Write ``default`` plus one scenario per case, pinned to the exact rendered prompt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "default.yaml").write_text(
        (stub_scenarios_dir / "default.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    scenarios: list[dict[str, Any]] = []
    for case in cases:
        if case.stub_response is None:
            continue
        rendered = registry.render(case.prompt, version=case.version, **case.variables)
        digest = hashlib.sha256(_canonical(rendered.messages).encode("utf-8")).hexdigest()
        scenarios.append(
            {
                "name": f"eval-{case.prompt}-v{case.version}-{case.case_id}",
                "prompt_sha256": digest,
                "capabilities": {"*": {"supports_json_schema": True, "supports_json_object": True}},
                "response": {"kind": "json", "content": case.stub_response},
            }
        )
    (out_dir / "eval-cases.yaml").write_text(
        yaml.safe_dump({"scenarios": scenarios}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def endpoint_from_json(
    raw: Mapping[str, Any], env: Mapping[str, str]
) -> tuple[RoleEndpointConfig, str]:
    """Build an endpoint config from a JSON entry. The API key is read from ``api_key_env``."""
    key = env.get(raw["api_key_env"], "") if raw.get("api_key_env") else ""
    cfg = RoleEndpointConfig(
        endpoint_id=raw["endpoint_id"],
        base_url=raw["base_url"],
        api_key_ref="eval/key" if key else None,
        model=raw["model"],
        capabilities=CapabilityProfile(**raw.get("capabilities", {})),
        timeout_s=float(raw.get("timeout_s", 120.0)),
        max_output_tokens=int(raw.get("max_output_tokens", 1024)),
        temperature=0.0,
        seed=raw.get("seed"),
    )
    return cfg, key


def _gateway(
    cfg: RoleEndpointConfig,
    key: str,
    roles: list[LLMRole],
    http_client: httpx.AsyncClient | None,
) -> tuple[LLMGateway, InMemorySink]:
    sink = InMemorySink()
    config = LLMRolesConfig(roles=dict.fromkeys(roles, cfg), endpoints={cfg.endpoint_id: cfg})
    secrets = StaticSecretResolver({"eval/key": key} if key else {})
    gateway = LLMGateway(
        config_provider=StaticRoleConfigProvider(config),
        secrets=secrets,
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=MISSION_LIMIT),
        sink=sink,
        clock=FixedClock(EVAL_NOW),
        http_client_factory=(lambda _cfg: http_client) if http_client is not None else None,
    )
    return gateway, sink


async def run_case(
    gateway: LLMGateway, registry: PromptRegistry, case: GoldenCase, endpoint_id: str
) -> CaseResult:
    try:
        rendered = registry.render(case.prompt, version=case.version, **case.variables)
        schema: type[BaseModel] = SCHEMAS[case.schema]
        value = await gateway.chat_structured(
            rendered.spec.role,
            rendered.messages,
            schema,
            mission_id=f"eval-{case.prompt}-{case.case_id}",
            tenant_id=TENANT,
            prompt_version=rendered.prompt_version,
        )
    except (StructuredOutputError, ValidationError) as exc:
        return CaseResult(endpoint_id, f"{case.prompt}/{case.case_id}", False, f"schema: {exc}")
    output = value.model_dump()
    input_text = json.dumps(case.variables, ensure_ascii=False)
    for check in case.expect:
        for kind, arg in check.items():
            reason = run_check(kind, arg, output, input_text)
            if reason is not None:
                return CaseResult(
                    endpoint_id, f"{case.prompt}/{case.case_id}", False, f"{kind}: {reason}"
                )
    return CaseResult(endpoint_id, f"{case.prompt}/{case.case_id}", True)


async def run_suite(
    endpoints: list[tuple[RoleEndpointConfig, str]],
    cases: list[GoldenCase],
    registry: PromptRegistry,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> SuiteReport:
    report = SuiteReport()
    roles = list(LLMRole)
    for cfg, key in endpoints:
        gateway, _ = _gateway(cfg, key, roles, http_client)
        try:
            for case in cases:
                report.results.append(await run_case(gateway, registry, case, cfg.endpoint_id))
        finally:
            await gateway.close()
    return report


def format_report(report: SuiteReport) -> str:
    lines = [
        f"{'PASS' if r.passed else 'FAIL'} {r.endpoint_id} {r.case} {r.failure}".rstrip()
        for r in report.results
    ]
    lines.append(f"{len(report.results) - len(report.failures)}/{len(report.results)} passed")
    return "\n".join(lines)


async def _main_async(args: argparse.Namespace) -> int:
    registry = PromptRegistry()
    cases = load_golden()
    if args.endpoints:
        raw = json.loads(Path(args.endpoints).read_text(encoding="utf-8"))
        endpoints = [endpoint_from_json(item, os.environ) for item in raw]
        report = await run_suite(endpoints, cases, registry)
    else:
        from llm_stub.testing import DEFAULT_SCENARIOS_DIR, mount_stub

        with tempfile.TemporaryDirectory() as tmp:
            build_stub_scenarios(cases, registry, DEFAULT_SCENARIOS_DIR, Path(tmp))
            client = mount_stub(tmp)
            try:
                cfg = RoleEndpointConfig(
                    endpoint_id="stub",
                    base_url="http://llm-stub",
                    model="stub-model",
                    capabilities=CapabilityProfile(
                        supports_json_schema=True, supports_json_object=True
                    ),
                )
                report = await run_suite([(cfg, "")], cases, registry, http_client=client)
            finally:
                await client.aclose()
    print(format_report(report))
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the golden prompt suite against endpoints.")
    parser.add_argument(
        "--endpoints",
        help="JSON file with the endpoints to test (live mode). Omit to run against the local stub.",
    )
    return asyncio.run(_main_async(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
