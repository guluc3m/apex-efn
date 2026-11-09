import type { WorkerErrorCode } from '@apex/shared-types/contracts/browser-worker'
import type { z } from 'zod'

import type { Clock } from '../clock.js'
import { KeyedMutex } from '../concurrency.js'
import { WorkerError } from '../errors.js'

import type { RobotsCache } from './robots.js'

export interface HttpRequest {
  method: 'GET' | 'POST'
  url: string
  headers?: Record<string, string>
  body?: string
  timeoutMs: number
}

export interface HttpResponse {
  status: number
  headers: Record<string, string>
  body: string
}

export interface HttpTransport {
  request(req: HttpRequest): Promise<HttpResponse>
}

export type Sleep = (ms: number) => Promise<void>

export const systemSleep: Sleep = (ms) =>
  new Promise((resolve) => {
    setTimeout(resolve, ms)
  })

/** Longest Retry-After the client waits for inline. Longer waits are returned to the job queue, not slept on. */
const MAX_INLINE_WAIT_SECONDS = 60
const CAPTCHA_MARKER = /captcha|are you a robot|verify you are human/i
const TRANSIENT_STATUS = new Set([502, 503, 504])
const CAPTCHA_STATUS = 503

function nameOf(error: unknown): string | undefined {
  if (typeof error === 'object' && error !== null && 'name' in error) {
    return String(error.name)
  }
  return undefined
}

function transportFailure(error: unknown): WorkerError {
  if (error instanceof WorkerError) {
    return error
  }
  if (nameOf(error) === 'TimeoutError') {
    return new WorkerError('timeout', 504, { retryable: true })
  }
  return new WorkerError('upstream_error', 502, { retryable: true })
}

/** Production transport: global `fetch` with a per-request timeout. No cookies are kept between calls. */
export const fetchTransport: HttpTransport = {
  async request(req) {
    try {
      const response = await fetch(req.url, {
        method: req.method,
        headers: req.headers,
        body: req.body,
        signal: AbortSignal.timeout(req.timeoutMs),
      })
      const headers: Record<string, string> = {}
      response.headers.forEach((value, name) => {
        headers[name.toLowerCase()] = value
      })
      return { status: response.status, headers, body: await response.text() }
    } catch (error) {
      throw transportFailure(error)
    }
  },
}

export interface PoliteHttpClientOptions {
  transport: HttpTransport
  /** Null only for JSON APIs whose compliance doc states that robots.txt does not apply. */
  robots: RobotsCache | null
  userAgent: string
  minIntervalMs: number
  maxRetries: number
  baseBackoffMs: number
  timeoutMs: number
  clock: Clock
  sleep: Sleep
  /** Injected so jitter is deterministic in tests. Production passes `Math.random`. */
  random: () => number
}

export interface RequestOptions {
  /** Code for a 404 answer. Defaults to `unknown_product`; seller calls pass `unknown_seller`. */
  notFound?: WorkerErrorCode
}

type Outcome =
  | { ok: true; response: HttpResponse }
  | { ok: false; error: WorkerError; transient: boolean; waitMs: number | null }

export function retryAfterSeconds(value: string | undefined, clock: Clock): number | null {
  if (value === undefined) {
    return null
  }
  const trimmed = value.trim()
  if (/^\d+$/.test(trimmed)) {
    return Number(trimmed)
  }
  const at = Date.parse(trimmed)
  if (Number.isNaN(at)) {
    return null
  }
  return Math.max(0, Math.ceil((at - clock.now().getTime()) / 1000))
}

function parseJsonBody<T>(body: string, schema: z.ZodTypeAny): T {
  let json: unknown
  try {
    json = JSON.parse(body)
  } catch {
    throw new WorkerError('dom_changed', 502, { retryable: false, detail: 'response is not JSON' })
  }
  const result = schema.safeParse(json)
  if (!result.success) {
    const paths = result.error.issues
      .slice(0, 5)
      .map((issue) => issue.path.join('.') || '(root)')
      .join(', ')
    throw new WorkerError('dom_changed', 502, {
      retryable: false,
      detail: `response does not match the expected shape at: ${paths}`,
    })
  }
  // The zod output is not returned: the generated zMoney coerces amount_minor to bigint. Callers get the validated
  // JSON with JavaScript numbers, which the generated TypeScript types describe.
  return json as T
}

/**
 * Reads platforms politely: robots.txt before every request, per-origin spacing, retries with exponential backoff
 * and full jitter, and a closed mapping from HTTP answers to WorkerError codes. Response bodies never appear in
 * errors.
 */
export class PoliteHttpClient {
  private readonly pacing = new KeyedMutex()
  private readonly lastStartMs = new Map<string, number>()

  constructor(private readonly options: PoliteHttpClientOptions) {}

