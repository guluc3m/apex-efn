import { describe, expect, it } from 'vitest'

import { WorkerError } from '../errors.js'
import { bearer, createHarness, idempotencyKey, TOKEN, type Harness } from '../testing/harness.js'

const SEARCH_BODY = {
  kind: 'search',
  tenant_id: 'tenant-1',
  mission_id: 'mission-1',
  trace_id: 'trace-1',
  platform: 'mock-a',
  query: 'steel bolts',
}

const OPEN_BODY = {
  tenant_id: 'tenant-1',
  mission_id: 'mission-1',
  trace_id: 'trace-1',
  negotiation_id: 'negotiation-1',
  platform: 'mock-b',
  account_id: 'account-1',
  platform_seller_id: 'seller-1',
  product_id: 'product-1',
}

async function openChat(h: Harness): Promise<string> {
  const response = await h.app.inject({
    method: 'POST',
    url: '/internal/v1/chats',
    headers: { ...bearer(), ...idempotencyKey('open') },
    payload: OPEN_BODY,
  })
  return response.json<{ chat_id: string }>().chat_id
}

function expectProblem(
  response: { statusCode: number; headers: Record<string, unknown>; json: () => unknown },
  status: number,
  code: string
) {
  expect(response.statusCode).toBe(status)
  expect(String(response.headers['content-type'])).toContain('application/problem+json')
  expect(response.json()).toMatchObject({ status, code, type: 'about:blank' })
}

describe('service authentication', () => {
  it('answers health without a token and lists platforms with their flag state', async () => {
    const h = createHarness()
    const response = await h.app.inject({ method: 'GET', url: '/internal/v1/health' })
    expect(response.statusCode).toBe(200)
    expect(response.json()).toEqual({
      status: 'ok',
      platforms: [
        { platform: 'mock-a', enabled: true, transport: 'http' },
        { platform: 'mock-b', enabled: true, transport: 'browser' },
        { platform: 'mock-c', enabled: false, transport: 'http' },
      ],
    })
  })

  it('rejects a request without a token', async () => {
    const h = createHarness()
    const response = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      payload: SEARCH_BODY,
    })
    expectProblem(response, 401, 'unauthorized')
  })

  it('rejects a wrong token, a token of another length and a non-Bearer scheme', async () => {
    const h = createHarness()
    for (const headers of [
      bearer('wrong-token-of-the-same-or-other-length'),
      bearer(TOKEN.slice(0, 10)),
      { authorization: `Basic ${TOKEN}` },
    ]) {
      const response = await h.app.inject({
        method: 'GET',
        url: '/internal/v1/jobs/anything',
        headers,
      })
      expectProblem(response, 401, 'unauthorized')
    }
  })

  it('answers an unknown route with a problem document after authentication', async () => {
    const h = createHarness()
    const response = await h.app.inject({
      method: 'GET',
      url: '/internal/v1/nope',
      headers: bearer(),
    })
    expectProblem(response, 404, 'validation_error')
  })
})

