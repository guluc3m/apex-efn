# Compliance: `<platform-id>` (template)

<!--
How to use this template:
1. Copy this file to docs/compliance/<platform-id>.md. Use the same id as the adapter and the flag
   (platform.<platform-id>.enabled, see docs/observability/flags.md).
2. Fill every section. Write "N/A" with a reason if a section does not apply. Do not delete sections.
3. Quote ToS clauses verbatim and link to the exact version, with the date you read it.
4. Status stays "draft" until compliance sign-off is recorded in section 9. No adapter for a platform
   may be merged while its doc is draft or rejected (PROMPT-IMPLEMENTACION.md §5.9).
5. If the ToS forbid automation, do not implement the adapter. Record the reason and an alternative here.
-->

## Header

| Field                             | Value                                                                |
| --------------------------------- | -------------------------------------------------------------------- |
| Platform id                       | _`<platform-id>`, lowercase, `[a-z0-9-]+`, same as the flag segment_ |
| Display name                      | _Name as shown to users_                                             |
| Adapter transport                 | _`http` or `browser`_                                                |
| Integration type                  | _`official API` or `scraping` or `mock`_                             |
| Feature flag                      | `platform.<platform-id>.enabled` (default OFF, fails closed)         |
| Owner lane                        | DEV-5 (Browser Automation & Negotiation)                             |
| Status                            | _`draft` or `approved` or `rejected`_                                |
| Approved by (compliance sign-off) | _TBD, see open question Q10 in AGENTS.md section 8_                  |
| Last reviewed                     | _YYYY-MM-DD_                                                         |

## 1. Terms of service review

<!-- Link the ToS, privacy policy, API terms and any robots/usage policy. Give the version and the date read. -->

- ToS: _URL_ (version/date: _..._)
- Privacy policy: _URL_
- API terms (if any): _URL_

Relevant clauses (quote verbatim, one line each):

| Topic                              | Clause (verbatim) | Source    | Impact on APEX-EFN |
| ---------------------------------- | ----------------- | --------- | ------------------ |
| Automated access / bots / scraping | _"..."_           | _section_ | _..._              |
| Data reuse and storage             | _"..."_           | _section_ | _..._              |
| Messaging / contacting sellers     | _"..."_           | _section_ | _..._              |
| Accounts and sharing credentials   | _"..."_           | _section_ | _..._              |

**Automation allowed?** _yes / no / conditional_ (conditions: _..._)

**Decision:** _implement / implement with limits / do not implement_. Reason: _..._

If "do not implement": alternative proposed: _..._

## 2. Official API

<!-- Prefer the official API over scraping (PROMPT-IMPLEMENTACION.md §5.9). -->

- Official API exists: _yes / no_. Documentation: _URL_
- Access model (key, OAuth, partner program): _..._
- Scopes needed (minimal set): _..._
- Quotas (per second / minute / day): _..._
- If an API exists and is not used, justify here: _..._

## 3. robots.txt and rate limits

- robots.txt URL: _URL_ (read on: _YYYY-MM-DD_)
- Paths allowed for this adapter: _..._
- Paths disallowed and therefore never requested: _..._
- Per-domain concurrency: _N_ (BullMQ per-domain queue, D5-01)
- Request spacing and backoff: _e.g. min 2 s between requests, exponential backoff with jitter on 429/5xx, max N retries_
- Circuit breaker: _open after N consecutive failures, cool-down M minutes_
- Chat messages per hour per account: _N_ (anti-abuse, see section 6)

## 4. Data collected and purpose

<!-- Data minimisation: collect only what a sourcing decision needs. Seller signals come only from public profile data. -->

