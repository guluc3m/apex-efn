"""SourcingService: the use cases behind ``/v1/sourcing-requests`` and ``/v1/missions`` (D4-08).

Ordering is code: create the request (LLM drafts it), create the mission, plan it (LLM drafts the steps,
code decides which platforms are searchable), append the events. Every failure after the mission exists is
recorded on the mission as ``FAILED`` with a reason, so a caller always has something to poll.

The service owns no HTTP concern and no clock of its own: both are injected.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from apex.agents.missions import (
    Mission,
    MissionEventBus,
    MissionEventType,
    MissionStatus,
    MissionStore,
    apply_event,
    transition,
)
from apex.agents.sourcing import (
    IntakeAgent,
    NoViablePlatform,
    PlannerAgent,
    QuantityTier,
    SourcingPlan,
    SourcingRequest,
)
from apex.common.clock import Clock
from apex.common.ids import IdGenerator
from apex.llm.structured import StructuredOutputError


@dataclass(frozen=True)
class SourcingServiceDeps:
    intake: IntakeAgent
    planner: PlannerAgent
    store: MissionStore
    bus: MissionEventBus
    clock: Clock
    ids: IdGenerator
    config_version: Callable[[str], str]
    """``tenant_id -> config_version``. Supplied by the tenant config service (D4-03); never a literal here."""


class SourcingService:
    def __init__(self, deps: SourcingServiceDeps) -> None:
        self._deps = deps

    async def create_request(
        self,
        *,
        tenant_id: str,
        text: str,
        base_currency: str,
        today: date,
    ) -> SourcingRequest:
        """Normalise free text into a request. The id is generated here so the caller can link a mission."""
        return await self._deps.intake.parse(
            request_id=self._deps.ids.new_id(),
            tenant_id=tenant_id,
            mission_id=f"intake:{tenant_id}",
            text=text,
            base_currency=base_currency,
            today=today,
            config_version=self._deps.config_version(tenant_id),
        )

    def build_request(
        self,
        *,
        tenant_id: str,
        request_id: str,
        spec: str,
        quantity_tiers: list[QuantityTier],
        deadline: date | None,
        destination_country: str | None,
        certifications: list[str],
        budget_text: str | None,
    ) -> SourcingRequest:
        """Assemble a request from values the caller already holds (a stored request, or an explicit body).

        The clock and the config version come from here, never from the caller, so two paths cannot disagree.
        """
        return SourcingRequest(
            id=request_id,
            tenant_id=tenant_id,
            spec=spec,
            quantity_tiers=quantity_tiers,
            deadline=deadline,
            deadline_text=None,
            destination_country=destination_country,
            certifications=certifications,
            budget_text=budget_text,
            missing_fields=[],
            created_at=self._deps.clock.now(),
            config_version=self._deps.config_version(tenant_id),
        )

    async def create_mission(
        self,
        *,
        tenant_id: str,
        request: SourcingRequest,
    ) -> Mission:
        """Create the mission and plan it inline.

        Planning is one LLM call, so it runs before the response: the caller gets a mission that is either
        ``PLANNED`` (with its plan) or ``FAILED`` (with a reason). D4-09 takes it from ``PLANNED``.
        """
        now = self._deps.clock.now()
        config_version = self._deps.config_version(tenant_id)
        mission = Mission(
            id=self._deps.ids.new_id(),
            tenant_id=tenant_id,
            sourcing_request_id=request.id,
            status=MissionStatus.QUEUED,
            config_version=config_version,
            created_at=now,
            updated_at=now,
        )
        mission = apply_event(
            mission,
            MissionEventType.MISSION_CREATED,
            at=now,
            payload={"sourcing_request_id": request.id, "config_version": config_version},
        )
        await self._deps.store.create(mission)
        self._deps.bus.publish(mission.id, mission.events[-1])
        return await self._plan(mission, request)

    async def _plan(self, mission: Mission, request: SourcingRequest) -> Mission:
        at = self._deps.clock.now()
        mission = transition(mission, MissionStatus.PLANNING, at=at)
        mission = apply_event(mission, MissionEventType.PLANNING_STARTED, at=at)
        await self._deps.store.save(mission)
        self._deps.bus.publish(mission.id, mission.events[-1])
        try:
            plan: SourcingPlan = await self._deps.planner.plan(
                tenant_id=mission.tenant_id,
                mission_id=mission.id,
                request=request,
                config_version=mission.config_version,
            )
        except (NoViablePlatform, StructuredOutputError) as exc:
            return await self._fail(mission, _reason(exc))
        at = self._deps.clock.now()
        mission = transition(mission, MissionStatus.PLANNED, at=at).model_copy(
            update={"plan": plan}
        )
        mission = apply_event(
            mission,
            MissionEventType.PLAN_READY,
            at=at,
            payload={
                "steps": len(plan.steps),
                "platforms": sorted({s.platform_id for s in plan.steps}),
                "rejected_steps": [r.model_dump(mode="json") for r in plan.rejected_steps],
            },
        )
        await self._deps.store.save(mission)
        self._deps.bus.publish(mission.id, mission.events[-1])
        return mission

    async def _fail(self, mission: Mission, reason: str) -> Mission:
        at = self._deps.clock.now()
        mission = transition(mission, MissionStatus.FAILED, at=at).model_copy(
            update={"failure_reason": reason}
        )
        mission = apply_event(
            mission, MissionEventType.MISSION_FAILED, at=at, payload={"reason": reason}
        )
        await self._deps.store.save(mission)
        self._deps.bus.publish(mission.id, mission.events[-1])
        return mission

    async def get_mission(self, *, tenant_id: str, mission_id: str) -> Mission:
        mission = await self._deps.store.get(tenant_id, mission_id)
        if mission is None:
            raise MissionMissing(mission_id)
        return mission


class MissionMissing(Exception):
    """The mission does not exist for this tenant. Indistinguishable from another tenant's mission on purpose."""

    def __init__(self, mission_id: str) -> None:
        super().__init__(f"mission {mission_id} not found")
        self.mission_id = mission_id


def _reason(exc: Exception) -> str:
    """A short, stable failure reason. Never the model's text and never a stack trace."""
    if isinstance(exc, NoViablePlatform):
        return f"no_viable_platform: {exc.detail}"
    if isinstance(exc, StructuredOutputError):
        return "planner_output_invalid"
    return type(exc).__name__


__all__ = ["MissionMissing", "SourcingService", "SourcingServiceDeps"]
