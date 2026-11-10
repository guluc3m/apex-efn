/**
 * `mock-b`: the mock marketplace rendered as HTML (ADR-500, ADR-505, docs/compliance/mock-marketplace.md).
 *
 * Transport is `http`: the pages are fetched with the polite client (robots.txt, spacing, retries, backoff) and
 * parsed, which is the same shape a crawler service gives a real platform. A browser is not needed for this mock;
 * the Camoufox path is for real platforms (D5-11) and for anything that only exists in a rendered DOM.
 *
 * Parsing lives in `./mapping.ts`, selectors in `./html.ts`, and this file only walks the flows.
 */

import type {
  RawOffer,
  RawSeller,
  RawSellerSignals,
  SkipReason,
  SkippedListing,
} from '@apex/shared-types/contracts/browser-worker'

import type { Clock } from '../../clock.js'
import { WorkerError } from '../../errors.js'
import type { ScrapingMetrics } from '../../metrics.js'
import {
  PoliteHttpClient,
  type HttpTransport,
  type RequestOptions,
  type Sleep,
} from '../http.js'
import type {
  ChatAdapter,
  ChatMessageRecord,
  ChatOpenInput,
  PlatformAdapter,
  SearchInput,
  SearchOutput,
} from '../index.js'
import { RobotsCache } from '../robots.js'

import {
  PLATFORM,
  chatFromPage,
  isoDay,
  offerFromItemPage,
  searchResults,
  sellerFromShopPage,
  signalsFromShopPage,
  type PageContext,
} from './mapping.js'

export const MOCK_B_PLATFORM = PLATFORM

const ROBOTS_TTL_MS = 15 * 60 * 1000
const DEFAULT_BASE_BACKOFF_MS = 1000

/** What the adapter itself needs: an origin and a polite client. Tests build this directly. */
export interface MockBHttpOptions {
  /** Origin only, for example `http://127.0.0.1:8002`. Paths carry the `/mock-b` prefix. */
  baseUrl: string
  http: PoliteHttpClient
  clock: Clock
}

/** What production passes: the same shape as the other adapters, so the registry wires them the same way. */
export interface MockBAdapterOptions {
  baseUrl: string
  transport: HttpTransport
  clock: Clock
  sleep: Sleep
  /** Production passes `Math.random`. Tests pass a fixed value so the jitter is deterministic. */
  random: () => number
  userAgent: string
  minIntervalMs: number
  maxRetries: number
  timeoutMs: number
  baseBackoffMs?: number
  metrics?: ScrapingMetrics
}

function pageUrl(baseUrl: string, path: string, query: Record<string, string> = {}): string {
  const url = new URL(`/mock-b${path}`, baseUrl)
  for (const [name, value] of Object.entries(query)) {
    url.searchParams.set(name, value)
  }
  return url.toString()
}

function contextOf(options: MockBHttpOptions): PageContext {
  return { baseUrl: options.baseUrl, capturedAt: options.clock.now() }
}

function errorOptions(notFound: RequestOptions['notFound']): RequestOptions {
  return { notFound }
}

class MockBChat implements ChatAdapter {
  constructor(private readonly options: MockBHttpOptions) {}

  async open(input: ChatOpenInput): Promise<{ platformChatId: string }> {
    // The mock has no login, so the opaque account_id stays in the worker and is not sent.
    const html = await this.options.http.postFormText(
      pageUrl(this.options.baseUrl, '/chat'),
      { seller: input.platformSellerId, item: input.productId },
      errorOptions('unknown_seller')
    )
    return { platformChatId: chatFromPage(html).platformChatId }
  }

  async send(platformChatId: string, text: string): Promise<{ platformSeq: number; at: Date }> {
    const html = await this.options.http.postFormText(
      pageUrl(this.options.baseUrl, `/chat/${encodeURIComponent(platformChatId)}/send`),
      { text },
      errorOptions('unknown_chat')
    )
    const sent = chatFromPage(html)
      .messages.filter((message) => message.role === 'buyer')
      .at(-1)
    if (sent === undefined) {
      throw new WorkerError('dom_changed', 502, {
        detail: 'mock-b chat page does not show the message that was just sent',
      })
    }
    return { platformSeq: sent.seq, at: sent.at }
  }

