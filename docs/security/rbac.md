# Authentication and RBAC

Owner: DEV-1. Tasks: D1-05 (orchestrator identity), D2-08 (signing sessions), D2-09 (decisions).

## How a request is authenticated

Every orchestrator endpoint depends on `apex.common.tenant.get_tenant_id` / `get_roles`, which resolve the
caller through `apex.auth.deps.current_principal`:

1. `Authorization: Bearer <access token>` → the token is verified against the realm's JWKS. **Algorithm is
   pinned to RS256**, so `alg=none` and HS256-with-the-public-key (algorithm confusion) are refused before
   any signature check. `iss`, `aud`, `exp`, `iat`, `nbf` and `sub` are required; `auth_time` is kept for
   the step-up signing session (ADR-900, Q11).
2. No bearer token + `APEX_ALLOW_TENANT_HEADER=true` → **development principal**: tenant from
   `X-Tenant-Id`, roles from `APEX_DEV_ROLES` (filtered to the closed set). Off by default. A valid bearer
   token always wins over the header; the two are never merged.
3. Otherwise `401` with `application/problem+json` and a `WWW-Authenticate: Bearer` header.

A token is never logged, echoed in a problem body or stored in the principal beyond its identifiers.

### Settings

| Variable | Default | Meaning |
|---|---|---|
| `APEX_AUTH_ISSUER` | `http://localhost:8080/realms/apex` | Required `iss`. Plain HTTP only for localhost. |
| `APEX_AUTH_AUDIENCE` | `apex-orchestrator` | Required audience claim. |
| `APEX_AUTH_JWKS_URL` | `{issuer}/protocol/openid-connect/certs` | Key set. |
| `APEX_AUTH_JWKS_CACHE_TTL_SECONDS` | `300` | Key cache lifetime. |
| `APEX_AUTH_JWKS_REFETCH_COOLDOWN_SECONDS` | `10` | One rotation refetch per unknown `kid` per window. |
| `APEX_AUTH_CLOCK_SKEW_SECONDS` | `30` | Leeway for `exp`/`iat`/`nbf`. |
| `APEX_AUTH_HTTP_TIMEOUT_SECONDS` | `5` | JWKS fetch timeout. |
| `APEX_AUTH_DISABLED` | `false` | Answers `503`; never authenticates anyone silently. |
| `APEX_ALLOW_TENANT_HEADER` | `false` | Dev escape hatch. Must stay off outside a developer machine. |
| `APEX_DEV_ROLES` | empty | Roles for the dev principal, filtered to the closed set. |

### Roles

Closed set: `owner`, `admin`, `buyer`, `finance`, `viewer`. Unknown roles a Keycloak token may carry
(`offline_access`, `uma_authorization`, client roles) are ignored. `viewer` never signs.

## Matrix

**Status of the role checks:** *authentication* is enforced for every endpoint now. The *role* check is
available as `apex.auth.deps.require_role(...)` / `require_signer()`, but wiring it into each router
belongs to the lane that owns the router (DEV-2 for signing/decisions/keys/audit, DEV-4 for missions and
gate, DEV-5 for negotiations). Until that wiring lands, an authenticated `viewer` can call a mutating
endpoint that the matrix marks as restricted. This table is the contract those lanes must implement.

| Endpoint(s) | Authenticated | Allowed roles | Status |
|---|---|---|---|
| `GET /v1/missions/*`, `GET /v1/sourcing-requests`, `GET /v1/sellers/*`, `GET /v1/dashboard/deals`, `GET /v1/gate/queue`, `GET /v1/missions/{id}/recommendation` | yes | any role (incl. `viewer`) | auth enforced; read-only |
| `POST /v1/onboarding/sessions`, `POST /v1/onboarding/{id}/financial-csv`, `POST /v1/sourcing-requests`, `POST /v1/missions` | yes | `owner`, `admin`, `buyer`, `finance` | auth enforced; role wiring pending (DEV-4) |
| `POST /v1/dashboard/deals/{id}/actions` (`follow`, `renegotiate`, `takeover`, `hold`, `discard`) | yes | `owner`, `admin`, `buyer`, `finance` | auth enforced; role + signature pending (DEV-4) |
| `POST /v1/gate/queue/{id}/actions` → `unblock` | yes | `owner`, `admin`, `buyer`, `finance` | pending (DEV-4) |
| `POST /v1/gate/queue/{id}/actions` → `override_discard` | yes | `finance`, `admin`, `owner` | pending (DEV-4) |
| `POST /v1/signing-sessions`, `POST /v1/decisions/{id}/sign`, `GET/POST /v1/keys/me`, `POST /v1/keys/{id}/revoke` | yes | `owner`, `admin`, `buyer`, `finance` (`viewer` never signs) | pending (DEV-2) |
| `POST /v1/negotiations/{id}/takeover`, `resume`, `abort` | yes | `owner`, `admin`, `buyer` | pending (DEV-5) |
| `POST /v1/config/...` (propose a change) | yes | `owner`, `admin` (signed decision, immediate reauth) | pending (DEV-4) |
| `GET /v1/audit` | yes | `admin`, `owner` | pending (DEV-2) |
| `GET /v1/audit/verify` | yes | `admin`, `owner` | pending (DEV-2) |
| `POST /v1/webhooks/platforms/{platform}` | no user token | platform signature / shared secret | pending (DEV-5) |

`/health` is public.

## Keycloak realm

`infra/keycloak/realm-apex.json` defines realm `apex`, clients `apex-web` (code flow, no password grant)
and `apex-orchestrator`, roles `owner|admin|buyer|finance|viewer`, `CONFIGURE_TOTP` as a default required
action, two tenant groups and ten test users (`*-a@apex.local`, `*-b@apex.local`, password `apex-dev`).
Tokens carry `tenant_id` (from a user attribute, admin-only in the user profile), `roles` and the audience
`apex-orchestrator` through protocol mappers.

Tenant isolation is enforced from the token: a caller cannot choose a tenant with a header while
authenticated, and `tenant_id` is never read from a body.

## Enforcement point

Authentication is applied to the **whole `/v1` surface** in `apex/main.py`
(`include_router(..., dependencies=[Depends(current_principal)])`), not per router. A stub that does not
depend on the tenant helper is therefore still closed to anonymous callers. When DEV-5 implements
`POST /v1/webhooks/platforms/{platform}` it must be mounted outside that dependency and authenticate the
platform by signature instead of a user token.
