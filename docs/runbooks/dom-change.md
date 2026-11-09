# Runbook: platform DOM or API change

**Owner:** DEV-5 (D5-10). **Applies to:** a platform response that no longer matches what an adapter expects: a body that is not JSON, a JSON shape that fails the adapter's zod schema, or a listing whose price cannot be read. The worker reports this as `error.code: "dom_changed"`.

Note on terms: the only registered adapter today is `mock-a`, a JSON API, so "DOM" here means the response shape. The same procedure applies to HTML adapters, which are not built yet (D5-06).

## What you see

- Job state from `GET /internal/v1/jobs/{id}` (service bearer token required): `status: "failed"`, `error.code: "dom_changed"`, `error.retryable: false`. The job is not retried.
- `error.message` is the bounded detail. It names up to five zod issue paths, for example `response does not match the expected shape at: metrics.orders.last_12m`, or says `response is not JSON`. It never contains the response body (`parseJsonBody` in `apps/browser-worker/src/adapters/http.ts`).
- `dom_changed` also comes from `getProduct` when a listing has no price (`listing has no price`) or the price text is not a decimal with at most two decimals (`workerErrorFor` in `apps/browser-worker/src/adapters/mock-a/mapping.ts`).
- **Search does not fail.** A listing with an unusable price is returned in `skipped[]` with `reason` `missing_price`, `parse_error` or `unsupported_currency` (`SkipReason` in `packages/shared-types`). A rising share of these is an early warning.
- Metric `apex_scraping_requests_total{outcome="error"}` rises. It is one panel of "Requests per second by outcome" in the "APEX-EFN · Scraping health" dashboard. The `error` outcome also covers 404s and other 5xx answers, so read it together with the job states.
- The worker log line `scraping job attempt failed` carries the closed error `code` (`dom_changed`), never the response body. The job state has the same code.

## Why it is not retried

A changed response does not change back on retry, and the adapter cannot guess the new shape. The error is non-retryable by design.

## What to do

1. **Read the paths.** From the job state, take `error.message`. The paths tell you which field moved.
2. **Stop the bleeding.** Switch `platform.<id>.enabled` OFF in Unleash (compose service `unleash`, port 4242; naming in `docs/observability/flags.md`). Every job for the platform would fail until the adapter is fixed, so the flag also saves platform traffic.
3. **Compare with the recorded fixtures.** Fixtures live under `apps/browser-worker/fixtures/<platform>/` (`mock-a` has recorded exchanges there). The response schemas are in `apps/browser-worker/src/adapters/<platform>/schemas.ts` (for example `apps/browser-worker/src/adapters/mock-a/schemas.ts`), and the field mapping is in `mapping.ts` next to it.
4. **Run the adapter tests in live mode.** `ADAPTER_FIXTURES=live pnpm --filter @apex/browser-worker test`. For `mock-a`, live mode starts the local mock marketplace on `127.0.0.1` (`apps/browser-worker/src/testing/mock-marketplace.ts`) and does not reach a real platform. The other modes are `replay` (the default, used in CI) and `record`.
5. **Fix the schema or mapping in code.** This is DEV-5 work under `apps/browser-worker/src/adapters/<platform>/`.
6. **Re-record the fixtures.** `ADAPTER_FIXTURES=record pnpm --filter @apex/browser-worker test`. For `mock-a`, record mode deletes the mock-a fixture directory before it writes new files (`apps/browser-worker/src/adapters/mock-a/index.test.ts`). **Review the diff of `apps/browser-worker/fixtures/` before you commit.** Recording is allowed only from approved platforms or the mock marketplace, never from authenticated pages (header of `apps/browser-worker/src/adapters/fixtures.ts`).
7. **Run the default tests.** `pnpm --filter @apex/browser-worker test` must pass in replay mode. Adapter test files use `describeAdapterContract` (`apps/browser-worker/src/adapters/contract-suite.ts`), so the contract suite has to pass too.
8. **Re-enable.** Switch the flag ON and restart the worker. Workers start only for platforms enabled at boot (`startJobWorkers` in `apps/browser-worker/src/jobs/bull.ts`).

Do not test against a real marketplace in CI (AGENTS.md, rule 0.8). A live check against a real platform is a manual step that needs compliance approval (`docs/compliance/<platform>.md`).

## If you see this

| Symptom                                                         | Likely cause                                                            | Action                                                                                                 |
| --------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `dom_changed` on every job for one platform, paths name a field | The platform renamed or moved the field                                 | Steps 1 to 8                                                                                           |
| `response is not JSON`                                          | The platform answers with HTML, for example a maintenance or block page | Check the HTTP status, and see `captcha-persistent.md`. A 200 HTML page is not recognised as a CAPTCHA |
| `listing has no price` on `getProduct`                          | That listing has no price now                                           | Expected for that listing. Act only if many listings are affected                                      |
| `price text is not a decimal amount with at most 2 decimals`    | The platform started sending a different price format                   | Steps 3 to 6, and check the price fixtures                                                             |
| `skipped[]` with `parse_error` rising in search                 | Price format change on part of the catalogue                            | Steps 3 to 6                                                                                           |
| `skipped[]` with `unsupported_currency` rising                  | The platform lists in a currency outside EUR, USD and CNY               | Not a DOM change. Report it to DEV-5                                                                   |
| `error` outcome rising, but no `dom_changed` job                | 5xx answers, 404s or `upstream_error`                                   | Check the platform status. For 429 and CAPTCHA, see `captcha-persistent.md`                            |

## Escalate when

- Every job for a platform fails with `dom_changed`, and the fixture diff is too large to review in one pass.
- A re-recorded fixture shows a change in the platform's terms or access rules. Stop, and do not re-enable until compliance has reviewed it.
- A response parses but a value changes meaning (for example, a rating scale). Schema checks cannot catch that, so DEV-5 reviews the mapping by hand.