  async read(platformChatId: string, afterSeq: number): Promise<ChatMessageRecord[]> {
    const html = await this.options.http.getText(
      pageUrl(this.options.baseUrl, `/chat/${encodeURIComponent(platformChatId)}`),
      errorOptions('unknown_chat')
    )
    return chatFromPage(html)
      .messages.filter((message) => message.seq > afterSeq)
      .map((message) => ({
        seq: message.seq,
        role: message.role,
        text: message.text,
        at: message.at,
      }))
  }

  screenshot(): Promise<Uint8Array> {
    return Promise.reject(
      new WorkerError('upstream_error', 502, {
        retryable: false,
        detail: 'mock-b has no rendered chat without a browser',
      })
    )
  }
}

class MockBAdapter implements PlatformAdapter {
  readonly platform = PLATFORM
  readonly transport = 'http' as const
  readonly chat: ChatAdapter

  constructor(private readonly options: MockBHttpOptions) {
    this.chat = new MockBChat(options)
  }

  async search(input: SearchInput): Promise<SearchOutput> {
    const html = await this.options.http.getText(
      pageUrl(this.options.baseUrl, '/search', { q: input.query })
    )
    const parsed = searchResults(html, contextOf(this.options))
    const selected = parsed.offers.slice(0, input.maxResults)
    return {
      offers: selected,
      skipped: parsed.skipped,
      truncated: parsed.offers.length > selected.length,
    }
  }

  async getProduct(platformOfferId: string): Promise<RawOffer> {
    const html = await this.options.http.getText(
      pageUrl(this.options.baseUrl, `/item/${encodeURIComponent(platformOfferId)}`),
      errorOptions('unknown_product')
    )
    return offerFromItemPage(html, contextOf(this.options))
  }

  async getSeller(platformSellerId: string): Promise<RawSeller> {
    const html = await this.options.http.getText(
      pageUrl(this.options.baseUrl, `/shop/${encodeURIComponent(platformSellerId)}`),
      errorOptions('unknown_seller')
    )
    return sellerFromShopPage(html, contextOf(this.options))
  }

  async getSellerSignals(
    platformSellerId: string,
    options: { maxReviews: number }
  ): Promise<RawSellerSignals> {
    const html = await this.options.http.getText(
      pageUrl(this.options.baseUrl, `/shop/${encodeURIComponent(platformSellerId)}`),
      errorOptions('unknown_seller')
    )
    return signalsFromShopPage(html, contextOf(this.options), {
      maxReviews: options.maxReviews,
      now: this.options.clock.now(),
    })
  }
}

/** Builds the adapter with a polite client: robots.txt, spacing, retries and the closed error mapping. */
export function createMockBAdapter(options: MockBAdapterOptions): PlatformAdapter {
  const { transport, clock } = options
  const robots = new RobotsCache(
    async (url) => {
      const response = await transport.request({ method: 'GET', url, timeoutMs: options.timeoutMs })
      return { status: response.status, body: response.body }
    },
    clock,
    ROBOTS_TTL_MS
  )
  const http = new PoliteHttpClient({
    transport,
    robots,
    userAgent: options.userAgent,
    minIntervalMs: options.minIntervalMs,
    maxRetries: options.maxRetries,
    baseBackoffMs: options.baseBackoffMs ?? DEFAULT_BASE_BACKOFF_MS,
    timeoutMs: options.timeoutMs,
    clock,
    sleep: options.sleep,
    random: options.random,
    ...(options.metrics === undefined ? {} : { metrics: options.metrics }),
    metricsPlatform: PLATFORM,
    metricsTransport: 'http',
  })
  return new MockBAdapter({ baseUrl: options.baseUrl, http, clock })
}

/** Re-exported for tests: the platform's date format is part of the mapping contract. */
export { isoDay }

/** Skip reasons the page can produce, for callers that summarise a search. */
export type MockBSkipReason = SkipReason | 'parse_error'
export type MockBSkipped = SkippedListing
