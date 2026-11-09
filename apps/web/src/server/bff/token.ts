/**
 * Stand-in for DEV-1's `getAccessToken()` (apps/web/src/server/auth/**, task D1-05).
 *
 * D1-05 is not merged yet, so the BFF reads a development token from the environment. Once DEV-1
 * exposes the real function, only the import in `proxy.ts` changes. The token is never returned
 * to the browser and never logged.
 */
export function getAccessToken(): Promise<string | null> {
  return Promise.resolve(process.env.APEX_DEV_ACCESS_TOKEN || null)
}

/**
 * Tenant header the orchestrator accepts before D1-05 lands, and only when it runs with
 * `APEX_ALLOW_TENANT_HEADER=true`. Ignored in production builds.
 */
export function getDevTenantId(): string | null {
  if (process.env.NODE_ENV === 'production') return null
  return process.env.APEX_DEV_TENANT_ID || null
}
