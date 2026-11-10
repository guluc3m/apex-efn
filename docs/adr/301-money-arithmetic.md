# ADR-301: Money arithmetic in TypeScript and Python

## Status

Accepted (D3-02, TL approved on PR #271)

## Context

Money is integer minor units, int64 (`Money {amount_minor: int64, currency}` in `contracts/openapi.yaml`). The
scaffold `@apex/money` had float paths (`fromMajor(number)`, `multiply(number)`, `toMajor()`), used
`Math.round`, which rounds `-2.5` to `-2`, and allocated remainders by ratio size, which could hand a cent to
a zero-ratio bucket. Python had no money type. Python (`apex.domain.money`) decides. TypeScript mirrors it for
display and previews. Both must pass the same vectors (ADR-300).

## Decision

1. **Representation and range.** Both languages accept amounts in **±(2^53 − 1)** minor units and refuse
   anything outside it (`amount_out_of_range`). That is about ±90 billion EUR, far beyond any purchase, and it
   fits in the int64 columns and the int64 contract field.
   - TypeScript: `number`, checked with `Number.isSafeInteger`. The generated contract types already give
     `amount_minor: number`, and `JSON.parse` cannot deliver more than 2^53 anyway, so a `bigint` field would
     promise precision the transport has already lost. Intermediate products (`amount × factor`, allocation
     shares) are computed in `bigint`, so only the result has to be in range.
   - Python: `int` (never `bool`), checked against the same range. Python could hold the whole int64 range, but
     then an amount between 2^53 and 2^63 would be valid in the authority and invalid in the mirror, and the
     shared vectors could not cover overflow. One range for both keeps them in agreement.
2. **One rounding rule.** Every operation that produces a fractional minor unit rounds **half away from zero**
   to the destination minor unit (ADR-900 Q1): `2.5 → 3`, `-2.5 → -3`, the same as Python `ROUND_HALF_UP`.
   `Math.round` and Python `round()` (banker's) are not used.
3. **No floats in or out.**
   - `Money.parse("-12.345", "EUR")` reads a plain decimal string (`-?digits(.digits)?`, no exponent, no
     separators, no spaces) and rounds by rule 2. Anything else is `invalid_decimal`.
   - `toDecimalString()` writes the exact major amount (`"-12.35"`). `toMajor()` and `fromMajor(number)` are gone.
   - `multiply(factor)` takes an integer or a decimal string (`"1.21"`), applied as an exact rational, then rule 2.
   - `divide(divisor)` takes a non-zero integer (`invalid_divisor`, `division_by_zero`), then rule 2.
4. **Allocation sums exactly.** `allocate(ratios)` takes non-negative integer ratios with a positive sum
   (callers scale percentages to basis points). It uses the largest-remainder method on the absolute amount:
   floor every share, then give one minor unit to the largest remainders, ties to the lower index, and apply
   the sign at the end. The parts always sum to the amount, each part is within one minor unit of its exact
   share, a zero ratio always gets zero, and `allocate(-x) = -allocate(x)`.
5. **Currencies.** The closed contract enum `EUR | USD | CNY` (`unsupported_currency` otherwise). All three
   have 2 minor digits (ISO 4217). Mixing currencies is `currency_mismatch`. Conversion is FX (D3-03).
6. **Errors carry codes** (ADR-300): `invalid_amount` (not an integer), `amount_out_of_range`,
   `invalid_decimal`, `invalid_ratios`, `invalid_divisor`, `division_by_zero`, `currency_mismatch`, `unsupported_currency`.

## Consequences

- Every money vector in `packages/test-vectors/money/` runs in Vitest and Pytest. Property tests (fast-check,
  hypothesis) cover the parse/format round trip, allocation sums and bounds, and sign symmetry of rounding.
- Callers that had a float must now hold a decimal string. That is the point.
- `fx.ts` still multiplies by a float rate. D3-03 replaces it with decimal-string rates.
- `Intl.NumberFormat` formats the decimal string, which is exact for display.

## Related

- ADR-300 (vectors, tolerance), ADR-900 Q1 (negative rounding)
- `PROMPT-IMPLEMENTACION.md` §3.5.1, AGENTS.md D3-02
