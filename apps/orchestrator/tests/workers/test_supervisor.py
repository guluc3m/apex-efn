"""SupervisorAgent: stuck-mission detection, token-budget control and escalation (pure logic)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from apex.agents.supervisor import (
    BudgetState,
    CrossTenantMission,
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
    assert a.actions == (SupervisorAction.FREEZE_LLM, SupervisorAction.ESCALATE_STUCK)
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
    # One escalation, the budget stop (ADR-402, ADR-900). The mission is still frozen because it is stuck,
    # and ESCALATE_STUCK is not requested: it would record a second item for the same mission.
    assert a.actions == (SupervisorAction.FREEZE_LLM, SupervisorAction.STOP_BUDGET)
    assert SupervisorAction.ESCALATE_STUCK not in a.actions
    assert a.escalation is not None
    assert a.escalation.reason is EscalationReason.TOKEN_BUDGET_EXHAUSTED
    assert a.escalation.idle_seconds == 2 * 3600


def test_assess_mission_is_pure_and_repeatable() -> None:
    m = _mission(idle=timedelta(hours=1))
    assert assess_mission(m, now=NOW, policy=POLICY) == assess_mission(m, now=NOW, policy=POLICY)


# --- SupervisorAgent.tick over ports -------------------------------------------------------------


@dataclass
class _Missions:
    """Tenant-scoped source. ``by_tenant`` maps tenant -> missions; ``asked`` records every tenant asked for."""

    by_tenant: dict[str, list[MissionSnapshot]]
    asked: list[str] = field(default_factory=list)

    async def tenants(self) -> list[str]:
        return list(self.by_tenant)

    async def active_missions(self, tenant_id: str) -> list[MissionSnapshot]:
        self.asked.append(tenant_id)
        return list(self.by_tenant[tenant_id])


@dataclass
class _Incidents:
    """Open-item semantics: one item per (tenant, mission, reason) until it is resolved."""

    recorded: list[Escalation] = field(default_factory=list)
    open_keys: set[tuple[str, str, str]] = field(default_factory=set)

    async def record(self, escalation: Escalation) -> bool:
        key = (escalation.tenant_id, escalation.mission_id, escalation.reason.value)
        if key in self.open_keys:
            return False
        self.open_keys.add(key)
        self.recorded.append(escalation)
        return True


@dataclass
class _Budget:
    degraded: list[tuple[str, str]] = field(default_factory=list)
    stopped: list[tuple[str, str, str]] = field(default_factory=list)
    frozen: list[tuple[str, str]] = field(default_factory=list)

    async def degrade(self, tenant_id: str, mission_id: str) -> None:
        self.degraded.append((tenant_id, mission_id))

    async def stop(self, tenant_id: str, mission_id: str, reason: str) -> None:
        self.stopped.append((tenant_id, mission_id, reason))

    async def freeze(self, tenant_id: str, mission_id: str) -> None:
        self.frozen.append((tenant_id, mission_id))


def _agent(
    missions: list[MissionSnapshot], policy: SupervisorPolicy = POLICY
) -> tuple[SupervisorAgent, _Incidents, _Budget]:
    by_tenant: dict[str, list[MissionSnapshot]] = {}
    for mission in missions:
        by_tenant.setdefault(mission.tenant_id, []).append(mission)
    agent, incidents, budget, _ = _agent_by_tenant(by_tenant, policy)
    return agent, incidents, budget


def _agent_by_tenant(
    by_tenant: dict[str, list[MissionSnapshot]], policy: SupervisorPolicy = POLICY
) -> tuple[SupervisorAgent, _Incidents, _Budget, _Missions]:
    source = _Missions(by_tenant)
    incidents = _Incidents()
    budget = _Budget()
    ports = SupervisorPorts(missions=source, incidents=incidents, budget=budget)
    return SupervisorAgent(ports, policy), incidents, budget, source


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
    assert budget.stopped == [("t-1", "m-budget", "token_budget_exhausted")]
    assert budget.frozen == [("t-1", "m-stuck")]
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
    assert budget.degraded == [("t-1", "m-budget")]
    assert budget.stopped == []
    assert incidents.recorded == []
    assert report.escalations == ()


async def test_tick_with_no_missions_is_a_no_op() -> None:
    agent, incidents, budget = _agent([])
    report = await agent.tick(NOW)
    assert report.assessments == ()
    assert incidents.recorded == [] and budget.degraded == [] and budget.stopped == []


async def test_tick_is_repeatable_and_does_not_duplicate_the_escalation() -> None:
    agent, incidents, _ = _agent([_mission(idle=timedelta(hours=1))])
    first = await agent.tick(NOW)
    second = await agent.tick(NOW)
    assert first.assessments == second.assessments
    assert len(incidents.recorded) == 1  # the second tick found the open item and created nothing
    assert first.recorded == (("t-1", "m-1", "mission_stuck"),) and first.deduplicated == ()
    assert second.recorded == () and second.deduplicated == (("t-1", "m-1", "mission_stuck"),)


async def test_tick_rejects_naive_now() -> None:
    agent, _, _ = _agent([])
    with pytest.raises(ValueError):
        await agent.tick(datetime(2026, 3, 1, 12, 0))


async def test_unwired_ports_fail_loudly_naming_the_owner() -> None:
    agent = SupervisorAgent(SupervisorPorts.unwired(), POLICY)
    with pytest.raises(NotImplementedError, match="DEV-2"):
        await agent.tick(NOW)
    with pytest.raises(NotImplementedError, match="D4-06"):
        await UnwiredMissionSource().active_missions("t-1")
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
    for call in (
        UnwiredBudgetController().degrade("t", "m"),
        UnwiredBudgetController().stop("t", "m", "token_budget_exhausted"),
        UnwiredBudgetController().freeze("t", "m"),
    ):
        with pytest.raises(NotImplementedError, match="D4-04"):
            await call


# --- ADR-900 / issue #99 review ---------------------------------------------------------------------


async def test_stuck_and_over_budget_records_exactly_one_escalation_across_ticks() -> None:
    """Review of #98: both the stuck and the budget branch used to append an escalation."""
    agent, incidents, budget = _agent(
        [_mission(idle=timedelta(hours=2), tokens_used=1000, token_budget=1000)], policy=STOP_POLICY
    )
    for _ in range(3):
        await agent.tick(NOW)
    assert [e.reason for e in incidents.recorded] == [EscalationReason.TOKEN_BUDGET_EXHAUSTED]
    assert (
        budget.stopped == [("t-1", "m-1", "token_budget_exhausted")] * 3
    )  # stop is idempotent per call
    assert budget.frozen == [("t-1", "m-1")] * 3


