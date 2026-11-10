import { cookies } from 'next/headers'
import { getToken } from 'next-auth/jwt'

/** Refresh margin: a token about to expire is treated as missing so the BFF gets a 401, not a race. */
const EXPIRY_SKEW_SECONDS = 10

function cookieHeader(cookiesToSend: { name: string; value: string }[]): string {
  return cookiesToSend.map(({ name, value }) => `${name}=${value}`).join('; ')
}

/**
 * Reads the Keycloak access token from the encrypted Auth.js session cookie.
 *
 * Server-only: it is used by the BFF proxy to attach `Authorization: Bearer …`. It must never be
 * imported into a Client Component; the token is never returned to the browser, logged or placed in
 * a URL. Returns `null` when there is no session, the session was invalidated after a failed
 * refresh, or the access token is already past its expiry.
 */
export async function getAccessToken(): Promise<string | null> {
  let header: string
  try {
    header = cookieHeader((await cookies()).getAll())
  } catch {
    // Called outside a request scope (unit tests, build-time collection): no session exists.
    return null
  }
  if (header.length === 0) return null

  const token = await getToken({ req: { headers: { cookie: header } } })
  if (!token || typeof token.access_token !== 'string' || token.access_token.length === 0) {
    return null
  }
  if (token.error) return null
  if (
    typeof token.expires_at === 'number' &&
    token.expires_at <= Math.floor(Date.now() / 1000) + EXPIRY_SKEW_SECONDS
  ) {
    return null
  }
  return token.access_token
}
