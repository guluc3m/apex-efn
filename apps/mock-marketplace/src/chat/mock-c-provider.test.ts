import type { FastifyInstance } from 'fastify'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { steppingClock } from '../clock.js'
import { buildServer } from '../server.js'

import { phraserFromEnv, type FetchLike } from './phraser.js'

const FIXED = new Date('2026-11-01T09:00:00.000Z')
const BUYER_LINE = 'Hello, we need 1000 units. What is your price?'
const REPLY = 'Hola, te lo dejo en €4.32 por unidad.'

interface FetchCall {
  url: string
  init: RequestInit
}

/** Injected in place of the global fetch: no socket is ever opened. */
function stubFetch(content: string): { impl: FetchLike; calls: FetchCall[] } {
  const calls: FetchCall[] = []
  const impl: FetchLike = (url, init = {}) => {
    calls.push({ url, init })
    return Promise.resolve(
      new Response(JSON.stringify({ choices: [{ message: { content } }] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    )
  }
  return { impl, calls }
}

async function openThread(app: FastifyInstance, buyerId?: string): Promise<string> {
  const opened = await app.inject({
    method: 'POST',
    url: '/mock-c/api/threads',
    payload: buyerId === undefined ? { item_id: 'c-gloves-01' } : { item_id: 'c-gloves-01', buyer_id: buyerId },
  })
  expect(opened.statusCode).toBe(201)
  return opened.json<{ thread_id: string }>().thread_id
}

function headersOf(call: FetchCall | undefined): Record<string, string> {
  return call?.init.headers as Record<string, string>
}

function bodyOf(call: FetchCall | undefined): { model: string } {
  const raw = call?.init.body
  if (typeof raw !== 'string') throw new Error('request body was not a string')
  return JSON.parse(raw) as { model: string }
}

describe('mock-c per-request LLM configuration', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses the x-sim-llm-* headers for this request only', async () => {
    const { impl, calls } = stubFetch(REPLY)
    vi.stubGlobal('fetch', impl)
    // No process-wide phraser: the reply can only be reworded through the request headers.
    const { app } = buildServer({ clock: steppingClock(FIXED), seed: 42 })
    const threadId = await openThread(app)

    const sent = await app.inject({
      method: 'POST',
      url: `/mock-c/api/threads/${threadId}/messages`,
      // Header names are case-insensitive; Fastify hands them over lowercased.
      headers: {
        'X-Sim-Llm-Url': 'https://llm.example.test/',
        'X-Sim-Llm-Key': 'sk-session-secret',
        'X-Sim-Llm-Model': 'deepseek-chat',
      },
      payload: { body: BUYER_LINE },
    })

    expect(sent.statusCode).toBe(201)
    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe('https://llm.example.test/v1/chat/completions')
    const headers = headersOf(calls[0])
    expect(headers.authorization).toBe('Bearer sk-session-secret')
    expect(headers['x-stub-scenario']).toBeUndefined()
    expect(bodyOf(calls[0]).model).toBe('deepseek-chat')

    expect(sent.json<{ received: Array<{ body: string }> }>().received[0]?.body).toBe(REPLY)
    // The key is a credential, not a response field.
    expect(sent.body).not.toContain('sk-session-secret')
    await app.close()
  })

  it('keeps the process-wide env phraser when no header is sent', async () => {
    const { impl, calls } = stubFetch(REPLY)
    vi.stubGlobal('fetch', impl)
    const phraser = phraserFromEnv({ SIM_LLM_URL: 'http://env-llm.test' })
    const { app } = buildServer({ clock: steppingClock(FIXED), seed: 42, phraser })
    const threadId = await openThread(app)

    const sent = await app.inject({
      method: 'POST',
      url: `/mock-c/api/threads/${threadId}/messages`,
      payload: { body: BUYER_LINE },
    })

    expect(sent.statusCode).toBe(201)
    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe('http://env-llm.test/v1/chat/completions')
    const headers = headersOf(calls[0])
    expect(headers.authorization).toBeUndefined()
    expect(headers['x-stub-scenario']).toBe('sim-negotiation')
    expect(bodyOf(calls[0]).model).toBe('seller')
    await app.close()
  })

  it('ignores a blank url header and keeps the env phraser', async () => {
    const { impl, calls } = stubFetch(REPLY)
    vi.stubGlobal('fetch', impl)
    const phraser = phraserFromEnv({ SIM_LLM_URL: 'http://env-llm.test' })
    const { app } = buildServer({ clock: steppingClock(FIXED), seed: 42, phraser })
    const threadId = await openThread(app)

    await app.inject({
      method: 'POST',
      url: `/mock-c/api/threads/${threadId}/messages`,
      headers: { 'x-sim-llm-url': '   ' },
      payload: { body: BUYER_LINE },
    })

    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe('http://env-llm.test/v1/chat/completions')
    await app.close()
  })

  it('keeps concurrent sessions on their own provider and key', async () => {
    const { impl, calls } = stubFetch(REPLY)
    vi.stubGlobal('fetch', impl)
    const { app } = buildServer({ clock: steppingClock(FIXED), seed: 42 })
    const first = await openThread(app, 'buyer-a')
    const second = await openThread(app, 'buyer-b')

    await Promise.all([
      app.inject({
        method: 'POST',
        url: `/mock-c/api/threads/${first}/messages`,
        headers: { 'x-sim-llm-url': 'https://a.example.test', 'x-sim-llm-key': 'sk-a' },
        payload: { body: BUYER_LINE },
      }),
      app.inject({
        method: 'POST',
        url: `/mock-c/api/threads/${second}/messages`,
        headers: { 'x-sim-llm-url': 'https://b.example.test', 'x-sim-llm-key': 'sk-b' },
        payload: { body: BUYER_LINE },
      }),
    ])

    expect(calls).toHaveLength(2)
    const byUrl = new Map(calls.map((call) => [call.url, headersOf(call).authorization]))
    expect(byUrl.get('https://a.example.test/v1/chat/completions')).toBe('Bearer sk-a')
    expect(byUrl.get('https://b.example.test/v1/chat/completions')).toBe('Bearer sk-b')
    await app.close()
  })
})
