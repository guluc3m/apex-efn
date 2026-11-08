# ADR-401: Celery vs. Arq for async background jobs

## Status

Accepted by the Tech Lead in ADR-900 (issue #99). FX ingestion `as_of` comes from the scheduled slot (`slot_start`).

## Context

Spec §5.3 and §5.7 require a task queue for long-running async work on Redis: scheduled jobs (FX
ingestion, audit chain re-verification, gate SLA reminders, seller snapshot refresh, stale financials
marking) and, later, SupervisorAgent work (issue #58, step 3, split out as 13b).

The orchestrator is FastAPI + asyncio end to end: `redis.asyncio` clients, async SQLAlchemy, async
`LLMGateway` and async LangGraph checkpointing. The `celery` dependency already sits in
`apps/orchestrator/pyproject.toml`, unused by any code. The idempotency store (D4-01b) already speaks
`redis.asyncio`.

Constraints that drive the choice:

- Job bodies are async and call async ports (DB, Redis, LLM, DEV-3 engines when they become async).
- Schedules and retry policy must come from configuration, never hardcoded business numbers (AGENTS.md
  section 0 rule 6).
- Code must type-check under `mypy --strict`.
- Scheduling must be testable with an injected clock and no sleeps.
- Observability must flow through OpenTelemetry (D1-07).

## Options

### Celery

- Mature, widely deployed, has beat (cron-like scheduler), retries, routing and a large ecosystem.
- **Sync-first.** Async bodies need `asyncio.run` shims or a separate event loop per task. This is at odds
  with an asyncio-only codebase and makes the async ports awkward to share with the request path.
- Beat is a separate process with its own schedule persistence (`celerybeat-schedule` file or a DB
  scheduler plugin). Run-once guarantees across replicas need extra work.
- Typing is weak: tasks are untyped decorators, and `mypy --strict` needs ignores or stubs.
- Brings a larger dependency tree (kombu, billiard, vine, click, ...).

### Arq

- Built on asyncio and Redis, the same stack as the rest of the orchestrator. Job functions are plain
  `async def` taking a context dict, so they reuse the same ports and injected clock as the request path.
- Native **cron jobs** (`cron(...)`) and **interval-free scheduling** through worker functions; retries via
  `Retry` and `max_tries`; job ids give deduplication (`_job_id`), which supports idempotent re-runs.
- Small surface, typed Python. Redis is its only broker, which matches the MVP queue choice in §5.7.
- Smaller community and fewer operational tools than Celery. Redis is a hard dependency (acceptable: it is
  already required).

## Decision

**Adopt Arq** for background jobs, and **remove `celery` from `pyproject.toml`**.

Implementation shape (this PR):

- Job bodies are plain async functions in `apex/workers/jobs.py`, taking an injected `Clock` and ports.
  They do not import Arq.
- A small `Scheduler` protocol (`apex/workers/scheduler.py`) with a `JobRegistry` holds the job
  definitions and schedule specs. The Arq adapter (`apex/workers/arq_adapter.py`) is the only module that
  imports `arq`. Swapping the backend means writing another adapter, not touching jobs.
- Schedule specs are read from configuration (`apex/workers/config.py` parses a list of
  `{name, cron | every_seconds, ...}` entries). Defaults are technical (cron expressions), business numbers
  (SLA hours, stale days) stay in tenant config (D4-03).
- Idempotent re-runs: each scheduled execution gets a deterministic job id from `(job name, scheduled
  slot)`, so a duplicate enqueue from a second replica is a no-op.

`arq` is added to the dependencies and `uv.lock` is regenerated. Justification: asyncio-native, Redis-only,
typed, and it removes a sync bridge from the async codebase. The adapter keeps the dependency replaceable.

## Consequences

- Easier: job bodies are testable as ordinary async functions; schedules are data; no event-loop bridging.
- Harder: fewer off-the-shelf dashboards than Celery Flower. Observability is provided by D1-07 spans we
  emit ourselves.
- Operational: a `worker` process (`arq apex.workers.arq_adapter.WorkerSettings`) is added to compose and
  Helm (D1-03 / D1-09 request via `platform-request`).
- Reversible: because jobs and the registry do not depend on Arq, moving to Celery would only replace the
  adapter.

## Follow-ups

- **13b (separate PR):** SupervisorAgent (stuck-mission detection, token-budget control, escalation) as a
  scheduled job on this registry, as well as the LangGraph wiring it needs.
- **Platform request:** add the `worker` service to `compose.yaml` (DEV-1).
- **Open question for TL:** whether Arq's retry defaults are acceptable for the FX ingestion job, which
  must not double-write rates. The idempotent job id covers the duplicate-enqueue case; the write itself
  must be an insert-only upsert (DEV-3 D3-03).

## Related

- Issue #58 (D4-13), spec §5.3 and §5.7
- ADR-002 (OpenAI-compatible gateway; async HTTP choice)
- ADR-000 (template)
