"""IntakeAgent and PlannerAgent (D4-08): the LLM drafts, code decides which platforms are searched."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import pytest

from apex.agents.schemas import SourcingPlanDraft, SourcingRequestDraft
from apex.agents.sourcing import (
    IntakeAgent,
    NoViablePlatform,
    PlannerAgent,
    PlanRejectionReason,
    PlatformInfo,
    StaticCatalogue,
)
from apex.common.clock import FixedClock as CommonFixedClock
from apex.llm.config import CapabilityProfile, LLMRole
from apex.llm.prompts import PromptRegistry
from apex.platform.flags import StaticFlags

NOW = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)
TENANT = "tenant-a"
CAPS = CapabilityProfile(supports_json_schema=True, supports_json_object=True)


class _Gateway:
    """Records the call and returns a scripted draft, so tests assert what the agent asked for."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def chat_structured(
        self,
        role: LLMRole,
        messages: list[dict[str, Any]],
        schema: type[Any],
        *,
        mission_id: str,
        tenant_id: str,
        prompt_version: str,
        **_: Any,
    ) -> Any:
        self.calls.append(
            {
                "role": role,
                "schema": schema.__name__,
                "prompt_version": prompt_version,
                "messages": messages,
                "mission_id": mission_id,
                "tenant_id": tenant_id,
            }
        )
        return self.response


def _request_draft(**overrides: Any) -> SourcingRequestDraft:
    base: dict[str, Any] = {
        "spec": "Botellas PET 500ml",
        "quantity_tiers": [{"min_quantity": 5000}],
        "deadline": "2027-06-01",
        "deadline_text": None,
        "destination_country": "ES",
        "certifications": ["food grade"],
        "budget_text": "4500 EUR",
        "missing_fields": [],
    }
    return SourcingRequestDraft(**{**base, **overrides})


def _plan_draft(
    *steps: tuple[str, str], rationale: str = "both ship to the EU"
) -> SourcingPlanDraft:
    return SourcingPlanDraft(
        steps=[{"platform_id": p, "query": q, "tier_index": 0} for p, q in steps],
        rationale=rationale,
    )


def _catalogue() -> StaticCatalogue:
    return StaticCatalogue(
        [
            PlatformInfo(platform_id="mock-a", transport="http", regions=("EU", "CN")),
            PlatformInfo(platform_id="mock-b", transport="browser", regions=("EU",)),
        ]
    )


ALL_ON = StaticFlags({"platform.mock-a.enabled": True, "platform.mock-b.enabled": True})


# ----- IntakeAgent -------------------------------------------------------------------------------


async def test_intake_renders_the_versioned_prompt_and_returns_a_typed_request() -> None:
    gateway = _Gateway(_request_draft())
    agent = IntakeAgent(gateway, PromptRegistry(), CommonFixedClock(NOW))  # type: ignore[arg-type]
    request = await agent.parse(
        request_id="sr-1",
        tenant_id=TENANT,
        mission_id="m-1",
        text="Necesito 5000 botellas PET",
        base_currency="EUR",
        today=date(2026, 11, 9),
        config_version="v7",
    )
    assert request.id == "sr-1" and request.tenant_id == TENANT
    assert request.spec == "Botellas PET 500ml"
    assert request.quantity_tiers[0].min_quantity == 5000
    assert request.deadline == date(2027, 6, 1)
    assert request.config_version == "v7"
    assert request.created_at == NOW
    call = gateway.calls[0]
    assert call["role"] is LLMRole.EXTRACTOR
    assert call["schema"] == "SourcingRequestDraft"
    assert call["prompt_version"].startswith("intake_sourcing_request@v")
    assert "2026-11-09" in call["messages"][1]["content"]


@pytest.mark.parametrize("raw", ["pronto", "2027-13-01", "", "next june"])
async def test_an_unparseable_deadline_stays_text_and_never_becomes_a_date(raw: str) -> None:
    agent = IntakeAgent(
        _Gateway(_request_draft(deadline=raw)), PromptRegistry(), CommonFixedClock(NOW)
    )  # type: ignore[arg-type]
    request = await agent.parse(
        request_id="sr-1",
        tenant_id=TENANT,
        mission_id="m-1",
        text="x",
        base_currency="EUR",
        today=date(2026, 11, 9),
        config_version="v7",
    )
    assert request.deadline is None


async def test_intake_never_invents_absent_fields() -> None:
    draft = _request_draft(
        quantity_tiers=[], deadline=None, destination_country=None, budget_text=None,
        certifications=[], missing_fields=["quantity_tiers", "deadline", "budget_text"],
    )  # fmt: skip
    agent = IntakeAgent(_Gateway(draft), PromptRegistry(), CommonFixedClock(NOW))  # type: ignore[arg-type]
    request = await agent.parse(
        request_id="sr-1", tenant_id=TENANT, mission_id="m-1", text="cajas", base_currency="EUR",
        today=date(2026, 11, 9), config_version="v7",
    )  # fmt: skip
    assert request.quantity_tiers == [] and request.deadline is None
    assert request.destination_country is None and request.budget_text is None
    assert request.missing_fields == ["quantity_tiers", "deadline", "budget_text"]


