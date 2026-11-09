# ADR-600: Signing UX (session indicator, countdown, 428 flow)

## Status

Proposed (draft, D6-03a; needs TL approval)

## Context

D6-03 shows the 15-minute signing window and recovers from `428 reauth_required`. ADR-900 Q11 chose Keycloak step-up (ACR + `auth_time`) over a WebAuthn relying party in the orchestrator. D2-07 (keys, `@apex/crypto-client`), D2-08 (signing sessions) and D1-05 (OIDC login) are not merged yet.

## Decision

- Step-up is Keycloak's, started from the browser by `startStepUp()` (`apps/web/src/lib/signing/step-up.ts`). Until D1-05 merges the default fails closed (resolves `false`).
- The countdown is `expires_at` corrected by `offset = server_time - local now at response`, stored with the session (Zustand). Logic is pure and takes the local time as a parameter; only the component reads the clock.
- The window is fixed: the UI never extends it. Length comes from the server `expires_at`, no minutes in the UI.
- On expiry (or revoked/exhausted) the indicator becomes read-only with a "re-authenticate to sign" button; nothing reloads and page state is kept.
- A `428` runs `startStepUp`, then retries once with the same idempotency key (existing `reauth.ts` + `client.ts`). If step-up fails, the error is surfaced. The UI never signs silently or degrades to unauthenticated.
- Local signing is behind D2-07's `@apex/crypto-client`; this slice does not touch keys. Key enrollment and the Ed25519 signing call are deferred.

## Consequences

The indicator, store and 428 flow can be built and tested now against MSW. Opening a session (`POST /v1/signing-sessions` needs `key_id`) and the Playwright virtual-authenticator tests wait for D2-07, D2-08 and D1-05.

## Related

- ADR-900 Q11, ADR-003, issue #74, `contracts/openapi.yaml` `SigningSession`
