import { type NextRequest, NextResponse } from 'next/server'

import { signIn } from '@/auth'
import { STEP_UP_ACR } from '@/lib/signing/step-up-acr'

// Each call issues fresh state/PKCE/nonce cookies and must never be cached.
export const dynamic = 'force-dynamic'

/** Only same-site absolute paths are accepted as post-login destinations. */
function relativeCallback(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//')) return '/'
  return value
}

/**
 * Single-provider convenience: Auth.js' built-in page would render a list with only Keycloak on it.
 * Going straight to the IdP keeps the redirect short and gives unauthenticated visitors a 302 to
 * Keycloak. The `state`/`PKCE` cookies are set by `signIn` before the redirect leaves the server.
 *
 * `?stepUp=1` asks for a fresh strong authentication (ADR-900 Q11): the ACR mapped to LoA 2 in the
 * realm, `max_age=0` (the SSO session may not satisfy the request) and `prompt=login` (no silent
 * reuse of an existing login). Auth.js forwards these authorization parameters to Keycloak; the
 * server still validates the resulting `acr` and `auth_time`, so this is a request, not a grant.
 */
export async function GET(request: NextRequest): Promise<Response> {
  const callbackUrl = relativeCallback(request.nextUrl.searchParams.get('callbackUrl'))
  const stepUp = request.nextUrl.searchParams.get('stepUp') === '1'
  const target = stepUp
    ? await signIn(
        'keycloak',
        { redirect: false, redirectTo: callbackUrl },
        { acr_values: STEP_UP_ACR, max_age: '0', prompt: 'login' }
      )
    : await signIn('keycloak', { redirect: false, redirectTo: callbackUrl })
  return NextResponse.redirect(typeof target === 'string' && target ? target : '/', 302)
}
