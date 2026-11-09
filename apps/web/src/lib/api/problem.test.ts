import { describe, expect, it } from 'vitest'

import { ApiError, asReauthRequired, problemFromResponse } from './problem'

function problemResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/problem+json' } })
}

describe('problemFromResponse', () => {
  it('keeps the RFC 9457 members and the extensions', async () => {
    const error = await problemFromResponse(
      problemResponse({ type: 'urn:apex:gate', title: 'Blocked', status: 409, detail: 'no', reason: 'financials_stale' }, 409),
    )
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(409)
    expect(error.title).toBe('Blocked')
    expect(error.message).toBe('no')
    expect(error.reason).toBe('financials_stale')
  })

  it('turns a non-problem body into an ApiError instead of throwing', async () => {
    const error = await problemFromResponse(new Response('<html>', { status: 503, statusText: 'Service Unavailable' }))
    expect(error.status).toBe(503)
    expect(error.type).toBe('about:blank')
  })
})

describe('asReauthRequired', () => {
  const base = { type: 'about:blank', title: 'Reauthentication required', status: 428 }

  it('accepts a reason from the closed contract enum', () => {
    const result = asReauthRequired(new ApiError({ ...base, reason: 'session_expired' }))
    expect(result?.reason).toBe('session_expired')
    expect(result?.error).toBe('reauth_required')
  })

  it('rejects a 428 whose reason is not in the contract, so nothing signs on a guess', () => {
    expect(asReauthRequired(new ApiError({ ...base, reason: 'made_up' }))).toBeNull()
    expect(asReauthRequired(new ApiError({ ...base }))).toBeNull()
  })

  it('ignores other statuses and non-API errors', () => {
    expect(asReauthRequired(new ApiError({ ...base, status: 409, reason: 'session_expired' }))).toBeNull()
    expect(asReauthRequired(new Error('x'))).toBeNull()
  })
})