describe('jobs routes', () => {
  it('accepts a job and replays it for the same Idempotency-Key', async () => {
    const h = createHarness()
    const headers = { ...bearer(), ...idempotencyKey('job-accept') }
    const first = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers,
      payload: SEARCH_BODY,
    })
    expect(first.statusCode).toBe(202)
    expect(first.json()).toMatchObject({ status: 'queued', deduplicated: false })

    const second = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers,
      payload: SEARCH_BODY,
    })
    expect(second.statusCode).toBe(202)
    expect(second.json()).toMatchObject({
      job_id: first.json<{ job_id: string }>().job_id,
      deduplicated: true,
    })
  })

  it('requires an Idempotency-Key of 16 to 128 characters', async () => {
    const h = createHarness()
    const missing = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers: bearer(),
      payload: SEARCH_BODY,
    })
    expectProblem(missing, 422, 'validation_error')

    const short = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers: { ...bearer(), 'idempotency-key': 'too-short' },
      payload: SEARCH_BODY,
    })
    expectProblem(short, 422, 'validation_error')
  })

  it('rejects unknown fields, unknown kinds and malformed JSON with 422 and no value in the detail', async () => {
    const h = createHarness()
    const headers = { ...bearer(), ...idempotencyKey('job-invalid') }

    const extra = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers,
      payload: { ...SEARCH_BODY, extra_field: 'secret-value-123' },
    })
    expectProblem(extra, 422, 'validation_error')
    expect(extra.json<{ detail: string }>().detail).toContain('extra_field')
    expect(extra.body).not.toContain('secret-value-123')

    const wrongKind = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers,
      payload: { ...SEARCH_BODY, kind: 'checkout' },
    })
    expectProblem(wrongKind, 422, 'validation_error')

    const malformed = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers: { ...headers, 'content-type': 'application/json' },
      payload: '{"kind": "search", "query": ',
    })
    expectProblem(malformed, 422, 'validation_error')
  })

  it('returns 409 for the same key with a different body', async () => {
    const h = createHarness()
    const headers = { ...bearer(), ...idempotencyKey('job-conflict') }
    await h.app.inject({ method: 'POST', url: '/internal/v1/jobs', headers, payload: SEARCH_BODY })
    const response = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers,
      payload: { ...SEARCH_BODY, query: 'copper wire' },
    })
    expectProblem(response, 409, 'idempotency_conflict')
  })

  it('returns 404 for an unknown platform and 409 for a disabled one without calling it', async () => {
    const h = createHarness()
    const unknown = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers: { ...bearer(), ...idempotencyKey('job-unknown') },
      payload: { ...SEARCH_BODY, platform: 'nope' },
    })
    expectProblem(unknown, 404, 'unknown_platform')

    const disabled = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers: { ...bearer(), ...idempotencyKey('job-disabled') },
      payload: { ...SEARCH_BODY, platform: 'mock-c' },
    })
    expectProblem(disabled, 409, 'platform_disabled')
    expect(h.disabled.calls).toEqual([])
  })

  it('returns the result of a finished job and 404 for an unknown id', async () => {
    const h = createHarness()
    const accepted = await h.app.inject({
      method: 'POST',
      url: '/internal/v1/jobs',
      headers: { ...bearer(), ...idempotencyKey('job-result') },
      payload: SEARCH_BODY,
    })
    const jobId = accepted.json<{ job_id: string }>().job_id
    await h.jobs.runAll()

    const state = await h.app.inject({
      method: 'GET',
      url: `/internal/v1/jobs/${jobId}`,
      headers: bearer(),
    })
    expect(state.statusCode).toBe(200)
    expect(state.json()).toMatchObject({
      job_id: jobId,
      status: 'succeeded',
      kind: 'search',
      result: { kind: 'search' },
    })

    const missing = await h.app.inject({
      method: 'GET',
      url: '/internal/v1/jobs/missing',
      headers: bearer(),
    })
    expectProblem(missing, 404, 'unknown_job')
  })
})

