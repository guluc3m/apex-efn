# ADR-300: Shared domain test vectors, tolerance policy and injected clock

## Status

Accepted (D3-01)

## Context

The deterministic engines (money, FX, CSV import, landed cost, seller confidence, price sanity, gate matrix,
MCDA) exist twice. Python (`apex.domain`) is the runtime authority for decisions. TypeScript (`@apex/money`,
`@apex/scoring`) mirrors it for UI previews. If they disagree, a buyer sees one number and signs another. The
spec also requires every result to be reproducible from its snapshot plus config (§3.4.2, §3.3), which is
impossible if an engine reads the clock or unseeded randomness. The scaffold called `new Date()` inside the
engines.

## Decision

1. **One set of vectors, two runners.** Vectors live in `packages/test-vectors/<domain>/*.json` with the format
   in `packages/test-vectors/schema.json`: `{engine, description, source?, tolerance?, vectors[], errors[]}`,
   each case `{name, input, config?, expected, tolerance?}`. Vitest loads them through `@apex/test-vectors`,
   Pytest through `tests/domain/vectors.py`. An unknown `engine` id fails the run. Pytest validates every file
   against the schema. A behaviour change in an engine lands with its vectors, and both languages pass them in
   the same PR.
2. **Errors are codes.** Error cases name a stable snake_case code. Engines raise errors that carry it (`code`).
3. **int64 as strings.** JSON integers beyond 2^53 are rejected by both loaders and are written as decimal
   strings, because `JSON.parse` would round them silently.
4. **Tolerance policy.**
   - Money, minor units, counts, bands, enums, verdicts and decisions: **exact**. No tolerance, ever.
   - Statistics (median, MAD, IQR, z-scores, Wilson bound, normalised signals, scores before banding): an
     absolute epsilon declared in the file or vector, at most `1e-3`, normally `1e-9` or tighter. The schema
     caps it. A band or decision derived from a statistic is compared exactly, so the epsilon can never flip
     an outcome in a vector.
   - The comparator is the same on both sides: numbers within the epsilon, everything else by type and value.
5. **Injected clock.** Engines take `now` (TS: `Date` or ISO-8601 string, Python: `datetime` with tzinfo) and
   config as parameters. Reading the clock (`new Date()`, `Date.now()`, `datetime.now()`, `time.time()`) or
   unseeded randomness (`Math.random()`, `random`, `uuid`) inside an engine is a bug. Enforced by an ESLint
   `no-restricted-syntax` rule in `packages/money` and `packages/scoring` (tests excluded) and by
   `tests/domain/test_determinism.py`, which scans `apex/domain/**` with `ast`. Callers get `now` from
   `apex.common.clock.Clock` (DEV-4) or the request.

## Consequences

- Cross-language drift shows up as a red vector in CI, not as a mismatch in production.
- Engines are pure: same snapshot + config + `now` gives the same output, which the signed decision payloads
  rely on.
- Callers must pass `now` everywhere. `FxConverter.getRate/convert/isRateFresh`, `SellerConfidenceEngine.compute`,
  `detectReviewAnomalies` and `PriceSanityEngine.check` now take it as a required argument.
- The TS runner does not validate the JSON schema (no new dependency for it). Pytest does, on every file, so a
  bad file still fails CI.

## Related

- AGENTS.md D3-01, rule 0.6; spec §3.3, §3.4.2, §5.10
- ADR-208 (signing vectors, `packages/test-vectors/signing/`, DEV-2)
- ADR-900 Q1 (half away from zero), used by the sample vectors
