# ADR-302: FX engine and ECB rate ingestion

## Status

Accepted (D3-03, TL approved on PR #274). The source (ECB reference rates) was approved in ADR-900 Q6.

## Context

Offers, quotes and CSV rows arrive in EUR, USD or CNY. Every comparison happens in EUR (`fx.pivot`, global,
ADR-900 Q13). The scaffold `FxConverter` used float rates, returned `null` on a stale rate and triangulated
with legs from different sources and days. Spec §3.5.1 and criterion 24 require recorded conversions
(`fx_rate`, `fx_as_of`, `fx_source`) and `fx_provisional` when the rate is older than `fx.max_age_hours`.

## Decision

1. **Rates are decimal strings.** A rate is `{base, quote, rate, as_of, source}`. `rate` is a positive plain
   decimal string (`invalid_rate` otherwise), read as an exact rational. Rates are stored as `Decimal(24, 12)`
   (`fx_rates`), never as floats.
2. **Choosing a rate.** `convert(money, to, rates, now, cfg)` ignores rates with `as_of > now`, then considers
   these paths:
   - direct `from→to`
   - inverse `to→from` (exact `1/r`)
   - when neither side is EUR, triangulation `from→EUR→to`, with each leg direct or inverse and **both legs
     from the same `source` and the same `as_of`**.

   The path with the latest `as_of` wins. Ties go to direct, then inverse, then triangulated, then the
   lexically smaller source. No path is `rate_unavailable`. A currency outside EUR/USD/CNY is
   `unsupported_currency`.

3. **Amount.** `amount_minor × rate × 10^(minor digits of to − minor digits of from)` as an exact rational,
   rounded half away from zero (ADR-301). The rate is never rounded before it is applied.
4. **Stale rates still convert.** If `now − as_of > fx.max_age_hours`, the conversion is returned with
   `fx_provisional = true`. Exactly `max_age_hours` is still fresh. D4-11 asks for extra confirmation on
   provisional conversions.
5. **The record is the contract's `ConvertedMoney`.**
   - It carries `amount_minor`, `currency`, `original_amount_minor`, `original_currency`, `fx_rate`, `fx_as_of`,
     `fx_source`, `converted` and `fx_provisional`.
   - `fx_rate` is the effective rate rounded half away from zero to 12 decimals, the precision of the column,
     with trailing zeros removed. It is for audit and display. The exact amount can be recomputed from the
     stored rows (`source`, `as_of`).
   - Same-currency "conversions" return `converted = false` with no FX fields.
6. **Ingestion (`apex/domain/fx/ingest.py`).**
   - It reads the ECB euro reference rates (`eurofxref-daily.xml`) through an injected `httpx.AsyncClient`
     and stores `EUR→USD` and `EUR→CNY` with `source = "ecb"`.
   - `as_of` is the ECB reference date at 16:00 Europe/Berlin, the ECB publication time, not the time the
     job happened to run.
   - Rows are inserted with `ON CONFLICT DO NOTHING` on `(base, quote, as_of, source)`, so the history stays
     insert-only and a retry, a late run or a second replica counts `already_present` instead of writing a
     second set.
   - `ingested_at` is the database's `CURRENT_TIMESTAMP`, so domain code still never reads the clock (ADR-300).
   - The row id is deterministic: `ecb:EUR:USD:<as_of>`.
   - The job's slot `as_of` (ADR-900, issue #99 item 6) is what the job reports. On a weekend or a TARGET
     holiday the ECB file still holds the last business day, and re-ingesting it is a no-op.

## Consequences

- Over a weekend the latest rate is about 56 hours old on Monday morning, so with the default
  `fx.max_age_hours = 36` conversions are `fx_provisional` until the Monday publication. That is the honest
  outcome. A tenant that wants otherwise raises `fx.max_age_hours`.
- TS (`@apex/money` `convert`) mirrors the engine for previews and passes the same vectors
  (`packages/test-vectors/fx/`).
- Wiring `FxPort` and `FxRateSource` into the app (`apex/wiring.py`, `workers/ports.py`) belongs to DEV-4.
  `apex.domain.fx` provides the functions and the ingestion adapter.

## Related

- ADR-300, ADR-301, ADR-900 Q6 and Q13, issue #99 item 6
- Spec §3.5.1, criterion 24
