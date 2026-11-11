# ADR-305: Financial CSV importer and derived values

Status: **Accepted** (TL decision, 2026-11-11). Lane DEV-3, task D3-04.

## Decisions
1. `apex.domain.finance.csv_import.parse(content, base_currency, rates, now, cfg) -> ImportResult` is pure. Unreadable
   files raise `CsvImportError`; every row problem rejects that row only. Later duplicates of `(period, metric)` are rejected.
2. Row reason codes use the closed contract enum. An FX rate that does not exist for a row maps to `unsupported_currency`.
3. FX is applied at the end of the period's month (capped at `now`). Staleness is measured against that date; any stale row sets
   `fx_provisional`. `ImportResult.warning_codes` holds deterministic codes; `report.warnings` stays empty for the LLM to word.
4. Column typing the spec leaves open: `safety_buffer_pct` takes `value_bp`; `payment_term_days` takes a plain integer in
   `value_minor` with no currency; every other metric takes `value_minor` + `currency`.
5. `projection_enabled` needs 3 periods with `cash_balance`; `periods_loaded` counts those periods; `reference_date` is the end of the latest one.
6. **Envelopes: none.** ADR-900 Q2 derives them from `budget` rows, but the closed metric enum of spec 3.1.1 has no budget metric.
   `envelopes` is always `[]` until the TL adds one (open question).
7. **net_buying_capacity (proposal):** at the reference period, `cash_balance + credit_line_available - tax_reserve - cash_balance * safety_buffer_bp / 10000`,
   in the base currency, missing parts counted as 0. `buying_power_score` stays `null` (Q2: informational, formula pending).

## TL decision (2026-11-11)
- Points 1 to 5 accepted as written.
- Point 6: accepted. Empty envelopes are the honest result; the offers then get `out_of_budget` / `no_envelope` per ADR-900 Q2.
  Adding a budget metric to the closed enum is a spec change and stays a follow-up for the product owner, not part of D3-04.
- Point 7: accepted as the default formula. It is conservative (it subtracts the tax reserve and the safety buffer) and
  `buying_power_score` stays informational, so it gates nothing. Changing it needs a new ADR.
