"""IntakeAgent and PlannerAgent (D4-08, spec §3.2).

The LLM only *drafts*: it turns free text into a structured request and proposes search steps. Code decides
which platforms are actually searched (enabled by feature flag, present in the catalogue, transport known)
and rejects anything the model invented. Nothing here computes a price, a budget or a ranking.

Prompts are versioned (D4-05): ``intake_sourcing_request@vN`` and ``planner_sourcing_plan@vN``; the version
string travels to ``LLMEvent`` so an evaluation is reproducible.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from apex.agents.schemas import SourcingPlanDraft, SourcingRequestDraft
from apex.common.clock import Clock
from apex.llm.config import LLMRole
from apex.llm.gateway import LLMGateway
from apex.llm.prompts import PromptRegistry
from apex.platform.flags import FlagProvider

Transport = Literal["http", "browser"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QuantityTier(_Model):
    min_quantity: int = Field(gt=0)


class SourcingRequest(_Model):
    """A normalised purchase need. ``budget_text`` stays the user's words: code parses money, not the LLM."""

    id: str
    tenant_id: str
    spec: str = Field(min_length=1)
    quantity_tiers: list[QuantityTier]
    deadline: date | None
    deadline_text: str | None
    destination_country: str | None
    certifications: list[str]
    budget_text: str | None
    missing_fields: list[str]
    created_at: datetime
    config_version: str

    @property
    def total_quantity(self) -> int:
        return max((t.min_quantity for t in self.quantity_tiers), default=0)


class PlatformInfo(_Model):
    """One searchable platform as the adapters advertise it (D5-03 fills this in)."""

    platform_id: str = Field(min_length=1)
    transport: Transport
    regions: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()


class PlatformCatalogue(Protocol):
    """Read side: the platforms this deployment knows about, before feature flags are applied."""

    def platforms(self) -> list[PlatformInfo]: ...


class StaticCatalogue:
    def __init__(self, platforms: list[PlatformInfo]) -> None:
        self._platforms = list(platforms)

    def platforms(self) -> list[PlatformInfo]:
        return list(self._platforms)


class PlanStep(_Model):
    platform_id: str
    transport: Transport
    query: str = Field(min_length=1)
    tier_index: int | None = Field(default=None, ge=0)


class RejectedStep(_Model):
    """A step the model proposed that code refused. Visible, never silently dropped."""

    platform_id: str
    reason: str


class PlanRejectionReason(StrEnum):
    NOT_IN_CATALOGUE = "not_in_catalogue"
    PLATFORM_DISABLED = "platform_disabled"


class SourcingPlan(_Model):
    steps: list[PlanStep] = Field(min_length=1)
    rationale: str
    rejected_steps: list[RejectedStep] = Field(default_factory=list)
    config_version: str


