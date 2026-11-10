# ADR-209: Decisions, signatures, the per-tenant hash chain and dual control

## Status

Proposed on 2026-11-10 for D2-09 (#31). Tech Lead calls delegated to the DEV-2 agent by @Toriomg; they are
recorded on the PR, #31 and #92.

## Context

Spec §5.10.2–5.10.4 and criteria 17, 18, 21 and 23 need four things: decisions with an immutable canonical
payload, Ed25519 signatures that the server checks before it stores them, a tamper-evident chain of signatures per
tenant, and two different signers above `approval.dual_control_above`. The schema has existed since D2-03
(`decisions`, `signatures`, immutability triggers). Keys (ADR-203) and signing windows (ADR-204) are merged.
DEV-4 codes against the interface in #92.

## Decision

**Decision types.** The DB and contract enum adopt the names DEV-4 already uses (#92):

- `unblock` is renamed `gate_unblock`.
- `override_discard` is renamed `gate_override_discard`.
- `activate_financial_snapshot` is renamed `financial_snapshot_activation`.
- `deal_action` is new. Its signed payload carries `action` (`follow|renegotiate|takeover|hold|discard|approve|reject`).
- `service_event` is new. It is an automatic graph transition signed by a service key.

Every name now has a single meaning. The types `follow` … `approve_purchase` stay in the enum for direct use.

**Payload.** The caller gives a JSON object. The server stores its RFC 8785 form (`payload_canonical`) and
`payload_hash = SHA-256(payload_canonical)`. Both are immutable (D2-03 trigger). The signed message is exactly the
UTF-8 bytes of `payload_canonical`, as the contract says. Gate types (`deal_action`, `gate_unblock`,
`gate_override_discard`, `follow` … `discard`, `approve_purchase`) are refused unless the payload has all of the
following (spec §5.10.2):

- `offer_id`
- `amount` `{amount_minor, currency}`
- `price_sanity` (object)
- `seller_confidence` `{score, band, model_version}`
- `financial_verdict`
- `config_version`

The check is presence and shape only. The server does not rebuild what DEV-3/DEV-4 computed.

**Thresholds are fixed when the decision is created.**

- `required_signers` is 2 when `amount > approval.dual_control_above`, else 1.
- `requires_immediate_reauth` is true when `amount > signing.high_value_reauth_above`, or when the type is one of
  `financial_snapshot_activation`, `config_change`, `change_pricing_threshold`, `change_confidence_weights`,
  `change_scoring_weights`, `gate_override_discard`, `rotate_key` or `revoke_key`.
- The amount and the threshold must share a currency. Otherwise the decision is refused, because FX is not the
  signer's job.
- If a threshold is unset, a decision with an amount fails (`ConfigKeyUnset`). It never defaults (ADR-900 Q7).

**Immediate reauth.** A window that is still alive is not enough. The session used to sign must have
`auth_at >= decision.created_at`, and it must not have signed anything yet. One fresh step-up covers one
immediate-reauth decision. Otherwise the answer is `428 reauth_required` with reason `high_value_decision` (amount)
or `immediate_reauth_required` (type). That check is a refusal of this decision only, so the session stays usable
for ordinary decisions.

**Human signature, in one transaction.** The server runs these steps in order:

1. Lock the decision row. It must be `pending_signature`.
2. Check that the request's `payload_hash` equals the stored one.
3. Check that the signer has not signed this decision already.
4. Verify Ed25519 with the stored public key of `key_id`. A bad signature is a `422` and does not touch the
   session.
5. Call `sessions.consume()` (session alive, key not revoked, device matches, immediate-reauth rule).
6. Take the per-tenant advisory lock and insert the `Signature` with `signing_session_id` and `auth_at` from the
   session.
7. Mark the decision `signed` once the number of distinct signers reaches `required_signers`.

`consume()` commits its refusal before it raises (ADR-204), so step 5 is the last step that can fail before the
insert.

**Chain.** Each tenant has one linear chain.

- `prev_signature_hash` is the `chain_hash` of the tenant's head, or NULL for the first signature.
- `chain_hash` is SHA-256 over the JCS form of these fields: `alg`, `auth_at`, `decision_id`, `key_id`,
  `payload_hash`, `prev_signature_hash`, `signature`, `signed_at`, `signer_id`, `signer_type`,
  `signing_session_id`. Timestamps are ISO 8601 in UTC.
- The head is the signature that no other signature names as previous. The advisory lock
  `signature_chain:<tenant>` and `UNIQUE (tenant_id, prev_signature_hash)` keep the chain linear.
- `verify_chain()` walks the chain from the first signature and recomputes every hash. D2-10 adds the WORM anchor
  and the endpoint.

**Dual control.** `UNIQUE (decision_id, signer_id)` already makes the second signer a different person. Step 3
returns a clean `409` instead of an integrity error.

**Service events.** `sign_service_event(service, payload, *, tenant_id)`:

- creates a `service_event` decision on `service:<service>`;
- signs `payload_canonical` in Vault Transit;
- registers the Transit key version with `keys.sync_service_key` if it is new;
- verifies the signature and chains it.

The signature has no signing session (the CHECK allows that for non-human signers). It returns the signature id.

**`apex.signing.api.SigningService`** is the seam for other lanes (#92). It is async and takes `tenant_id` as a
keyword argument. It has these methods:

- `create_decision(type, subject_ref, payload, *, tenant_id)`
- `require_signed(decision_id, *, tenant_id) -> SignedDecision`
- `sign_service_event`
- `mark_session_risky(session_id, *, tenant_id)`

`require_signed` does not trust `status`. It re-hashes the payload and re-verifies every signature, then:

- raises `PendingSignature` while signatures are missing;
- raises `DecisionRejected` for a `rejected` or `expired` decision;
- raises `SignatureInvalid` on any mismatch, so tampering is loud and never read as a rejection.

`POST /v1/keys/{id}/revoke` uses `require_signed`, so it needs a signed `revoke_key` decision on
`signing_key:<id>`.

## Consequences

- A payload that changes by one byte breaks `payload_hash`. A score that changes in the payload breaks the
  Ed25519 signature. A row that changes in the chain breaks `chain_hash`. The tests cover all three (criteria 17,
  18 and 23).
- Gate payloads from DEV-4 must carry the six fields above, and `action` must be in the payload **when the decision
  is created**. The payload is immutable, so a signer cannot add the action later (noted on #92).
- Nothing expires or rejects decisions yet, and no endpoint does it. `DecisionRejected` is ready for that.
- Finding the head scans the tenant's signatures (indexed by `(tenant_id, prev_signature_hash)`). If D1-10 shows
  it matters, a head pointer row is a later change with no API change.

## Related

- ADR-203 (keys), ADR-204 (sessions), ADR-208 (JCS and signature format), ADR-900 Q7.
- Issues #31 (D2-09), #92 (interface), #32 (D2-10).
