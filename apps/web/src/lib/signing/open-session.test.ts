import type { SigningKey, SigningSession } from '@apex/shared-types/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSigningSession } from '@/stores/signing-session'

import { openSigningSession, SigningUnsupportedError, type OpenSessionDeps } from './open-session'

const key = (id: string) => ({ id }) as SigningKey
const session = { id: 's1', server_time: '2026-11-10T10:00:00Z' } as SigningSession

function deps(over: Partial<OpenSessionDeps> & { loaded?: string | null; listed?: string[] } = {}) {
  const { loaded = null, listed = [], ...rest } = over
  const keys = {
    load: vi.fn(() => Promise.resolve(loaded !== null)),
    loadedKeyId: loaded,
    generateKey: vi.fn(() => Promise.resolve('PUB')),
    persist: vi.fn(() => Promise.resolve()),
  }
  const d: OpenSessionDeps = {
    keys,
    isSupported: () => Promise.resolve(true),
    listKeys: () => Promise.resolve({ items: listed.map(key) }),
    registerKey: vi.fn(() => Promise.resolve(key('new'))),
    openSession: vi.fn(() => Promise.resolve(session)),
    deviceFingerprintRef: () => 'dev',
    nowMs: () => Date.parse('2026-11-10T10:00:00Z'),
    ...rest,
  }
  return { d, keys }
}

describe('openSigningSession', () => {
  beforeEach(() => useSigningSession.getState().clear())

  it('enrolls a key on a device that has none, then opens the window', async () => {
    const { d, keys } = deps()
    await openSigningSession('u1', d)
    expect(d.registerKey).toHaveBeenCalledWith({ public_key: 'PUB', alg: 'Ed25519' })
    expect(keys.persist).toHaveBeenCalledWith('u1', 'new')
    expect(d.openSession).toHaveBeenCalledWith({ key_id: 'new', device_fingerprint_ref: 'dev' })
    expect(useSigningSession.getState().session?.id).toBe('s1')
  })

  it('reuses the device key while the server still lists it', async () => {
    const { d, keys } = deps({ loaded: 'k1', listed: ['k1'] })
    await openSigningSession('u1', d)
    expect(d.registerKey).not.toHaveBeenCalled()
    expect(keys.persist).not.toHaveBeenCalled()
    expect(d.openSession).toHaveBeenCalledWith({ key_id: 'k1', device_fingerprint_ref: 'dev' })
  })

  it('enrolls again when the device key was revoked on the server', async () => {
    const { d } = deps({ loaded: 'old', listed: ['other'] })
    await openSigningSession('u1', d)
    expect(d.registerKey).toHaveBeenCalled()
  })

  it('blocks signing without Ed25519 and never touches the server', async () => {
    const { d } = deps({ isSupported: () => Promise.resolve(false) })
    await expect(openSigningSession('u1', d)).rejects.toBeInstanceOf(SigningUnsupportedError)
    expect(d.listKeys).toBeDefined()
    expect(d.registerKey).not.toHaveBeenCalled()
    expect(d.openSession).not.toHaveBeenCalled()
  })
})