describe('chats routes', () => {
  it('runs the takeover flow over HTTP: lock, refusal, human send, release', async () => {
    const h = createHarness()
    const chatId = await openChat(h)

    const acquired = await h.app.inject({
      method: 'PUT',
      url: `/internal/v1/chats/${chatId}/lock`,
      headers: bearer(),
      payload: { user_id: 'user-1', ttl_seconds: 300 },
    })
    expect(acquired.statusCode).toBe(200)
    expect(acquired.json()).toMatchObject({ holder: 'human', user_id: 'user-1' })

    const otherUser = await h.app.inject({
      method: 'PUT',
      url: `/internal/v1/chats/${chatId}/lock`,
      headers: bearer(),
      payload: { user_id: 'user-2', ttl_seconds: 300 },
    })
    expectProblem(otherUser, 409, 'lock_held')

    const agentSend = await h.app.inject({
      method: 'POST',
      url: `/internal/v1/chats/${chatId}/messages`,
      headers: { ...bearer(), ...idempotencyKey('agent-send') },
      payload: { text: 'Hello', sender: 'agent' },
    })
    expectProblem(agentSend, 409, 'chat_locked')

    const humanSend = await h.app.inject({
      method: 'POST',
      url: `/internal/v1/chats/${chatId}/messages`,
      headers: { ...bearer(), ...idempotencyKey('human-send') },
      payload: { text: 'Hello, I am taking over', sender: 'human', user_id: 'user-1' },
    })
    expect(humanSend.statusCode).toBe(201)
    expect(humanSend.json()).toMatchObject({ role: 'buyer', sent_by: 'human' })

    const foreignRelease = await h.app.inject({
      method: 'DELETE',
      url: `/internal/v1/chats/${chatId}/lock?user_id=user-2`,
      headers: bearer(),
    })
    expectProblem(foreignRelease, 409, 'not_lock_holder')

    const release = await h.app.inject({
      method: 'DELETE',
      url: `/internal/v1/chats/${chatId}/lock?user_id=user-1`,
      headers: bearer(),
    })
    expect(release.statusCode).toBe(204)
    expect(release.body).toBe('')

    const freeRelease = await h.app.inject({
      method: 'DELETE',
      url: `/internal/v1/chats/${chatId}/lock?user_id=user-1`,
      headers: bearer(),
    })
    expect(freeRelease.statusCode).toBe(204)
  })

  it('reads messages with paging parameters and validates them', async () => {
    const h = createHarness()
    const chatId = await openChat(h)
    h.chatAdapter.seedSellerMessage('Hi')
    h.chatAdapter.seedSellerMessage('Quantity?')

    const page = await h.app.inject({
      method: 'GET',
      url: `/internal/v1/chats/${chatId}/messages?after_seq=0&limit=1`,
      headers: bearer(),
    })
    expect(page.statusCode).toBe(200)
    expect(page.json()).toMatchObject({
      chat_id: chatId,
      last_seq: 2,
      messages: [{ seq: 1, role: 'seller', sent_by: null }],
    })

    const badLimit = await h.app.inject({
      method: 'GET',
      url: `/internal/v1/chats/${chatId}/messages?limit=0`,
      headers: bearer(),
    })
    expectProblem(badLimit, 422, 'validation_error')
  })

  it('answers unknown chats with 404 and requires the Idempotency-Key on writes', async () => {
    const h = createHarness()
    const unknown = await h.app.inject({
      method: 'GET',
      url: '/internal/v1/chats/missing',
      headers: bearer(),
    })
    expectProblem(unknown, 404, 'unknown_chat')

    const chatId = await openChat(h)
    const noKey = await h.app.inject({
      method: 'POST',
      url: `/internal/v1/chats/${chatId}/messages`,
      headers: bearer(),
      payload: { text: 'Hello', sender: 'agent' },
    })
    expectProblem(noKey, 422, 'validation_error')
  })

  it('creates a screenshot with 201', async () => {
    const h = createHarness()
    const chatId = await openChat(h)
    const response = await h.app.inject({
      method: 'POST',
      url: `/internal/v1/chats/${chatId}/screenshots`,
      headers: { ...bearer(), ...idempotencyKey('shot') },
    })
    expect(response.statusCode).toBe(201)
    expect(response.json<{ sha256: string }>().sha256).toMatch(/^[0-9a-f]{64}$/)
  })

  it('sends Retry-After for a platform rate limit and hides internal messages', async () => {
    const h = createHarness()
    const chatId = await openChat(h)
    h.chatAdapter.failSendWith = new WorkerError('rate_limited', 429, {
      retryable: true,
      retryAfterSeconds: 30,
    })
    const limited = await h.app.inject({
      method: 'POST',
      url: `/internal/v1/chats/${chatId}/messages`,
      headers: { ...bearer(), ...idempotencyKey('rate-limit') },
      payload: { text: 'Hello', sender: 'agent' },
    })
    expectProblem(limited, 429, 'rate_limited')
    expect(limited.headers['retry-after']).toBe('30')
    expect(limited.json()).toMatchObject({ retryable: true, retry_after_seconds: 30 })

    h.chatAdapter.failSendWith = new Error('secret-internal-detail')
    const broken = await h.app.inject({
      method: 'POST',
      url: `/internal/v1/chats/${chatId}/messages`,
      headers: { ...bearer(), ...idempotencyKey('broken-send') },
      payload: { text: 'Hello', sender: 'agent' },
    })
    expectProblem(broken, 500, 'internal')
    expect(broken.body).not.toContain('secret-internal-detail')
  })
})
