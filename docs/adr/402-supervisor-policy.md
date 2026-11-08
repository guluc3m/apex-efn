# ADR-402: SupervisorAgent policy — stuck missions, token budget and escalation

## Status

Accepted by the Tech Lead in ADR-900 (issue #99), with the review changes listed under "Decisions from
the Tech Lead" implemented. The channel for phase 1 is one gate queue item.

## Context

Spec §4 assigns `SupervisorAgent` "quality control, blockage detection, escalation, cost control".
Acceptance criterion 28 makes the per-mission LLM token budget a **hard** limit: when it is exceeded the
system degrades to a cheap model or stops with a warning. The spec does not define *when* a mission
counts as stuck, nor what the escalation looks like, and AGENTS.md section 0 rule 6 forbids inventing
business numbers in code.

The supervisor runs as a scheduled job on the registry from ADR-401 (D4-13 step 2), every few minutes,
for every tenant.

## Decision

1. **Pure logic, ports, injected time.** `apex/agents/supervisor.py` contains no I/O and never reads the
   clock: `assess_mission(mission, now=..., policy=...)` is a pure function and
   `SupervisorAgent.tick(now)` applies side effects through `SupervisorPorts`
   (`missions`, `incidents`, `budget`). Default implementations raise `NotImplementedError` naming the
   owning lane (D4-06 mission graph, D4-04 LLMGateway, D4-11 gate queue / D2-10 audit).
2. **Thresholds come from config.** `SupervisorPolicy` has no defaults: `stuck_after` (a `timedelta`,
   so the unit is explicit) and `degrade_on_budget_exhausted` are required. They will be resolved from
   tenant config (D4-03) when the job is wired; the key names are proposed in the open questions below.
3. **Stuck** = a `RUNNING` mission whose last progress is at or past `stuck_after` before `now`.
   `AWAITING_HUMAN` missions are never stuck (a human owns the clock). `COMPLETED`/`FAILED` missions are
   ignored entirely, including their budget.
4. **Budget** = `tokens_used >= token_budget` is exhausted. With `degrade_on_budget_exhausted` the action
   is `DEGRADE_LLM` (no incident); without it the action is `STOP_BUDGET` plus a `CRITICAL` escalation.
   The budget is enforced while `AWAITING_HUMAN` too, because a waiting mission that keeps calling the
   LLM is a cost leak.
5. **Escalations are structured**, not LLM text: mission, tenant, reason (closed enum), severity,
   `raised_at`, idle seconds, tokens used and budget. One escalation per mission per tick, and a budget
   stop replaces a stuck escalation for the same mission so humans get one actionable item. A stuck
   mission that is also over budget (with degradation off) yields the budget escalation only, and its
   actions are `FREEZE_LLM` + `STOP_BUDGET`, never `ESCALATE_STUCK` as well.
6. **Idempotent re-runs.** The tick is safe to repeat. The incident sink is idempotent per
   `(tenant_id, mission_id, reason)`: while an open gate item exists for that key, `record` returns `False`
   and creates nothing, and the tick reports it as deduplicated. Different reasons for one mission are
   separate items.
7. **Tenant-scoped reads.** `SupervisorPort.active_missions(tenant_id)` is called once per tenant, so RLS
   applies. Listing the tenants is a separate system-role operation owned by DEV-2. A mission that comes
   back with another tenant's id raises `CrossTenantMission` before anything is applied.
8. **A stuck mission is frozen.** `FREEZE_LLM` makes the budget controller refuse every LLM call for that
   mission until a human resumes it.

## Consequences

- The supervisor is fully testable without a graph, a database or a model (no network, no sleeps).
- Wiring the real mission source, incident sink and budget controller is a small follow-up once D4-06 and
  D4-04 land; nothing in the supervisor changes.
- LLM-assisted quality review of mission transcripts is **not** part of this ADR: it needs prompt and eval
  work (D4-05) and a budget for the reviewer itself, so it is deferred.

## Decisions from the Tech Lead (ADR-900, issue #99)

1. `supervisor.stuck_after_minutes`, tenant scope, default **30**.
2. `supervisor.degrade_on_budget_exhausted`, default **true**: degrade first, and if degrading fails stop with
   a CRITICAL escalation.
3. A stuck mission is escalated **and its LLM calls are frozen** until a human resumes it.
4. Phase 1 channel: **one gate queue item** (`type=supervisor`, closed reason enum, no LLM text).
5. Keep D4-13 in one PR; ADR numbers 401 and 402 stand.
6. Arq approved. FX ingestion is idempotent per slot: `as_of` comes from the scheduled slot
   (`slot_start`), not from the execution instant, so a late run, a retry or a second replica uses the same
   `as_of`.

## Related

- ADR-401 (Arq), spec §4, §5.6, acceptance criterion 28
- D4-13 task (AGENTS.md section 5), D4-06, D4-04, D4-11
