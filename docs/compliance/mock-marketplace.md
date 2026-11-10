# Compliance: mock marketplace (`mock-a`, `mock-b`)

## Header

| Field                             | Value                                                                               |
| --------------------------------- | ----------------------------------------------------------------------------------- |
| Platform id                       | `mock-a` (JSON API), `mock-b` (HTML and chat page)                                  |
| Display name                      | APEX Mock Marketplace (synthetic)                                                   |
| Adapter transport                 | `mock-a`: `http`; `mock-b`: `browser`                                               |
| Integration type                  | mock (internal test double, no third party)                                         |
| Feature flag                      | `platform.mock-a.enabled`, `platform.mock-b.enabled` (default OFF, fails closed)    |
| Owner lane                        | DEV-5 (Browser Automation & Negotiation)                                            |
| Status                            | approved for test use only                                                          |
| Approved by (compliance sign-off) | N/A (internal, synthetic). Real platforms remain TBD per Q10 in AGENTS.md section 8 |
| Last reviewed                     | 2026-11-10                                                                          |

## 1. Terms of service review

- ToS: N/A. The mock is an internal application in this repository (`apps/mock-marketplace/`). It is not a
  third-party service and has no terms of its own.
- Privacy policy: N/A. All data is synthetic (see section 4).
- Automation: allowed, because the mock is ours. Automated access is the purpose of the mock.
- Decision: implement. Test use only.

Rule that applies regardless: **never test against real marketplaces** (AGENTS.md rule 0.8). Tests and E2E
run against the mock, fixtures and the LLM stub. Real platforms need their own compliance doc
(`docs/compliance/_template.md`) and TL approval.

## 2. Official API

- Not applicable. `mock-a` exposes a JSON API that imitates an official API shape for adapter testing only.
  It does not replace or mirror any real provider API.

## 2b. Tooling used against this platform

- Read-only collection (search, product, seller, reviews): deterministic crawler (crw, Firecrawl-compatible
  API) for HTML, plain HTTP for `mock-a` JSON. No LLM involved in extraction.
- Interaction (chat): Playwright driving a shared Camoufox (Firefox) instance.
- Tool choices and licensing (crw is AGPL-3.0) are recorded in an ADR in the 500 range and need TL review.

## 3. robots.txt and rate limits

- robots.txt: the mock serves `/robots.txt` that allows everything except `/__control/`. Adapters and the
  crawler must honour it exactly as they would on a real platform.
- Crawling: the deterministic crawler (crw, see section 2b) can crawl `mock-b` HTML pages without a browser,
  because they are fully server-rendered. The chat requires interaction and goes through Playwright.
- Rate limits: **not enforced by the mock**. Adapters still apply their normal production limits, so
  behaviour matches production:
  - Per-domain concurrency queue and exponential backoff with jitter (D5-01).
  - Request spacing and circuit breaker as configured for the adapter.
  - Chat messages per hour per account (section 6), enforced in the negotiation engine, not in the mock.
- Reason: testing rate-limit handling needs the adapter to behave as if the limit exists.

## 4. Data collected and purpose

All data is **synthetic**: sellers, products, reviews, prices and chat personas are fixtures under
`apps/mock-marketplace/fixtures`. No real company, person or payment data is present.

Both mock platforms are consumed by adapters (D5-05 `mock-a` over its JSON API, D5-06 `mock-b` over its HTML,
ADR-505). `mock-b` is read with the polite HTTP client: `robots.txt` is honoured (it only disallows
`/__control/`), requests are spaced, and the adapter never touches the control endpoints.

| Data item                                                                | Source page / endpoint                                      | Purpose                                                       | Retention                                 |
| ------------------------------------------------------------------------ | ----------------------------------------------------------- | ------------------------------------------------------------- | ----------------------------------------- |
| Product title, price, currency                                           | `mock-a` JSON API; `mock-b` HTML product page               | Test offer normalisation and price sanity (criterion 5, 3)    | Fixtures in repo, versioned               |
| Seller profile: account age, sales, catalog size                         | `mock-a` seller endpoint; `mock-b` seller page              | Test seller confidence (criteria 6 to 9)                      | Fixtures in repo                          |
| Seller reviews: rating, count, dates, verified flag                      | `mock-a` reviews endpoint; `mock-b` reviews section         | Test manipulation flags (review burst, abnormal 5-star share) | Fixtures in repo                          |
| Product specs, certifications, tiers, MOQ, shipping, incoterm, lead time | `mock-a` product endpoint; `mock-b` product page            | Test landed cost, hard constraints and MCDA (criteria 4, 15)  | Fixtures in repo                          |
| Seller display name, country, GMV, dispute and refund rates              | `mock-a` seller and metrics endpoints; `mock-b` seller page | Test seller confidence and its penalties (criteria 6 to 9)    | Fixtures in repo                          |
| Review text (at most 2000 characters each, at most `max_reviews`)        | `mock-a` reviews endpoint; `mock-b` reviews section         | Test duplicate or generic review text detection (spec 3.4.2)  | Fixtures in repo                          |
| Scripted chat messages                                                   | `mock-a` JSON conversations API; `mock-b` chat page         | Test negotiation and adversarial suite (criteria 13, 14)      | Fixtures in repo; test runs are ephemeral |
| Test transcripts and screenshots                                         | Local test output                                           | Debugging test failures                                       | Deleted with the test run or reset        |

