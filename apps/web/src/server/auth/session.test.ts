import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ auth: vi.fn() }))

vi.mock('@/auth', () => ({ auth: mocks.auth }))

import { getSession } from './session'

describe('getSession', () => {
  it('returns null without a session', async () => {
    mocks.auth.mockResolvedValueOnce(null)
    await expect(getSession()).resolves.toBeNull()
  })

  it('returns null when the session has no user id', async () => {
    mocks.auth.mockResolvedValueOnce({ expires: '2099-01-01', user: { id: '' } })
    await expect(getSession()).resolves.toBeNull()
  })

  it('maps the tenant, roles and auth_time', async () => {
    mocks.auth.mockResolvedValueOnce({
      expires: '2099-01-01',
      user: { id: 'user-1', tenantId: 'tenant-a', roles: ['buyer', 'finance'], authTime: 1700 },
    })
    await expect(getSession()).resolves.toEqual({
      user: { id: 'user-1', tenantId: 'tenant-a', roles: ['buyer', 'finance'], authTime: 1700 },
    })
  })

  it('never returns tokens, even if a session callback leaked them', async () => {
    mocks.auth.mockResolvedValueOnce({
      expires: '2099-01-01',
      access_token: 'access-token-value',
      refresh_token: 'refresh-token-value',
      user: {
        id: 'user-1',
        tenantId: 'tenant-a',
        roles: ['owner'],
        authTime: 1700,
        access_token: 'access-token-value',
        refresh_token: 'refresh-token-value',
      },
    })

    const session = await getSession()
    expect(session).toEqual({
      user: { id: 'user-1', tenantId: 'tenant-a', roles: ['owner'], authTime: 1700 },
    })
    expect(JSON.stringify(session)).not.toContain('access-token-value')
    expect(JSON.stringify(session)).not.toContain('refresh-token-value')
  })
})
