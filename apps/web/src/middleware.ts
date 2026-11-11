import { NextResponse, type NextFetchEvent, type NextRequest } from 'next/server'

import { auth } from '@/auth'
import { isLocale } from '@/i18n/routing'

/**
 * Auth.js middleware (D1-05b). The `authorized` callback in `server/auth/config.ts` decides what is
 * public; Auth.js redirects unauthenticated page requests to the sign-in entry with a `callbackUrl`.
 *
 * Once a request is allowed, the locale in the URL is forwarded in the header next-intl reads as
 * `requestLocale` (`i18n/request.ts`). Without it every locale fell back to Spanish (#335).
 */
export default async function middleware(request: NextRequest, event: NextFetchEvent) {
  // Auth.js decides first: a redirect or a 401 is returned untouched.
  const guarded = await (
    auth as unknown as (r: NextRequest, e: NextFetchEvent) => Promise<Response | undefined>
  )(request, event)
  if (guarded && guarded.headers.get('x-middleware-next') !== '1') return guarded

  const segment = request.nextUrl.pathname.split('/')[1]
  if (!isLocale(segment)) return guarded
  const headers = new Headers(request.headers)
  headers.set('x-next-intl-locale', segment)
  const response = NextResponse.next({ request: { headers } })
  // Keep whatever Auth.js set on the pass-through (a refreshed session cookie).
  guarded?.headers.getSetCookie().forEach((cookie) => response.headers.append('set-cookie', cookie))
  return response
}

export const config = {
  // Skip Auth.js' own routes, Next internals, the brand assets and any file with an extension.
  matcher: ['/((?!api/auth|_next/static|_next/image|favicon.ico|brand/|.*\\.[^/]+$).*)'],
}
