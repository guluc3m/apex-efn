"""SupervisorAgent (D4-13 step 3): stuck-mission detection, token-budget control and escalation.

Pure logic over ports. The supervisor never reads the wall clock (``now`` is passed in), never calls an
LLM and never hardcodes a threshold: every limit comes from a required :class:`SupervisorPolicy`. It
only *decides*; effects (recording an incident, asking the gateway to degrade, notifying a human) go
through :class:`SupervisorPorts`, whose default implementations raise ``NotImplementedError`` naming the
owning lane.

Spec references: §4 (``SupervisorAgent``: quality control, blockage detection, escalation, cost
control) and §5.6 / acceptance criterion 28 (the per-mission LLM token budget is a hard limit: degrade
to a cheaper model or stop with a warning).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from apex.common.clock import _require_aware_utc


class MissionPhase(StrEnum):
    """Coarse phase of a mission, as the supervisor sees it.

    The offer-level states live in the mission graph (spec §4); the supervisor only needs to know
    whether a mission is making progress, waiting for a human, or finished.
    """

    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"
    COMPLETED = "completed"
    FAILED = "failed"


class MissionHealth(StrEnum):
    """Verdict for one mission in one supervisor tick."""

    HEALTHY = "healthy"
    STUCK = "stuck"


class BudgetState(StrEnum):
    """Token-budget verdict for one mission (criterion 28)."""

    WITHIN_BUDGET = "within_budget"
    EXHAUSTED = "exhausted"


class SupervisorAction(StrEnum):
    """What the supervisor asks for. The caller (graph, worker or API) performs the effect."""

    #: Nothing to do for this mission.
    NONE = "none"
    #: Mission is stuck: record an incident and escalate to a human.
    ESCALATE_STUCK = "escalate_stuck"
    #: Token budget is used up: degrade to the cheap model tier, keep going.
    DEGRADE_LLM = "degrade_llm"
    #: Token budget is used up and degradation is not allowed: stop with a warning.
    STOP_BUDGET = "stop_budget"


class EscalationSeverity(StrEnum):
    """Severity of an escalation. ``CRITICAL`` for budget stops, ``HIGH`` for stuck missions."""

    HIGH = "high"
    CRITICAL = "critical"


class EscalationReason(StrEnum):
    """Closed list of escalation reasons (no free text; the incident carries the numbers)."""

    MISSION_STUCK = "mission_stuck"
    TOKEN_BUDGET_EXHAUSTED = "token_budget_exhausted"


@dataclass(frozen=True)
class SupervisorPolicy:
    """Thresholds and switches. Required fields, no defaults: they come from tenant config (D4-03).

    ``stuck_after`` is a duration, not a number of minutes, so the unit is explicit at the call site.
    """

    stuck_after: timedelta
    #: When the budget is exhausted, degrade to the cheap tier instead of stopping (spec §5.6).
    degrade_on_budget_exhausted: bool

    def __post_init__(self) -> None:
        if self.stuck_after <= timedelta(0):
            raise ValueError("stuck_after must be positive")


@dataclass(frozen=True)
class MissionSnapshot:
    """What the supervisor needs to know about one mission. Built by the caller from the checkpoint."""

    mission_id: str
    tenant_id: str
    phase: MissionPhase
    #: Last state transition or progress event. ``None`` means the mission has not started yet.
    last_progress_at: datetime | None
    tokens_used: int
    token_budget: int

    def __post_init__(self) -> None:
        if self.last_progress_at is not None:
            object.__setattr__(self, "last_progress_at", _require_aware_utc(self.last_progress_at))
        if self.tokens_used < 0:
            raise ValueError("tokens_used must be >= 0")
        if self.token_budget < 0:
            raise ValueError("token_budget must be >= 0")

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.token_budget - self.tokens_used)


@dataclass(frozen=True)
class Escalation:
    """An incident for a human. Carries the numbers that triggered it, never free-form LLM text."""

    mission_id: str
    tenant_id: str
    reason: EscalationReason
    severity: EscalationSeverity
    raised_at: datetime
    #: Seconds since the last progress event; ``None`` when the mission never progressed.
    idle_seconds: int | None
    tokens_used: int
    token_budget: int


@dataclass(frozen=True)
class MissionAssessment:
    """Supervisor verdict for one mission."""

    mission_id: str
    health: MissionHealth
    budget: BudgetState
    actions: tuple[SupervisorAction, ...]
    escalation: Escalation | None

    @property
    def is_healthy(self) -> bool:
        return self.health is MissionHealth.HEALTHY and self.budget is BudgetState.WITHIN_BUDGET


class SupervisorPort(Protocol):
    """Read side: missions the supervisor should look at."""

    async def active_missions(self) -> list[MissionSnapshot]: ...


class IncidentSink(Protocol):
    """Write side: record an escalation (audit event, gate queue item or notification)."""

    async def record(self, escalation: Escalation) -> None: ...


class BudgetController(Protocol):
    """Write side: tell the LLM layer to degrade or stop for a mission (spec §5.6)."""

    async def degrade(self, mission_id: str) -> None: ...

    async def stop(self, mission_id: str, reason: str) -> None: ...


class UnwiredMissionSource:
    async def active_missions(self) -> list[MissionSnapshot]:
        raise NotImplementedError(
            "supervisor mission source is not wired yet (owner: DEV-4, D4-06 mission graph)"
        )


class UnwiredIncidentSink:
    async def record(self, escalation: Escalation) -> None:
        raise NotImplementedError(
            "supervisor incident sink is not wired yet (owner: DEV-4, D4-11 gate queue / DEV-2 audit)"
        )


class UnwiredBudgetController:
    async def degrade(self, mission_id: str) -> None:
        raise NotImplementedError(
            "budget controller is not wired yet (owner: DEV-4, D4-04 LLMGateway)"
        )

    async def stop(self, mission_id: str, reason: str) -> None:
        raise NotImplementedError(
            "budget controller is not wired yet (owner: DEV-4, D4-04 LLMGateway)"
        )


@dataclass(frozen=True)
class SupervisorPorts:
    """Dependencies of the supervisor. Build with ``SupervisorPorts.unwired()`` and replace fields."""

    missions: SupervisorPort
    incidents: IncidentSink
    budget: BudgetController

    @classmethod
    def unwired(cls) -> SupervisorPorts:
        return cls(
            missions=UnwiredMissionSource(),
            incidents=UnwiredIncidentSink(),
            budget=UnwiredBudgetController(),
        )


@dataclass(frozen=True)
class SupervisorReport:
    """Outcome of one supervisor tick (one scheduled run)."""

    checked_at: datetime
    assessments: tuple[MissionAssessment, ...]

    @property
    def escalations(self) -> tuple[Escalation, ...]:
        return tuple(a.escalation for a in self.assessments if a.escalation is not None)


def assess_mission(
    mission: MissionSnapshot, *, now: datetime, policy: SupervisorPolicy
) -> MissionAssessment:
    """Classify one mission. Pure: no I/O, no clock, no randomness.

    Rules:

    * ``COMPLETED`` / ``FAILED`` missions are never stuck and never consume budget.
    * ``AWAITING_HUMAN`` missions are not stuck by definition (the human owns the clock), but their
      budget is still enforced: a mission that keeps burning tokens while waiting is a cost leak.
    * ``RUNNING`` missions are stuck when ``now - last_progress_at >= stuck_after``. ``last_progress_at``
      is the creation time for a mission that has not progressed yet, so a never-started mission is
      stuck once it is older than ``stuck_after``. ``None`` (the caller has no timestamp at all) is
      reported as stuck immediately: the supervisor never assumes progress it cannot see.
    """
    moment = _require_aware_utc(now)
    if mission.phase in (MissionPhase.COMPLETED, MissionPhase.FAILED):
        return MissionAssessment(
            mission_id=mission.mission_id,
            health=MissionHealth.HEALTHY,
            budget=BudgetState.WITHIN_BUDGET,
            actions=(SupervisorAction.NONE,),
            escalation=None,
        )

    actions: list[SupervisorAction] = []
    escalation: Escalation | None = None
    idle_seconds: int | None = None

    stuck = False
    if mission.phase is MissionPhase.RUNNING:
        if mission.last_progress_at is None:
            stuck = True
        else:
            idle = moment - mission.last_progress_at
            idle_seconds = int(idle.total_seconds())
            stuck = idle >= policy.stuck_after

    if stuck:
        actions.append(SupervisorAction.ESCALATE_STUCK)
        escalation = Escalation(
            mission_id=mission.mission_id,
            tenant_id=mission.tenant_id,
            reason=EscalationReason.MISSION_STUCK,
            severity=EscalationSeverity.HIGH,
            raised_at=moment,
            idle_seconds=idle_seconds,
            tokens_used=mission.tokens_used,
            token_budget=mission.token_budget,
        )

    budget = BudgetState.WITHIN_BUDGET
    if mission.tokens_used >= mission.token_budget:
        budget = BudgetState.EXHAUSTED
        if policy.degrade_on_budget_exhausted:
            actions.append(SupervisorAction.DEGRADE_LLM)
        else:
            actions.append(SupervisorAction.STOP_BUDGET)
            budget_escalation = Escalation(
                mission_id=mission.mission_id,
                tenant_id=mission.tenant_id,
                reason=EscalationReason.TOKEN_BUDGET_EXHAUSTED,
                severity=EscalationSeverity.CRITICAL,
                raised_at=moment,
                idle_seconds=idle_seconds,
                tokens_used=mission.tokens_used,
                token_budget=mission.token_budget,
            )
            # A budget stop is the more severe incident; it replaces a stuck escalation for the same
            # mission so a human gets one actionable item, not two.
            escalation = budget_escalation

    if not actions:
        actions.append(SupervisorAction.NONE)

    return MissionAssessment(
        mission_id=mission.mission_id,
        health=MissionHealth.STUCK if stuck else MissionHealth.HEALTHY,
        budget=budget,
        actions=tuple(actions),
        escalation=escalation,
    )


class SupervisorAgent:
    """Runs one supervisor tick: assess every active mission, then apply the side effects.

    Side effects are applied for assessments that carry them, in a stable order (missions sorted by
    id), so a re-run after a crash converges. Ports must be idempotent per ``(mission_id, reason)``:
    recording the same escalation twice is acceptable, double-degrading is not.
    """

    def __init__(self, ports: SupervisorPorts, policy: SupervisorPolicy) -> None:
        self._ports = ports
        self._policy = policy

    @property
    def policy(self) -> SupervisorPolicy:
        return self._policy

    async def tick(self, now: datetime) -> SupervisorReport:
        """Assess all active missions at ``now`` and apply the resulting actions."""
        moment = _require_aware_utc(now)
        missions = sorted(await self._ports.missions.active_missions(), key=lambda m: m.mission_id)
        assessments = tuple(
            assess_mission(mission, now=moment, policy=self._policy) for mission in missions
        )
        for assessment in assessments:
            await self._apply(assessment)
        return SupervisorReport(checked_at=moment, assessments=assessments)

    async def _apply(self, assessment: MissionAssessment) -> None:
        if SupervisorAction.ESCALATE_STUCK in assessment.actions and assessment.escalation:
            await self._ports.incidents.record(assessment.escalation)
        if SupervisorAction.DEGRADE_LLM in assessment.actions:
            await self._ports.budget.degrade(assessment.mission_id)
        if SupervisorAction.STOP_BUDGET in assessment.actions:
            await self._ports.budget.stop(
                assessment.mission_id, EscalationReason.TOKEN_BUDGET_EXHAUSTED.value
            )
            if assessment.escalation:
                await self._ports.incidents.record(assessment.escalation)


__all__ = [
    "BudgetController",
    "BudgetState",
    "Escalation",
    "EscalationReason",
    "EscalationSeverity",
    "IncidentSink",
    "MissionAssessment",
    "MissionHealth",
    "MissionPhase",
    "MissionSnapshot",
    "SupervisorAction",
    "SupervisorAgent",
    "SupervisorPolicy",
    "SupervisorPort",
    "SupervisorPorts",
    "SupervisorReport",
    "UnwiredBudgetController",
    "UnwiredIncidentSink",
    "UnwiredMissionSource",
    "assess_mission",
]