Explicitly not collected or stored: any real personal data, real account credentials, payment data, or
data from any real marketplace. Fixtures must pass the secret scan in CI (D1-04).

## 5. Accounts, credentials and sessions

- The mock has **no login and no accounts** in this version (D5-04). Every page and API call is anonymous,
  so there are no credentials to store.
- Adapters must still pass an opaque `account_id` through the same code path as for real platforms (D5-02),
  so the credential and session handling can be exercised once login is added to the mock.
- Follow-up (D5-02): add a fake login and a session-expired switch under `/__control/*` to test session
  invalidation detection and human-assisted reauth (runbook `platform-session-invalidated.md`).

## 6. Chat / negotiation use

- Chat is allowed in the mock, and the mock exists to test it.
- Scripted personas are **deterministic**. Each persona has fixed replies, so suite runs are reproducible.
  Personas: `cooperative`, `aggressive`, `evasive`, `off_platform`, `sensitive_data`, `lowball`, `chinese`,
  `truncated`, `unsupported_currency`.
- Purpose: drive the adversarial negotiation suite (criterion 14, D5-09) and the E2E tests (D6-08). The suite
  checks no `max_discount` breach, no unauthorised concessions, escalation on `off_platform` and
  `sensitive_data`, and a stop on anomalous prices.
- Mode under test: semi-automatic (human approval per message, Phase 1). Autonomous sending is tested only
  behind `negotiation.autonomous_send` in test configuration.
- Anti-abuse rules are still tested as in production: no simultaneous missions contacting the same seller,
  per-account message rate limit, and escalation to a human.

### Test control endpoints

- The mock exposes control endpoints under `/__control/*` for tests only: reset with a seed, set the active
  persona for a chat, read a transcript.
- These endpoints must **never** exist on a real platform adapter. Adapters must not call `/__control/*`.
- The mock must never be deployed to production or exposed to the internet. It is for local compose
  (profile `apps`, port 8002) and CI only.

## 7. Kill switch

- Flags: `platform.mock-a.enabled`, `platform.mock-b.enabled`.
- Seeded in Unleash **disabled** by `infra/unleash/seed-flags.mjs`. The seed script never changes an
  existing flag. Tests use static flags (`StaticFlags`) and do not need Unleash.
- How to disable: switch the flag OFF in Unleash, or in tests set the static flag to `false`. No code change.
- Expected behaviour when OFF (fail closed): the adapter registry does not call the mock. The adapter contract
  test for disabled platforms (D5-03) asserts that no request reaches the mock.
- Unknown flag, Unleash unreachable with no snapshot, or evaluation error: treated as OFF.

## 8. Risks and open questions

| #   | Risk or question                                                              | Mitigation or owner                                                                | Status |
| --- | ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ------ |
| 1   | Mock behaviour drifts from real platforms, so tests pass but production fails | Adapter contract suite (D5-03) and recorded fixtures from approved platforms only  | open   |
| 2   | Mock reachable outside the test environment                                   | Compose `apps` profile only; never in production Helm or Terraform (D1-09 review)  | open   |
| 3   | Control endpoints leak into a real adapter                                    | Adapter code review and a CI grep for `/__control` outside `apps/mock-marketplace` | open   |
| 4   | Real platforms not chosen yet; who signs their compliance docs                | AGENTS.md section 8, Q10 (TL)                                                      | open   |

## 9. Sign-off

| Role                        | Name                           | Date  | Decision             |
| --------------------------- | ------------------------------ | ----- | -------------------- |
| Adapter owner (DEV-5)       | _to be recorded_               | _..._ | approve for test use |
| Compliance / legal reviewer | N/A (internal, synthetic data) | -     | -                    |
| Tech Lead                   | _to be recorded_               | _..._ | _..._                |

Scope of approval: local and CI testing only. This document does not approve any real platform.
