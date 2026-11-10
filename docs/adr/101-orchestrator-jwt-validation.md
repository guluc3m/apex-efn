# ADR-101: Orchestrator JWT validation with PyJWT and JWKS

## Status

Proposed (DEV-1). Applies the Tech Lead decision in ADR-900 (issue #105, Option A).

## Context

The orchestrator must authenticate every request against Keycloak. The scaffold declared
`python-jose[cryptography]` but nothing imported it; `pip-audit` flagged it as
**CVE-2026-85394** (HMAC/asymmetric key confusion in JWT validation) with **no fixed version**.
ADR-900 chose Option A: PyJWT with RS256 pinned and keys from the realm's JWKS, and remove python-jose.

The caller must reach routers as a principal `{user_id, tenant_id, roles}` (AGENTS section 4), roles must
never come from a body or a header, and the signing session (D2-08) needs the token's `auth_time` because
ADR-900 Q11 uses Keycloak step-up (ACR + `auth_time`).

## Decision

1. **Library:** `pyjwt[crypto]`, `algorithms=["RS256"]`. `python-jose` is removed.
2. **Algorithm pinning happens before decoding.** A token whose header `alg` is not `RS256` is refused with
   `unsupported_algorithm`, so `alg=none` and HS256-signed-with-the-public-key never reach a signature check.
3. **Keys** come from `{issuer}/protocol/openid-connect/certs`, cached for a TTL. An unknown `kid` triggers
   one refetch per cooldown window (key rotation without hammering the IdP). A failed refresh keeps the
   previous keys so an IdP outage does not log every caller out; with no keys at all the request fails
   closed as `jwks_unavailable`.
4. **Claims:** `iss`, `aud`, `exp`, `iat`, `sub` are required; `nbf` is honoured when present; `tenant_id`
   and `sub` must be non-empty strings. Optional `auth_time` and `acr` must be integers/strings respectively
   when present (a non-string `acr` is `malformed`). Time checks use an injected clock with a configurable
   skew, so the behaviour is deterministic in tests.
5. **Roles are a closed set** (`owner|admin|buyer|finance|viewer`), read from the `roles` claim or, when a
   client does not map it, from `realm_access.roles`. Unknown roles are dropped, not granted. `viewer` is
   never a signer.
6. **Principal** is immutable and carries `user_id`, `tenant_id`, `roles`, `auth_time` (for D2-08) and `acr`
   (the Authentication Context Class Reference of the authentication, `urn:apex:loa:2` for the signing
   step-up). `current_principal` is the dependency; `require_role`/`require_signer` are the authorisation
   helpers.
7. **Development escape hatch:** `APEX_ALLOW_TENANT_HEADER=true` with no bearer token authenticates a
   development principal from `X-Tenant-Id` plus `APEX_DEV_ROLES`. Off by default; a valid bearer token
   always wins, and the header is never merged into an authenticated request. This keeps local UI work and
   the existing API tests unblocked without weakening production: nothing authenticates by header unless
   the environment explicitly opts in.
8. **Fail closed:** `APEX_AUTH_DISABLED=true` answers `503`. It never means "anonymous caller".
9. **No secrets in the surface:** tokens and key material never appear in logs, exceptions, problem bodies
   or the principal representation.

## Consequences

### Easier

- One dependency for every router; no route had to be rewired (they already used `get_tenant_id`/`get_roles`).
- Key rotation and IdP outages degrade predictably instead of failing every request.
- Deterministic time checks: the tests freeze the clock and assert `expired`/`not_yet_valid` without sleeping.
- The same module serves the step-up signing session through `auth_time`.

### Harder / limits

- The role checks are available but not yet wired into the routers: that belongs to the lane owning each
  router (see `docs/security/rbac.md`). Until then an authenticated `viewer` can reach a mutating endpoint.
- The JWKS provider caches per process. A fleet-wide rotation is picked up within the TTL, not instantly.
- `APEX_ALLOW_TENANT_HEADER` is a real bypass when enabled; the runbook and the realm docs say it must stay
  off outside a developer machine.
- A token minted for another tenant is accepted as long as its `tenant_id` claim is valid; membership is
  asserted by Keycloak at login, not re-checked against the database per request. D2-04's RLS is the
  second line of defence for data access.

10. **Enforcement point:** authentication is a dependency of the whole `/v1` router mounted in
    `main.py`, not of individual routes. Several stubs (audit, decisions, keys, signing) had no tenant
    dependency and were reachable anonymously; a per-router rule would have left that hole open. Role
    checks stay per route (owning lane). The platform webhooks route must later be mounted outside this
    dependency and authenticate the platform by signature.
