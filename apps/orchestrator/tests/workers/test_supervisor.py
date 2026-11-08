"""SupervisorAgent: stuck-mission detection, token-budget control and escalation (pure logic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from apex.agents.supervisor import (
    BudgetState,
    Escalation,
    EscalationReason,
    EscalationSeverity,
    MissionHealth,
    MissionPhase,
    MissionSnapshot,
    SupervisorAction,
    SupervisorAgent,
    SupervisorPolicy,
    SupervisorPorts,
    UnwiredBudgetController,
    UnwiredIncidentSink,
    UnwiredMissionSource,
    assess_mission,
)

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
POLICY = SupervisorPolicy(stuck_after=timedelta(minutes=30), degrade_on_budget_exhausted=True)
STOP_POLICY = SupervisorPolicy(stuck_after=timedelta(minutes=30), degrade_on_budget_exhausted=False)


def _mission(
    *,
    mission_id: str = "m-1",
    phase: MissionPhase = MissionPhase.RUNNING,
    idle: timedelta = timedelta(minutes=1),
    tokens_used: int = 100,
    token_budget: int = 1000,
    tenant_id: str = "t-1",
) -> MissionSnapshot:
    return MissionSnapshot(
        mission_id=mission_id,
        tenant_id=tenant_id,
        phase=phase,
        last_progress_at=NOW - idle,
        tokens_used=tokens_used,
        token_budget=token_budget,
    )


# --- policy and snapshot validation ---------------------------------------------------------------


def test_policy_requires_positive_stuck_window() -> None:
    with pytest.raises(ValueError):
        SupervisorPolicy(stuck_after=timedelta(0), degrade_on_budget_exhausted=True)


def test_policy_has_no_defaults() -> None:
    with pytest.raises(TypeError):
        SupervisorPolicy()  # type: ignore[call-arg]


def test_snapshot_rejects_negative_tokens_and_naive_times() -> None:
    with pytest.raises(ValueError):
        _mission(tokens_used=-1)
    with pytest.raises(ValueError):
        MissionSnapshot(
            mission_id="m",
            tenant_id="t",
            phase=MissionPhase.RUNNING,
            last_progress_at=datetime(2026, 3, 1, 12, 0),  # naive
            tokens_used=0,
            token_budget=1,
        )


def test_snapshot_normalises_to_utc_and_reports_remaining() -> None:
    m = _mission(tokens_used=400, token_budget=1000)
    assert m.tokens_remaining == 600
    assert m.last_progress_at is not None and m.last_progress_at.tzinfo is UTC
    assert _mission(tokens_used=1200, token_budget=1000).tokens_remaining == 0


# --- stuck-mission detection ---------------------------------------------------------------------


def test_running_mission_with_recent_progress_is_healthy() -> None:
    a = assess_mission(_mission(idle=timedelta(minutes=29)), now=NOW, policy=POLICY)
    assert a.health is MissionHealth.HEALTHY
    assert a.budget is BudgetState.WITHIN_BUDGET
    assert a.actions == (SupervisorAction.NONE,)
    assert a.escalation is None
    assert a.is_healthy


def test_running_mission_at_exactly_the_window_is_stuck() -> None:
    a = assess_mission(_mission(idle=timedelta(minutes=30)), now=NOW, policy=POLICY)
    assert a.health is MissionHealth.STUCK
    assert a.actions == (SupervisorAction.ESCALATE_STUCK,)
    assert a.escalation is not None
    assert a.escalation.reason is EscalationReason.MISSION_STUCK
    assert a.escalation.severity is EscalationSeverity.HIGH
    assert a.escalation.idle_seconds == 30 * 60
    assert a.escalation.raised_at == NOW
    assert a.escalation.mission_id == "m-1" and a.escalation.tenant_id == "t-1"


def test_running_mission_without_any_timestamp_is_stuck() -> None:
    m = MissionSnapshot(
        mission_id="m-9",
        tenant_id="t-1",
        phase=MissionPhase.RUNNING,
        last_progress_at=None,
        tokens_used=0,
        token_budget=10,
    )
    a = assess_mission(m, now=NOW, policy=POLICY)
    assert a.health is MissionHealth.STUCK
    assert a.escalation is not None and a.escalation.idle_seconds is None


def test_awaiting_human_is_never_stuck() -> None:
    a = assess_mission(
        _mission(phase=MissionPhase.AWAITING_HUMAN, idle=timedelta(days=3)), now=NOW, policy=POLICY
    )
    assert a.health is MissionHealth.HEALTHY
    assert a.actions == (SupervisorAction.NONE,)


@pytest.mark.parametrize("phase", [MissionPhase.COMPLETED, MissionPhase.FAILED])
def test_terminal_missions_are_ignored_even_when_over_budget(phase: MissionPhase) -> None:
    a = assess_mission(
        _mission(phase=phase, idle=timedelta(days=1), tokens_used=5000, token_budget=10),
        now=NOW,
        policy=POLICY,
    )
    assert a.is_healthy
    assert a.actions == (SupervisorAction.NONE,)
    assert a.escalation is None


# --- token budget (criterion 28) -----------------------------------------------------------------


def test_budget_just_below_limit_is_within() -> None:
    a = assess_mission(_mission(tokens_used=999, token_budget=1000), now=NOW, policy=POLICY)
    assert a.budget is BudgetState.WITHIN_BUDGET
    assert a.actions == (SupervisorAction.NONE,)


def test_budget_at_limit_degrades_when_allowed() -> None:
    a = assess_mission(_mission(tokens_used=1000, token_budget=1000), now=NOW, policy=POLICY)
    assert a.budget is BudgetState.EXHAUSTED
    assert a.actions == (SupervisorAction.DEGRADE_LLM,)
    assert a.escalation is None  # degradation is a policy decision, not an incident
    assert not a.is_healthy


def test_budget_over_limit_stops_and_escalates_when_degradation_disabled() -> None:
    a = assess_mission(_mission(tokens_used=1500, token_budget=1000), now=NOW, policy=STOP_POLICY)
    assert a.budget is BudgetState.EXHAUSTED
    assert a.actions == (SupervisorAction.STOP_BUDGET,)
    assert a.escalation is not None
    assert a.escalation.reason is EscalationReason.TOKEN_BUDGET_EXHAUSTED
    assert a.escalation.severity is EscalationSeverity.CRITICAL
    assert a.escalation.tokens_used == 1500 and a.escalation.token_budget == 1000


def test_zero_budget_means_immediate_exhaustion() -> None:
    a = assess_mission(_mission(tokens_used=0, token_budget=0), now=NOW, policy=POLICY)
    assert a.budget is BudgetState.EXHAUSTED


def test_budget_is_enforced_while_awaiting_human() -> None:
    a = assess_mission(
        _mission(phase=MissionPhase.AWAITING_HUMAN, tokens_used=1000, token_budget=1000),
        now=NOW,
        policy=STOP_POLICY,
    )
    assert a.health is MissionHealth.HEALTHY
    assert a.budget is BudgetState.EXHAUSTED
    assert a.actions == (SupervisorAction.STOP_BUDGET,)


def test_stuck_and_over_budget_prefers_the_budget_stop_incident() -> None:
    a = assess_mission(
        _mission(idle=timedelta(hours=2), tokens_used=1000, token_budget=1000),
        now=NOW,
        policy=STOP_POLICY,
    )
    assert a.health is MissionHealth.STUCK
    assert a.actions == (SupervisorAction.ESCALATE_STUCK, SupervisorAction.STOP_BUDGET)
    assert a.escalation is not None
    assert a.escalation.reason is EscalationReason.TOKEN_BUDGET_EXHAUSTED
    assert a.escalation.idle_seconds == 2 * 3600


def test_assess_mission_is_pure_and_repeatable() -> None:
    m = _mission(idle=timedelta(hours=1))
    assert assess_mission(m, now=NOW, policy=POLICY) == assess_mission(m, now=NOW, policy=POLICY)


# --- SupervisorAgent.tick over ports -------------------------------------------------------------


@dataclass
class _Missions:
    missions: list[MissionSnapshot]

    async def active_missions(self) -> list[MissionSnapshot]:
        return list(self.missions)


@dataclass
class _Incidents:
    recorded: list[Escalation] = field(default_factory=list)

    async def record(self, escalation: Escalation) -> None:
        self.recorded.append(escalation)


@dataclass
class _Budget:
    degraded: list[str] = field(default_factory=list)
    stopped: list[tuple[str, str]] = field(default_factory=list)

    async def degrade(self, mission_id: str) -> None:
        self.degraded.append(mission_id)

    async def stop(self, mission_id: str, reason: str) -> None:
        self.stopped.append((mission_id, reason))


def _agent(
    missions: list[MissionSnapshot], policy: SupervisorPolicy = POLICY
) -> tuple[SupervisorAgent, _Incidents, _Budget]:
    incidents = _Incidents()
    budget = _Budget()
    ports = SupervisorPorts(missions=_Missions(missions), incidents=incidents, budget=budget)
    return SupervisorAgent(ports, policy), incidents, budget


async def test_tick_applies_actions_for_stuck_and_over_budget_missions() -> None:
    agent, incidents, budget = _agent(
        [
            _mission(mission_id="m-healthy"),
            _mission(mission_id="m-stuck", idle=timedelta(hours=1)),
            _mission(mission_id="m-budget", tokens_used=1000, token_budget=1000),
        ],
        policy=STOP_POLICY,
    )
    report = await agent.tick(NOW)
    assert [a.mission_id for a in report.assessments] == ["m-budget", "m-healthy", "m-stuck"]
    assert report.checked_at == NOW
    assert budget.degraded == []
    assert budget.stopped == [("m-budget", "token_budget_exhausted")]
    assert [e.mission_id for e in incidents.recorded] == ["m-budget", "m-stuck"]
    assert [e.reason for e in report.escalations] == [
        EscalationReason.TOKEN_BUDGET_EXHAUSTED,
        EscalationReason.MISSION_STUCK,
    ]


async def test_tick_degrades_instead_of_stopping_when_policy_allows() -> None:
    agent, incidents, budget = _agent(
        [_mission(mission_id="m-budget", tokens_used=2000, token_budget=1000)], policy=POLICY
    )
    report = await agent.tick(NOW)
    assert budget.degraded == ["m-budget"]
    assert budget.stopped == []
    assert incidents.recorded == []
    assert report.escalations == ()


async def test_tick_with_no_missions_is_a_no_op() -> None:
    agent, incidents, budget = _agent([])
    report = await agent.tick(NOW)
    assert report.assessments == ()
    assert incidents.recorded == [] and budget.degraded == [] and budget.stopped == []


async def test_tick_is_repeatable_for_the_same_instant() -> None:
    agent, incidents, _ = _agent([_mission(idle=timedelta(hours=1))])
    first = await agent.tick(NOW)
    second = await agent.tick(NOW)
    assert first == second
    assert len(incidents.recorded) == 2  # ports must be idempotent per (mission, reason)


async def test_tick_rejects_naive_now() -> None:
    agent, _, _ = _agent([])
    with pytest.raises(ValueError):
        await agent.tick(datetime(2026, 3, 1, 12, 0))


async def test_unwired_ports_fail_loudly_naming_the_owner() -> None:
    agent = SupervisorAgent(SupervisorPorts.unwired(), POLICY)
    with pytest.raises(NotImplementedError, match="D4-06"):
        await agent.tick(NOW)
    with pytest.raises(NotImplementedError, match="D4-11"):
        await UnwiredIncidentSink().record(
            Escalation(
                mission_id="m",
                tenant_id="t",
                reason=EscalationReason.MISSION_STUCK,
                severity=EscalationSeverity.HIGH,
                raised_at=NOW,
                idle_seconds=1,
                tokens_used=0,
                token_budget=1,
            )
        )
    with pytest.raises(NotImplementedError, match="D4-04"):
        await UnwiredBudgetController().degrade("m")
    with pytest.raises(NotImplementedError, match="D4-06"):
        await UnwiredMissionSource().active_missions()
