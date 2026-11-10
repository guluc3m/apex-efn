import { auth } from '@/auth'

/**
 * Auth.js middleware (D1-05b). The `authorized` callback in `server/auth/config.ts` decides what is
 * public; Auth.js redirects unauthenticated page requests to the sign-in entry with a `callbackUrl`.
 */
export default auth

export const config = {
  // Skip Auth.js' own routes, Next internals, the brand assets and any file with an extension.
  matcher: ['/((?!api/auth|_next/static|_next/image|favicon.ico|brand/|.*\\.[^/]+$).*)'],
}
