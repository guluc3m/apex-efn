import type { Decision, SigningKey, SigningSession } from '@apex/shared-types/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSigningSession } from '@/stores/signing-session'

import { SigningUnsupportedError } from './open-session'
import { NoSigningSessionError, PayloadMismatchError, revokeKey, type RevokeKeyDeps } from './revoke-key'

const live = { id: 's1', status: 'active', server_time: '2026-11-10T10:00:00Z' } as SigningSession
const closed = { ...live, status: 'revoked' } as SigningSession
const decision = { id: 'd1', payload_canonical: '{"a":1}', payload_hash: 'H' } as Decision

function deps(over: Partial<RevokeKeyDeps> = {}) {
  const d: RevokeKeyDeps = {
    keys: {
      load: vi.fn(() => Promise.resolve(true)),
      sign: vi.fn(() => Promise.resolve({ keyId: 'k1', payloadHash: 'H', signature: 'SIG' })),
    },
    isSupported: () => Promise.resolve(true),
    hash: () => Promise.resolve('H'),
    createDecision: vi.fn(() => Promise.resolve(decision)),
    signDecision: vi.fn(() => Promise.resolve({})),
    revokeKey: vi.fn(() => Promise.resolve({ id: 'k2' } as SigningKey)),
    getSession: vi.fn(() => Promise.resolve(closed)),
    nowMs: () => Date.parse('2026-11-10T10:00:00Z'),
    ...over,
  }
  return d
}

describe('revokeKey', () => {
  beforeEach(() => useSigningSession.getState().setSession(live, 0))

  it('signs the server payload, then revokes and refreshes the session', async () => {
    const d = deps()
    await revokeKey('u1', 'k2', d)
    expect(d.createDecision).toHaveBeenCalledWith({ type: 'revoke_key', subject_ref: 'k2', params: { key_id: 'k2' } })
    expect(d.keys.sign).toHaveBeenCalledWith({ a: 1 })
    expect(d.signDecision).toHaveBeenCalledWith('d1', { key_id: 'k1', payload_hash: 'H', signature: 'SIG', signing_session_id: 's1' })
    expect(d.revokeKey).toHaveBeenCalledWith('k2', { decision_id: 'd1' })
    expect(useSigningSession.getState().session?.status).toBe('revoked')
  })

  it('refuses to sign when the server hash does not match the payload', async () => {
    const d = deps({ hash: () => Promise.resolve('OTHER') })
    await expect(revokeKey('u1', 'k2', d)).rejects.toBeInstanceOf(PayloadMismatchError)
    expect(d.keys.sign).not.toHaveBeenCalled()
  })

  it('needs an open session and a supported browser, and never calls the API otherwise', async () => {
    useSigningSession.getState().clear()
    const d = deps()
    await expect(revokeKey('u1', 'k2', d)).rejects.toBeInstanceOf(NoSigningSessionError)
    const e = deps({ isSupported: () => Promise.resolve(false) })
    await expect(revokeKey('u1', 'k2', e)).rejects.toBeInstanceOf(SigningUnsupportedError)
    expect(d.createDecision).not.toHaveBeenCalled()
    expect(e.createDecision).not.toHaveBeenCalled()
  })
})
