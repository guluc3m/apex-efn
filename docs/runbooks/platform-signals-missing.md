# Runbook: seller signals missing

**Owner:** DEV-5 (D5-10). **Applies to:** seller signals that a platform does not publish, for one seller or for a whole platform. The worker returns them as `null`, and the metric `apex_scraping_signals_missing_total` counts them.

**Core rule:** a signal the platform does not publish is `null`, never `0`. The contract says so (`RawSellerSignals` in `contracts/internal/browser-worker.openapi.yaml`). A `0` means "the platform says there are none", and a `null` means "unknown". Turning a `null` into a `0` anywhere in the worker, the dashboard or the orchestrator is a defect.

## What you see

- Metric `apex_scraping_signals_missing_total{platform, signal}`, the "Missing seller signals (last hour)" panel in the "APEX-EFN · Scraping health" dashboard.
- The `signal` label takes these values, each mapped from one contract field (`missingSignalsOf` in `apps/browser-worker/src/metrics.ts`):

  | `signal`       | Counted as missing when                                                    |
  | -------------- | -------------------------------------------------------------------------- |
  | `rating_count` | `rating_count` is null or absent                                           |
  | `sales_count`  | `transactions_12m` **and** `lifetime_transactions` are both null or absent |
  | `account_age`  | `account_age_days` is null or absent                                       |
  | `reviews`      | `reviews_total` is null or absent                                          |
  | `catalog`      | `published_products_count` is null or absent                               |

- A signal of `0` is never counted as missing.
- The counter goes up once per **successful** `seller_signals` job, not once per seller. A seller re-scraped again counts again. The metric has no seller label, by design (cardinality rule in `docs/observability/metrics.md`), so you cannot see which seller from the metric.
- The job itself succeeds (`status: "succeeded"`). The `null` fields are in `result.signals` of the job state.

**Worked example:** the mock seller `a-new-shop` (recording: `apps/browser-worker/fixtures/mock-a/GET-mock-a.test_mock-a_api_sellers_a-new-shop_metrics-6e239266013e.json`) publishes null for its orders, its feedback counts, its rated orders and its badges. Its `registered_at` and catalog listings are present. Its expected missing set is therefore `rating_count`, `sales_count` and `reviews`.

## Two different situations

**(a) One seller genuinely has no data.** A new seller with no sales or reviews is the usual case. The `null` fields are correct, and nothing is broken. The decision for such sellers is already made: new or insufficient-data sellers always go to the human gate, with no looser threshold (ADR-900, Q13, `docs/adr/900-tech-lead-decisions-2026-11-08.md`). The rule that counts signals (`values.seller.min_signals`, in `config/defaults/tenant-config.v1.json`) and the confidence engine that uses it (D3-06) are **not built yet**. `apps/orchestrator/src/apex/domain/` contains only `__init__.py`. So this runbook cannot confirm that the gate applies the rule.

**(b) Many sellers of one platform miss the same signal at once.** This points to a platform change or a broken mapping, not to sellers. Signs:

- `apex_scraping_signals_missing_total` for one `signal` rises sharply for a platform, while its other signals stay flat.
- Result payloads show the same field null across many sellers, including sellers that obviously have data.

Treat (b) as `dom-change.md`.

## What to do

1. **Identify the platform and the signal** from the panel labels.
2. **Look at the raw results.** Take the `job_id` of a few `seller_signals` jobs and read `result.signals` from `GET /internal/v1/jobs/{id}` (service bearer token required). Note which field is null.
3. **Decide (a) or (b).** For (a), do nothing in the worker. For (b), go on:
   - Check the field in the mapping table at the top of `apps/browser-worker/src/adapters/mock-a/mapping.ts` (for `mock-a`), and check the value in the recorded platform response under `apps/browser-worker/fixtures/<platform>/`.
   - If the response has the value and the signal is still null, the mapping is wrong. Fix it in DEV-5 code, following `dom-change.md`.
   - If the response does not have the value, the platform stopped publishing it. Follow `dom-change.md` as well. Do not work around it in the worker.
4. **Do not fill gaps.** Do not replace nulls with `0`, averages or defaults, in the worker, in the dashboard or in ad-hoc queries.
5. **Escalate.** Adapter problems go to DEV-5. A confidence band that looks wrong for a seller with null signals goes to the owners of the confidence engine (D3-06) once it exists.

## If you see this

| Symptom                                                | Likely cause                                                                                 | Action                                                                                                                    |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `sales_count` missing for a new seller                 | Situation (a)                                                                                | None                                                                                                                      |
| `rating_count` missing for every seller on a platform  | The platform stopped publishing the rating count, or the mapping broke                       | Situation (b), `dom-change.md`                                                                                            |
| Counter flat, but a seller's job result has nulls      | The counter counts only successful `seller_signals` jobs, not other job kinds or failed jobs | Check the job states for the platform                                                                                     |
| Panel shows "No data"                                  | No `seller_signals` job succeeded in the window, or metrics export is off                    | Check `OTEL_SDK_DISABLED` and `OTEL_EXPORTER_OTLP_ENDPOINT` (defaults in `apps/browser-worker/src/platform/telemetry.ts`) |
| A signal is `0` where the platform does not publish it | Mapping converts null to 0. This breaks the core rule                                        | Escalate to DEV-5 as a defect                                                                                             |
| Missing `reviews` count, but the seller has reviews    | The mapping reads the wrong field, or the platform moved its count                           | Situation (b)                                                                                                             |

## Escalate when

- Any mapping turns a `null` into a `0`. This is a contract violation and it must not wait.
- A single signal goes missing for all sellers of a platform, and the platform's job states show nothing wrong. This points to a silent platform change.
- A seller with null signals gets a high seller-confidence band, or skips the gate, once the orchestrator applies the rule. This bypasses ADR-900 Q13.
