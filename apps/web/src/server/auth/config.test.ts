import { NextRequest } from 'next/server'
import type { Session } from 'next-auth'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ linkExternalSubject: vi.fn() }))

vi.mock('./provision', () => ({ linkExternalSubject: mocks.linkExternalSubject }))

import {
  authorized,
  isPublicPath,
  jwtCallback,
  refreshAccessToken,
  sessionCallback,
  type AuthDeps,
} from './config'

const ISSUER = 'http://keycloak.test/realms/apex'
const ORIGINAL_ENV = { ...process.env }

beforeEach(() => {
  process.env.AUTH_KEYCLOAK_ISSUER = ISSUER
  process.env.AUTH_KEYCLOAK_ID = 'apex-web'
  process.env.AUTH_KEYCLOAK_SECRET = 'secret'
  mocks.linkExternalSubject.mockReset()
  mocks.linkExternalSubject.mockResolvedValue(1)
})

afterEach(() => {
  process.env = { ...ORIGINAL_ENV }
})

function deps(overrides: Partial<AuthDeps> = {}): AuthDeps {
  return {
    now: () => 1_000,
    fetch: vi.fn<typeof fetch>(),
    ...overrides,
  }
}

const signIn = {
  token: {},
  account: {
    provider: 'keycloak',
    providerAccountId: 'user-1',
    type: 'oidc' as const,
    access_token: 'access-token',
    refresh_token: 'refresh-token',
    expires_at: 1_300,
  },
  profile: {
    sub: 'user-1',
    email: 'user-1@apex.local',
    tenant_id: 'tenant-a',
    roles: ['buyer', 'offline_access', 'finance'],
    auth_time: 900,
  },
}

function expiredToken(overrides: Record<string, unknown> = {}) {
  return {
    sub: 'user-1',
    access_token: 'old-access',
    refresh_token: 'old-refresh',
    expires_at: 900,
    ...overrides,
  }
}

describe('jwtCallback', () => {
  it('stores tokens and Keycloak claims on the encrypted JWT at sign-in', async () => {
    const token = await jwtCallback(signIn, deps())
    expect(token).toMatchObject({
      sub: 'user-1',
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      expires_at: 1_300,
      tenant_id: 'tenant-a',
      roles: ['buyer', 'finance'],
      auth_time: 900,
    })
  })

  it('links the external subject to the token subject on first sign-in', async () => {
    await jwtCallback(signIn, deps())
    expect(mocks.linkExternalSubject).toHaveBeenCalledExactlyOnceWith({
      sub: 'user-1',
      email: 'user-1@apex.local',
    })
  })

  it('does not try to link a user when the profile has no email', async () => {
    await jwtCallback({ ...signIn, profile: { sub: 'user-1' } }, deps())
    expect(mocks.linkExternalSubject).not.toHaveBeenCalled()
  })

  it('still completes the sign-in when provisioning fails', async () => {
    mocks.linkExternalSubject.mockRejectedValueOnce(new Error('database down'))
    const token = await jwtCallback(signIn, deps())
    expect(token.sub).toBe('user-1')
    expect(token.access_token).toBe('access-token')
  })

  it('keeps a valid token untouched and does not refresh', async () => {
    const fetchMock = vi.fn<typeof fetch>()
    const token = await jwtCallback(
      { token: { ...expiredToken(), expires_at: 1_100 } },
      deps({ fetch: fetchMock })
    )
    expect(token.access_token).toBe('old-access')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refreshes an expired token against the realm token endpoint', async () => {
    const fetchMock = vi.fn<typeof fetch>()
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: 'new-access',
          refresh_token: 'new-refresh',
          expires_in: 300,
        }),
        { headers: { 'content-type': 'application/json' } }
      )
    )

    const token = await jwtCallback({ token: expiredToken() }, deps({ fetch: fetchMock }))

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toBe(`${ISSUER}/protocol/openid-connect/token`)
    const body = init?.body as URLSearchParams
    expect(body.get('grant_type')).toBe('refresh_token')
    expect(body.get('refresh_token')).toBe('old-refresh')
    expect(token).toMatchObject({
      access_token: 'new-access',
      refresh_token: 'new-refresh',
      expires_at: 1_300,
      error: undefined,
    })
  })

  it('marks the token invalid when the refresh is rejected', async () => {
    const fetchMock = vi.fn<typeof fetch>()
    fetchMock.mockResolvedValue(new Response('nope', { status: 400 }))
    const token = await jwtCallback({ token: expiredToken() }, deps({ fetch: fetchMock }))
    expect(token.error).toBe('RefreshAccessTokenError')
    expect(token.access_token).toBeUndefined()
  })

  it('marks the token invalid when it expired with no refresh token', async () => {
    const token = await jwtCallback({ token: expiredToken({ refresh_token: undefined }) }, deps())
    expect(token.error).toBe('RefreshAccessTokenError')
    expect(token.access_token).toBeUndefined()
  })

  it('treats an unreachable token endpoint as an invalid token, never a crash', async () => {
    const fetchMock = vi.fn<typeof fetch>()
    fetchMock.mockRejectedValue(new Error('network down'))
    const token = await refreshAccessToken({ refresh_token: 'r' }, deps({ fetch: fetchMock }))
    expect(token.error).toBe('RefreshAccessTokenError')
  })
})

