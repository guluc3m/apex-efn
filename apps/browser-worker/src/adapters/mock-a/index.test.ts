/**
 * mock-a against the mock marketplace. Modes (ADAPTER_FIXTURES):
 * - replay (default): the committed fixtures in fixtures/mock-a. No process, no network.
 * - record: starts the mock, runs everything and rewrites the fixtures. Run it when the mock or the mapping changes.
 * - live: starts the mock and runs everything without writing fixtures.
 */
import { rm } from 'node:fs/promises'

import type { RawOffer, RawSellerSignals } from '@apex/shared-types/contracts/browser-worker'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { processJob } from '../../jobs/processor.js'
import { StaticFlags } from '../../platform/flags.js'
import { FixedClock } from '../../testing/fakes.js'
import {
  MOCK_A_FIXTURE_DIR,
  MOCK_A_LOGICAL_ORIGIN,
  rewriteOrigin,
  startMockMarketplace,
  type RunningMockMarketplace,
} from '../../testing/mock-marketplace.js'
import {
  assertValidOffer,
  assertValidSearchResult,
  assertValidSignals,
  assertWorkerError,
  describeAdapterContract,
  type AdapterContractSubject,
} from '../contract-suite.js'
import { fixtureModeFromEnv, ReplayTransport, transportForMode } from '../fixtures.js'
import { fetchTransport, type HttpRequest, type HttpResponse, type HttpTransport } from '../http.js'
import { AdapterRegistry } from '../index.js'

import { createMockAAdapter, type MockAAdapter } from './index.js'

const MODE = fixtureModeFromEnv()
const UA = 'APEX-EFN-bot/0.1 (+https://example.invalid/bot)'
const NOW = '2026-11-09T10:00:00.000Z'
const LIFECYCLE_TIMEOUT_MS = 60_000
const CHAT_MESSAGE = 'Hello, what volume tiers do you offer for 5000 units?'

interface Connection {
  transport: HttpTransport
  close(): Promise<void>
}

function buildAdapter(transport: HttpTransport): MockAAdapter {
  return createMockAAdapter({
    baseUrl: MOCK_A_LOGICAL_ORIGIN,
    transport,
    clock: new FixedClock(NOW),
    sleep: () => Promise.resolve(),
    random: () => 0.5,
    userAgent: UA,
    minIntervalMs: 0,
    maxRetries: 0,
    timeoutMs: 15_000,
  })
}

function subjectFor(adapter: MockAAdapter): AdapterContractSubject {
  return {
    adapter,
    search: { query: 'gloves', quantity: 5000 },
    knownOfferId: 'a-gloves-01',
    knownSellerId: 'a-solid-veteran',
    missingOfferId: 'does-not-exist',
    missingSellerId: 'does-not-exist',
    chat: {
      platformSellerId: 'a-solid-veteran',
      productId: 'a-gloves-01',
      accountId: 'acct-test',
      message: CHAT_MESSAGE,
    },
  }
}

function offerById(offers: RawOffer[], id: string): RawOffer {
  const offer = offers.find((candidate) => candidate.platform_offer_id === id)
  if (offer === undefined) {
    throw new Error(`offer ${id} is missing from the result`)
  }
  return offer
}

