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

| Variable                                  | Default                                  | Meaning                                                      |
| ----------------------------------------- | ---------------------------------------- | ------------------------------------------------------------ |
| `APEX_AUTH_ISSUER`                        | `http://localhost:8080/realms/apex`      | Required `iss`. Plain HTTP only for localhost.               |
| `APEX_AUTH_AUDIENCE`                      | `apex-orchestrator`                      | Required audience claim.                                     |
| `APEX_AUTH_JWKS_URL`                      | `{issuer}/protocol/openid-connect/certs` | Key set.                                                     |
| `APEX_AUTH_JWKS_CACHE_TTL_SECONDS`        | `300`                                    | Key cache lifetime.                                          |
| `APEX_AUTH_JWKS_REFETCH_COOLDOWN_SECONDS` | `10`                                     | One rotation refetch per unknown `kid` per window.           |
| `APEX_AUTH_CLOCK_SKEW_SECONDS`            | `30`                                     | Leeway for `exp`/`iat`/`nbf`.                                |
| `APEX_AUTH_HTTP_TIMEOUT_SECONDS`          | `5`                                      | JWKS fetch timeout.                                          |
| `APEX_AUTH_DISABLED`                      | `false`                                  | Answers `503`; never authenticates anyone silently.          |
| `APEX_ALLOW_TENANT_HEADER`                | `false`                                  | Dev escape hatch. Must stay off outside a developer machine. |
| `APEX_DEV_ROLES`                          | empty                                    | Roles for the dev principal, filtered to the closed set.     |

### Roles

Closed set: `owner`, `admin`, `buyer`, `finance`, `viewer`. Unknown roles a Keycloak token may carry
(`offline_access`, `uma_authorization`, client roles) are ignored. `viewer` never signs.

### Web session

The Next.js app (`apps/web`) authenticates with **Auth.js v5** (`next-auth@5.0.0-beta.32`) and the
Keycloak provider. Files: `src/auth.ts`, `src/server/auth/{config,token,session,types}.ts`,
`src/middleware.ts`, `src/app/api/auth/[...nextauth]/route.ts`, `src/app/api/auth/signin/route.ts`.

- **Cookie.** Auth.js stores the session in `authjs.session-token` (`__Secure-authjs.session-token` over
  HTTPS). It is `httpOnly`, `SameSite=Lax`, never readable by JavaScript, and the payload is a JWE
  encrypted with `AUTH_SECRET` (A256CBC-HS512). `AUTH_URL` fixes the origin; `trustHost: true` lets the
  request host be used behind a proxy.
- **What the cookie carries.** The Keycloak `access_token`, `refresh_token`, `expires_at`, and the claims
  `sub`, `tenant_id`, `roles` (filtered to the closed set) and `auth_time`. When the access token is
  within 30 s of expiry the `jwt` callback refreshes it against
  `{issuer}/protocol/openid-connect/token`; a failed refresh marks the token invalid
  (`error: RefreshAccessTokenError`, access token dropped) instead of continuing with a stale token.
- **What the browser sees.** Only `user.id`, `user.tenantId`, `user.roles` and `user.authTime`. Tokens are
  never copied into the session object: the `session` callback rebuilds it field by field, and
  `getSession()` rebuilds it again so a future callback cannot leak a token. `GET /api/auth/session` is
  safe to call from the client.
- **Server-side token access.** `getAccessToken()` (`src/server/auth/token.ts`) decrypts the cookie with
  `next-auth/jwt` and returns `string | null`. It is for Route Handlers/Server Components only (the BFF
  proxy uses it to set `Authorization: Bearer …`). It must never be imported into a Client Component and
  never logs or returns the token.
- **Route protection.** `src/middleware.ts` runs Auth.js' `auth` with the `authorized` callback. Public:
  `/`, `/{es,en,zh,he}`, `/{locale}/acceso`, `/login`, `/api/auth/*` and static assets. Every other
  localized route requires a session; an unauthenticated page request is redirected to the sign-in entry
  with `callbackUrl`, which goes straight to Keycloak. Protected `/api/*` calls get `401
application/problem+json` instead of an HTML redirect.
- **Signing step-up (D2-08).** `authTime` is the Keycloak `auth_time` of the current session. The web
  layer only exposes it; DEV-2 uses it (via the token) to open the 15-minute signing session (ADR-900
  Q11). Merely having a web session does not authorise a signature.
- **Logout.** `signOut()` clears the Auth.js cookie. The Keycloak SSO session is not ended yet (no
  `end_session_endpoint` call), so a new login can reuse it until it expires; wiring RP-initiated logout
  is a follow-up.
- **Settings.** `AUTH_SECRET`, `AUTH_KEYCLOAK_ID`, `AUTH_KEYCLOAK_SECRET`, `AUTH_KEYCLOAK_ISSUER`,
  `AUTH_URL` (see `.env.example`). A missing `AUTH_SECRET` makes Auth.js fail loudly at request time.

## Matrix

