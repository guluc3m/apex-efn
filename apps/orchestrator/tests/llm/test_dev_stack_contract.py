"""The dev stack contract: the D4-05 prompts and the D4-02 stub must work together with no special header.

In compose the orchestrator calls the LLM stub exactly like a real model: same URL, no `X-Stub-Scenario`.
The stub picks a scenario from the `role: <name>` marker in the system message, so every shipped prompt
must carry that marker and the stub must ship a scenario per role whose document matches the schema the
prompt asks for. This test is that contract.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from llm_stub.testing import DEFAULT_SCENARIOS_DIR, mount_stub

from apex.agents.schemas import SCHEMAS, SourcingPlanDraft, SourcingRequestDraft
from apex.common.clock import FixedClock
from apex.llm.accounting import InMemorySink
from apex.llm.budget import InMemoryBudgetStore, TokenBudget
from apex.llm.config import LLMRole
from apex.llm.gateway import LLMGateway
from apex.llm.prompts import PROMPTS_DIR, PromptRegistry
from apex.wiring import DefaultRoleConfigProvider

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"


@pytest.fixture
async def stub() -> httpx.AsyncClient:
    client = mount_stub(DEFAULT_SCENARIOS_DIR)  # the scenarios shipped with the stub
    try:
        yield client
    finally:
        await client.aclose()


def _gateway(stub: httpx.AsyncClient) -> LLMGateway:
    """Real gateway, real role config, no scenario header: exactly what compose does."""
    return LLMGateway(
        config_provider=DefaultRoleConfigProvider(),
        secrets=__import__(
            "apex.llm.config", fromlist=["StaticSecretResolver"]
        ).StaticSecretResolver({}),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=1_000_000),
        sink=InMemorySink(),
        clock=FixedClock(NOW),
        http_client_factory=lambda cfg: stub,
    )


def test_every_shipped_prompt_declares_its_role_in_the_system_message() -> None:
    """The stub matches on this line; without it every dev call falls back to the default scenario."""
    registry = PromptRegistry()
    for spec in registry.specs():
        rendered = registry.render(spec.name, **dict.fromkeys(spec.variables, "x"))
        system = rendered.messages[0]["content"]
        assert f"role: {spec.role.value}" in system, (
            f"{spec.prompt_version}: the system message must contain 'role: {spec.role.value}'"
        )


def test_the_stub_ships_a_scenario_for_every_llm_role() -> None:
    """A role with no scenario silently falls back to `default`, whose document matches nothing."""
    names = set()
    for path in DEFAULT_SCENARIOS_DIR.glob("*.yaml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("role:"):
                names.add(stripped.split(":", 1)[1].strip())
    # The embedder calls /v1/embeddings, which the stub answers with deterministic vectors and does not
    # scenario-match on content, so it needs no role scenario.
    for role in LLMRole:
        if role is LLMRole.EMBEDDER:
            continue
        assert role.value in names, f"the stub has no scenario for role {role.value!r}"


async def test_the_intake_prompt_gets_a_valid_request_from_the_bundled_scenarios(
    stub: httpx.AsyncClient,
) -> None:
    registry = PromptRegistry()
    rendered = registry.render(
        "intake_sourcing_request",
        today="2026-11-09",
        base_currency="EUR",
        user_text="500 cajas de guantes",
    )
    draft = await _gateway(stub).chat_structured(
        rendered.spec.role,
        rendered.messages,
        SourcingRequestDraft,
        mission_id="m-1",
        tenant_id=TENANT,
        prompt_version=rendered.prompt_version,
    )
    assert draft.spec
    assert draft.quantity_tiers[0].min_quantity == 500
    assert draft.destination_country == "ES"


async def test_the_planner_prompt_gets_a_valid_plan_from_the_bundled_scenarios(
    stub: httpx.AsyncClient,
) -> None:
    registry = PromptRegistry()
    rendered = registry.render("planner_sourcing_plan", request_json="{}", platforms_json="[]")
    draft = await _gateway(stub).chat_structured(
        rendered.spec.role,
        rendered.messages,
        SourcingPlanDraft,
        mission_id="m-1",
        tenant_id=TENANT,
        prompt_version=rendered.prompt_version,
    )
    assert {step.platform_id for step in draft.steps} == {"mock-a", "mock-b"}


def test_every_prompt_schema_is_known_to_the_eval_suite() -> None:
    """The schemas the prompts ask for are the ones the eval suite can validate."""
    assert {"SourcingRequestDraft", "SourcingPlanDraft"} <= set(SCHEMAS)
    assert (PROMPTS_DIR / "intake_sourcing_request.v1.jinja").exists()