describe('sessionCallback', () => {
  it('exposes only identifiers and never the tokens', () => {
    const session = sessionCallback({
      session: {
        expires: '2099-01-01',
        user: { id: '', user_id: '', tenantId: null, roles: [], authTime: null },
      },
      token: {
        sub: 'user-1',
        tenant_id: 'tenant-a',
        roles: ['owner', 'not-a-role'],
        auth_time: 900,
        access_token: 'access-token-value',
        refresh_token: 'refresh-token-value',
      },
    })

    expect(session.user).toEqual({
      id: 'user-1',
      user_id: 'user-1',
      tenantId: 'tenant-a',
      roles: ['owner'],
      authTime: 900,
    })
    expect(JSON.stringify(session)).not.toContain('access-token-value')
    expect(JSON.stringify(session)).not.toContain('refresh-token-value')
  })

  it('uses nulls for claims a token may not carry', () => {
    const session = sessionCallback({
      session: {
        expires: '2099-01-01',
        user: { id: '', user_id: '', tenantId: null, roles: [], authTime: null },
      },
      token: { sub: 'user-1' },
    })
    expect(session.user).toEqual({
      id: 'user-1',
      user_id: 'user-1',
      tenantId: null,
      roles: [],
      authTime: null,
    })
  })
})

describe('authorized', () => {
  const loggedIn = { user: { id: 'user-1' } } as unknown as Session

  function request(path: string) {
    return new NextRequest(`http://localhost:3000${path}`)
  }

  it.each(['/', '/es', '/en/', '/es/acceso', '/login', '/api/auth/session'])(
    'allows the public path %s',
    (path) => {
      expect(authorized({ request: request(path), auth: null })).toBe(true)
    }
  )

  it('allows a protected page once the session has a user', () => {
    expect(authorized({ request: request('/es/dashboard'), auth: loggedIn })).toBe(true)
  })

  it('returns false for a protected page without a session so Auth.js redirects', () => {
    expect(authorized({ request: request('/es/dashboard'), auth: null })).toBe(false)
  })

  it('answers 401 problem+json for protected API calls instead of a page redirect', () => {
    const response = authorized({ request: request('/api/v1/missions'), auth: null })
    expect(response).toBeInstanceOf(Response)
    const problem = response as Response
    expect(problem.status).toBe(401)
    expect(problem.headers.get('content-type')).toBe('application/problem+json')
  })
})

describe('isPublicPath', () => {
  it('does not treat a nested app route as public', () => {
    expect(isPublicPath('/es/decisiones')).toBe(false)
    expect(isPublicPath('/es/dashboard')).toBe(false)
  })
})
