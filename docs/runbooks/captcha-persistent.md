# Runbook: persistent CAPTCHA

**Owner:** DEV-5 (D5-10). **Applies to:** a platform that keeps answering with a CAPTCHA or robot check. The worker recognises one when a 401 or 403 body matches `/captcha|are you a robot|verify you are human/i` (`apps/browser-worker/src/adapters/http.ts`). Those answers become `error.code: "captcha"`.

**Principle:** the worker never solves CAPTCHAs, and no solver integration exists in this repository. Stealth and anti-detection through Camoufox (ADR-500) is **not built yet**, and proxies (D5-02) are **not built yet**. A persistent challenge is a stop signal, not something to work around.

## What you see

- Job state from `GET /internal/v1/jobs/{id}` (service bearer token required): `error.code: "captcha"`, `error.retryable: true`.
- Retries happen at job level only. A CAPTCHA response is not retried inside one request. BullMQ retries the job up to `JOB_ATTEMPTS` (default 3) with exponential backoff from `JOB_BACKOFF_MS` (default 2000). When the attempts run out, the job is `dead_lettered` and a copy goes to the `dead-letter` queue (`apps/browser-worker/src/jobs/bull.ts`).
- Metric `apex_scraping_captchas_total{platform}` increases. It is the "CAPTCHAs (last hour)" panel in the "APEX-EFN · Scraping health" dashboard.
- "Blocked + CAPTCHA share per platform" in the same dashboard is the share of requests with outcome `blocked` or `captcha`. It mixes two causes. Check the outcome breakdown before deciding.

## Interim procedure

1. **Confirm.** Check that the job errors are `captcha` and that the increase is limited to one platform.
2. **Stop.** Switch `platform.<id>.enabled` OFF in Unleash (compose service `unleash`, port 4242; naming in `docs/observability/flags.md`). The worker reads flags every 15 seconds. While the flag is off, no request reaches the platform. Queued jobs for it should end as `failed` with `platform_disabled` (see the note in `platform-session-invalidated.md`).
3. **Do not push through.** Do not raise retries or lower spacing to get past the challenge. The settings are `ADAPTER_MIN_INTERVAL_MS` (default 1000, minimum spacing between requests to one origin) and `ADAPTER_MAX_RETRIES` (default 3, `apps/browser-worker/src/config.ts`). Changing them is a DEV-5 decision after review.
4. **Check the compliance record.** Each platform needs `docs/compliance/<platform>.md` (ToS, robots.txt, rate limits, data collected). Only `docs/compliance/mock-marketplace.md` exists today. Real-platform documents belong to D5-05 and D5-06 and are not written yet. If the platform's document is missing, or it does not allow automated reads, do not re-enable the platform.
5. **Escalate to DEV-5** with the platform id, job ids, timestamps and the panel values. Do not paste response bodies. The CAPTCHA body is never copied into errors, but do not copy it into tickets either.
6. **Re-enable only after DEV-5 confirms.** Switch the flag ON and restart the worker. Workers start only for platforms enabled at boot (`startJobWorkers` in `apps/browser-worker/src/jobs/bull.ts`).

## Retries multiply

With the defaults, a CAPTCHA costs one request per job attempt, so at most `JOB_ATTEMPTS` (3) requests per job. A GET that fails with 502, 503 or 504, a timeout or a network error is retried inside the request up to `ADAPTER_MAX_RETRIES` (3) times, so four HTTP attempts per job attempt, up to 12 requests per job. A 429 with `Retry-After` longer than 60 seconds is not waited on inline. The job fails as `rate_limited` and is retried by BullMQ on its own backoff, not after `Retry-After`. These are the reasons not to add retries when you see errors.

## If you see this

| Symptom                                                        | Likely cause                                                                   | Action                                                           |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------- |
| CAPTCHA on every request to one platform                       | The platform challenges all automated traffic                                  | Interim procedure, steps 2 and 5                                 |
| CAPTCHA after bursts of requests                               | Request rate is too high                                                       | Keep the flag off. DEV-5 reviews spacing before re-enabling      |
| CAPTCHA for one listing or seller only                         | A challenge on one page                                                        | Still back off. Report the platform id and job ids to DEV-5      |
| High "Blocked + CAPTCHA share", but `captchas` counter is flat | The share includes `blocked`: robots.txt refusals and 429 `rate_limited`       | Read the `outcome` breakdown in "Requests per second by outcome" |
| `captcha` on the mock marketplace                              | The mock never sends one, so the adapter points at a real platform by mistake  | Stop, check `MOCK_A_BASE_URL`, escalate to DEV-5                 |
| HTTP 200 page that looks like a challenge                      | The worker only checks the marker on 401 and 403, so it shows as `dom_changed` | See `dom-change.md`                                              |

## Escalate when

- A CAPTCHA appears on a platform whose compliance document is missing or unsigned.
- A CAPTCHA appears again after the flag was turned back on and the worker restarted.
- A CAPTCHA appears on the mock marketplace. It should never happen, so the configuration is wrong.