**Status of the role checks:** _authentication_ is enforced for every endpoint now. The _role_ check is
available as `apex.auth.deps.require_role(...)` / `require_signer()`, but wiring it into each router
belongs to the lane that owns the router (DEV-2 for signing/decisions/keys/audit, DEV-4 for missions and
gate, DEV-5 for negotiations). Until that wiring lands, an authenticated `viewer` can call a mutating
endpoint that the matrix marks as restricted. This table is the contract those lanes must implement.

| Endpoint(s)                                                                                                                                                     | Authenticated | Allowed roles                                               | Status                                          |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ----------------------------------------------------------- | ----------------------------------------------- |
| `GET /v1/missions/*`, `GET /v1/sourcing-requests`, `GET /v1/sellers/*`, `GET /v1/dashboard/deals`, `GET /v1/gate/queue`, `GET /v1/missions/{id}/recommendation` | yes           | any role (incl. `viewer`)                                   | auth enforced; read-only                        |
| `POST /v1/onboarding/sessions`, `POST /v1/onboarding/{id}/financial-csv`, `POST /v1/sourcing-requests`, `POST /v1/missions`                                     | yes           | `owner`, `admin`, `buyer`, `finance`                        | auth enforced; role wiring pending (DEV-4)      |
| `POST /v1/dashboard/deals/{id}/actions` (`follow`, `renegotiate`, `takeover`, `hold`, `discard`)                                                                | yes           | `owner`, `admin`, `buyer`, `finance`                        | auth enforced; role + signature pending (DEV-4) |
| `POST /v1/gate/queue/{id}/actions` → `unblock`                                                                                                                  | yes           | `owner`, `admin`, `buyer`, `finance`                        | pending (DEV-4)                                 |
| `POST /v1/gate/queue/{id}/actions` → `override_discard`                                                                                                         | yes           | `finance`, `admin`, `owner`                                 | pending (DEV-4)                                 |
| `POST /v1/signing-sessions`, `POST /v1/decisions/{id}/sign`, `GET/POST /v1/keys/me`, `POST /v1/keys/{id}/revoke`                                                | yes           | `owner`, `admin`, `buyer`, `finance` (`viewer` never signs) | pending (DEV-2)                                 |
| `POST /v1/negotiations/{id}/takeover`, `resume`, `abort`                                                                                                        | yes           | `owner`, `admin`, `buyer`                                   | pending (DEV-5)                                 |
| `POST /v1/config/...` (propose a change)                                                                                                                        | yes           | `owner`, `admin` (signed decision, immediate reauth)        | pending (DEV-4)                                 |
| `GET /v1/audit`                                                                                                                                                 | yes           | `admin`, `owner`                                            | pending (DEV-2)                                 |
| `GET /v1/audit/verify`                                                                                                                                          | yes           | `admin`, `owner`                                            | pending (DEV-2)                                 |
| `POST /v1/webhooks/platforms/{platform}`                                                                                                                        | no user token | platform signature / shared secret                          | pending (DEV-5)                                 |

`/health` is public.

## Keycloak realm

`infra/keycloak/realm-apex.json` defines realm `apex`, clients `apex-web` (code flow, no password grant)
and `apex-orchestrator`, roles `owner|admin|buyer|finance|viewer`, `CONFIGURE_TOTP` as a default required
action, two tenant groups and ten test users (`*-a@apex.local`, `*-b@apex.local`, password `apex-dev`).
Tokens carry `tenant_id` (from a user attribute, admin-only in the user profile), `roles` and the audience
`apex-orchestrator` through protocol mappers.

Tenant isolation is enforced from the token: a caller cannot choose a tenant with a header while
authenticated, and `tenant_id` is never read from a body.

## Database role and row-level security

The token is only the first half. The orchestrator also runs under a PostgreSQL role that RLS can
constrain (D1-03/D2-04, issue #221):

- **Runtime role `apex_app_login`**: `LOGIN`, member of the `apex_app` group (`NOLOGIN`, `NOSUPERUSER`,
  `NOBYPASSRLS`), created by `infra/postgres/bootstrap-app-role.sh` after the RLS migration. Every
  transaction from `apex.db.session.tenant_session()` sets `app.tenant_id`; without it, tenant tables
  return zero rows and refuse writes (fail closed).
- **Schema owner / migrator `apex`**: owns the tables and runs migrations, the seed and
  `load_defaults`. Only the pre-upgrade migration Job gets its DSN (`database.migrate` in the Helm
  chart). It is never mounted into the orchestrator or web Deployments, because an owner or superuser
  bypasses RLS.
- **Web/BFF**: still on the owner DSN until its Prisma tenant extension sets `app.tenant_id` per
  transaction (DEV-2/6). It does not query the database at runtime today.

`docs/runbooks/local-dev.md` ("Database roles") has the dev commands and a transcript showing the
difference between the two roles.

## Enforcement point

Authentication is applied to the **whole `/v1` surface** in `apex/main.py`
(`include_router(..., dependencies=[Depends(current_principal)])`), not per router. A stub that does not
depend on the tenant helper is therefore still closed to anonymous callers. When DEV-5 implements
`POST /v1/webhooks/platforms/{platform}` it must be mounted outside that dependency and authenticate the
platform by signature instead of a user token.
