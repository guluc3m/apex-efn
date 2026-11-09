# Runbook: missions in the orchestrator

**Owner:** DEV-4. **Applies to:** the mission lifecycle (`POST /v1/missions` → offers → gate → decision).

## The lifecycle

```
queued ──▶ planning ──▶ planned ──▶ running ──▶ completed
             │             │           │
             └─────────────┴───────────┴──▶ failed
                                         └─▶ cancelled
```

| Status | What it means | Who moves it |
|---|---|---|
| `queued` | The record exists, planning has not started | the sourcing service |
| `planning` | The planner is choosing platforms and queries | the sourcing service |
| `planned` | A plan exists with at least one usable step | the sourcing service |
| `running` | Offers are being collected and analysed; the deals now await humans | the mission runner |
| `completed` | Every deal has a signed decision | the graph (D4-06) — **not implemented yet** |
| `failed` | A step could not run; `failure_reason` says which | anything |
| `cancelled` | A person stopped it | D4-11 (not implemented yet) |

Only `queued → planning → planned` happens automatically today (`POST /v1/missions` plans inline). The
runner that goes from `planned` to `running` only runs when `mission_autorun` is on, and it needs the
browser worker (D5-01) and the DEV-3 engines.

## Reading a mission

- `GET /v1/missions/{id}` — the contract's `Mission`: `state`, `offers_discovered`, `offers_in_gate`,
  `tokens_used`, `token_budget`, `started_at`, `completed_at` and `error` (an RFC 9457 problem carrying the
  failure reason). The plan steps are not in this body: they are in the `plan_ready` event payload.
- `GET /v1/missions/{id}/events` — SSE. Reconnect with `Last-Event-ID: <seq>` to resume without gaps. The
  stream ends at `planned` on purpose (planning is the last step the sourcing service performs); reconnect
  when the mission starts running.

  Frames are the contract's `MissionEvent` (`id`, `mission_id`, `type`, `at`, `data`), so the SSE `event:`
  field is one of the contract's closed set: `state_changed`, `offer_discovered`, `sanity_checked`, `error`,
  … The orchestrator's internal step names (`planning_started`, `offers_collected`, `analysis_completed`) are
  mapped onto that set and the step detail travels in `data`.

## When a mission is `failed`

The failure lands in `Mission.error.detail` (the contract's `Problem`) and in the `error` event. It is a
stable code followed by a detail. The codes:

| `failure_reason` starts with | Meaning | What to do |
|---|---|---|
| `no_viable_platform:` | The planner proposed only platforms that are disabled or not in the catalogue | Check `platform.<id>.enabled` feature flags and the platform catalogue |
| `planner_output_invalid` | The model did not return a valid plan after the structured-output ladder | Check the LLM endpoint; the gateway already retried and repaired |
| `not_wired: ...` | A port the runner needs is not implemented yet; the detail names the owner lane | Expected until the DEV-3 engines land (the browser worker is wired as soon as `browser_worker_url` is set) |
| `gate_rejected` | A human rejected the gate decision | Nothing; the offer is rejected by design |
| `renegotiation_limit` | `gate.max_renegotiations` reached | Raise the limit in tenant config if the case justifies it |

## When a mission is stuck in `planned`

That is the normal state today: nothing advances it because the runner needs ports that do not exist yet.
Either turn on `mission_autorun` (it will then fail with `not_wired: ...`, which is honest) or leave it
until D5-01 lands.

## When a mission is stuck in `running`

The offers are in the gate queue awaiting signed human decisions. Check
`GET /v1/gate/queue` (needs D3-* and D2-09). If the queue is empty and the mission is still `running`,
the runner stopped between analysis and the queue: the last event should be `analysis_completed`, whose
payload carries `offers_analysed` and `gate_items`.

## Invariants that must hold

1. **No mission without an active financial snapshot** (criterion 1). Enforced by
   `OnboardingService.require_active_snapshot`; see `financial-snapshot-stale.md`.
2. **Only a `planned` mission can be run.** Running any other status raises `MissionNotRunnable`; the
   runner never re-runs a finished mission.
3. **Every status change is validated** against the table in `apex/agents/missions.py`. Skipping a step or
   reopening a terminal state raises `InvalidMissionTransition`.
4. **Every status change is an event.** The event log is append-only and its `seq` is what SSE replays.
5. **A mission carries the quantity its sourcing request asked for** (`Mission.quantity`), so the runner
   never invents one.

## Escalate when

- A mission fails with `not_wired` and the named lane says its task is merged: the wiring is stale, reopen it.
- The event stream stops mid-mission and `Last-Event-ID` replay returns nothing: the event log was lost
  (in-memory store until D2-05).
- A mission reaches `running` but no gate item exists for any of its offers: the gate rules are not
  classifying, check the analysis verdicts on `GET /v1/missions/{id}/offers`.
