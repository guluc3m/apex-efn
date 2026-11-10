# ADR-203: Browser Ed25519 keys and the signing key lifecycle

## Status

Proposed (D2-07). Needs Tech Lead approval.

## Context

Spec §5.10.1: every responsible person signs with their own Ed25519 key, generated in the browser with
WebCrypto as non-exportable; the server never receives a human private key. Revoking or rotating a key is a
signed decision and must never invalidate past signatures. Agents and services sign with their own keys held in
a KMS. ADR-900 Q16 says there is no key escrow.

WebCrypto Ed25519 is recent: Chrome 137+, Firefox 129+, Safari 17+, Node 22. Older browsers throw on
`generateKey({name: 'Ed25519'})`.

## Decision

### Browser (`@apex/crypto-client`)

- `SigningClient.generateKey()` creates the pair with `extractable: false`. When the browser has no Ed25519 it
  throws `Ed25519UnsupportedError` with a user-facing message, and the UI disables signing on that device.
  There is no fallback: no JS polyfill holding a raw private key, no server-held key, no escrow.
- The `CryptoKeyPair` is stored as a structured-cloned `CryptoKey` in IndexedDB (`apex-signing`, store `keys`),
  one record per user id. The private key bytes are never visible to JavaScript.
- Enrollment is generate → `POST /v1/keys/me` → `persist(userId, serverKeyId)`, so a key the server refused is
  never stored. The client has no clock: timestamps are the server's.

### Server (`apex.signing.keys`, `/v1/keys`)

- **One active human key per user.** A new device or a lost key means: revoke the old key, then enroll. A second
  active key is `409 active_key_exists`. Rotation is therefore revoke + enroll; an atomic `rotate_key` flow can
  be added later without a schema change.
- **Enrollment needs a fresh step-up.** `auth_time` of the access token must be within
  `signing.session_minutes` (the same freshness a signing session gets, ADR-900 Q11); otherwise
  `428 reauth_required` with reason `step_up_required`. Only signer roles may enroll (`viewer` never signs).
- **Revocation needs a signed `revoke_key` decision** whose `subject_ref` is `signing_key:<key_id>`. The key
  owner may revoke, and so may an `owner` or `admin` of the tenant (lost-device procedure, since the owner can no
  longer sign). Immediate reauth for that decision is enforced when it is signed (D2-09). Until D2-09 merges the
  route answers 501.
- Revoking only sets `revoked_at` and `revoked_reason = decision:<id>`. Rows are never deleted and `public_key`
  never changes, so every historical signature verifies with the stored key.
- `public_key` is unique across tenants; a duplicate is `409 public_key_in_use`.
- Key rows reference `users.id`. The token `sub` is mapped through `users.external_subject`
  (`apex.db.users.user_id_for_subject`) inside the tenant session, so only a member of the tenant resolves.

### Service keys

- One Vault Transit `ed25519` key per service, non-exportable, named like the service (`gate-agent`). The
  Transit name is the `owner_id`; the row is global (`tenant_id` NULL) and written only from a
  `system_session`.
- Each Transit version is its own row, `svc:<name>:v<version>`, `vault_key_ref = <name>:<version>`. Registering a
  newer version sets `rotated_at` on the older ones, which keep verifying old signatures.
  `sync_service_key()` is idempotent; D2-09 calls it before `sign_service_event`.

## Consequences

- Users on browsers without Ed25519 can review but not sign.
- Losing the device means an admin-signed revocation and a re-enrollment; nothing is recoverable, by design.
- Signing-session invalidation on revocation is D2-08.
