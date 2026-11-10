import { type NextRequest, NextResponse } from 'next/server'

import { signIn } from '@/auth'

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
 */
export async function GET(request: NextRequest): Promise<Response> {
  const callbackUrl = relativeCallback(request.nextUrl.searchParams.get('callbackUrl'))
  const target = await signIn('keycloak', { redirect: false, redirectTo: callbackUrl })
  return NextResponse.redirect(typeof target === 'string' && target ? target : '/', 302)
}
