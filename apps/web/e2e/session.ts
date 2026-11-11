import type { BrowserContext } from '@playwright/test'
import { encode } from 'next-auth/jwt'

import { AUTH_SECRET } from '../playwright.config'

const COOKIE = 'authjs.session-token'

/** Signs in as a role without Keycloak: the same encrypted JWT cookie Auth.js would set. */
export async function signInAs(context: BrowserContext, roles: string[] = ['buyer']): Promise<void> {
  const token = await encode({
    secret: AUTH_SECRET,
    salt: COOKIE,
    token: {
      sub: 'user-e2e',
      access_token: 'e2e-access-token',
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      tenant_id: 'tenant-a',
      roles,
    },
  })
  await context.addCookies([{ name: COOKIE, value: token, url: 'http://localhost:3100' }])
}
