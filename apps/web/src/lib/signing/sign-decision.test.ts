import type { Decision, SigningSession } from '@apex/shared-types/contracts'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSigningSession } from '@/stores/signing-session'

import { NoSigningSessionError, PayloadMismatchError, signLoadedDecision, type SignDeps } from './sign-decision'

const live = { id: 's1', status: 'active', server_time: '2026-11-10T10:00:00Z' } as SigningSession
const decision = { id: 'd1', payload_canonical: '{"a":1}', payload_hash: 'H' } as Decision

function deps(over: Partial<SignDeps> = {}): SignDeps {
  return {
    keys: {
      load: vi.fn(() => Promise.resolve(true)),
      sign: vi.fn(() => Promise.resolve({ keyId: 'k1', payloadHash: 'H', signature: 'SIG' })),
    },
    isSupported: () => Promise.resolve(true),
    hash: () => Promise.resolve('H'),
    signDecision: vi.fn(() => Promise.resolve({})),
    ...over,
  }
}

describe('signLoadedDecision', () => {
  beforeEach(() => useSigningSession.getState().setSession(live, 0))

  it('signs the server payload inside the open window', async () => {
    const d = deps()
    await signLoadedDecision('u1', decision, d)
    expect(d.signDecision).toHaveBeenCalledWith('d1', { key_id: 'k1', payload_hash: 'H', signature: 'SIG', signing_session_id: 's1' })
  })

  it('refuses without an open window and signs nothing', async () => {
    useSigningSession.getState().setSession({ ...live, status: 'revoked' }, 0)
    const d = deps()
    await expect(signLoadedDecision('u1', decision, d)).rejects.toBeInstanceOf(NoSigningSessionError)
    expect(d.signDecision).not.toHaveBeenCalled()
  })

  it('refuses a payload whose hash differs from the server hash', async () => {
    const d = deps({ hash: () => Promise.resolve('OTHER') })
    await expect(signLoadedDecision('u1', decision, d)).rejects.toBeInstanceOf(PayloadMismatchError)
    expect(d.keys.sign).not.toHaveBeenCalled()
  })
})
