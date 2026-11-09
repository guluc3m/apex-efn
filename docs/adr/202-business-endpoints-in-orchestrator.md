# ADR-202: Business endpoints live in the orchestrator, the Next.js BFF only proxies

## Status

Accepted on 2026-11-09 by the repository owner, who waived the Tech Lead gate for D2-02 so DEV-2 could
continue. It has not been reviewed by the TL. The TL may still amend or reverse it with a 900-range ADR.

## Context

Spec §5.1 describes `apps/web` as "frontend + BFF" and `apps/orchestrator` as the home of agents, trust,
sanity, scoring and finance. Both apps can reach Postgres (Prisma and SQLAlchemy, ADR-201). Without a rule,
business logic could end up in Next.js route handlers or server components, next to the same logic in Python.
Then there would be two places that compute bands, verdicts or eligibility, and two places to secure, audit
and keep under RLS.

The API surface in spec §8 is already declared in `contracts/openapi.yaml` (ADR-200), and DEV-4 serves it from
FastAPI.

## Decision

1. **Every business endpoint is served by the orchestrator** under `/v1`, and declared in `contracts/openapi.yaml`.
   That includes onboarding, missions, offers, sellers, dashboard, gate, negotiations, signing sessions,
   decisions, keys, audit, config and webhooks. The route-parity test from D2-01 keeps FastAPI and the contract
   aligned.
2. **The BFF (`apps/web/src/app/api/**`) may only:**
   - handle the OIDC login, session and token refresh (DEV-1, `apps/web/src/server/auth/**`);
   - proxy a request to the orchestrator with the user's access token from `getAccessToken()`;
   - pass through `Idempotency-Key`. The browser creates the key once per user intent, so retries reuse it. The BFF
     only adds a key when a write arrives without one;
   - stream SSE responses through unchanged (`/v1/missions/{id}/events`);
   - return orchestrator errors unchanged, including `application/problem+json` bodies and `428 reauth_required`.
3. **The BFF must not:**
   - compute or change business results: money, FX, bands, scores, verdicts, eligibility, gate outcomes;
   - read or write business tables with Prisma Client. In `apps/web`, Prisma is used for migrations and the seed
     script only (ADR-201);
   - decide authorization. It forwards the token, and the orchestrator checks roles and tenant
     (`current_principal()`, `require_role()`, D1-05). The BFF never sends a tenant ID header the orchestrator
     would trust;
   - hold, generate or use human signing keys, or change a signed payload. The browser signs with
     `@apex/crypto-client`, and the orchestrator verifies the signature before it persists it (D2-09).
4. **Server components** that need data call the orchestrator through the same server-side client the BFF uses.
   The same rules apply.
5. **Typed client.** The web app calls the API with types generated from the contract (`@apex/shared-types/contracts`,
   D6-01). It does not keep hand-written DTOs.
6. **Exceptions** need a new ADR approved by the TL. "It's only a read" is not an exception.

## Consequences

- There is one authority for every business rule and one place to apply RLS, roles and audit, so criteria 16, 17
  and 30 are enforced once, in Python.
- Every screen costs one extra network hop (browser → BFF → orchestrator). For SSE the BFF must stream and not
  buffer. D6-01 covers this.
- The web app can be built against MSW mocks generated from the contract before the orchestrator is ready.
- `@apex/scoring` and `@apex/money` in the browser are limited to previews that pass the same test vectors. The
  orchestrator's answer stays authoritative (AGENTS.md, DEV-6 note).
- A Next.js developer cannot ship a feature without a contract change and an orchestrator endpoint. That is
  slower, and it is intended.

## Related

- AGENTS.md section 2 (ownership of `apps/web/src/server/auth/**`, `apps/web/**`), 3.7 (contract first), 5 (D2-02, D1-05, D6-01)
- PROMPT-IMPLEMENTACION.md §5.1, §5.2, §8
- ADR-200 (contracts and codegen), ADR-201 (DDL ownership), ADR-900 Q11 (signing session step-up)
