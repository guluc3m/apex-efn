# ADR-208: Canonical JSON, payload hash and Ed25519 signature format

## Status

Accepted on 2026-11-09 by the repository owner, who waived the Tech Lead gate for the DEV-2 tasks. The TL has
not reviewed it and may amend or reverse it with a 900-range ADR.

## Context

Spec §5.10.2 says every decision is serialized as canonical JSON (RFC 8785), hashed with SHA-256 and signed with
Ed25519. Humans sign in the browser (`@apex/crypto-client`) and the orchestrator verifies (`apex.signing`), so the
two implementations must produce the same bytes for the same payload, forever: a signature that verified once
must verify again during an audit years later.

RFC 8785 leaves some choices to the application (which inputs are allowed, what is signed exactly, how keys and
signatures are encoded), and a lax implementation silently diverges. `JSON.stringify` drops `undefined` members,
turns `NaN` into `null` and calls `toJSON` on dates. Python's `json.dumps` accepts integers of any size and
`Decimal` through custom encoders. Any of these makes "the same payload" mean different bytes in each language.

## Decision

### What is signed

- `canonical = JCS(payload)`, the RFC 8785 canonical form, encoded as UTF-8. This is `payload_canonical` in the
  API.
- `payload_hash = lowercase hex SHA-256(canonical)`.
- The Ed25519 signature (RFC 8032, pure Ed25519, no prehash, no context) is computed over the **canonical
  bytes**, not over the hash. The hash is an index and a chain link, not the signed message.
- Public keys are the raw 32 bytes, and signatures the raw 64 bytes, both in **standard Base64 with padding**
  (RFC 4648 §4), as `contracts/openapi.yaml` already says. Verifiers reject anything else, including URL-safe
  Base64, missing padding, whitespace and non-zero padding bits (the encoding must round-trip exactly), so one
  signature has only one accepted text form.

### Accepted input: the JSON data model, strictly

Both implementations accept `null`, booleans, strings, finite numbers, arrays and objects with string keys, and
throw `CanonicalizationError` on anything else instead of coercing it:

- TypeScript rejects `undefined` (also as a member or element), sparse arrays, `bigint`, functions, symbols and
  symbol keys, and any object that is not plain (`Date`, `Map`, boxed primitives, class instances).
- Python rejects `Decimal`, `datetime`, `Enum` members (`StrEnum` and `IntEnum` included), `bytes`, sets and
  non-`str` keys. Payload builders convert those on purpose: dates as RFC 3339 strings, FX rates and ratios as
  decimal strings, enums as their value.
- Strings with lone surrogates are rejected (RFC 8785 §3.2.2.2). `NaN` and infinities are rejected.
- Errors carry a JSONPath-like location (`$.offer.prices[1]`).

### Numbers

- Numbers are IEEE 754 doubles serialized with ECMAScript `Number::toString` (RFC 8785 §3.2.2.3). Python builds
  the same text from `repr()`, which gives the same shortest round-trip digits, laid out with the ECMAScript
  rules.
- Python `int` values must lie within ±(2^53 − 1). A larger integer cannot be represented exactly in the browser,
  so it would be signed as a different number there. Money is `*_minor` int64 in the database (ADR-205), but
  amounts that are signed stay far below 2^53 (about 90 trillion euros in cents). Anything bigger must be sent
  as a string.
- `apex.signing.jcs.loads()` parses JSON the way `JSON.parse` does (I-JSON, RFC 7493): integers outside the safe
  range become doubles, duplicate member names and `NaN`/`Infinity` literals are errors. The server uses it when
  it re-canonicalizes a payload received as text.

### Shared vectors

`packages/test-vectors/signing/` holds the vectors both test suites run (`README.md` there lists the files and
their provenance): RFC 8785 examples, unicode and escaping cases, 2,024 number vectors (Appendix B plus a seeded
sample), RFC 8032 known answers, and end-to-end payload → hash → signature vectors. Expected values come from
independent sources (the RFC texts, the RFC 8785 reference implementation, pyca/cryptography), not from the code
under test. Property tests (fast-check, hypothesis) check that the canonical form is a fixed point of
parse + canonicalize, that member order does not matter, and that every finite double round-trips.

The vector files follow `{name, input, expected}`, the shape D3-01 plans for `packages/test-vectors/`. DEV-2 owns
`packages/test-vectors/signing/**` only; the runners live in DEV-2 packages until the D3-01 framework exists.

## Consequences

- A payload that cannot be canonicalized fails loudly where it is built, instead of producing a signature the
  other side cannot reproduce.
- Payload builders (D2-09) must convert `Decimal`, dates and enums explicitly. That is extra code, but it is the
  only place where the representation is decided.
- Changing any rule here invalidates existing signatures. It needs a new ADR, a new algorithm or format
  identifier on the `Signature`, and verifiers that keep the old rules for old signatures.
- WebCrypto Ed25519 availability in browsers is D2-07 (ADR-203). The test suite uses Node's WebCrypto.

## Related

- RFC 8785 (JCS), RFC 8032 (EdDSA), RFC 7493 (I-JSON), RFC 4648 (Base64)
- ADR-205 (money as int64 minor units); ADR-203 (browser key handling, D2-07)
- AGENTS.md D2-06; PROMPT-IMPLEMENTACION.md §5.10.2
