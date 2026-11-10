import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ cookies: vi.fn(), getToken: vi.fn() }))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))
vi.mock('next-auth/jwt', () => ({ getToken: mocks.getToken }))

import { getAccessToken } from './token'

function cookieStore(values: { name: string; value: string }[]) {
  return { getAll: () => values }
}

beforeEach(() => {
  mocks.cookies.mockReset()
  mocks.getToken.mockReset()
})

describe('getAccessToken', () => {
  it('returns null when there is no cookie at all', async () => {
    mocks.cookies.mockResolvedValue(cookieStore([]))
    await expect(getAccessToken()).resolves.toBeNull()
    expect(mocks.getToken).not.toHaveBeenCalled()
  })

  it('returns null outside a request scope instead of throwing', async () => {
    mocks.cookies.mockRejectedValue(new Error('called outside a request scope'))
    await expect(getAccessToken()).resolves.toBeNull()
  })

  it('returns null when the cookie has no decodable session', async () => {
    mocks.cookies.mockResolvedValue(cookieStore([{ name: 'authjs.session-token', value: 'jwe' }]))
    mocks.getToken.mockResolvedValue(null)
    await expect(getAccessToken()).resolves.toBeNull()
  })

  it('decodes the cookie and returns the Keycloak access token', async () => {
    mocks.cookies.mockResolvedValue(cookieStore([{ name: 'authjs.session-token', value: 'jwe' }]))
    mocks.getToken.mockResolvedValue({
      access_token: 'keycloak-access-token',
      expires_at: Math.floor(Date.now() / 1000) + 300,
    })

    await expect(getAccessToken()).resolves.toBe('keycloak-access-token')
    expect(mocks.getToken).toHaveBeenCalledWith({
      req: { headers: { cookie: 'authjs.session-token=jwe' } },
    })
  })

  it('returns null after a failed refresh and for expired tokens', async () => {
    mocks.cookies.mockResolvedValue(cookieStore([{ name: 'authjs.session-token', value: 'jwe' }]))

    mocks.getToken.mockResolvedValueOnce({
      access_token: 'stale',
      error: 'RefreshAccessTokenError',
    })
    await expect(getAccessToken()).resolves.toBeNull()

    mocks.getToken.mockResolvedValueOnce({
      access_token: 'stale',
      expires_at: Math.floor(Date.now() / 1000) - 1,
    })
    await expect(getAccessToken()).resolves.toBeNull()
  })
})
