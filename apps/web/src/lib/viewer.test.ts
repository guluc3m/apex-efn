import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSession = vi.fn()
vi.mock('@/server/auth/session', () => ({ getSession: () => getSession() as unknown }))

import { getViewer } from './viewer'

const withRoles = (roles: string[]) => ({ user: { roles, tenantId: 't1' } })

describe('getViewer', () => {
  beforeEach(() => getSession.mockReset())
  it('picks the highest-privilege role', async () => {
    getSession.mockResolvedValue(withRoles(['buyer', 'admin']))
    expect(await getViewer()).toEqual({ role: 'admin', tenantId: 't1' })
  })
  it('falls back to viewer without a session or roles', async () => {
    getSession.mockResolvedValue(null)
    expect((await getViewer()).role).toBe('viewer')
    getSession.mockResolvedValue(withRoles([]))
    expect((await getViewer()).role).toBe('viewer')
  })
})
