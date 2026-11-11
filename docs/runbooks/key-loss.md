# Runbook: signing key lost or compromised

**Owner:** DEV-2 (D2-10). **Applies to:** a user lost the device that holds their Ed25519 signing key, or the
key may be exposed.

The private key is non-exportable and lives only in the user's browser. There is **no escrow and no server copy**
(ADR-900 Q16): a lost key cannot be recovered, only replaced.

## Steps

1. **Revoke the old key.** The key owner, or an `owner`/`admin` for a lost device, calls
   `POST /v1/keys/{id}/revoke` with a signed `revoke_key` decision (`subject_ref = signing_key:<id>`). If the
   owner has no working key, an admin signs the decision with their own. Revocation ends the key's signing
   sessions at once.
2. **Enroll a new key** on the new device: `POST /v1/keys/me`. It needs a fresh step-up (`auth_time` within
   `signing.session_minutes`) and only one active key per user is allowed (`active_key_exists` otherwise: revoke first).
3. Open a new signing session (passkey ceremony).
4. **Decisions pending on the old key** stay `pending_signature`. Sign them again with the new key.

## What does not change

Revoking never invalidates past signatures: they still verify against the historical public key and stay in the
chain. Do not delete the old key row.

## If compromise is suspected

1. Revoke first, investigate second.
2. Review what the key signed since the suspected time: `GET /v1/audit` filtered by the decisions, then
   `POST /v1/decisions/{id}/verify` on each.
3. Run `GET /v1/audit/verify` to confirm the chain is intact (`audit-chain-broken.md` if not).
4. Dual-control decisions needed a second, different signer, so check the second signer too.
