# Authentication and RBAC

Owner: DEV-1. Tasks: D1-05 (orchestrator identity), D2-08 (signing sessions), D2-09 (decisions).

## How a request is authenticated

Every orchestrator endpoint depends on `apex.common.tenant.get_tenant_id` / `get_roles`, which resolve the
caller through `apex.auth.deps.current_principal`:

1. `Authorization: Bearer <access token>` → the token is verified against the realm's JWKS. **Algorithm is
   pinned to RS256**, so `alg=none` and HS256-with-the-public-key (algorithm confusion) are refused before
   any signature check. `iss`, `aud`, `exp`, `iat`, `nbf` and `sub` are required; `auth_time` and `acr` are
   kept for the step-up signing session (ADR-900, Q11). A captured `acr` that is not a string is refused as
   `malformed`, so a client cannot smuggle a JSON object into the principal.
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
- **What the browser sees.** `user_id` at the top level plus the `user` object (`id`, `user_id`,
  `tenantId`, `roles`, `authTime`). `user_id` is the Keycloak `sub`; `user.id` is kept for compatibility and
  always equals it. `getSession()` (`src/server/auth/session.ts`) rebuilds both field by field, so a future
  callback cannot leak a token. Tokens are never copied into the session object, never logged and never put
  in a URL. `GET /api/auth/session` is safe to call from the client.
- **External subject provisioning (#270).** On the first sign-in only (the `jwt` callback runs with
  `account` present), `src/server/auth/provision.ts` sets `users.external_subject = <token sub>` when a row
  with the same email still has a null subject: `updateMany({ where: { email, externalSubject: null } })`.
  It never overwrites an existing subject, so a different IdP subject cannot take over an account by
  claiming the same email. A missing email or a database failure is logged and the login continues.
  **RLS caveat:** this write happens during sign-in, **before any tenant context**, under the web app's
  owner DSN. The Prisma tenant extension (`prisma/tenant-extension.ts`, DEV-2) is not used here because
  `tenant_session()` fails closed without `app.tenant_id`; when the web app adopts it, this call must move
  to an explicitly documented pre-tenant bootstrap path (see "Database role and row-level security").
- **Server-side token access.** `getAccessToken()` (`src/server/auth/token.ts`) decrypts the cookie with
  `next-auth/jwt` and returns `string | null`. It is for Route Handlers/Server Components only (the BFF
  proxy uses it to set `Authorization: Bearer …`). It must never be imported into a Client Component and
  never logs or returns the token.
- **Route protection.** `src/middleware.ts` runs Auth.js' `auth` with the `authorized` callback. Public:
  `/`, `/{es,en,zh,he}`, `/{locale}/acceso`, `/login`, `/api/auth/*` and static assets. Every other
  localized route requires a session; an unauthenticated page request is redirected to the sign-in entry
  with `callbackUrl`, which goes straight to Keycloak. Protected `/api/*` calls get `401
application/problem+json` instead of an HTML redirect.
- **Signing step-up (D2-08, #279).** `authTime` is the Keycloak `auth_time` of the current session. The web
  layer only exposes it; DEV-2 uses it (via the token) to open the 15-minute signing session (ADR-900
  Q11). Merely having a web session does not authorise a signature.
  - On `428 reauth_required`, the client calls `startStepUp()` (`src/lib/signing/step-up.ts`). It sends the
    browser to `/api/auth/signin?stepUp=1&callbackUrl=<current path>` and resolves `true`; outside a
    browser (or if redirecting throws) it resolves `false`, so the 428 is surfaced and nothing is signed
    silently.
  - `src/app/api/auth/signin/route.ts` handles `stepUp=1` by calling Auth.js `signIn` with three
    arguments: the provider, the redirect options, and the authorization parameters `acr_values`
    (`STEP_UP_ACR`), `max_age: '0'` and `prompt: 'login'`. The three parameters reach the Keycloak
    authorization URL; only same-site absolute `callbackUrl` values are accepted.
  - `STEP_UP_ACR` is defined once in `src/lib/signing/step-up-acr.ts` (`urn:apex:loa:2`) and must match the
    realm's `acr.loa.map`. Auth.js forwards the parameters as query parameters of the sign-in POST and
    `@auth/core` copies them into the authorization URL.
  - The server never trusts the request: D2-08 validates the resulting token's `auth_time` and (once wired)
    `acr`. The step-up is a request for fresh strong authentication, not a grant.
- **Logout.** `signOut()` clears the Auth.js cookie. The user menu now runs `signOutWithCleanup()`
  (`src/lib/signing/sign-out.ts`) first: it closes the active signing session on this device through
  `DELETE /v1/signing-sessions/{id}` and clears the local store, **best-effort** — a failed close is
  swallowed so logout still happens, and the window expires on its own. Cross-device revocation (closing
  signing sessions opened elsewhere) needs a new `invalidate_user_sessions` endpoint that DEV-2 owns; the
  current contract only closes one session per call. The Keycloak SSO session is not ended yet (no
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
Tokens carry `tenant_id` (from a user attribute, admin-only in the user profile), `roles`, the audience
`apex-orchestrator` and — because the built-in `acr` client scope is a default scope of `apex-web` — the
`acr` claim through the `acr loa level` mapper.

**ACR / step-up mapping (#279, #272).** The realm declares the Keycloak 26 realm attribute
`"acr.loa.map": "{\"urn:apex:loa:2\": 2}"`: `urn:apex:loa:2` maps to Level of Authentication 2, the value
requested by `STEP_UP_ACR`. The attribute is stored by Keycloak as a realm attribute (a JSON string) and is
visible through `GET /admin/realms/apex`; the `acr` client scope is a default scope of both clients, so the
`acr` claim is emitted in the ID and access tokens. Verified against Keycloak 26.0 (the compose image) by
importing this realm into a fresh database and reading the admin API.

**Known limit.** A realm mapping alone does not _enforce_ a LoA: Keycloak only demands the stronger
authenticator when the browser flow has a `Condition - Level of Authentication` subflow for that level. This
realm keeps the built-in browser flow, so the step-up currently forces a fresh login (`prompt=login`,
`max_age=0`) and the orchestrator anchors the signing window on `auth_time`; it does not yet reject a token
whose `acr` is below `urn:apex:loa:2`. Adding the LoA-2 conditional subflow, and requiring `acr` in the
signing session (D2-08), is the follow-up that turns the mapping into enforcement.

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
  transaction (DEV-2/6). Its one runtime write is the `users.external_subject` link at sign-in (#270), which
  runs before any tenant context exists and therefore cannot use `tenant_session()`. Moving it behind the
  app role requires a pre-tenant bootstrap policy or an explicit exception; that design is DEV-2/6's.

`docs/runbooks/local-dev.md` ("Database roles") has the dev commands and a transcript showing the
difference between the two roles.

## Enforcement point

Authentication is applied to the **whole `/v1` surface** in `apex/main.py`
(`include_router(..., dependencies=[Depends(current_principal)])`), not per router. A stub that does not
depend on the tenant helper is therefore still closed to anonymous callers. When DEV-5 implements
`POST /v1/webhooks/platforms/{platform}` it must be mounted outside that dependency and authenticate the
platform by signature instead of a user token.
