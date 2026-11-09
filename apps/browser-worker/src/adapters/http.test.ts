import { zRawOffer } from '@apex/shared-types/contracts/browser-worker/zod'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { z } from 'zod'

import { WorkerError } from '../errors.js'
import { InMemoryContractAdapter } from '../testing/contract-fake.js'
import { FixedClock } from '../testing/fakes.js'

import {
  fetchTransport,
  type HttpRequest,
  type HttpResponse,
  type HttpTransport,
  PoliteHttpClient,
  retryAfterSeconds,
  type PoliteHttpClientOptions,
} from './http.js'
import { RobotsCache } from './robots.js'

const UA = 'APEX-EFN-bot/0.1 (+https://example.invalid/bot)'
const START = '2026-11-09T10:00:00.000Z'
const ORIGIN = 'https://mock.example.invalid'
const OK = z.object({ ok: z.boolean() })

class ScriptedTransport implements HttpTransport {
  readonly requests: HttpRequest[] = []

  constructor(private readonly script: Array<HttpResponse | Error>) {}

  request(req: HttpRequest): Promise<HttpResponse> {
    this.requests.push(req)
    const next = this.script.shift()
    if (next === undefined) {
      return Promise.reject(new Error('script exhausted'))
    }
    return next instanceof Error ? Promise.reject(next) : Promise.resolve(next)
  }
}

class RecordingSleep {
  readonly waits: number[] = []

  constructor(private readonly clock: FixedClock) {}

  sleep = (ms: number): Promise<void> => {
    this.waits.push(ms)
    this.clock.advance(ms)
    return Promise.resolve()
  }
}

function response(status: number, body = '', headers: Record<string, string> = {}): HttpResponse {
  return { status, headers, body }
}

function okJson(body: unknown): HttpResponse {
  return response(200, JSON.stringify(body))
}

function clientWith(
  transport: HttpTransport,
  overrides: Partial<PoliteHttpClientOptions> & { robotsText?: string | null } = {}
): { client: PoliteHttpClient; clock: FixedClock; sleeper: RecordingSleep } {
  const clock = new FixedClock(START)
  const sleeper = new RecordingSleep(clock)
  const { robotsText = '', ...rest } = overrides
  const robots =
    robotsText === null
      ? null
      : new RobotsCache(() => Promise.resolve({ status: 200, body: robotsText }), clock, 60_000)
  const client = new PoliteHttpClient({
    transport,
    robots,
    userAgent: UA,
    minIntervalMs: 0,
    maxRetries: 3,
    baseBackoffMs: 100,
    timeoutMs: 1000,
    clock,
    sleep: sleeper.sleep,
    random: () => 0.5,
    ...rest,
  })
  return { client, clock, sleeper }
}

