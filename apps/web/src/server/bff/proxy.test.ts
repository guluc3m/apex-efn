import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { isSafeSegments, proxyToOrchestrator } from './proxy'

const ORIGINAL_ENV = { ...process.env }

beforeEach(() => {
  process.env.ORCHESTRATOR_URL = 'http://orch.test:8000/'
  delete process.env.APEX_DEV_ACCESS_TOKEN
  delete process.env.APEX_DEV_TENANT_ID
})
afterEach(() => {
  process.env = { ...ORIGINAL_ENV }
})

function upstream(response: Response = new Response('{}', { headers: { 'content-type': 'application/json' } })) {
  const fetchMock = vi.fn(() => Promise.resolve(response))
  return { fetchMock, impl: fetchMock as unknown as typeof fetch }
}

function lastCall(fetchMock: ReturnType<typeof upstream>['fetchMock']) {
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
  return { url, init, headers: new Headers(init.headers) }
}

describe('isSafeSegments', () => {
  it.each([[['missions', '1']], [['gate', 'queue', 'x', 'actions']]])('accepts %j', (segments) => {
    expect(isSafeSegments(segments)).toBe(true)
  })
  it.each([[[]], [['..', 'admin']], [['a', '']], [['a/b']], [['a\\b']], [['.']]])('rejects %j', (segments) => {
    expect(isSafeSegments(segments)).toBe(false)
  })
})

describe('proxyToOrchestrator', () => {
  it('forwards to /v1 with the query string and returns the upstream status', async () => {
    const { fetchMock, impl } = upstream(new Response('{}', { status: 404 }))
    const res = await proxyToOrchestrator(new Request('http://web.test/api/v1/missions/7?x=1'), ['missions', '7'], impl)
    expect(res.status).toBe(404)
    expect(lastCall(fetchMock).url).toBe('http://orch.test:8000/v1/missions/7?x=1')
  })

  it('refuses path traversal without calling the orchestrator', async () => {
    const { fetchMock, impl } = upstream()
    const res = await proxyToOrchestrator(new Request('http://web.test/api/v1/x'), ['..', 'health'], impl)
    expect(res.status).toBe(400)
    expect(res.headers.get('content-type')).toBe('application/problem+json')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('never forwards the browser Authorization header; it uses the server-side token', async () => {
    process.env.APEX_DEV_ACCESS_TOKEN = 'server-token'
    const { fetchMock, impl } = upstream()
    await proxyToOrchestrator(
      new Request('http://web.test/api/v1/m', { headers: { authorization: 'Bearer from-browser', cookie: 'a=b' } }),
      ['m'],
      impl,
    )
    const { headers } = lastCall(fetchMock)
    expect(headers.get('authorization')).toBe('Bearer server-token')
    expect(headers.get('cookie')).toBeNull()
  })

  it('sends no Authorization when there is no token', async () => {
    const { fetchMock, impl } = upstream()
    await proxyToOrchestrator(new Request('http://web.test/api/v1/m', { headers: { authorization: 'Bearer x' } }), ['m'], impl)
    expect(lastCall(fetchMock).headers.get('authorization')).toBeNull()
  })

  it('keeps the client Idempotency-Key and generates one only for writes without it', async () => {
    const a = upstream()
    await proxyToOrchestrator(
      new Request('http://web.test/api/v1/missions', { method: 'POST', body: '{}', headers: { 'idempotency-key': 'mine' } }),
      ['missions'],
      a.impl,
    )
    expect(lastCall(a.fetchMock).headers.get('idempotency-key')).toBe('mine')

    const b = upstream()
    await proxyToOrchestrator(new Request('http://web.test/api/v1/missions', { method: 'POST', body: '{}' }), ['missions'], b.impl)
    expect(lastCall(b.fetchMock).headers.get('idempotency-key')).toMatch(/^[0-9a-f-]{36}$/)

    const c = upstream()
    await proxyToOrchestrator(new Request('http://web.test/api/v1/missions/1'), ['missions', '1'], c.impl)
    expect(lastCall(c.fetchMock).headers.get('idempotency-key')).toBeNull()
  })

  it('refuses a write whose Origin is another site, and allows same-origin and no Origin', async () => {
    const post = (headers: Record<string, string>) =>
      new Request('http://web.test/api/v1/missions', { method: 'POST', body: '{}', headers })

    const evil = upstream()
    const refused = await proxyToOrchestrator(post({ origin: 'https://evil.test', host: 'web.test' }), ['missions'], evil.impl)
    expect(refused.status).toBe(403)
    expect(evil.fetchMock).not.toHaveBeenCalled()

    const same = upstream()
    expect((await proxyToOrchestrator(post({ origin: 'http://web.test', host: 'web.test' }), ['missions'], same.impl)).status).toBe(200)

    const none = upstream()
    expect((await proxyToOrchestrator(post({}), ['missions'], none.impl)).status).toBe(200)

    const read = upstream()
    const get = new Request('http://web.test/api/v1/missions/1', { headers: { origin: 'https://evil.test' } })
    expect((await proxyToOrchestrator(get, ['missions', '1'], read.impl)).status).toBe(200)
  })

  it('passes an SSE body through as a stream with buffering disabled', async () => {
    const sse = new Response('id: 1\ndata: {}\n\n', { headers: { 'content-type': 'text/event-stream' } })
    const { impl } = upstream(sse)
    const res = await proxyToOrchestrator(new Request('http://web.test/api/v1/missions/1/events'), ['missions', '1', 'events'], impl)
    expect(res.headers.get('content-type')).toBe('text/event-stream')
    expect(res.headers.get('cache-control')).toBe('no-store, no-transform')
    expect(res.headers.get('x-accel-buffering')).toBe('no')
    expect(await res.text()).toBe('id: 1\ndata: {}\n\n')
  })

  it('answers 502 problem+json when the orchestrator is down', async () => {
    const impl = (() => Promise.reject(new TypeError('fetch failed'))) as unknown as typeof fetch
    const res = await proxyToOrchestrator(new Request('http://web.test/api/v1/m'), ['m'], impl)
    expect(res.status).toBe(502)
  })
})
