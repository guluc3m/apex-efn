# Runbook: platform session invalidated

**Owner:** DEV-5 (D5-10). **Applies to:** a platform whose requests come back as `session_invalid`: HTTP 401 or 403 without a CAPTCHA marker (`apps/browser-worker/src/adapters/http.ts`).

**Status today:** the only registered adapter is `mock-a`, and the mock marketplace has no login (`docs/compliance/mock-marketplace.md`, section 5). It never returns 401 or 403, so this error cannot happen against the mock. The session handling this runbook depends on is **not built yet**: automatic session refresh, detection beyond the `session_invalid` code, and the human-assisted reauth flow all belong to D5-02 (issue #61, open).

## What you see

- Job state from `GET /internal/v1/jobs/{id}` (service bearer token required): `status: "failed"`, `error.code: "session_invalid"`, `error.retryable: false`. The job is **not** retried and is not dead-lettered.
- Metric `apex_scraping_session_invalidations_total{platform}` increases. It is the "Session invalidations (last hour)" panel in the "APEX-EFN · Scraping health" dashboard (`infra/grafana/dashboards/scraping-health.json`). `apex_scraping_requests_total{outcome="session_invalid"}` increases too.
- The worker log line `scraping job attempt failed` carries `platform`, `jobId`, `kind` and the closed error `code` (`session_invalid`). It never carries the response body.

## Why the worker does not retry

A retry with the same invalid session fails the same way. It only adds traffic to the platform. The job is marked non-retryable on purpose.

## Interim procedure

There is no supported way to restore a session yet. Until D5-02 lands, follow these steps.

1. **Confirm the code.** Read `error.code` in the job state. Do not re-enqueue the job.
2. **Stop calls to the platform.** Switch the feature flag `platform.<id>.enabled` OFF in Unleash (compose service `unleash`, port 4242; naming in `docs/observability/flags.md`). The worker polls flags every 15 seconds (`FLAG_POLL_INTERVAL_MS` in `apps/browser-worker/src/index.ts`).
   - New jobs for that platform are refused with `409 platform_disabled` (`apps/browser-worker/src/jobs/service.test.ts` covers this).
   - Jobs already queued for the platform should end as `failed` with `platform_disabled` and are not retried. This follows from `processJob` and `runJob` but is not covered by a test.
   - The adapter is never called while the flag is off (`AdapterRegistry.require` in `apps/browser-worker/src/adapters/index.ts`).
3. **Do not rebuild the session with scripts.** Do not log in with stored credentials from a script or from any browser automation to "fix" the session. Session state lives in Vault (`apps/browser-worker/src/platform/vault.ts`: `getSessionState`, `putSessionState`, `getCredential`), but nothing outside the tests calls `putSessionState` today.
4. **Escalate to DEV-5** with the platform id, the job ids, the timestamps and the panel values. Do not include credentials, cookies or response bodies.
5. **Re-enable only after DEV-5 confirms.** Switch the flag ON, then restart the worker process. BullMQ workers start only for platforms that are enabled at boot (`startJobWorkers` in `apps/browser-worker/src/jobs/bull.ts`). Jobs enqueued while the platform was off stay `queued` until the restart.

Known gap: in `infra/docker-compose.yml` the `browser-worker` service sets neither `BROWSER_WORKER_TOKEN` nor `UNLEASH_URL`. The worker refuses to start without them (`apps/browser-worker/src/config.ts`, `apps/browser-worker/src/platform/flags.ts`). Use your deployment's configuration until DEV-1 fixes the compose service.

## If you see this

| Symptom                                                     | Likely cause                                                  | Action                                                                                                                    |
| ----------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `session_invalid` on every job for one platform             | Session expired or revoked, or the platform changed its login | Interim procedure, steps 2 and 4                                                                                          |
| `session_invalid` on one job only                           | One 401 or 403 answer                                         | Check whether other jobs for the platform fail the same way before escalating                                             |
| `captcha` instead of `session_invalid`                      | The 401 or 403 body matched the CAPTCHA marker                | Use `captcha-persistent.md`                                                                                               |
| Jobs stay `queued` after you re-enable the flag             | Workers start only at boot                                    | Restart the worker (step 5)                                                                                               |
| Jobs fail with `platform_disabled`                          | The flag is off                                               | Expected. Nothing to fix                                                                                                  |
| Session counter flat while jobs fail with `session_invalid` | No metrics export                                             | Check `OTEL_SDK_DISABLED` and `OTEL_EXPORTER_OTLP_ENDPOINT` (defaults in `apps/browser-worker/src/platform/telemetry.ts`) |

## Escalate when

- `session_invalid` appears on a platform whose flag is still ON.
- More than one platform reports `session_invalid` at the same time.
- A credential reference cannot be read (`getCredential` fails). Do not paste the error text if it could contain secrets.
- A human needs to sign in again. There is no reauth flow yet, so this is a DEV-5 decision.
