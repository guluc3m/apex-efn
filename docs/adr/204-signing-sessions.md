# ADR-204: Signing sessions on Keycloak step-up, stored in Postgres

## Status

Proposed (D2-08). Needs Tech Lead approval.

## Context

Spec §5.10.4 defines a fixed 15-minute signing window opened by one strong authentication. The task offered a
WebAuthn relying party in the orchestrator or a Keycloak step-up. ADR-900 Q11 already chose **Keycloak step-up**:
`auth_at` is the step-up token's `auth_time`. The spec also says to keep the session in "Redis + Postgres".

## Decision

- **Opening.** `POST /v1/signing-sessions` takes `{key_id, device_fingerprint_ref}`. `auth_at` is the token's
  `auth_time` and `expires_at = auth_at + signing.session_minutes`. If the token has no `auth_time`, or the window
  it gives has already passed, the answer is `428 step_up_required`. The key must be the caller's own key and not
  revoked. `max_decisions` is taken from `signing.max_decisions_per_session` when the window opens.
- **Fixed window.** Nothing writes `expires_at` after insert. Expiry is lazy: any read or signature after
  `expires_at` marks the row `expired`.
- **Every signature goes through `apex.signing.sessions.consume()`** (D2-09). It locks the row and checks, in
  this order: own and active session, then window, then key not revoked, then device. It records the decision,
  and the signature that reaches `max_decisions` ends the session as `exhausted`. Every refusal raises
  `ReauthRequired(reason)`, which the API maps to `428 {error: "reauth_required", reason}`. The new state is
  committed before raising, so a device mismatch kills the session even though the caller's transaction rolls
  back.
- **Invalidation.**
  - Revoking a key ends its sessions in the same transaction (`keys.revoke`, criterion 22).
  - A device change ends the session on the first mismatched signature.
  - `DELETE` closes the session.
  - `mark_session_risky()` (GateAgent) and `invalidate(..., network_anomaly)` are the hooks for risk and ASN or
    country jumps.
  - `invalidate_user_sessions()` is the logout hook.
- **Postgres only, no Redis.** The row is the session, and `SELECT … FOR UPDATE` serialises the signatures of one
  window. A Redis copy would be a second source of truth that has to be invalidated at once (criterion 22) for no
  measurable gain at a few signatures per minute. If load tests (D1-10) show a need, Redis can become a read
  cache without an API change.

## Not done here, and why

- **ACR check.** `Principal` does not expose `acr` and the realm defines no step-up level yet, so only
  `auth_time` freshness is enforced. DEV-1 issue #272.
- **Logout and ASN/country detection** need DEV-1 inputs: a Keycloak logout event, and a GeoIP/ASN source on the
  request. The invalidation functions exist; nobody calls them yet. Same issue.

## Consequences

- Criteria 19, 20 and 22 are tested at the service layer and over HTTP with an injected clock.
- D2-09 must call `consume()` inside the transaction that stores the signature.
