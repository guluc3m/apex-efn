"""Mission runner: drives a planned mission through sourcing, analysis and the gate (D4-09/D4-10/D4-11).

This is the piece that connects the services. It is deliberately a straight line of steps, each one a call
to a service that is already tested on its own:

    PLANNED -> RUNNING -> scrape -> analyse every offer -> queue what needs a human -> stay RUNNING

The mission stays ``RUNNING`` after that on purpose: the deals are now waiting for signed human decisions
(D4-11), so the mission is not complete. It becomes ``COMPLETED`` when the decisions are in, which is the
graph's job (D4-06) once signing is wired.

A step whose port is not wired (the browser worker, the FX engine, the trust/sanity/finance engines) fails
the mission with a reason that names the owning lane, instead of leaving it silently stuck.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from apex.agents.analysis import AnalysisNodes
from apex.agents.gate import GateAgent, GateRules
from apex.agents.missions import (
    Mission,
    MissionEventBus,
    MissionEventType,
    MissionStatus,
    MissionStore,
    apply_event,
    transition,
)
from apex.agents.scraping import ScrapingService
from apex.agents.sourcing import SourcingPlan
from apex.common.clock import Clock
from apex.common.metrics import get_metrics


class MissionNotRunnable(Exception):
    """The mission is not in a state this runner can advance."""

    def __init__(self, mission_id: str, status: MissionStatus) -> None:
        super().__init__(f"mission {mission_id} is {status.value}, not planned")
        self.mission_id = mission_id
        self.status = status


@dataclass(frozen=True)
class MissionRunnerDeps:
    scraping: ScrapingService
    nodes: AnalysisNodes
    gate: GateAgent
    store: MissionStore
    bus: MissionEventBus
    clock: Clock
    rules_for: Callable[[str], GateRules]
    """``tenant_id -> GateRules``, read from tenant config. Never a literal here."""
    mission_cost_minor: Callable[[str], int | None] = lambda _mission_id: None
    """``mission_id -> cost in minor units``, or ``None`` when nothing is priced. Injected: the runner must
    not know about the gateway."""


@dataclass(frozen=True)
class MissionRunResult:
    mission: Mission
    offers_collected: int
    offers_analysed: int
    gate_items: int
    failed_reason: str | None = None


class MissionRunner:
    def __init__(self, deps: MissionRunnerDeps) -> None:
        self._deps = deps

    async def run(self, *, tenant_id: str, mission_id: str) -> MissionRunResult:
        """Advance one mission as far as the wired services allow."""
        mission = await self._deps.store.get(tenant_id, mission_id)
        if mission is None:
            raise LookupError(f"mission {mission_id} not found")
        if mission.status is not MissionStatus.PLANNED:
            raise MissionNotRunnable(mission_id, mission.status)
        plan = mission.plan
        if plan is None:
            raise MissionNotRunnable(mission_id, mission.status)

        mission = await self._publish(
            transition(mission, MissionStatus.RUNNING, at=self._deps.clock.now()),
            MissionEventType.SOURCING_STARTED,
            payload={"platforms": [step.platform_id for step in plan.steps]},
        )
        try:
            return await self._run(mission, plan)
        except NotImplementedError as exc:
            # A port is not wired: fail loudly with the owner, never leave the mission stuck.
            return await self._fail(mission, f"not_wired: {exc}")

    async def _run(self, mission: Mission, plan: SourcingPlan) -> MissionRunResult:
        scrape = await self._deps.scraping.scrape(
            tenant_id=mission.tenant_id,
            mission_id=mission.id,
            plan=plan,
            quantity=mission.quantity,
        )
        mission = await self._publish(
            mission,
            MissionEventType.OFFERS_COLLECTED,
            payload={
                "offers_collected": scrape.collected,
                "offers_kept": scrape.kept,
                "platforms": scrape.platforms,
                "duplicates": len(scrape.duplicates),
                "skipped": len(scrape.skipped),
                "fx_provisional": scrape.fx_provisional,
            },
        )
        rules = self._deps.rules_for(mission.tenant_id)
        analysed = 0
        gate_items = 0
        for offer, _ in await self._deps.nodes.mission_offers(
            tenant_id=mission.tenant_id, mission_id=mission.id
        ):
            analysis = await self._deps.nodes.analyse_offer(
                tenant_id=mission.tenant_id, offer=offer
            )
            analysed += 1
            item = await self._deps.gate.enqueue(
                tenant_id=mission.tenant_id, offer=offer, analysis=analysis, rules=rules
            )
            if item is not None:
                gate_items += 1
        mission = await self._publish(
            mission,
            MissionEventType.ANALYSIS_COMPLETED,
            payload={"offers_analysed": analysed, "gate_items": gate_items},
        )
        return MissionRunResult(
            mission=mission,
            offers_collected=scrape.collected,
            offers_analysed=analysed,
            gate_items=gate_items,
        )

    def _record_cost(self, mission_id: str) -> None:
        """``apex.mission.llm_cost``: one observation per mission at close, with no labels.

        The catalogue says "one observation per mission when it closes", and a failed mission has closed.
        """
        cost = self._deps.mission_cost_minor(mission_id)
        if cost is None:
            return
        get_metrics().mission_llm_cost.record(cost / 100.0)

    async def _fail(self, mission: Mission, reason: str) -> MissionRunResult:
        self._record_cost(mission.id)
        at = self._deps.clock.now()
        failed = transition(mission, MissionStatus.FAILED, at=at).model_copy(
            update={"failure_reason": reason}
        )
        failed = apply_event(
            failed, MissionEventType.MISSION_FAILED, at=at, payload={"reason": reason}
        )
        await self._deps.store.save(failed)
        self._deps.bus.publish(failed.id, failed.events[-1])
        return MissionRunResult(
            mission=failed,
            offers_collected=0,
            offers_analysed=0,
            gate_items=0,
            failed_reason=reason,
        )

    async def _publish(
        self, mission: Mission, event: MissionEventType, *, payload: dict[str, Any]
    ) -> Mission:
        updated = apply_event(mission, event, at=self._deps.clock.now(), payload=payload)
        await self._deps.store.save(updated)
        self._deps.bus.publish(updated.id, updated.events[-1])
        return updated


__all__ = [
    "MissionNotRunnable",
    "MissionRunResult",
    "MissionRunner",
    "MissionRunnerDeps",
]
