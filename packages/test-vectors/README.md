# Domain test vectors (DEV-3, ADR-300)

Known-answer cases shared by the TypeScript mirror (`@apex/money`, `@apex/scoring`) and the Python runtime
authority (`apex.domain`). Both sides run every case. A green run on both means both languages compute the
same result for the same input, config and clock.

`signing/` belongs to DEV-2 and has its own format and runners (see `signing/README.md`). The runners below
never load it.

## Format

One folder per domain (`money/`, `fx/`, `trust/`, ...). Each `*.json` file follows [`schema.json`](schema.json):

```json
{
  "$schema": "../schema.json",
  "engine": "money.round",
  "description": "What this file checks",
  "source": "Where the expected values come from",
  "tolerance": 0,
  "vectors": [{ "name": "half-negative", "input": {}, "config": {}, "expected": {} }],
  "errors": [
    { "name": "bad-currency", "input": {}, "expected": { "error": "unsupported_currency" } }
  ]
}
```

- `engine` is a dotted id. Each runner maps it to its implementation and fails on an unknown id, so a file is
  never skipped silently.
- `config` is the config slice the case runs with. `now`, when the engine needs it, goes in `input` as an
  ISO-8601 UTC string. Engines never read the clock.
- `errors[].expected.error` is a stable error code. TS engines throw an error with a `code` property, Python
  engines raise an exception with a `code` attribute.
- Integers beyond 2^53 (int64 money) are written as decimal strings. Both loaders reject unsafe JSON integers.
- `tolerance` (file or vector) is an absolute epsilon for numbers, default `0` (exact), at most `0.001`.
  Money, minor units and integers are always exact. See ADR-300.

## Runners

- TypeScript: `loadVectorFiles(folder)` and `mismatch(actual, expected, tolerance)` from `@apex/test-vectors`
  (example: `packages/money/src/vectors.test.ts`).
- Python: `cases(folder)` and `mismatch(...)` from `apps/orchestrator/tests/domain/vectors.py` (example:
  `tests/domain/test_vectors.py`). The Python side also validates every file against `schema.json`.

`money/` holds the money arithmetic vectors (D3-02, ADR-301) and `fx/` the FX conversion vectors (D3-03, ADR-302).