| Data item                                                  | Source page / endpoint | Purpose                                       | Retention |
| ---------------------------------------------------------- | ---------------------- | --------------------------------------------- | --------- |
| Product title, price, currency, list url                   | _..._                  | Offer comparison and price sanity (spec §3.3) | _..._     |
| Seller public profile: account age                         | _..._                  | Seller confidence signal (§3.4.2)             | _..._     |
| Seller public profile: completed sales count               | _..._                  | Seller confidence signal                      | _..._     |
| Seller public profile: catalog size                        | _..._                  | Seller confidence signal                      | _..._     |
| Seller public reviews: rating, count, dates, verified flag | _..._                  | Seller confidence and manipulation flags      | _..._     |
| Seller guarantees / return policy (public)                 | _..._                  | Seller confidence and gate reasons            | _..._     |
| Chat transcripts (negotiation)                             | _..._                  | Audit and human review                        | _..._     |
| Screenshots of chat (negotiation)                          | _..._                  | Audit evidence                                | _..._     |

Explicitly **not** collected: _personal data of individuals (name, address, phone, email), private buyer data,
payment data, anything behind a login beyond the account's own negotiation, ..._

Legal basis and GDPR notes: _..._

## 5. Accounts, credentials and sessions

- Accounts are referenced only by opaque `account_id` (`CredentialRef`). The orchestrator and the LLM never see
  usernames, passwords, cookies or tokens.
- Credentials and browser session state (cookies, storage) are stored encrypted in Vault, per tenant
  (D1-06). Only the browser worker reads them.
- Session invalidation is detected and the worker stops. A human-assisted reauth flow is used
  (runbook: `platform-session-invalidated.md`). The worker never attempts to bypass CAPTCHAs or MFA.
- Credentials never appear in prompts, logs, traces or fixtures (criterion 29, leak test in CI).
- Accounts owned by: _tenant / APEX-EFN operator_. Number of accounts: _N_.

## 6. Chat / negotiation use

- Chat with sellers allowed by ToS: _yes / no / conditional_ (conditions: _..._)
- Mode: _semi-automatic (every drafted message waits for human approval, Phase 1)_ or _autonomous (behind `negotiation.autonomous_send`, Phase 2+)_
- Anti-abuse rules (PROMPT-IMPLEMENTACION.md §5.9):
  - Rate limit per seller account: _N messages per hour_
  - Rate limit per platform account: _N messages per hour_
  - Never contact the same seller from simultaneous missions (lock per seller)
  - Stop and escalate to a human on off-platform payment requests and on requests for sensitive data
- The agent never accepts a binding commitment (see §3.6 and D5-07 guardrails).

## 7. Kill switch

- Flag: `platform.<platform-id>.enabled`
- How to disable: switch the flag OFF in Unleash (UI or admin API). No code change and no deploy.
  Propagation: the next `refresh()` (orchestrator) or the next polling interval (browser worker, 60 s in the example).
- Expected behaviour when OFF (fail closed):
  - The adapter registry does not call the platform for search, product, seller, chat or any other operation.
  - Open chat sessions for this platform are stopped cleanly and reported to the gate as `platform_disabled`.
  - Unknown flag, Unleash unreachable with no snapshot, or evaluation error are all treated as OFF.
- Verification: test in D5-03 proves a disabled platform's adapter is never called.

## 8. Risks and open questions

| #   | Risk or question                                                      | Mitigation or owner | Status          |
| --- | --------------------------------------------------------------------- | ------------------- | --------------- |
| 1   | _..._                                                                 | _..._               | _open / closed_ |
| 2   | Who signs this document for real platforms (AGENTS.md section 8, Q10) | TL decision         | open            |

## 9. Sign-off

| Role                        | Name        | Date  | Decision           |
| --------------------------- | ----------- | ----- | ------------------ |
| Adapter owner (DEV-5)       | _..._       | _..._ | _..._              |
| Compliance / legal reviewer | _TBD (Q10)_ | _..._ | _approve / reject_ |
| Tech Lead                   | _TBD_       | _..._ | _..._              |

Status change to `approved` requires the compliance reviewer and the Tech Lead decision recorded above.