class NoViablePlatform(Exception):
    """Every proposed step was rejected, or the enabled catalogue is empty. A loud failure, not an empty plan."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class IntakeAgent:
    """Free text -> :class:`SourcingRequest` (spec §3.2)."""

    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry, clock: Clock) -> None:
        self._gateway = gateway
        self._prompts = prompts
        self._clock = clock

    async def parse(
        self,
        *,
        request_id: str,
        tenant_id: str,
        mission_id: str,
        text: str,
        base_currency: str,
        today: date,
        config_version: str,
    ) -> SourcingRequest:
        rendered = self._prompts.render(
            "intake_sourcing_request",
            today=today.isoformat(),
            base_currency=base_currency,
            user_text=text,
        )
        draft = await self._gateway.chat_structured(
            LLMRole.EXTRACTOR,
            rendered.messages,
            SourcingRequestDraft,
            mission_id=mission_id,
            tenant_id=tenant_id,
            prompt_version=rendered.prompt_version,
        )
        return SourcingRequest(
            id=request_id,
            tenant_id=tenant_id,
            spec=draft.spec,
            quantity_tiers=[
                QuantityTier(min_quantity=t.min_quantity) for t in draft.quantity_tiers
            ],
            deadline=_parse_deadline(draft.deadline),
            deadline_text=draft.deadline_text,
            destination_country=draft.destination_country,
            certifications=list(draft.certifications),
            budget_text=draft.budget_text,
            missing_fields=list(draft.missing_fields),
            created_at=self._clock.now(),
            config_version=config_version,
        )


def _parse_deadline(raw: str | None) -> date | None:
    """A deadline is a date only when the model produced an unambiguous ISO date; otherwise it stays text."""
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


class PlannerAgent:
    """Sourcing request -> :class:`SourcingPlan` (spec §3.2).

    Code, not the model, decides the searchable set: a platform is considered only when it is in the
    catalogue **and** ``platform.<id>.enabled`` is on. Steps naming anything else are rejected and reported.
    """

    def __init__(
        self,
        gateway: LLMGateway,
        prompts: PromptRegistry,
        catalogue: PlatformCatalogue,
        flags: FlagProvider,
    ) -> None:
        self._gateway = gateway
        self._prompts = prompts
        self._catalogue = catalogue
        self._flags = flags

    def searchable(self) -> list[PlatformInfo]:
        """Platforms that are in the catalogue and enabled by feature flag, in a stable order."""
        enabled = [
            p for p in self._catalogue.platforms() if self._flags.is_platform_enabled(p.platform_id)
        ]
        return sorted(enabled, key=lambda p: p.platform_id)

    async def plan(
        self,
        *,
        tenant_id: str,
        mission_id: str,
        request: SourcingRequest,
        config_version: str,
    ) -> SourcingPlan:
        available = self.searchable()
        if not available:
            raise NoViablePlatform(
                "no platform is enabled: check platform.<id>.enabled feature flags"
            )
        rendered = self._prompts.render(
            "planner_sourcing_plan",
            request_json=request.model_dump_json(),
            platforms_json=_platforms_json(available),
        )
        draft = await self._gateway.chat_structured(
            LLMRole.PLANNER,
            rendered.messages,
            SourcingPlanDraft,
            mission_id=mission_id,
            tenant_id=tenant_id,
            prompt_version=rendered.prompt_version,
        )
        by_id = {p.platform_id: p for p in available}
        known = {p.platform_id for p in self._catalogue.platforms()}
        steps: list[PlanStep] = []
        rejected: list[RejectedStep] = []
        for step in draft.steps:
            platform = by_id.get(step.platform_id)
            if platform is None:
                reason = (
                    PlanRejectionReason.PLATFORM_DISABLED
                    if step.platform_id in known
                    else PlanRejectionReason.NOT_IN_CATALOGUE
                )
                rejected.append(RejectedStep(platform_id=step.platform_id, reason=reason.value))
                continue
            steps.append(
                PlanStep(
                    platform_id=platform.platform_id,
                    transport=platform.transport,
                    query=step.query,
                    tier_index=step.tier_index,
                )
            )
        if not steps:
            raise NoViablePlatform(
                "the planner proposed no usable platform; rejected: "
                + ", ".join(f"{r.platform_id} ({r.reason})" for r in rejected)
            )
        return SourcingPlan(
            steps=steps,
            rationale=draft.rationale,
            rejected_steps=rejected,
            config_version=config_version,
        )


def _platforms_json(platforms: list[PlatformInfo]) -> str:
    """The catalogue as the prompt sees it: ids, transport and coverage only."""
    import json

    payload: list[Mapping[str, Any]] = [
        {
            "platform_id": p.platform_id,
            "transport": p.transport,
            "regions": list(p.regions),
            "categories": list(p.categories),
        }
        for p in platforms
    ]
    return json.dumps(payload, ensure_ascii=False)


__all__ = [
    "IntakeAgent",
    "NoViablePlatform",
    "PlanRejectionReason",
    "PlanStep",
    "PlannerAgent",
    "PlatformCatalogue",
    "PlatformInfo",
    "QuantityTier",
    "RejectedStep",
    "SourcingPlan",
    "SourcingRequest",
    "StaticCatalogue",
    "Transport",
]