function registerScenarios(current: () => Connection & { adapter: MockAAdapter }): void {
  const adapter = (): MockAAdapter => current().adapter

  describe('search mapping', () => {
    it('skips the GBP listing with its currency as shown, and keeps the other seven', async () => {
      const result = await adapter().search({ query: 'gloves', quantity: 5000, maxResults: 200 })
      assertValidSearchResult(result, 'mock-a', 200)
      expect(result.skipped).toEqual([
        { platform_offer_id: 'a-gloves-07', reason: 'unsupported_currency', currency_raw: 'GBP' },
      ])
      expect(result.offers.map((offer) => offer.platform_offer_id)).toEqual([
        'a-gloves-01',
        'a-gloves-02',
        'a-gloves-03',
        'a-gloves-04',
        'a-gloves-05',
        'a-gloves-06',
        'a-gloves-08',
      ])
      expect(result.truncated).toBe(false)
    })

    it('reads the tier that covers the requested quantity, and keeps every tier sorted', async () => {
      const { offers } = await adapter().search({
        query: 'gloves',
        quantity: 5000,
        maxResults: 200,
      })
      const first = offerById(offers, 'a-gloves-01')
      expect(first.unit_price).toEqual({ amount_minor: 415, currency: 'EUR' })
      expect(first.price_tiers).toEqual([
        {
          min_quantity: 500,
          max_quantity: 1999,
          unit_price: { amount_minor: 445, currency: 'EUR' },
        },
        {
          min_quantity: 2000,
          max_quantity: null,
          unit_price: { amount_minor: 415, currency: 'EUR' },
        },
      ])
      expect(offerById(offers, 'a-gloves-04').unit_price).toEqual({
        amount_minor: 45,
        currency: 'EUR',
      })
      expect(offerById(offers, 'a-gloves-02').unit_price).toEqual({
        amount_minor: 459,
        currency: 'USD',
      })
    })

    it('keeps CNY as CNY, with the tiers in CNY', async () => {
      const { offers } = await adapter().search({ query: 'kraft', quantity: null, maxResults: 10 })
      const kraft = offerById(offers, 'a-kraft-02')
      expect(kraft.unit_price).toEqual({ amount_minor: 290, currency: 'CNY' })
      expect(kraft.price_tiers.map((tier) => tier.unit_price)).toEqual([
        { amount_minor: 290, currency: 'CNY' },
        { amount_minor: 265, currency: 'CNY' },
      ])
      expect(kraft.shipping).toBeNull()
      expect(kraft.incoterm).toBe('FOB')
    })

    it('maps the product fields: specs, certificates, shipping, incoterm and lead time', async () => {
      const { offers } = await adapter().search({
        query: 'gloves',
        quantity: null,
        maxResults: 200,
      })
      const offer = offerById(offers, 'a-gloves-01')
      assertValidOffer(offer, 'mock-a')
      expect(offer).toMatchObject({
        platform: 'mock-a',
        platform_offer_id: 'a-gloves-01',
        product_id: 'a-gloves-01',
        platform_seller_id: 'a-solid-veteran',
        product_url: `${MOCK_A_LOGICAL_ORIGIN}/mock-a/api/products/a-gloves-01`,
        unit_price: { amount_minor: 445, currency: 'EUR' },
        list_price: null,
        moq: 500,
        quantity_available: null,
        seller_country: null,
        certifications: ['EN 455', 'CE'],
        incoterm: 'DAP',
        lead_time_days: 10,
        shipping: {
          cost: { amount_minor: 1200, currency: 'EUR' },
          min_days: 5,
          max_days: 10,
          carrier: null,
        },
      })
      expect(offer.specifications).toEqual({
        material: 'nitrile',
        size: 'M',
        thickness: '4 mil',
        powder: 'powder-free',
        pieces_per_box: '100',
      })
      expect(offer.seller_name).toEqual(expect.any(String))
    })

    it('maps missing shipping, incoterm and lead time to null, and empty certificates to []', async () => {
      const { offers } = await adapter().search({
        query: 'gloves',
        quantity: null,
        maxResults: 200,
      })
      const newShop = offerById(offers, 'a-gloves-05')
      expect(newShop).toMatchObject({ incoterm: null, lead_time_days: null, certifications: [] })
      expect(offerById(offers, 'a-gloves-04').certifications).toEqual([])
    })

    it('reports truncation when maxResults cuts the list, and not when it does not', async () => {
      const narrow = await adapter().search({ query: 'gloves', quantity: null, maxResults: 3 })
      expect(narrow.offers.map((offer) => offer.platform_offer_id)).toEqual([
        'a-gloves-01',
        'a-gloves-02',
        'a-gloves-03',
      ])
      expect(narrow.skipped).toEqual([])
      expect(narrow.truncated).toBe(true)
      const wide = await adapter().search({ query: 'gloves', quantity: null, maxResults: 8 })
      expect(wide.offers).toHaveLength(7)
      expect(wide.truncated).toBe(false)
    })

    it('returns an empty result and no truncation for a query that matches nothing', async () => {
      const result = await adapter().search({
        query: 'zzz-no-match',
        quantity: null,
        maxResults: 5,
      })
      expect(result).toEqual({ offers: [], skipped: [], truncated: false })
    })

    it('serves the search through the registry when the platform flag is on', async () => {
      const registry = new AdapterRegistry(
        [adapter()],
        new StaticFlags({ 'platform.mock-a.enabled': true })
      )
      const result = await processJob(
        {
          kind: 'search',
          tenant_id: 'tenant-test',
          mission_id: 'mission-test',
          trace_id: 'trace-test',
          platform: 'mock-a',
          query: 'kraft',
          quantity: null,
          max_results: 5,
        },
        registry
      )
      expect(result).toMatchObject({ kind: 'search', truncated: false })
    })
  })

  describe('seller signals mapping', () => {
    async function signalsOf(sellerId: string, maxReviews = 10): Promise<RawSellerSignals> {
      const signals: unknown = await adapter().getSellerSignals(sellerId, { maxReviews })
      assertValidSignals(signals, 'mock-a', maxReviews)
      return signals
    }

    it('keeps the signals a new shop does not publish as null, never 0', async () => {
      const signals = await signalsOf('a-new-shop')
      expect(signals).toMatchObject({
        account_age_days: 25,
        published_products_count: 2,
        recent_reviews: [],
      })
      for (const field of [
        'first_sale_date',
        'months_active_last_12',
        'lifetime_transactions',
        'transactions_12m',
        'gmv_12m',
        'repeat_buyer_share',
        'catalog_churn_30d',
        'spec_completeness_avg',
        'reviews_total',
        'reviews_12m',
        'rating_avg',
        'rating_count',
        'verified_review_share',
        'response_rate',
        'identity_verified',
        'trade_assurance',
        'escrow_available',
        'dispute_rate',
        'refund_rate',
      ] as const) {
        expect(signals[field], field).toBeNull()
      }
    })

    it('maps the single-review seller and the solid veteran (criterion 7 pair)', async () => {
      const single = await signalsOf('a-single-review')
      expect(single).toMatchObject({
        rating_avg: 5,
        rating_count: 1,
        reviews_total: 1,
        reviews_12m: 1,
        verified_review_share: 1,
        dispute_rate: 0,
        refund_rate: 0,
        gmv_12m: { amount_minor: 1850000, currency: 'EUR' },
      })
      expect(single.recent_reviews).toEqual([
        expect.objectContaining({ rating: 5, verified_purchase: true }),
      ])

      const veteran = await signalsOf('a-solid-veteran', 3)
      expect(veteran).toMatchObject({
        first_sale_date: '2019-04-02',
        months_active_last_12: 12,
        lifetime_transactions: 4200,
        transactions_12m: 900,
        gmv_12m: { amount_minor: 410000000, currency: 'USD' },
        repeat_buyer_share: 0.41,
        published_products_count: 140,
        catalog_churn_30d: 0.03,
        spec_completeness_avg: 0.9,
        reviews_total: 500,
        reviews_12m: 260,
        rating_avg: 4.8,
        rating_count: 500,
        verified_review_share: 0.92,
        response_rate: 0.97,
        identity_verified: true,
        trade_assurance: true,
        escrow_available: true,
        dispute_rate: 0.01,
        refund_rate: 0.02,
      })
    })

    it('recovers a two-decimal rating from the mock scale, and a GMV in an unsupported currency is null', async () => {
      const burst = await signalsOf('a-review-burst')
      expect(burst).toMatchObject({ rating_avg: 4.97, verified_review_share: 0.08 })
      expect(burst.catalog_churn_30d).toBe(0.6)

      const gbp = await signalsOf('a-standard-gbp')
      expect(gbp.gmv_12m).toBeNull()
      expect(gbp.published_products_count).toBe(120)
    })

    it('returns at most maxReviews reviews, most recent first', async () => {
      const veteran = await signalsOf('a-solid-veteran', 3)
      expect(veteran.recent_reviews).toHaveLength(3)
      const dates = veteran.recent_reviews.map((review) => review.created_at ?? '')
      expect([...dates].sort().reverse()).toEqual(dates)
    })
  })

  describe('chat mapping', () => {
    it('reads the seller reply as role seller, with the message time as a Date', async () => {
      const chat = adapter().chat
      // A different listing from the contract's chat, so the two POSTs have different fixture keys.
      const { platformChatId } = await chat.open({
        accountId: 'acct-test',
        platformSellerId: 'a-solid-veteran',
        productId: 'a-gloves-02',
      })
      const sent = await chat.send(platformChatId, 'Could you confirm the MOQ for 5000 units?')
      expect(sent.at).toBeInstanceOf(Date)
      const thread = await chat.read(platformChatId, 0)
      expect(thread.map((message) => [message.seq, message.role])).toEqual([
        [1, 'buyer'],
        [2, 'seller'],
      ])
      expect(thread[0]?.seq).toBe(sent.platformSeq)
      expect(thread.every((message) => message.at instanceof Date)).toBe(true)
    })

    it('refuses a screenshot: mock-a has no rendered chat', async () => {
      const chat = adapter().chat
      const error = await chat.screenshot('chat-mock-a-0001').catch((caught: unknown) => caught)
      assertWorkerError(error, 'upstream_error')
      expect(error).toMatchObject({ detail: 'mock-a has no rendered chat', retryable: false })
    })
  })
}

