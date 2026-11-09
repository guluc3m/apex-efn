import type { SigningSession } from '@apex/shared-types/contracts'
import { beforeEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/lib/api/client'
import { setReauthHandler } from '@/lib/api/reauth'
import { useSigningSession } from '@/stores/signing-session'

import { clockOffsetMs, formatMmSs, remainingMs, signingView } from './countdown'
import { installStepUpOn428, setStepUp } from './step-up'

const T0 = Date.parse('2026-11-09T09:00:00Z')
const session = (over: Partial<SigningSession> = {}): SigningSession => ({
  id: 's1', user_id: 'u1', key_id: 'k1', auth_method: 'keycloak_step_up',
  auth_at: '2026-11-09T09:00:00Z', expires_at: '2026-11-09T09:15:00Z',
  device_fingerprint_ref: 'd', decisions_signed: [], max_decisions: 5, remaining_decisions: 5,
  status: 'active', server_time: '2026-11-09T09:00:00Z', ...over,
})

describe('countdown', () => {
  it('corrects a local clock that is 2 min fast', () => {
    const local = T0 + 120_000
    const offset = clockOffsetMs('2026-11-09T09:00:00Z', local)
    expect(offset).toBe(-120_000)
    expect(formatMmSs(remainingMs('2026-11-09T09:15:00Z', local, offset))).toBe('15:00')
  })
  it('formats mm:ss and clamps at zero', () => {
    expect(formatMmSs(61_000)).toBe('01:01')
    expect(formatMmSs(-5)).toBe('00:00')
  })
  it('flips to read-only at expiry, never extends', () => {
    const s = session()
    expect(signingView(s, T0 + 899_000, 0)).toBe('active')
    expect(signingView(s, T0 + 900_000, 0)).toBe('read_only')
  })
  it('is read-only when exhausted or not active; none without session', () => {
    expect(signingView(session({ remaining_decisions: 0 }), T0, 0)).toBe('read_only')
    expect(signingView(session({ status: 'revoked' }), T0, 0)).toBe('read_only')
    expect(signingView(null, T0, 0)).toBe('none')
  })
  it('store keeps the offset from server_time', () => {
    useSigningSession.getState().setSession(session(), T0 + 5_000)
    expect(useSigningSession.getState().offsetMs).toBe(-5_000)
    expect(useSigningSession.getState().session?.remaining_decisions).toBe(5)
  })
})

describe('428 -> step-up -> retry once', () => {
  const problem = () => new Response(JSON.stringify({ type: 'about:blank', title: 'x', status: 428, error: 'reauth_required', reason: 'step_up_required' }), { status: 428, headers: { 'content-type': 'application/problem+json' } })
  beforeEach(() => setReauthHandler(null))

  it('runs step-up then retries with the same idempotency key', async () => {
    const calls: Array<string | undefined> = []
    const fetchMock = ((_u: string, init: RequestInit) => {
      calls.push((init.headers as Record<string, string>)['idempotency-key'])
      return Promise.resolve(calls.length === 1 ? problem() : new Response('{}', { status: 200 }))
    }) as unknown as typeof fetch
    let stepUps = 0
    setStepUp(() => { stepUps++; return Promise.resolve(true) })
    installStepUpOn428()
    await createApiClient({ fetch: fetchMock, baseUrl: 'http://x' }).request('/v1/decisions', { method: 'POST', path: undefined })
    expect(stepUps).toBe(1)
    expect(calls).toHaveLength(2)
    expect(calls[0]).toBe(calls[1])
  })

  it('fails closed when step-up is not completed: no retry', async () => {
    let n = 0
    const fetchMock = (() => { n++; return Promise.resolve(problem()) }) as unknown as typeof fetch
    setStepUp(() => Promise.resolve(false))
    installStepUpOn428()
    await expect(createApiClient({ fetch: fetchMock, baseUrl: 'http://x' }).request('/v1/decisions', { method: 'POST', path: undefined })).rejects.toBeTruthy()
    expect(n).toBe(1)
  })
})
