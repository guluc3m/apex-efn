/**
 * `mock-a`: the mock marketplace JSON API (ADR-500, docs/compliance/mock-marketplace.md). Transport `http`, so no
 * browser is used. Mapping lives in ./mapping.ts, response shapes in ./schemas.ts.
 */
import type {
  RawOffer,
  RawSeller,
  RawSellerSignals,
  SkippedListing,
} from '@apex/shared-types/contracts/browser-worker'
import type { z } from 'zod'

import type { Clock } from '../../clock.js'
import { WorkerError } from '../../errors.js'
import type { ScrapingMetrics } from '../../metrics.js'
import { PoliteHttpClient, type HttpTransport, type RequestOptions, type Sleep } from '../http.js'
import {
  type ChatAdapter,
  type ChatMessageRecord,
  type ChatOpenInput,
  type PlatformAdapter,
  type SearchInput,
  type SearchOutput,
} from '../index.js'
import { RobotsCache } from '../robots.js'

import {
  ListingPriceError,
  chatRecordFrom,
  classifyMockError,
  listingPriceProblem,
  offerFrom,
  sellerFrom,
  signalsFrom,
  skippedFrom,
  workerErrorFor,
  type OfferContext,
} from './mapping.js'
import {
  ConversationSchema,
  MessagesSchema,
  MetricsSchema,
  ProductSchema,
  ReviewsSchema,
  SearchPageSchema,
  SellerSchema,
  SentMessageSchema,
  type MockMessages,
  type MockMetrics,
  type MockProduct,
  type MockReviews,
  type MockSearchPage,
  type MockSeller,
} from './schemas.js'

export const MOCK_A_PLATFORM = 'mock-a'
const API_PREFIX = '/mock-a/api'
const ROBOTS_TTL_MS = 15 * 60 * 1000
const DEFAULT_BASE_BACKOFF_MS = 1000

export interface MockAHttpOptions {
  /** Origin only, for example `http://127.0.0.1:8002`. Paths carry the `/mock-a/api` prefix. */
  baseUrl: string
  http: PoliteHttpClient
  clock: Clock
}

type NotFoundCode = 'unknown_product' | 'unknown_seller' | 'unknown_chat'

function apiUrl(baseUrl: string, path: string, query: Record<string, string> = {}): string {
  const url = new URL(`${API_PREFIX}${path}`, baseUrl)
  for (const [name, value] of Object.entries(query)) {
    url.searchParams.set(name, value)
  }
  return url.toString()
}

/** The mock answers 404 with a body code, which the classifier maps. `notFound` covers bodies it does not know. */
function errorOptions(notFound: NotFoundCode): RequestOptions {
  return { notFound, classify: classifyMockError }
}

function conversationPath(platformChatId: string): string {
  return `/conversations/${encodeURIComponent(platformChatId)}/messages`
}

class MockAChat implements ChatAdapter {
  constructor(private readonly options: MockAHttpOptions) {}

  async open(input: ChatOpenInput): Promise<{ platformChatId: string }> {
    // The mock has no login, so the opaque account_id stays in the worker and is not sent.
    const body = await this.options.http.postJson<{ conversation_id: string }>(
      apiUrl(this.options.baseUrl, '/conversations'),
      { vendor_id: input.platformSellerId, listing_id: input.productId },
      ConversationSchema,
      errorOptions('unknown_seller')
    )
    return { platformChatId: body.conversation_id }
  }

  async send(platformChatId: string, text: string): Promise<{ platformSeq: number; at: Date }> {
    const body = await this.options.http.postJson<{
      message: { id: number; sent_at: number }
    }>(
      apiUrl(this.options.baseUrl, conversationPath(platformChatId)),
      { body: text },
      SentMessageSchema,
      errorOptions('unknown_chat')
    )
    return {
      platformSeq: body.message.id,
      at: new Date(body.message.sent_at * 1000),
    }
  }

  async read(platformChatId: string, afterSeq: number): Promise<ChatMessageRecord[]> {
    const body = await this.options.http.getJson<MockMessages>(
      apiUrl(this.options.baseUrl, conversationPath(platformChatId), { after: String(afterSeq) }),
      MessagesSchema,
      errorOptions('unknown_chat')
    )
    return body.messages.map(chatRecordFrom)
  }

  screenshot(_platformChatId: string): Promise<Uint8Array> {
    return Promise.reject(
      new WorkerError('upstream_error', 502, {
        retryable: false,
        detail: 'mock-a has no rendered chat',
      })
    )
  }
}

