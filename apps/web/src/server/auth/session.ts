import { auth } from '@/auth'

import type { WebSession } from './types'

/**
 * Sanitized server-side session for the BFF and Server Components.
 *
 * Rebuilds the object field by field instead of forwarding `auth()`: even if a future callback
 * accidentally copies a token into the session, this function cannot leak it to the caller/browser.
 */
export async function getSession(): Promise<WebSession | null> {
  const session = await auth()
  const user = session?.user
  if (!user?.id) return null

  return {
    user_id: user.id,
    user: {
      id: user.id,
      user_id: user.id,
      tenantId: user.tenantId ?? null,
      roles: Array.isArray(user.roles) ? [...user.roles] : [],
      authTime: typeof user.authTime === 'number' ? user.authTime : null,
    },
  }
}
