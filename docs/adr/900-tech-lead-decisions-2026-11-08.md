# ADR-900: Tech Lead decisions, 2026-11-08 (open questions Q1–Q16, issues #81 #96 #99 #105, ADRs 403 500 501)

## Status

Accepted (Tech Lead). Applied to `AGENTS.md` in the same PR. A decision here can only be changed by a later
TL ADR in the 900 range.

## Context

Several lanes are blocked on Tech Lead questions: AGENTS.md section 8 (Q1–Q16), the `tl-question` issues
#81, #96, #99 and #105, and the TL questions inside ADR-403 (PR #112), ADR-500 (PR #129) and ADR-501
(PR #133). The project is a hackathon with a few days left, so decisions favour the simplest option that
keeps the spec's invariants (spec §11 "puntos que no se deben suavizar"). Where the spec leaves a business
number open, it is set here and lives in versioned config, never in code (rule 0.6).

## Decisions

### Process

- **P1. Phase gates for the hackathon (rule 0.7).** The `phase-<N>-done` tags no longer gate merges. A task
  of any phase may merge once every `Blocked by` task is merged, `pnpm ci:local` passes on the rebased branch
  (rule 0.10), and, for `TL approval: yes` tasks, the TL has approved the PR. The TL still tags the phases,
  as milestones.
- **P2. D5-04 has no blocker.** The mock marketplace is a standalone app that never calls the browser
  worker. Its `Blocked by: D5-01` is removed so DEV-4 (D4-09) and DEV-6 (D6-08) can use it now.

### Open questions (AGENTS.md section 8)

| ID  | Decision                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Q1  | Half-up rounds **away from zero** for negative amounts too (`-2.5 → -3`), the same as Python `Decimal` `ROUND_HALF_UP`. TS must implement it explicitly. `Math.round` is forbidden in money code.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Q2  | **BuyingPowerScore** is informational only. It never gates, ranks or blocks anything. DEV-3 proposes a deterministic formula in an ADR in its own range, and the TL approves it there. Envelopes come from the CSV `budget` rows per category. If a category has no budget row, it has **no envelope** (no implicit split), and its offers get `out_of_budget` with reason `no_envelope`.                                                                                                                                                                                                                                                                                                                                       |
| Q3  | `seller.min_signals` **counts present raw signals** (integer). `data_completeness` stays a reported ratio. Default weights and `x_sat` per signal come from DEV-3's ADR-304, which the TL approves. Institutional signals (KYC, escrow, trade assurance, disputes) must weigh more than volume signals (TL notes §7). Until ADR-304 is approved, `seller.weights.*` stays unset and the trust engine refuses to run. That is intended.                                                                                                                                                                                                                                                                                          |
| Q4  | Sanity reference weights: `sanity.reference_weights` = mission **0.5**, history **0.3**, benchmark **0.2**. They are renormalised over the sources that have data. In Phase 1 there is usually only mission data, so it gets weight 1.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Q5  | No external duties/VAT source in Phase 1. Tenant config `landed.duty_rate` (per category) and `landed.import_vat_rate` (per destination country), plus `finance.cost_of_capital_rate` (tenant), all as decimal fractions. If any of them is unset, that landed-cost line is reported as `unknown`, never as 0, and the offer carries the reason `landed_cost_incomplete`.                                                                                                                                                                                                                                                                                                                                                       |
| Q6  | FX source: **ECB euro reference rates** (they cover USD and CNY). Approved as proposed in ADR-302.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Q7  | Option **A** for `neg.target_discount`, `neg.max_discount`, `approval.threshold`, `approval.dual_control_above`, `signing.high_value_reauth_above`, and `sanity.floor_per_unit` / `ceiling_per_unit`. They stay unset in `/config/defaults`, each tenant sets them during onboarding, and a mission cannot launch while a value it needs is unset. Option **B** for `llm.roles.*`: a global default that points every role at the LLM stub in dev. The **seed** for the two demo tenants (D2-03 seed plus D4-03 `load_defaults`) sets demo values: `neg.target_discount` 0.08, `neg.max_discount` 0.15, `approval.threshold` EUR 5,000, `approval.dual_control_above` EUR 20,000, `signing.high_value_reauth_above` EUR 10,000. |
| Q8  | `stretch` goes to the gate when the landed total is above `approval.threshold`. No new key.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Q9  | **Prisma Migrate is the only owner of DDL** (ADR-201 approved). SQLAlchemy maps tables and never migrates.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Q10 | **No real marketplace in Phase 1 or in the hackathon demo.** Adapter #1 ("official API") is the `mock-a` adapter and adapter #2 ("scraping") is the `mock-b` adapter. Both are built in D5-03 against the D5-04 mock, so D5-05 and D5-06 are satisfied by them. Real platforms move to D5-11 (Phase 2). For each one, its compliance doc is written first and signed by the TL.                                                                                                                                                                                                                                                                                                                                                 |
| Q11 | **Keycloak step-up** (ACR plus `auth_time`) opens the signing session, not a WebAuthn RP in the orchestrator. Keycloak already enforces MFA. The orchestrator takes `auth_at` from the step-up token's `auth_time`. Ed25519 signing stays in the browser (`@apex/crypto-client`).                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Q12 | **Block.** `insufficient_reference` always goes to the gate (spec §3.3.1, "no se negocia a ciegas"). `sanity.on_insufficient_reference` becomes a single-value enum `gate`. The `negotiate` value is removed.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| Q13 | New sellers (`insufficient_data`) **always go to the gate**, with "vendedor nuevo, sin historial suficiente". There is no looser threshold. `fx.pivot` is global (EUR) and cannot be overridden per tenant.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Q14 | Platform KYC/escrow is **not** a hard requirement. It is a confidence signal, plus an optional profile hard constraint `constraints.require_escrow`, off by default.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Q15 | Counterparts use the per-profile mechanism `neg.allowed_counterparts`, default `[]`. In Phase 1 a profile may enable **only `higher_volume` and `framework_contract`**. `prepayment`, `payment_terms`, `guarantee` and `penalty` cannot be enabled before Phase 2, whatever the profile says.                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| Q16 | **No key escrow.** A lost key is handled as a revocation plus a new enrolment (runbook `key-loss.md`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |

### Issue #96 (D4-03 tenant config)

1. Q7 and Q12: see above.
2. **The `config_version` hash covers every category override.** A category patch must change the hash.
   Category patches are validated at propose time and at apply time.
3. **Only leaves may be `null`**, never a whole section, `llm.roles` or `seller.weights`.
4. `fx.pivot` and `money.supported_currencies` are global and closed.
5. **Money in config** is `{amount_minor: int, currency}`, never a float. Rates and percentages are decimal
   fractions parsed as `Decimal`, never `float`.
6. Keys for the negotiation guardrails (spec §3.6), all with tenant scope:

   | Key                                     | Default                  |
   | --------------------------------------- | ------------------------ |
   | `neg.max_tokens_per_conversation`       | **20000**                |
   | `neg.max_messages_per_hour_per_account` | **20**                   |
   | `neg.max_message_chars`                 | **1200**                 |
   | `neg.allowed_counterparts`              | `[]`, constrained by Q15 |

### Issue #99 (D4-13 supervisor)

1. Default `supervisor.stuck_after_minutes` is **30** (tenant scope).
2. Default `supervisor.degrade_on_budget_exhausted` is **true**. Degrade first; if degrading fails, stop with
   a CRITICAL escalation.
3. A stuck mission is escalated, and **its LLM calls are frozen** until a human resumes it.
4. The Phase 1 escalation channel is **one gate queue item** (`type=supervisor`, closed reason enum, no LLM
   text). Notifications come later.
5. Keep D4-13 in one PR. The ADR-401 and ADR-402 numbering is fine.
6. Arq is approved (ADR-401). FX ingestion must be idempotent per slot: `as_of` comes from the scheduled
   slot (`slot_key()`), not from the execution instant.

### Issue #105 (D1-05 JWT library)

Option **A**: PyJWT[crypto], with `algorithms=["RS256"]` pinned and keys from JWKS. Remove `python-jose`.
DEV-1 opens the `pyproject.toml` change and DEV-4 reviews it.

### Issue #81 (local S3 with Object Lock)

1. Option **B** in the short term: mirror the last MinIO images to GHCR (`ghcr.io/guluc3m/...`). Option C
   (SeaweedFS) is a Phase 2 spike.
2. Production default retention for the audit bucket in COMPLIANCE mode is **6 years**, the retention
   period for commercial books and records under Spanish Commercial Code art. 30. Local dev keeps `1d`.

### ADR-403 (D4-06, PR #112)

1. Yes. After a pre-stage unblock, the offer still runs the financial check before negotiating.
2. A price that becomes anomalous after negotiation needs a **new** signed unblock. Reusing the earlier
   unblock is not allowed.
3. Confirmed: D4-11 enforces `financials_stale` and `fx_provisional` at purchase time. The graph also
   blocks `purchase` on `out_of_budget`.
4. **Negotiation contract** (between the graph and DEV-5, replacing `outcome: str`):
   - `NegotiationResult.outcome` is a closed enum: `agreed | no_agreement | escalated |
stopped_anomalous_price | awaiting_human_approval | aborted`.
   - The result carries `negotiation_id`, `price_minor`, `currency` and `quantity`. `price_minor` is the
     **unit** price and is set only when the outcome is `agreed`.
   - `escalated` and `stopped_anomalous_price` route to the **gate**, not to reject. `no_agreement` and
     `aborted` route to reject. `awaiting_human_approval` makes the graph interrupt, and the graph resumes on
     the negotiation event.
   - Non-terminal results are never cached by the effect ledger.
   - The idempotency key includes the attempt: `negotiate:<subject_ref>:<attempt>`. This lets `renegotiate`
     (up to `gate.max_renegotiations`) start a new attempt.

### ADR-500 and ADR-501 (DEV-5)

- **ADR-500 approved.** Interaction uses Playwright on a shared Camoufox, and reading uses crw. crw's AGPL-3.0
  is acceptable because we run it **unmodified as a separate service** and only call its HTTP API. Any patch
  to crw must be published or dropped, and that needs TL approval.
- **ADR-501 approved.** Guardrail limits are built from the #96 keys above.

## Consequences

- Every lane can proceed. The remaining TL gates are code review of `needs-tech-lead` PRs, not open questions.
- New config keys go into `/config/defaults/tenant-config.v1.json` in D4-03 (DEV-4).
- `PROMPT-IMPLEMENTACION.md` is not edited. Where these decisions fill a gap in the spec, this ADR is the
  reference.

## Related

- AGENTS.md sections 0, 5 and 8; issues #81, #96, #99, #105; PRs #107, #112, #129, #133
- ADR-201, ADR-302, ADR-304, ADR-400 to ADR-403, ADR-500, ADR-501