if (MODE === 'replay') {
  describe('mock-a adapter, replay', () => {
    let connection: (Connection & { adapter: MockAAdapter }) | undefined
    const current = (): Connection & { adapter: MockAAdapter } => {
      if (connection === undefined) {
        throw new Error('mock-a replay connection was not opened')
      }
      return connection
    }
    beforeAll(() => {
      const transport = new ReplayTransport(MOCK_A_FIXTURE_DIR)
      connection = { transport, adapter: buildAdapter(transport), close: () => Promise.resolve() }
    })
    describeAdapterContract('mock-a (replay)', () => Promise.resolve(subjectFor(current().adapter)))
    registerScenarios(current)
  })
}

if (MODE === 'record' || MODE === 'live') {
  describe(`mock-a adapter, against the mock (${MODE})`, () => {
    let mock: RunningMockMarketplace | undefined
    let connection: (Connection & { adapter: MockAAdapter }) | undefined
    const current = (): Connection & { adapter: MockAAdapter } => {
      if (connection === undefined) {
        throw new Error('mock-a live connection was not opened')
      }
      return connection
    }
    beforeAll(async () => {
      if (MODE === 'record') {
        await rm(MOCK_A_FIXTURE_DIR, { recursive: true, force: true })
      }
      mock = await startMockMarketplace()
      const live = rewriteOrigin(fetchTransport, MOCK_A_LOGICAL_ORIGIN, mock.origin)
      const transport = transportForMode(MODE, MOCK_A_FIXTURE_DIR, live)
      connection = { transport, adapter: buildAdapter(transport), close: () => Promise.resolve() }
    }, LIFECYCLE_TIMEOUT_MS)
    afterAll(async () => {
      await mock?.stop()
    }, LIFECYCLE_TIMEOUT_MS)
    describeAdapterContract(`mock-a (${MODE})`, () =>
      Promise.resolve(subjectFor(current().adapter))
    )
    registerScenarios(current)
  })
}

describe('mock-a registry', () => {
  it('never reaches the mock while the platform flag is off', async () => {
    let requests = 0
    const transport: HttpTransport = {
      request(_req: HttpRequest): Promise<HttpResponse> {
        requests += 1
        return Promise.reject(new Error('the mock must not be reached'))
      },
    }
    const registry = new AdapterRegistry([buildAdapter(transport)], new StaticFlags({}))
    await expect(
      processJob(
        {
          kind: 'search',
          tenant_id: 'tenant-test',
          mission_id: 'mission-test',
          trace_id: 'trace-test',
          platform: 'mock-a',
          query: 'gloves',
          quantity: null,
          max_results: 5,
        },
        registry
      )
    ).rejects.toMatchObject({ code: 'platform_disabled' })
    expect(requests).toBe(0)
  })
})
