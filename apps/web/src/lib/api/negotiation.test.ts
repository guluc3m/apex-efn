import { http, HttpResponse } from 'msw'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { errorMessage } from '@/components/negotiation/negotiation-view'
import { server } from '@/mocks/server'

import { createApiClient } from './client'
import { createOperations } from './operations'
import { ApiError } from './problem'

const ops = () => createOperations(createApiClient({ baseUrl: 'http://bff.test', newIdempotencyKey: () => 'key-negotiation-1' }))

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('negotiation operations', () => {
  it('translates a message with both path ids and the target language', async () => {
    let seen: { url: string; body: unknown } | null = null
    server.use(
      http.post('*/api/v1/negotiations/:id/messages/:mid/translate', async ({ request }) => {
        seen = { url: new URL(request.url).pathname, body: await request.json() }
        return HttpResponse.json({ message_id: 'neg_1:2', target_language: 'he', text: 'x' })
      }),
    )
    await ops().translateNegotiationMessage('neg_1', 'neg_1:2', 'he')
    expect(seen).toEqual({ url: expect.stringContaining('/negotiations/neg_1/messages/neg_1%3A2/translate') as unknown, body: { target_language: 'he' } })
  })

  it('approves the exact draft id with an Idempotency-Key', async () => {
    let seen: { body: unknown; key: string | null } | null = null
    server.use(
      http.post('*/api/v1/negotiations/:id/approve', async ({ request }) => {
        seen = { body: await request.json(), key: request.headers.get('idempotency-key') }
        return HttpResponse.json({ id: 'neg_1' })
      }),
    )
    await ops().approveNegotiationDraft('neg_1', { draft_id: 'd_9' })
    expect(seen).toEqual({ body: { draft_id: 'd_9' }, key: 'key-negotiation-1' })
  })

  it('sends the control reason only when there is one', async () => {
    const bodies: unknown[] = []
    server.use(
      http.post('*/api/v1/negotiations/:id/takeover', async ({ request }) => {
        bodies.push(await request.text())
        return HttpResponse.json({ id: 'neg_1' })
      }),
    )
    await ops().takeoverNegotiation('neg_1')
    await ops().takeoverNegotiation('neg_1', 'seller asked for a call')
    expect(bodies).toEqual(['', JSON.stringify({ reason: 'seller asked for a call' })])
  })

  it('surfaces the closed 409 reason so the screen can explain it', async () => {
    server.use(
      http.post('*/api/v1/negotiations/:id/approve', () =>
        HttpResponse.json(
          { type: 'about:blank', title: 'Conflict', status: 409, reason: 'draft_superseded' },
          { status: 409, headers: { 'content-type': 'application/problem+json' } },
        ),
      ),
    )
    const error = await ops()
      .approveNegotiationDraft('neg_1', { draft_id: 'd_9' })
      .catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(errorMessage(error, (k) => k)).toBe('errors.draft_superseded')
    expect(errorMessage(new Error('x'), (k) => k)).toBe('errors.generic')
  })
})
