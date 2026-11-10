import type { NextRequest } from 'next/server'
import type { Account, NextAuthConfig, Profile, Session, User } from 'next-auth'
import type { JWT } from 'next-auth/jwt'
import Keycloak from 'next-auth/providers/keycloak'

import { locales } from '@/i18n/routing'

import { toRoles, type KeycloakClaims } from './types'

/** Refresh this many seconds before the access token really expires. */
const EXPIRY_SKEW_SECONDS = 30

export interface AuthDeps {
  /** Injectable for tests; never called with credentials in the URL. */
  fetch: typeof fetch
  /** Epoch seconds. Injected so token logic is deterministic in tests (AGENTS.md rule 0.6). */
  now: () => number
}

const defaultDeps: AuthDeps = {
  fetch: (input, init) => fetch(input, init),
  now: () => Math.floor(Date.now() / 1000),
}

type JwtCallbackParams = {
  token: JWT
  account?: Account | null
  profile?: Profile
  user?: User
  trigger?: 'signIn' | 'signUp' | 'update'
}

type SessionCallbackParams = {
  session: Session
  token: JWT
  user?: User
}

const localeRoots = new RegExp(`^/(${locales.join('|')})/?$`)
const localeAccess = new RegExp(`^/(${locales.join('|')})/acceso/?$`)

/**
 * Public surface: the root redirect, the localized landing, the access screen, the sign-in entry
 * and Keycloak's Auth.js routes. Everything else under a locale is protected.
 */
export function isPublicPath(pathname: string): boolean {
  return (
    pathname === '/' ||
    pathname === '/login' ||
    localeRoots.test(pathname) ||
    localeAccess.test(pathname) ||
    pathname.startsWith('/api/auth/')
  )
}

function unauthorizedApi(): Response {
  return new Response(
    JSON.stringify({ type: 'about:blank', title: 'Authentication required', status: 401 }),
    {
      status: 401,
      headers: {
        'content-type': 'application/problem+json',
        'www-authenticate': 'Bearer',
        'cache-control': 'no-store',
      },
    }
  )
}

/**
 * Middleware guard. Returning `false` makes Auth.js redirect to its sign-in entry with a
 * `callbackUrl`, which then goes straight to Keycloak (see app/api/auth/signin/route.ts).
 */
export function authorized({
  request,
  auth,
}: {
  request: NextRequest
  auth: Session | null
}): boolean | Response {
  const { pathname } = request.nextUrl
  if (isPublicPath(pathname)) return true
  if (auth?.user?.id) return true
  if (pathname.startsWith('/api/')) return unauthorizedApi()
  return false
}

function isExpired(token: JWT, now: number): boolean {
  if (typeof token.expires_at !== 'number') return false
  return token.expires_at <= now + EXPIRY_SKEW_SECONDS
}

function invalidate(token: JWT): JWT {
  const next: JWT = { ...token, error: 'RefreshAccessTokenError' }
  delete next.access_token
  return next
}

/** Exchanges the refresh token at Keycloak. Never throws: a failure invalidates the token. */
export async function refreshAccessToken(token: JWT, deps: AuthDeps = defaultDeps): Promise<JWT> {
  const issuer = (process.env.AUTH_KEYCLOAK_ISSUER ?? '').replace(/\/+$/, '')
  const refreshToken = typeof token.refresh_token === 'string' ? token.refresh_token : null
  if (!issuer || !refreshToken) return invalidate(token)

  try {
    const response = await deps.fetch(`${issuer}/protocol/openid-connect/token`, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'refresh_token',
        client_id: process.env.AUTH_KEYCLOAK_ID ?? '',
        client_secret: process.env.AUTH_KEYCLOAK_SECRET ?? '',
        refresh_token: refreshToken,
      }),
    })
    if (!response.ok) return invalidate(token)
    const body = (await response.json()) as {
      access_token?: unknown
      refresh_token?: unknown
      expires_in?: unknown
    }
    if (typeof body.access_token !== 'string' || body.access_token.length === 0) {
      return invalidate(token)
    }
    return {
      ...token,
      access_token: body.access_token,
      refresh_token:
        typeof body.refresh_token === 'string' ? body.refresh_token : token.refresh_token,
      expires_at:
        typeof body.expires_in === 'number' ? deps.now() + body.expires_in : token.expires_at,
      error: undefined,
    }
  } catch {
    return invalidate(token)
  }
}

/**
 * On sign-in it stores the Keycloak tokens and the claims the BFF needs; on later calls it
 * refreshes an expired access token. The JWT is encrypted in the cookie, so this is the only place
 * the raw tokens live on the server.
 */
export async function jwtCallback(
  { token, account, profile }: JwtCallbackParams,
  deps: AuthDeps = defaultDeps
): Promise<JWT> {
  if (account) {
    const claims = (profile ?? {}) as KeycloakClaims
    token.access_token = account.access_token ?? token.access_token
    token.refresh_token = account.refresh_token ?? token.refresh_token
    token.expires_at =
      typeof account.expires_at === 'number'
        ? account.expires_at
        : typeof account.expires_in === 'number'
          ? deps.now() + account.expires_in
          : token.expires_at
    token.tenant_id = typeof claims.tenant_id === 'string' ? claims.tenant_id : token.tenant_id
    token.roles = toRoles(claims.roles)
    token.auth_time = typeof claims.auth_time === 'number' ? claims.auth_time : token.auth_time
    if (typeof claims.sub === 'string') token.sub = claims.sub
    return token
  }

  if (typeof token.access_token !== 'string') return invalidate(token)
  if (!isExpired(token, deps.now())) return token
  return refreshAccessToken(token, deps)
}

/** Only identifiers, never tokens: the session object reaches the browser. */
export function sessionCallback({ session, token }: SessionCallbackParams): Session {
  session.user = {
    id: typeof token.sub === 'string' ? token.sub : '',
    tenantId: typeof token.tenant_id === 'string' ? token.tenant_id : null,
    roles: toRoles(token.roles),
    authTime: typeof token.auth_time === 'number' ? token.auth_time : null,
  }
  return session
}

export const authConfig: NextAuthConfig = {
  providers: [
    Keycloak({
      clientId: process.env.AUTH_KEYCLOAK_ID,
      clientSecret: process.env.AUTH_KEYCLOAK_SECRET,
      issuer: process.env.AUTH_KEYCLOAK_ISSUER,
      // Auth.js defaults to PKCE only. Add the OAuth `state` (login CSRF) and OIDC `nonce`
      // (ID-token replay) checks; both are stored in short-lived httpOnly cookies.
      checks: ['pkce', 'state', 'nonce'],
    }),
  ],
  session: { strategy: 'jwt' },
  trustHost: true,
  callbacks: {
    authorized,
    jwt: jwtCallback,
    session: sessionCallback,
  },
}
