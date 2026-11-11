/**
 * `mock-c`: an API-first B2B marketplace (ADR-507).
 *
 * This is the shape we would consume from a platform that *invites* API access — search, item, supplier and
 * metrics endpoints plus a threads/messages resource for the negotiation — so the adapter and its tests are the
 * ones we keep when a real platform says yes. No browser, no login, no forms.
 */

import type {
  RawOffer,
  RawSeller,
  RawSellerSignals,
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
  classifyMockCError,
  messageOf,
  offerFromItem,
  offerFromSummary,
  sellerFrom,
  signalsFrom,
  type OfferContext,
} from './mapping.js'
import {
  ItemSchema,
  MessagesSchema,
  MetricsSchema,
  SearchSchema,
  SendResultSchema,
  SupplierSchema,
  ThreadOpenedSchema,
  type Item,
  type MessagesPage,
  type Metrics,
  type SearchPage,
  type SendResult,
  type Supplier,
  type ThreadOpened,
} from './schemas.js'

export const MOCK_C_PLATFORM = PLATFORM
const API_PREFIX = '/mock-c/api'
const ROBOTS_TTL_MS = 15 * 60 * 1000
const DEFAULT_BASE_BACKOFF_MS = 1000

function apiUrl(baseUrl: string, path: string, query: Record<string, string> = {}): string {
  const url = new URL(`${API_PREFIX}${path}`, baseUrl)
  for (const [name, value] of Object.entries(query)) {
    url.searchParams.set(name, value)
  }
  return url.toString()
}

function errorOptions(notFound: RequestOptions['notFound']): RequestOptions {
  return { notFound, classify: classifyMockCError }
}

class MockCChat implements ChatAdapter {
  private readonly threads = new Map<string, string>()

  constructor(private readonly options: MockCClientOptions) {}

  async open(input: ChatOpenInput): Promise<{ platformChatId: string }> {
    const body = await this.options.http.postJson<ThreadOpened>(
      apiUrl(this.options.baseUrl, '/threads'),
      { item_id: input.productId },
      ThreadOpenedSchema,
      errorOptions('unknown_product')
    )
    if (body.supplier_id !== input.platformSellerId) {
      throw new WorkerError('unknown_seller', 404, {
        detail: 'the item is not sold by that supplier',
      })
    }
    this.threads.set(body.thread_id, body.thread_id)
    return { platformChatId: body.thread_id }
  }

  async send(platformChatId: string, text: string): Promise<{ platformSeq: number; at: Date }> {
    const body = await this.options.http.postJson<SendResult>(
      apiUrl(this.options.baseUrl, `/threads/${encodeURIComponent(platformChatId)}/messages`),
      { body: text },
      SendResultSchema,
      errorOptions('unknown_chat')
    )
    if (body.sent === null) {
      throw new WorkerError('upstream_error', 502, {
        detail: 'the platform accepted the message but returned no sequence',
      })
    }
    return { platformSeq: body.sent.seq, at: new Date(body.sent.sent_at) }
  }

  async read(platformChatId: string, afterSeq: number): Promise<ChatMessageRecord[]> {
    const body = await this.options.http.getJson<MessagesPage>(
      apiUrl(this.options.baseUrl, `/threads/${encodeURIComponent(platformChatId)}/messages`, {
        after_seq: String(afterSeq),
      }),
      MessagesSchema,
      errorOptions('unknown_chat')
    )
    return body.messages
      .filter((message) => message.seq > afterSeq)
      .map((message) => messageOf(message))
  }

  screenshot(): Promise<Uint8Array> {
    return Promise.reject(
      new WorkerError('upstream_error', 502, {
        retryable: false,
        detail: 'mock-c has no rendered chat; it is an API-only platform',
      })
    )
  }
}

/** What the adapter itself needs. Tests build this directly. */
export interface MockCClientOptions {
  baseUrl: string
  http: PoliteHttpClient
  clock: Clock
}

/** What production passes: the same shape as the other adapters. */
export interface MockCAdapterOptions {
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

class MockCAdapter implements PlatformAdapter {
  readonly platform = PLATFORM
  readonly transport = 'http' as const
  readonly chat: ChatAdapter

  constructor(private readonly options: MockCClientOptions) {
    this.chat = new MockCChat(options)
  }

  private context(): OfferContext {
    return { baseUrl: this.options.baseUrl, capturedAt: this.options.clock.now() }
  }

  async search(input: SearchInput): Promise<SearchOutput> {
    const page = await this.options.http.getJson<SearchPage>(
      apiUrl(this.options.baseUrl, '/search', { q: input.query, limit: '50' }),
      SearchSchema
    )
    const offers: RawOffer[] = []
    const skipped: SkippedListing[] = []
    for (const summary of page.items) {
      const mapped = offerFromSummary(summary, this.context())
      if ('skip' in mapped) {
        skipped.push(mapped.skip)
      } else {
        offers.push(mapped.offer)
      }
    }
    const selected = offers.slice(0, input.maxResults)
    return { offers: selected, skipped, truncated: offers.length > selected.length }
  }

  async getProduct(platformOfferId: string): Promise<RawOffer> {
    const item = await this.options.http.getJson<Item>(
      apiUrl(this.options.baseUrl, `/items/${encodeURIComponent(platformOfferId)}`),
      ItemSchema,
      errorOptions('unknown_product')
    )
    return offerFromItem(item, this.context())
  }

  async getSeller(platformSellerId: string): Promise<RawSeller> {
    const supplier = await this.options.http.getJson<Supplier>(
      apiUrl(this.options.baseUrl, `/suppliers/${encodeURIComponent(platformSellerId)}`),
      SupplierSchema,
      errorOptions('unknown_seller')
    )
    return sellerFrom(supplier, this.context())
  }

  async getSellerSignals(
    platformSellerId: string,
    options: { maxReviews: number }
  ): Promise<RawSellerSignals> {
    const metrics = await this.options.http.getJson<Metrics>(
      apiUrl(this.options.baseUrl, `/suppliers/${encodeURIComponent(platformSellerId)}/metrics`),
      MetricsSchema,
      errorOptions('unknown_seller')
    )
    return signalsFrom(metrics, this.context(), {
      maxReviews: options.maxReviews,
      now: this.options.clock.now(),
    })
  }
}

/** Builds the adapter with a polite client: robots.txt, spacing, retries and the closed error mapping. */
export function createMockCAdapter(options: MockCAdapterOptions): PlatformAdapter {
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
  return new MockCAdapter({ baseUrl: options.baseUrl, http, clock })
}