async function failureOf(action: Promise<unknown>): Promise<WorkerError> {
  try {
    await action
  } catch (error) {
    if (error instanceof WorkerError) {
      return error
    }
    throw error
  }
  throw new Error('expected the call to fail')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('PoliteHttpClient: robots and pacing', () => {
  it('consults robots.txt first, so a disallowed URL is never requested', async () => {
    const transport = new ScriptedTransport([okJson({ ok: true })])
    const { client } = clientWith(transport, { robotsText: 'User-agent: *\nDisallow: /private' })
    const error = await failureOf(client.getJson(`${ORIGIN}/private/x`, OK))
    expect(error).toMatchObject({ code: 'robots_disallowed', status: 403 })
    expect(transport.requests).toEqual([])
    await expect(client.getJson(`${ORIGIN}/products/1`, OK)).resolves.toEqual({ ok: true })
    expect(transport.requests.map((request) => request.url)).toEqual([`${ORIGIN}/products/1`])
  })

  it('skips the robots check only when the client is given no robots cache', async () => {
    const transport = new ScriptedTransport([okJson({ ok: true })])
    const { client } = clientWith(transport, { robotsText: null })
    await expect(client.getJson(`${ORIGIN}/private/x`, OK)).resolves.toEqual({ ok: true })
  })

  it('sends the configured user agent with every request', async () => {
    const transport = new ScriptedTransport([okJson({ ok: true })])
    const { client } = clientWith(transport)
    await client.getJson(`${ORIGIN}/products/1`, OK)
    expect(transport.requests[0]?.headers?.['user-agent']).toBe(UA)
    expect(transport.requests[0]?.timeoutMs).toBe(1000)
  })

  it('spaces requests to the same origin by minIntervalMs, and not across origins', async () => {
    const transport = new ScriptedTransport([
      response(200, 'a'),
      response(200, 'b'),
      response(200, 'c'),
    ])
    const { client, sleeper } = clientWith(transport, { minIntervalMs: 1000 })
    await client.getText(`${ORIGIN}/a`)
    await client.getText('https://other.example.invalid/b')
    await client.getText(`${ORIGIN}/c`)
    expect(sleeper.waits).toEqual([1000])
  })

  it('keeps the interval for concurrent requests to the same origin', async () => {
    const transport = new ScriptedTransport([response(200, 'a'), response(200, 'b')])
    const { client, sleeper } = clientWith(transport, { minIntervalMs: 1000 })
    await Promise.all([client.getText(`${ORIGIN}/a`), client.getText(`${ORIGIN}/b`)])
    expect(sleeper.waits).toEqual([1000])
  })

  it('does not sleep when the interval has already passed', async () => {
    const transport = new ScriptedTransport([response(200, 'a'), response(200, 'b')])
    const { client, clock, sleeper } = clientWith(transport, { minIntervalMs: 1000 })
    await client.getText(`${ORIGIN}/a`)
    clock.advance(1000)
    await client.getText(`${ORIGIN}/a`)
    expect(sleeper.waits).toEqual([])
  })
})

describe('PoliteHttpClient: retries', () => {
  it('waits Retry-After seconds on 429, then succeeds', async () => {
    const transport = new ScriptedTransport([
      response(429, '', { 'retry-after': '2' }),
      okJson({ ok: true }),
    ])
    const { client, sleeper } = clientWith(transport)
    await expect(client.getJson(`${ORIGIN}/products/1`, OK)).resolves.toEqual({ ok: true })
    expect(sleeper.waits).toEqual([2000])
    expect(transport.requests).toHaveLength(2)
  })

  it('gives up after the retries with rate_limited and the Retry-After value', async () => {
    const transport = new ScriptedTransport(
      Array.from({ length: 4 }, () => response(429, '', { 'retry-after': '5' }))
    )
    const { client, sleeper } = clientWith(transport)
    const error = await failureOf(client.getJson(`${ORIGIN}/products/1`, OK))
    expect(error).toMatchObject({
      code: 'rate_limited',
      status: 429,
      retryable: true,
      retryAfterSeconds: 5,
    })
    expect(transport.requests).toHaveLength(4)
    expect(sleeper.waits).toEqual([5000, 5000, 5000])
  })

  it('falls back to exponential backoff on 429 when Retry-After is missing', async () => {
    const transport = new ScriptedTransport([response(429), okJson({ ok: true })])
    const { client, sleeper } = clientWith(transport)
    await expect(client.getJson(`${ORIGIN}/products/1`, OK)).resolves.toEqual({ ok: true })
    expect(sleeper.waits).toEqual([50])
  })

  it('returns a Retry-After longer than a minute to the caller instead of sleeping on it', async () => {
    const transport = new ScriptedTransport([response(429, '', { 'retry-after': '3600' })])
    const { client, sleeper } = clientWith(transport)
    const error = await failureOf(client.getJson(`${ORIGIN}/products/1`, OK))
    expect(error).toMatchObject({ code: 'rate_limited', retryAfterSeconds: 3600 })
    expect(transport.requests).toHaveLength(1)
    expect(sleeper.waits).toEqual([])
  })

  it('backs off exponentially with the injected jitter', async () => {
    const transport = new ScriptedTransport([
      response(503),
      response(503),
      response(503),
      okJson({ ok: true }),
    ])
    const { client, sleeper } = clientWith(transport)
    await expect(client.getJson(`${ORIGIN}/products/1`, OK)).resolves.toEqual({ ok: true })
    expect(sleeper.waits).toEqual([50, 100, 200])
  })

  it('reports an exhausted 503 as retryable upstream_error without the body', async () => {
    const transport = new ScriptedTransport(
      Array.from({ length: 4 }, () => response(503, 'internal-secret-body'))
    )
    const { client } = clientWith(transport)
    const error = await failureOf(client.getJson(`${ORIGIN}/products/1`, OK))
    expect(error).toMatchObject({ code: 'upstream_error', status: 502, retryable: true })
    expect(error.message).not.toContain('internal-secret-body')
  })

  it('retries a transient transport timeout and reports timeout when it persists', async () => {
    const timeout = new WorkerError('timeout', 504, { retryable: true })
    const transport = new ScriptedTransport([timeout, timeout, timeout, timeout])
    const { client, sleeper } = clientWith(transport)
    const error = await failureOf(client.getJson(`${ORIGIN}/products/1`, OK))
    expect(error).toMatchObject({ code: 'timeout', status: 504, retryable: true })
    expect(transport.requests).toHaveLength(4)
    expect(sleeper.waits).toEqual([50, 100, 200])
  })

  it('does not retry a transport error that is not retryable', async () => {
    const transport = new ScriptedTransport([
      new WorkerError('upstream_error', 502, { retryable: false }),
    ])
    const { client } = clientWith(transport)
    await expect(failureOf(client.getText(`${ORIGIN}/a`))).resolves.toMatchObject({
      code: 'upstream_error',
    })
    expect(transport.requests).toHaveLength(1)
  })

  it('rethrows a non-WorkerError from the transport unchanged and does not retry it', async () => {
    const boom = new Error('fixture missing for this request')
    const transport = new ScriptedTransport([boom])
    const { client } = clientWith(transport)
    await expect(client.getText(`${ORIGIN}/a`)).rejects.toBe(boom)
    expect(transport.requests).toHaveLength(1)
  })
})

describe('PoliteHttpClient: status mapping', () => {
  it('maps 404 to unknown_product by default and to the caller code when given', async () => {
    const transport = new ScriptedTransport([response(404), response(404)])
    const { client } = clientWith(transport)
    await expect(failureOf(client.getJson(`${ORIGIN}/p/1`, OK))).resolves.toMatchObject({
      code: 'unknown_product',
      status: 404,
      retryable: false,
    })
    await expect(
      failureOf(client.getJson(`${ORIGIN}/s/1`, OK, { notFound: 'unknown_seller' }))
    ).resolves.toMatchObject({ code: 'unknown_seller', status: 404 })
    expect(transport.requests).toHaveLength(2)
  })

  it.each([
    'Please complete the CAPTCHA to continue',
    'Are you a robot?',
    'Verify you are human before continuing',
  ])('maps a 403 challenge page (%j) to a retryable captcha without retrying', async (body) => {
    const transport = new ScriptedTransport([response(403, body)])
    const { client } = clientWith(transport)
    const error = await failureOf(client.getJson(`${ORIGIN}/p/1`, OK))
    expect(error).toMatchObject({ code: 'captcha', retryable: true })
    expect(error.message).not.toContain(body)
    expect(transport.requests).toHaveLength(1)
  })

  it('maps a plain 403 to session_invalid without retrying', async () => {
    const transport = new ScriptedTransport([response(403, 'Forbidden')])
    const { client } = clientWith(transport)
    await expect(failureOf(client.getJson(`${ORIGIN}/p/1`, OK))).resolves.toMatchObject({
      code: 'session_invalid',
      status: 401,
      retryable: false,
    })
    expect(transport.requests).toHaveLength(1)
  })

  it('maps other 4xx to a non-retryable upstream_error', async () => {
    const transport = new ScriptedTransport([response(400, 'bad request')])
    const { client } = clientWith(transport)
    await expect(failureOf(client.getJson(`${ORIGIN}/p/1`, OK))).resolves.toMatchObject({
      code: 'upstream_error',
      retryable: false,
    })
    expect(transport.requests).toHaveLength(1)
  })

  it('returns the body as text without parsing it', async () => {
    const transport = new ScriptedTransport([response(200, '<html>plain</html>')])
    const { client } = clientWith(transport)
    await expect(client.getText(`${ORIGIN}/page`)).resolves.toBe('<html>plain</html>')
  })
})

describe('PoliteHttpClient: parsing', () => {
  it('turns invalid JSON into dom_changed without echoing the body', async () => {
    const transport = new ScriptedTransport([response(200, '<html>internal-secret-body</html>')])
    const { client } = clientWith(transport)
    const error = await failureOf(client.getJson(`${ORIGIN}/p/1`, OK))
    expect(error).toMatchObject({ code: 'dom_changed', status: 502, retryable: false })
    expect(error.detail).not.toContain('internal-secret-body')
  })

  it('turns a schema mismatch into dom_changed that lists only the field paths', async () => {
    const transport = new ScriptedTransport([okJson({ price: '12.50', secret: 'leak-value' })])
    const { client } = clientWith(transport)
    const error = await failureOf(client.getJson(`${ORIGIN}/p/1`, z.object({ price: z.number() })))
    expect(error).toMatchObject({ code: 'dom_changed', retryable: false })
    expect(error.detail).toContain('price')
    expect(error.detail).not.toContain('leak-value')
    expect(error.detail).not.toContain('12.50')
  })

  it('keeps numbers as JavaScript numbers, even though the generated zod money schema coerces to bigint', async () => {
    const offer = await new InMemoryContractAdapter().getProduct('offer-1')
    const transport = new ScriptedTransport([okJson(offer)])
    const { client } = clientWith(transport)
    const parsed = await client.getJson<{ unit_price: { amount_minor: unknown } }>(
      `${ORIGIN}/products/offer-1`,
      zRawOffer
    )
    expect(typeof parsed.unit_price.amount_minor).toBe('number')
    expect(parsed.unit_price.amount_minor).toBe(offer.unit_price.amount_minor)
  })

  it('sends a POST body as JSON and retries it only on 429', async () => {
    const transport = new ScriptedTransport([response(503), okJson({ ok: true })])
    const { client, sleeper } = clientWith(transport)
    await expect(
      failureOf(client.postJson(`${ORIGIN}/chats`, { text: 'hi' }, OK))
    ).resolves.toMatchObject({
      code: 'upstream_error',
    })
    expect(transport.requests).toHaveLength(1)
    expect(sleeper.waits).toEqual([])
    expect(transport.requests[0]).toMatchObject({ method: 'POST', body: '{"text":"hi"}' })
    expect(transport.requests[0]?.headers?.['content-type']).toBe('application/json')
  })

  it('retries a POST after a 429 with Retry-After', async () => {
    const transport = new ScriptedTransport([
      response(429, '', { 'retry-after': '1' }),
      okJson({ ok: true }),
    ])
    const { client, sleeper } = clientWith(transport)
    await expect(client.postJson(`${ORIGIN}/chats`, { text: 'hi' }, OK)).resolves.toEqual({
      ok: true,
    })
    expect(sleeper.waits).toEqual([1000])
    expect(transport.requests).toHaveLength(2)
  })
})

describe('retryAfterSeconds', () => {
  const clock = new FixedClock(START)

  it('reads delta seconds and HTTP dates, and rejects garbage', () => {
    expect(retryAfterSeconds('2', clock)).toBe(2)
    expect(retryAfterSeconds(' 7 ', clock)).toBe(7)
    expect(retryAfterSeconds('Mon, 09 Nov 2026 10:00:30 GMT', clock)).toBe(30)
    expect(retryAfterSeconds('Mon, 09 Nov 2026 09:00:00 GMT', clock)).toBe(0)
    expect(retryAfterSeconds('soon', clock)).toBeNull()
    expect(retryAfterSeconds(undefined, clock)).toBeNull()
  })
})

describe('fetchTransport', () => {
  it('returns status, lower-cased headers and body', async () => {
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve(
        new Response('{"ok":true}', {
          status: 200,
          headers: { 'X-Test': 'yes', 'Set-Cookie': 'session=secret' },
        })
      )
    )
    vi.stubGlobal('fetch', fetchMock)
    const result = await fetchTransport.request({
      method: 'GET',
      url: `${ORIGIN}/products/1`,
      headers: { 'user-agent': UA },
      timeoutMs: 500,
    })
    expect(result.status).toBe(200)
    expect(result.body).toBe('{"ok":true}')
    expect(result.headers['x-test']).toBe('yes')
    expect(result.headers['set-cookie']).toContain('session=secret')
    const init = fetchMock.mock.calls[0]?.[1]
    expect(init?.method).toBe('GET')
    expect(init?.signal).toBeInstanceOf(AbortSignal)
  })

  it('maps a timeout to a retryable timeout error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new DOMException('timed out', 'TimeoutError')))
    )
    await expect(
      fetchTransport.request({ method: 'GET', url: `${ORIGIN}/a`, timeoutMs: 500 })
    ).rejects.toMatchObject({ code: 'timeout', status: 504, retryable: true })
  })

  it('maps a network failure to a retryable upstream_error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed')))
    )
    await expect(
      fetchTransport.request({ method: 'GET', url: `${ORIGIN}/a`, timeoutMs: 500 })
    ).rejects.toMatchObject({ code: 'upstream_error', status: 502, retryable: true })
  })
})