# ----- PlannerAgent: code decides the searchable set ---------------------------------------------


async def test_plan_keeps_only_enabled_catalogue_platforms_and_attaches_transport() -> None:
    gateway = _Gateway(_plan_draft(("mock-a", "PET bottle"), ("mock-b", "botella PET")))
    planner = PlannerAgent(gateway, PromptRegistry(), _catalogue(), ALL_ON)
    plan = await planner.plan(
        tenant_id=TENANT,
        mission_id="m-1",
        request=_request(),
        config_version="v7",
    )
    assert [(s.platform_id, s.transport) for s in plan.steps] == [
        ("mock-a", "http"),
        ("mock-b", "browser"),
    ]
    assert plan.rejected_steps == []
    assert gateway.calls[0]["role"] is LLMRole.PLANNER
    assert gateway.calls[0]["prompt_version"].startswith("planner_sourcing_plan@v")


async def test_a_disabled_platform_is_never_offered_to_the_model_and_its_steps_are_rejected() -> (
    None
):
    flags = StaticFlags({"platform.mock-a.enabled": True})  # mock-b off
    gateway = _Gateway(_plan_draft(("mock-a", "PET bottle"), ("mock-b", "botella PET")))
    planner = PlannerAgent(gateway, PromptRegistry(), _catalogue(), flags)
    plan = await planner.plan(
        tenant_id=TENANT, mission_id="m-1", request=_request(), config_version="v7"
    )
    assert [s.platform_id for s in plan.steps] == ["mock-a"]
    assert [(r.platform_id, r.reason) for r in plan.rejected_steps] == [
        ("mock-b", PlanRejectionReason.PLATFORM_DISABLED.value)
    ]
    catalogue_in_prompt = gateway.calls[0]["messages"][1]["content"]
    assert "mock-b" not in catalogue_in_prompt, "a disabled platform must not even be advertised"


async def test_an_invented_platform_is_rejected_and_reported() -> None:
    gateway = _Gateway(_plan_draft(("mock-a", "PET"), ("alibaba", "PET bottles")))
    planner = PlannerAgent(gateway, PromptRegistry(), _catalogue(), ALL_ON)
    plan = await planner.plan(
        tenant_id=TENANT, mission_id="m-1", request=_request(), config_version="v7"
    )
    assert [s.platform_id for s in plan.steps] == ["mock-a"]
    assert [(r.platform_id, r.reason) for r in plan.rejected_steps] == [
        ("alibaba", PlanRejectionReason.NOT_IN_CATALOGUE.value)
    ]


async def test_a_plan_with_no_usable_step_fails_loudly() -> None:
    gateway = _Gateway(_plan_draft(("alibaba", "PET")))
    planner = PlannerAgent(gateway, PromptRegistry(), _catalogue(), ALL_ON)
    with pytest.raises(NoViablePlatform, match="alibaba"):
        await planner.plan(
            tenant_id=TENANT, mission_id="m-1", request=_request(), config_version="v7"
        )


async def test_no_enabled_platform_fails_before_calling_the_model() -> None:
    gateway = _Gateway(_plan_draft(("mock-a", "PET")))
    planner = PlannerAgent(gateway, PromptRegistry(), _catalogue(), StaticFlags({}))
    with pytest.raises(NoViablePlatform, match="no platform is enabled"):
        await planner.plan(
            tenant_id=TENANT, mission_id="m-1", request=_request(), config_version="v7"
        )
    assert gateway.calls == []


async def test_searchable_is_sorted_and_flag_gated() -> None:
    planner = PlannerAgent(
        _Gateway(_plan_draft(("mock-a", "x"))), PromptRegistry(), _catalogue(), ALL_ON
    )
    assert [p.platform_id for p in planner.searchable()] == ["mock-a", "mock-b"]


async def test_the_prompt_carries_the_request_and_only_the_catalogue_metadata() -> None:
    gateway = _Gateway(_plan_draft(("mock-a", "PET")))
    planner = PlannerAgent(gateway, PromptRegistry(), _catalogue(), ALL_ON)
    await planner.plan(tenant_id=TENANT, mission_id="m-1", request=_request(), config_version="v7")
    user = gateway.calls[0]["messages"][1]["content"]
    assert "Botellas PET 500ml" in user
    payload = json.loads(user.split("Platform catalogue (JSON):")[1].split("Return a JSON")[0])
    assert {p["platform_id"] for p in payload} == {"mock-a", "mock-b"}
    assert payload[0]["transport"] in {"http", "browser"}


def _request() -> Any:
    from apex.agents.sourcing import QuantityTier, SourcingRequest

    return SourcingRequest(
        id="sr-1",
        tenant_id=TENANT,
        spec="Botellas PET 500ml",
        quantity_tiers=[QuantityTier(min_quantity=5000)],
        deadline=date(2027, 6, 1),
        deadline_text=None,
        destination_country="ES",
        certifications=["food grade"],
        budget_text="4500 EUR",
        missing_fields=[],
        created_at=NOW,
        config_version="v7",
    )