async def test_stuck_mission_is_frozen_and_escalated_once() -> None:
    agent, incidents, budget = _agent([_mission(idle=timedelta(hours=1))])
    report = await agent.tick(NOW)
    assert budget.frozen == [("t-1", "m-1")]
    assert [e.reason for e in incidents.recorded] == [EscalationReason.MISSION_STUCK]
    assert report.assessments[0].actions == (
        SupervisorAction.FREEZE_LLM,
        SupervisorAction.ESCALATE_STUCK,
    )


async def test_healthy_and_waiting_missions_are_not_frozen() -> None:
    agent, _, budget = _agent(
        [
            _mission(mission_id="a"),
            _mission(mission_id="b", phase=MissionPhase.AWAITING_HUMAN, idle=timedelta(days=3)),
        ]
    )
    await agent.tick(NOW)
    assert budget.frozen == []


async def test_different_reasons_for_the_same_mission_are_separate_items() -> None:
    """Dedupe is per (mission, reason): a stuck item does not hide a later budget stop."""
    agent, incidents, _ = _agent([_mission(idle=timedelta(hours=1))], policy=STOP_POLICY)
    await agent.tick(NOW)
    assert [e.reason for e in incidents.recorded] == [EscalationReason.MISSION_STUCK]
    stopped = _mission(idle=timedelta(hours=1), tokens_used=1000, token_budget=1000)
    agent2, _, _ = _agent([stopped], policy=STOP_POLICY)
    agent2._ports.incidents.open_keys.add(("t-1", "m-1", "mission_stuck"))  # type: ignore[attr-defined]
    await agent2.tick(NOW)
    assert [e.reason for e in agent2._ports.incidents.recorded] == [  # type: ignore[attr-defined]
        EscalationReason.TOKEN_BUDGET_EXHAUSTED
    ]


async def test_same_mission_id_in_two_tenants_is_deduplicated_per_tenant() -> None:
    agent, incidents, budget, _ = _agent_by_tenant(
        {
            "t-1": [_mission(mission_id="m-1", tenant_id="t-1", idle=timedelta(hours=1))],
            "t-2": [_mission(mission_id="m-1", tenant_id="t-2", idle=timedelta(hours=1))],
        }
    )
    await agent.tick(NOW)
    assert sorted((e.tenant_id, e.mission_id) for e in incidents.recorded) == [
        ("t-1", "m-1"),
        ("t-2", "m-1"),
    ]
    assert sorted(budget.frozen) == [("t-1", "m-1"), ("t-2", "m-1")]


async def test_missions_are_read_one_tenant_at_a_time_never_all_at_once() -> None:
    """Review of #98: ``active_missions()`` was not tenant-scoped, so RLS could not apply."""
    agent, _, _, source = _agent_by_tenant(
        {"t-b": [_mission(tenant_id="t-b")], "t-a": [_mission(tenant_id="t-a")]}
    )
    await agent.tick(NOW)
    assert source.asked == ["t-a", "t-b"]  # one scoped call per tenant, in a stable order


async def test_a_source_that_leaks_another_tenants_mission_is_refused() -> None:
    agent, incidents, budget, _ = _agent_by_tenant({"t-1": [_mission(tenant_id="t-2")]})
    with pytest.raises(CrossTenantMission) as caught:
        await agent.tick(NOW)
    assert (caught.value.asked, caught.value.actual) == ("t-1", "t-2")
    assert incidents.recorded == [] and budget.frozen == []


async def test_no_tenants_is_a_no_op() -> None:
    agent, incidents, budget, source = _agent_by_tenant({})
    report = await agent.tick(NOW)
    assert report.assessments == () and source.asked == []
    assert incidents.recorded == [] and budget.frozen == []
