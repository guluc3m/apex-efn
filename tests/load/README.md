# Load tests (k6) — D1-10

Load tests for the orchestrator HTTP surface: the read-heavy API, the mission queue and the gate queue.
They answer the question unit tests cannot: does the API stay fast and honest when dozens of buyers and
missions hit it at once?

They are **not** a benchmark of business engines. Price sanity, trust and financial fit are deterministic
domain code with their own test vectors (DEV-3); these scripts only exercise HTTP behaviour, auth, the
idempotency middleware and the in-memory stores.

Spec reference: `PROMPT-IMPLEMENTACION.md` §5.11 ("Load testing (k6) sobre orquestador, cola de misiones
y cola de gate").

## Scripts

| Script             | What it exercises                                                                                                       | Ramp           |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------- | -------------- |
| `orchestrator.js`  | `GET /health`, `GET /v1/gate/queue`, `GET /v1/missions/{id}`, `GET /v1/sellers/{id}/confidence`                         | 5 → 20 → 5 VUs |
| `mission-queue.js` | `POST /v1/sourcing-requests` → `POST /v1/missions` (both with `Idempotency-Key`) → poll `GET /v1/missions/{id}`         | 2 → 6 VUs      |
| `gate-queue.js`    | `GET /v1/gate/queue`, `GET /v1/dashboard/deals` with `price_band` / `verdict` / `platform` / `signature_status` filters | 5 → 15 VUs     |

`config.js` holds the base URL, tenant and content headers, the expected status sets, the ramps and the
end-of-test summary. There is no business configuration in this directory: thresholds and weights live in
`/config/defaults` and the tenant versions.

### Documented responses are not failures

Every request declares `http.expectedStatuses(...)`, so `http_req_failed` only counts _unexpected_
answers:

- `404` for a fixed mission id that does not exist. The read still proves the route, the auth and the store
  lookup work.
- `501` for a route whose engine is still owned by another lane (the gate queue needs D2-09/D4-11 wiring,
  seller confidence needs D3-06). A 501 is a correct answer from a partial stack, and the check records it
  as such.
- `5xx` codes that mean a real defect (`500`, `503`, `504`) are **not** in the expected sets, so a broken
  response fails the run.

### What is deliberately not load-tested

`POST /v1/gate/queue/{id}/actions` and `POST /v1/dashboard/deals/{id}/actions` create a decision that must
be signed by a human key. A load test cannot drive them without forging a signature, which would defeat
the audit chain the platform exists to protect. There is no read-only variant of a signed action, so
`gate-queue.js` stays read-only. Those paths are covered by the API tests with a decision-port double and
by the Playwright E2E with a virtual authenticator (D6-08).

## Auth model — development tenant header (local only)

The scripts do not carry a bearer token. They impersonate a developer through the opt-in escape hatch in
`apex.auth.deps`:

- the orchestrator must run with **`APEX_ALLOW_TENANT_HEADER=true`**;
- every request sends **`X-Tenant-Id: tenant-a`**;
- `APEX_DEV_ROLES` may select the development roles (default: none).

This is a **local development mechanism**. With a real bearer token the header is ignored, and the hatch is
off unless the environment variable says otherwise. Never enable it in a shared or production deployment:
it would let any caller choose its tenant. The `D1-05` runbook and `docs/security/rbac.md` own that rule.

## Running locally

1. Start the orchestrator (from the repository root):

   ```bash
   cd apps/orchestrator
   uv sync --locked --dev
   APEX_ALLOW_TENANT_HEADER=true OTEL_SDK_DISABLED=true IDEMPOTENCY_BACKEND=memory \
     uv run uvicorn apex.main:app --port 8000
   ```

2. `mission-queue.js` also needs an OpenAI-compatible endpoint for the `extractor` and `planner` roles.
   In development that is the LLM stub (port 8001, already the `llm.roles` target in the defaults). Start
   it in a second terminal from `apps/orchestrator`:

   ```bash
   LLM_STUB_SCENARIOS_DIR=../llm-stub/scenarios uv run python -m llm_stub
   ```

   Without it, the two writes answer `502 llm_unavailable`; the script reports that as a failed check
   instead of pretending the mission queue works.

   The intake ledger is keyed per tenant (`intake:<tenant>`), not per mission, so a long run consumes
   `LLM_MISSION_TOKEN_BUDGET` and the guard starts answering `429`. That is a documented response and the
   script skips the mission creation for those iterations; the nightly workflow raises the limit
   (`LLM_MISSION_TOKEN_BUDGET`) so the whole run exercises the queue.

3. Run a script (Docker with the pinned `grafana/k6:0.54.0` image; Linux for `--network host`):

   ```bash
   bash tests/load/run-local.sh --script orchestrator.js
   bash tests/load/run-local.sh --script mission-queue.js
   bash tests/load/run-local.sh --script gate-queue.js --base-url http://127.0.0.1:8000
   ```

   From the repository root, the same through pnpm:

   ```bash
   pnpm load:test            # orchestrator.js
   pnpm load:test:missions   # mission-queue.js
   pnpm load:test:gate       # gate-queue.js
   ```

   A short run for a quick check (5–10 s ramp):

   ```bash
   K6_PROFILE=smoke bash tests/load/run-local.sh --script gate-queue.js
   ```

`run-local.sh` first calls `GET /health` with a 5 s timeout and exits non-zero with instructions when the
orchestrator is not up. It writes `results/k6-<script>-summary.json` and `.txt`; the directory is
git-ignored. On macOS the script rewrites `localhost` to `host.docker.internal`, since `--network host`
is Linux-only.

## Thresholds

Defined once in `config.js` and applied to all three scripts:

| Metric              | Threshold   | What it means                                                                                                                                           |
| ------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `http_req_failed`   | `rate<0.01` | Fewer than 1% unexpected statuses or transport errors. Declared expected statuses (404/501/known write outcomes) do not count.                          |
| `http_req_duration` | `p(95)<800` | 95% of requests answer within 800 ms against a developer machine / CI runner.                                                                           |
| `checks`            | `rate>0.99` | The response-shape assertions pass: the body has the documented fields, a created mission echoes its sourcing request, a poll returns the same mission. |

These are **load thresholds**, not business thresholds. A failure means the HTTP layer or its dependencies
degraded; it never changes a price band, a seller score or an approval limit.

## Nightly workflow

`.github/workflows/load.yml` runs nightly (`schedule`) and on demand (`workflow_dispatch`, with a `script`
choice). It:

1. installs uv and the Python dependencies (`uv sync --locked --dev`) and the pinned Node toolchain;
2. starts the LLM stub and the orchestrator with `APEX_ALLOW_TENANT_HEADER=true`, `OTEL_SDK_DISABLED=true`
   and the in-memory idempotency backend, then waits on `/health`;
3. runs the selected scripts through the same `run-local.sh` and Docker image used locally;
4. uploads `tests/load/results/` (JSON + text summaries) and the app logs as artifacts, always;
5. stops both processes in an `always()` step.

GitHub Actions is disabled in this repository, so the workflow is delivered but not executed here. It must
still pass `actionlint` (the `workflow-lint` job of `ci.yml`); `run-local.sh` must pass `bash -n` and
`shellcheck`.

## Files

```
tests/load/
  README.md          this file
  config.js          base URL, headers, expected statuses, ramps, summary
  orchestrator.js    read-heavy API
  mission-queue.js   create sourcing request + mission, then poll
  gate-queue.js      gate queue + deals dashboard filters (read-only)
  run-local.sh       health check + docker run of one script
  results/           generated summaries (git-ignored)
```