  async getJson<T>(url: string, schema: z.ZodTypeAny, options: RequestOptions = {}): Promise<T> {
    const response = await this.send({
      method: 'GET',
      url,
      headers: { accept: 'application/json' },
      notFound: options.notFound,
    })
    return parseJsonBody<T>(response.body, schema)
  }

  async getText(url: string, options: RequestOptions = {}): Promise<string> {
    const response = await this.send({ method: 'GET', url, notFound: options.notFound })
    return response.body
  }

  async postJson<T>(
    url: string,
    payload: object,
    schema: z.ZodTypeAny,
    options: RequestOptions = {}
  ): Promise<T> {
    const response = await this.send({
      method: 'POST',
      url,
      headers: { accept: 'application/json', 'content-type': 'application/json' },
      body: JSON.stringify(payload),
      notFound: options.notFound,
    })
    return parseJsonBody<T>(response.body, schema)
  }

  private async send(req: {
    method: 'GET' | 'POST'
    url: string
    headers?: Record<string, string>
    body?: string
    notFound?: WorkerErrorCode
  }): Promise<HttpResponse> {
    for (let retry = 0; ; retry += 1) {
      const outcome = await this.attempt(req)
      if (outcome.ok) {
        return outcome.response
      }
      // POST is retried only on 429, which the platform rejects before it applies the write. Retrying a timeout
      // or 5xx could send a chat message twice.
      const retryable =
        outcome.transient &&
        (req.method === 'GET' || outcome.error.code === 'rate_limited') &&
        retry < this.options.maxRetries
      if (!retryable) {
        throw outcome.error
      }
      await this.options.sleep(outcome.waitMs ?? this.backoffMs(retry))
    }
  }

  private async attempt(req: {
    method: 'GET' | 'POST'
    url: string
    headers?: Record<string, string>
    body?: string
    notFound?: WorkerErrorCode
  }): Promise<Outcome> {
    if (this.options.robots !== null) {
      await this.options.robots.assertAllowed(req.url, this.options.userAgent)
    }
    await this.pace(new URL(req.url).origin)
    let response: HttpResponse
    try {
      response = await this.options.transport.request({
        method: req.method,
        url: req.url,
        headers: { 'user-agent': this.options.userAgent, ...req.headers },
        body: req.body,
        timeoutMs: this.options.timeoutMs,
      })
    } catch (error) {
      // Only WorkerErrors come from a transport. Anything else is a bug or a test double, and is rethrown as-is so
      // its message is not hidden behind a retry.
      if (!(error instanceof WorkerError)) {
        throw error
      }
      return { ok: false, error, transient: error.retryable, waitMs: null }
    }
    if (response.status >= 200 && response.status < 300) {
      return { ok: true, response }
    }
    return this.failureFor(response, req.notFound)
  }

  private failureFor(response: HttpResponse, notFound: WorkerErrorCode | undefined): Outcome {
    const { status } = response
    if (status === 429) {
      const seconds = retryAfterSeconds(response.headers['retry-after'], this.options.clock)
      const inline = seconds === null || seconds <= MAX_INLINE_WAIT_SECONDS
      return {
        ok: false,
        transient: inline,
        waitMs: seconds === null ? null : seconds * 1000,
        error: new WorkerError('rate_limited', 429, {
          retryable: true,
          retryAfterSeconds: seconds,
        }),
      }
    }
    if (status === 401 || status === 403) {
      if (CAPTCHA_MARKER.test(response.body)) {
        return this.final(new WorkerError('captcha', CAPTCHA_STATUS, { retryable: true }))
      }
      return this.final(new WorkerError('session_invalid', 401, { retryable: false }))
    }
    if (status === 404) {
      return this.final(new WorkerError(notFound ?? 'unknown_product', 404, { retryable: false }))
    }
    if (status >= 500) {
      return {
        ok: false,
        transient: TRANSIENT_STATUS.has(status),
        waitMs: null,
        error: new WorkerError('upstream_error', 502, { retryable: true }),
      }
    }
    return this.final(new WorkerError('upstream_error', 502, { retryable: false }))
  }

  private final(error: WorkerError): Outcome {
    return { ok: false, transient: false, waitMs: null, error }
  }

  private backoffMs(retry: number): number {
    return Math.floor(this.options.random() * this.options.baseBackoffMs * 2 ** retry)
  }

  /** Waits until `minIntervalMs` has passed since the previous request started to the same origin. */
  private async pace(origin: string): Promise<void> {
    await this.pacing.run(origin, async () => {
      const { clock, sleep, minIntervalMs } = this.options
      const last = this.lastStartMs.get(origin)
      if (last !== undefined) {
        const wait = last + minIntervalMs - clock.now().getTime()
        if (wait > 0) {
          await sleep(wait)
        }
      }
      this.lastStartMs.set(origin, clock.now().getTime())
    })
  }
}
