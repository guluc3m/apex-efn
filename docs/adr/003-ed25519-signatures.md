# ADR-003: Ed25519 Signatures for Decision Audit Trail

## Status

Accepted

## Context

APEX-EFN handles financial decisions (approving purchases, setting thresholds) that require:
1. Non-repudiation: proof that a specific person made a decision
2. Integrity: detection of any tampering with the decision record
3. Audit trail: verifiable chain of all decisions

We need a signing scheme that:
- Works in the browser (for human signatures)
- Works on the server (for agent/service signatures)
- Is simple and well-understood
- Has good library support

## Decision

Use **Ed25519 (EdDSA)** for all signatures:

### Key Management
- Human keys: generated in browser with WebCrypto, `extractable: false`
- Service keys: stored in KMS (AWS KMS, HashiCorp Vault)
- Each key has a `key_id` for rotation without breaking verification

### What Gets Signed
- Canonical JSON (RFC 8785 JCS) of the decision payload
- Payload includes: decision type, subject, amounts, SellerConfidence, config_version
- Signature record includes: payload_hash (SHA-256), signature, prev_signature_hash

### Chain of Hashes
- Each signature includes hash of previous signature in tenant
- Creates append-only log that detects insertions/deletions
- Anchor hash stored in S3 Object Lock (WORM)

### Signing Sessions (15-minute window)
- Opened with WebAuthn/passkey authentication
- Fixed duration, not sliding (signing doesn't extend)
- Max decisions per session (default 10)
- Immediate reauth for high-value or sensitive operations

## Consequences

### Easier
- Ed25519 has excellent performance and small signatures (64 bytes)
- WebCrypto support is universal in modern browsers
- Simple key format (32-byte public key)
- Deterministic signatures (same input = same output)

### Harder
- Key recovery requires backup strategy (escrow or re-enrollment)
- Browser IndexedDB is the weak point for key storage
- Need to handle key rotation gracefully

## Related

- [Section 5.10 of PROMPT-IMPLEMENTACION.md](../../PROMPT-IMPLEMENTACION.md)
- [@apex/crypto-client](../../packages/crypto-client/)
