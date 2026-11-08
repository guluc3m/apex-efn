# Runbook: financial snapshot stale

**Owner:** DEV-4 (D4-07). **Applies to:** any tenant whose active financial snapshot is older than
`finance.stale_after_days` (default 45 days), or that has none.

## What the user sees

- `financials_stale` is set on the tenant.
- The dashboard blocks **direct purchase** from every deal and explains why (`financials_stale` in
  `blocked_actions`).
- A mission cannot launch at all when there is **no active snapshot** (`OnboardingIncomplete`, criterion 1).

## Why it is a hard block

The financial fit of every offer is computed against the snapshot. Buying against an old snapshot means
committing money the company may not have. The spec makes this a blocking condition, not a warning
(section 3.5).

## What to do

1. Ask the tenant to re-import the CSV in the onboarding wizard
   (`POST /v1/onboarding/{id}/financial-csv`). The upload **never activates** anything: it returns an
   import report with per-row rejections.
2. Check the report before activating. A file with rejected rows still activates, but the derived
   envelopes exclude them; if the rejections are material, ask for a corrected file.
3. The tenant signs the activation (`POST /v1/onboarding/{id}/financial-csv/activate` creates the decision;
   the snapshot becomes `active` only after the signature). Activation needs immediate re-authentication.
4. The previous snapshot becomes `superseded` and stays immutable for audit and projection.

## If the import is rejected

| Symptom | Cause | Fix |
|---|---|---|
| Every row rejected | Wrong separator or encoding | UTF-8, `,` `;` or tab; the importer autodetects |
| `unknown metric` | Metric outside the closed enum | Use the metric names from spec 3.1.1 |
| `duplicate period` | The same metric twice for one period | Keep one row per metric and period; the later row is rejected, the file is not |
| Decimals rejected | Amounts are integer minor units | `12345` means 123.45 EUR |
| `projection_enabled` false | Fewer than 3 periods | Supply 3 periods to enable projection; 1 period with `cash_balance` is the minimum |

## Escalate when

- The tenant cannot produce a valid file at all: they cannot buy, so this is a commercial blocker.
- The activation decision stays `pending_signature` for more than a day: the signing session may be
  blocked (see `signing-session-blocked.md`).
- A snapshot was activated with numbers that look wrong: do **not** edit it. Activate a corrected file;
  the old one stays immutable in the audit trail.
