# Signing test vectors (DEV-2, D2-06)

Shared known-answer tests for the canonical JSON, hashing and Ed25519 signatures of decisions (spec §5.10.2,
ADR-208). Both implementations run every file:

- TypeScript: `packages/crypto-client/src/signing-vectors.test.ts` (`pnpm --filter @apex/crypto-client test`)
- Python: `apps/orchestrator/tests/signing/test_vectors.py` (`uv run pytest tests/signing`)

Passing on both sides means the browser and the orchestrator produce the same bytes, hashes and signatures.

Each file is `{description, source, vectors: [{name, input, expected}], errors?: [{name, input, expected: {error}}]}`.

| File                   | What it checks                                                                                                                                                                                                                                                                                           |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `jcs.json`             | RFC 8785 canonicalization. `input` is JSON text: parse it, canonicalize it, then compare the text, its SHA-256 and (when present) the UTF-8 bytes. Covers the RFC §3.2.2–3.2.4 examples, key sorting by UTF-16 code units, escapes, non-ASCII text, nesting and number forms. `errors`: lone surrogates. |
| `jcs-numbers.json`     | Number serialization (ECMAScript `Number::toString`). `input.ieee754` is the hex of a double. Covers RFC 8785 Appendix B plus a seeded sample of 2,000 doubles. `errors`: NaN and infinities.                                                                                                            |
| `ed25519.json`         | RFC 8032 §7.1 TEST 1, 2, 3 and 1024 (hex). Sign `message` with `secret_key`, compare with `signature`, and verify it with `public_key`.                                                                                                                                                                  |
| `signatures.json`      | End to end: payload JSON → canonical text → `payload_hash` (SHA-256 hex) → Ed25519 signature over the canonical UTF-8 bytes (padded standard Base64, as in the API). Flipping a byte must fail verification.                                                                                             |
| `generate-numbers.mjs` | Regenerates `jcs-numbers.json`: `node packages/test-vectors/signing/generate-numbers.mjs`. The output is deterministic.                                                                                                                                                                                  |

## Provenance

- `jcs.json`: expected values from the RFC 8785 author's reference implementation (npm `canonicalize` 2.1.0). The
  first two vectors are also checked against the literal outputs printed in the RFC.
- `jcs-numbers.json`: Appendix B copied from RFC 8785, and a sample serialized by the JavaScript engine. The
  generator refuses to run if the engine disagrees with Appendix B.
- `ed25519.json`: parsed from the RFC 8032 text and checked with pyca/cryptography.
- `signatures.json`: keys from RFC 8032 TEST 1 and 2, canonical text from the reference implementation, and
  signatures from pyca/cryptography. Ed25519 is deterministic, so the signatures are reproducible.

These files are test data. Do not edit expected values by hand to make an implementation pass: a mismatch means
the implementation is wrong, or the vector needs a new provenance note in ADR-208.
