import { describe, expect, it, vi } from 'vitest'

import { signOutWithCleanup, type SignOutCleanupDeps } from './sign-out'

function harness(overrides: Partial<SignOutCleanupDeps> = {}) {
  const events: string[] = []
  const deps: SignOutCleanupDeps = {
    activeSessionId: 's1',
    closeSession: vi.fn((id: string) => {
      events.push(`close:${id}`)
      return Promise.resolve({ id, status: 'revoked' })
    }),
    clearLocal: vi.fn(() => {
      events.push('clear')
    }),
    signOut: vi.fn(() => {
      events.push('signOut')
      return Promise.resolve()
    }),
    ...overrides,
  }
  return { deps, events }
}

describe('signOutWithCleanup', () => {
  it('with no active session only clears local state and signs out', async () => {
    const { deps, events } = harness({ activeSessionId: null })
    const result = await signOutWithCleanup(deps)

    expect(deps.closeSession).not.toHaveBeenCalled()
    expect(events).toEqual(['clear', 'signOut'])
    expect(result).toEqual({ remoteSessionClosed: false })
  })

  it('closes the session before clearing and signing out', async () => {
    const { deps, events } = harness()
    const result = await signOutWithCleanup(deps)

    expect(events).toEqual(['close:s1', 'clear', 'signOut'])
    expect(result).toEqual({ remoteSessionClosed: true })
  })

  it('still signs out when the remote close rejects, and does not throw', async () => {
    const failure = new Error('network down')
    const { deps, events } = harness({ closeSession: vi.fn(() => Promise.reject(failure)) })
    const result = await signOutWithCleanup(deps)

    expect(events).toEqual(['clear', 'signOut'])
    expect(result.remoteSessionClosed).toBe(false)
    expect(result.closeError).toBe(failure)
  })

  it('still signs out when clearing local state throws, and does not throw', async () => {
    const { deps, events } = harness({
      clearLocal: () => {
        events.push('clear')
        throw new Error('store unavailable')
      },
    })
    const result = await signOutWithCleanup(deps)

    expect(events).toEqual(['close:s1', 'clear', 'signOut'])
    expect(result).toEqual({ remoteSessionClosed: true })
  })

  it('propagates a signOut failure: the caller must know the logout did not happen', async () => {
    const failure = new Error('auth.js down')
    const { deps } = harness({ signOut: vi.fn(() => Promise.reject(failure)) })

    await expect(signOutWithCleanup(deps)).rejects.toBe(failure)
  })
})
