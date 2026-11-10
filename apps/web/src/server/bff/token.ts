/**
 * Stand-in replaced by DEV-1's real Auth.js session (D1-05b).
 *
 * `getAccessToken()` now reads the Keycloak access token from the encrypted Auth.js cookie. The
 * development tenant header is kept for the unauthenticated dev escape hatch the orchestrator
 * accepts only with `APEX_ALLOW_TENANT_HEADER=true`; it is ignored whenever a bearer token is sent.
 */
export { getAccessToken } from '@/server/auth/token'

/**
 * Tenant header the orchestrator accepts only when it runs with `APEX_ALLOW_TENANT_HEADER=true`.
 * Ignored in production builds.
 */
export function getDevTenantId(): string | null {
  if (process.env.NODE_ENV === 'production') return null
  return process.env.APEX_DEV_TENANT_ID || null
}