export class MockAAdapter implements PlatformAdapter {
  readonly platform = MOCK_A_PLATFORM
  readonly transport = 'http' as const
  readonly chat: ChatAdapter

  constructor(private readonly options: MockAHttpOptions) {
    this.chat = new MockAChat(options)
  }

  async search(input: SearchInput): Promise<SearchOutput> {
    const offers: RawOffer[] = []
    const skipped: SkippedListing[] = []
    const context = this.offerContext(input.quantity)
    let consumed = 0
    let total = 0
    for (let page = 1; ; page += 1) {
      const body = await this.options.http.getJson<MockSearchPage>(
        apiUrl(this.options.baseUrl, '/search', { q: input.query, page: String(page) }),
        SearchPageSchema
      )
      total = body.total
      for (const listing of body.results) {
        if (offers.length >= input.maxResults) {
          break
        }
        consumed += 1
        // A listing whose price cannot be used is skipped before its product page is requested.
        const problem = listingPriceProblem(listing.price)
        if (problem !== null) {
          skipped.push(skippedFrom(listing.listing_id, problem))
          continue
        }
        const detail = await this.fetchProduct(listing.listing_id)
        try {
          offers.push(offerFrom(detail, context))
        } catch (error) {
          if (!(error instanceof ListingPriceError)) {
            throw error
          }
          skipped.push(skippedFrom(listing.listing_id, error))
        }
      }
      if (offers.length >= input.maxResults || body.results.length === 0 || consumed >= total) {
        break
      }
    }
    return {
      offers,
      skipped,
      truncated: offers.length >= input.maxResults && consumed < total,
    }
  }

  async getProduct(platformOfferId: string): Promise<RawOffer> {
    const detail = await this.fetchProduct(platformOfferId)
    try {
      return offerFrom(detail, this.offerContext(null))
    } catch (error) {
      if (error instanceof ListingPriceError) {
        throw workerErrorFor(error)
      }
      throw error
    }
  }

  async getSeller(platformSellerId: string): Promise<RawSeller> {
    const seller = await this.getSellerJson<MockSeller>(platformSellerId, '', SellerSchema)
    return sellerFrom(seller, this.platform, this.options.clock)
  }

  async getSellerSignals(
    platformSellerId: string,
    options: { maxReviews: number }
  ): Promise<RawSellerSignals> {
    const metrics = await this.getSellerJson<MockMetrics>(
      platformSellerId,
      '/metrics',
      MetricsSchema
    )
    const reviews = await this.getSellerJson<MockReviews>(
      platformSellerId,
      '/reviews',
      ReviewsSchema
    )
    try {
      return signalsFrom(metrics, reviews, {
        platform: this.platform,
        sellerId: platformSellerId,
        clock: this.options.clock,
        maxReviews: options.maxReviews,
      })
    } catch (error) {
      if (error instanceof ListingPriceError) {
        throw workerErrorFor(error)
      }
      throw error
    }
  }

  private offerContext(quantity: number | null): OfferContext {
    return {
      platform: this.platform,
      baseUrl: this.options.baseUrl,
      clock: this.options.clock,
      quantity,
    }
  }

  private fetchProduct(platformOfferId: string): Promise<MockProduct> {
    return this.options.http.getJson<MockProduct>(
      apiUrl(this.options.baseUrl, `/products/${encodeURIComponent(platformOfferId)}`),
      ProductSchema,
      errorOptions('unknown_product')
    )
  }

  private getSellerJson<T>(
    platformSellerId: string,
    suffix: string,
    schema: z.ZodTypeAny
  ): Promise<T> {
    return this.options.http.getJson<T>(
      apiUrl(this.options.baseUrl, `/sellers/${encodeURIComponent(platformSellerId)}${suffix}`),
      schema,
      errorOptions('unknown_seller')
    )
  }
}

export interface MockAAdapterOptions {
  baseUrl: string
  /** The raw transport, `fetchTransport` in production. robots.txt is fetched through it, never through the polite client. */
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

/** Builds the adapter with a polite client: robots.txt, spacing, retries and the closed error mapping. */
export function createMockAAdapter(options: MockAAdapterOptions): MockAAdapter {
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
    metrics: options.metrics,
    metricsPlatform: MOCK_A_PLATFORM,
    metricsTransport: 'http',
  })
  return new MockAAdapter({ baseUrl: options.baseUrl, http, clock })
}
