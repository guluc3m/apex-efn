import { describe, expect, it } from 'vitest'

import { WorkerError } from '../../errors.js'
import { processJob } from '../../jobs/processor.js'
import { StaticFlags } from '../../platform/flags.js'
import { FixedClock } from '../../testing/fakes.js'
import { MOCK_A_LOGICAL_ORIGIN } from '../../testing/mock-marketplace.js'
import type { HttpRequest, HttpResponse, HttpTransport } from '../http.js'
import { AdapterRegistry } from '../index.js'

import {
  accountAgeDays,
  classifyMockError,
  listingPriceProblem,
  moneyFrom,
  ListingPriceError,
  ratingOf,
  ratioOf,
  recentReviewsFrom,
  signalsFrom,
} from './mapping.js'
import type { MockMetrics, MockProduct } from './schemas.js'

import { createMockAAdapter } from './index.js'

const NOW = '2026-11-09T10:00:00.000Z'
const clock = new FixedClock(NOW)

type Reply = { status: number; body?: unknown }

/** Answers from a table keyed by `METHOD /path?query`. Unlisted robots.txt is a 404, anything else unlisted fails. */
function routed(table: Record<string, Reply>): { transport: HttpTransport; requests: string[] } {
  const requests: string[] = []
  const transport: HttpTransport = {
    request(req: HttpRequest): Promise<HttpResponse> {
      const url = new URL(req.url)
      const key = `${req.method} ${url.pathname}${url.search}`
      requests.push(key)
      const reply = table[key] ?? (url.pathname === '/robots.txt' ? { status: 404 } : undefined)
      if (reply === undefined) {
        return Promise.reject(new Error(`unrouted request ${key}`))
      }
      const body =
        reply.body === undefined
          ? ''
          : typeof reply.body === 'string'
            ? reply.body
            : JSON.stringify(reply.body)
      return Promise.resolve({ status: reply.status, headers: {}, body })
    },
  }
  return { transport, requests }
}

function adapterOver(transport: HttpTransport) {
  return createMockAAdapter({
    baseUrl: MOCK_A_LOGICAL_ORIGIN,
    transport,
    clock,
    sleep: () => Promise.resolve(),
    random: () => 0.5,
    userAgent: 'APEX-EFN-bot/0.1 (+https://example.invalid/bot)',
    minIntervalMs: 0,
    maxRetries: 0,
    timeoutMs: 1000,
  })
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

const LISTING = {
  listing_id: 'x-1',
  name: 'Test gloves',
  url: '/mock-a/api/products/x-1',
  price: { amount: '4.45', currency: 'EUR' },
  min_order_qty: 100,
  vendor: { vendor_id: 'x-seller', display_name: 'Seller X' },
}

const PRODUCT: MockProduct = {
  ...LISTING,
  attributes: [{ key: 'size', value: 'M' }],
  certs: [],
  bulk_pricing: [{ from_qty: 100, to_qty: null, price: '4.45' }],
  delivery: null,
  trade_term: null,
  production_days: null,
}

function searchPage(results: unknown[], total = results.length) {
  return { query: 'x', total, page: 1, results }
}

const SEARCH = 'GET /mock-a/api/search?q=x&page=1'
const PRODUCT_PATH = '/mock-a/api/products/x-1'

describe('price text to Money', () => {
  it.each([
    ['4.45', 445],
    ['4,45', 445],
    ['12', 1200],
    ['0.5', 50],
    ['1 234.50', 123450],
    ['1,234.50', 123450],
  ])('parses %j exactly to %i minor units', (text, minor) => {
    expect(moneyFrom(text, 'EUR')).toEqual({ amount_minor: minor, currency: 'EUR' })
  })

  it('keeps CNY and maps RMB to CNY', () => {
    expect(moneyFrom('34.50', 'CNY')).toEqual({ amount_minor: 3450, currency: 'CNY' })
    expect(moneyFrom('34.50', 'RMB')).toEqual({ amount_minor: 3450, currency: 'CNY' })
  })

  it.each([
    ['a price with three decimals', '12.345', 'EUR', 'parse_error'],
    ['an ambiguous thousands-looking price', '1,234', 'EUR', 'parse_error'],
    ['a negative price', '-1.00', 'EUR', 'parse_error'],
    ['a missing amount', null, 'EUR', 'missing_price'],
    ['a blank amount', '  ', 'EUR', 'missing_price'],
  ])('reports %s as %s', (_label, amount, currency, reason) => {
    expect(() => moneyFrom(amount, currency)).toThrow(ListingPriceError)
    expect(listingPriceProblem({ amount, currency })?.reason).toBe(reason)
  })

  it('reports a currency outside EUR, USD and CNY with the code as shown', () => {
    expect(listingPriceProblem({ amount: '3.90', currency: 'GBP' })).toMatchObject({
      reason: 'unsupported_currency',
      currencyRaw: 'GBP',
    })
    expect(listingPriceProblem({ amount: '3.90', currency: null })).toMatchObject({
      reason: 'unsupported_currency',
      currencyRaw: null,
    })
    expect(listingPriceProblem({ amount: '3.90', currency: 'EUR' })).toBeNull()
  })
})

describe('search mapping edge cases', () => {
  it('skips a listing without a price before requesting its product page', async () => {
    const { transport, requests } = routed({
      [SEARCH]: { status: 200, body: searchPage([{ ...LISTING, price: null }]) },
    })
    const result = await adapterOver(transport).search({
      query: 'x',
      quantity: null,
      maxResults: 5,
    })
    expect(result.skipped).toEqual([{ platform_offer_id: 'x-1', reason: 'missing_price' }])
    expect(requests.some((key) => key.includes('/products/'))).toBe(false)
  })

  it('skips a listing whose price text is not a decimal amount, with parse_error', async () => {
    const { transport } = routed({
      [SEARCH]: {
        status: 200,
        body: searchPage([{ ...LISTING, price: { amount: '12.345', currency: 'EUR' } }]),
      },
    })
    const result = await adapterOver(transport).search({
      query: 'x',
      quantity: null,
      maxResults: 5,
    })
    expect(result).toMatchObject({
      offers: [],
      skipped: [{ platform_offer_id: 'x-1', reason: 'parse_error' }],
    })
  })

  it('skips a listing whose bulk price cannot be parsed, after the product page is read', async () => {
    const { transport, requests } = routed({
      [SEARCH]: { status: 200, body: searchPage([LISTING]) },
      [`GET ${PRODUCT_PATH}`]: {
        status: 200,
        body: { ...PRODUCT, bulk_pricing: [{ from_qty: 100, to_qty: null, price: '1,234' }] },
      },
    })
    const result = await adapterOver(transport).search({
      query: 'x',
      quantity: null,
      maxResults: 5,
    })
    expect(result.skipped).toEqual([{ platform_offer_id: 'x-1', reason: 'parse_error' }])
    expect(requests).toContain(`GET ${PRODUCT_PATH}`)
  })

  it('keeps an offer whose shipping currency is not supported, with shipping null', async () => {
    const { transport } = routed({
      [SEARCH]: { status: 200, body: searchPage([LISTING]) },
      [`GET ${PRODUCT_PATH}`]: {
        status: 200,
        body: { ...PRODUCT, delivery: { fee: '9.99', currency: 'GBP', eta_days: [3, 5] } },
      },
    })
    const result = await adapterOver(transport).search({
      query: 'x',
      quantity: null,
      maxResults: 5,
    })
    expect(result.offers).toHaveLength(1)
    expect(result.offers[0]?.shipping).toBeNull()
  })

  it('skips the listing when the shipping fee text cannot be parsed', async () => {
    const { transport } = routed({
      [SEARCH]: { status: 200, body: searchPage([LISTING]) },
      [`GET ${PRODUCT_PATH}`]: {
        status: 200,
        body: { ...PRODUCT, delivery: { fee: 'free', currency: 'EUR', eta_days: [3, 5] } },
      },
    })
    const result = await adapterOver(transport).search({
      query: 'x',
      quantity: null,
      maxResults: 5,
    })
    expect(result).toMatchObject({ offers: [], skipped: [{ reason: 'parse_error' }] })
  })

  it('maps an incoterm the contract does not know to null', async () => {
    const { transport } = routed({
      [SEARCH]: { status: 200, body: searchPage([LISTING]) },
      [`GET ${PRODUCT_PATH}`]: { status: 200, body: { ...PRODUCT, trade_term: 'XYZ' } },
    })
    const result = await adapterOver(transport).search({
      query: 'x',
      quantity: null,
      maxResults: 5,
    })
    expect(result.offers[0]?.incoterm).toBeNull()
  })

  it('follows pages until maxResults is reached, and marks truncation when more listings exist', async () => {
    const second = { ...LISTING, listing_id: 'x-2', url: '/mock-a/api/products/x-2' }
    const third = { ...LISTING, listing_id: 'x-3', url: '/mock-a/api/products/x-3' }
    const { transport, requests } = routed({
      [SEARCH]: { status: 200, body: searchPage([LISTING, second], 3) },
      'GET /mock-a/api/search?q=x&page=2': {
        status: 200,
        body: { ...searchPage([third], 3), page: 2 },
      },
      [`GET ${PRODUCT_PATH}`]: { status: 200, body: PRODUCT },
      'GET /mock-a/api/products/x-2': { status: 200, body: { ...PRODUCT, listing_id: 'x-2' } },
      'GET /mock-a/api/products/x-3': { status: 200, body: { ...PRODUCT, listing_id: 'x-3' } },
    })
    const all = await adapterOver(transport).search({ query: 'x', quantity: null, maxResults: 10 })
    expect(all.offers.map((offer) => offer.platform_offer_id)).toEqual(['x-1', 'x-2', 'x-3'])
    expect(all.truncated).toBe(false)

    requests.length = 0
    const capped = await adapterOver(transport).search({
      query: 'x',
      quantity: null,
      maxResults: 2,
    })
    expect(capped.offers).toHaveLength(2)
    expect(capped.truncated).toBe(true)
    expect(requests.filter((key) => key.startsWith('GET /mock-a/api/search'))).toEqual([SEARCH])
  })

  it('stops paging when a page comes back empty, even if the total says more', async () => {
    const { transport } = routed({
      [SEARCH]: { status: 200, body: searchPage([], 5) },
    })
    const result = await adapterOver(transport).search({
      query: 'x',
      quantity: null,
      maxResults: 5,
    })
    expect(result).toEqual({ offers: [], skipped: [], truncated: false })
  })
})

describe('getProduct and getSeller errors', () => {
  it('maps a single product in an unsupported currency to upstream_error, not to an offer', async () => {
    const { transport } = routed({
      [`GET ${PRODUCT_PATH}`]: {
        status: 200,
        body: { ...PRODUCT, price: { amount: '3.90', currency: 'GBP' } },
      },
    })
    const error = await failureOf(adapterOver(transport).getProduct('x-1'))
    expect(error).toMatchObject({ code: 'upstream_error', retryable: false })
  })

  it('maps a product without a price to dom_changed', async () => {
    const { transport } = routed({
      [`GET ${PRODUCT_PATH}`]: { status: 200, body: { ...PRODUCT, price: null } },
    })
    const error = await failureOf(adapterOver(transport).getProduct('x-1'))
    expect(error).toMatchObject({ code: 'dom_changed', retryable: false })
  })

  it('maps the mock listing_not_found body to unknown_product', async () => {
    const { transport } = routed({
      [`GET ${PRODUCT_PATH}`]: { status: 404, body: { error: 'listing_not_found' } },
    })
    await expect(failureOf(adapterOver(transport).getProduct('x-1'))).resolves.toMatchObject({
      code: 'unknown_product',
      status: 404,
    })
  })

  it('maps a 404 with an unknown body to the caller default, unknown_seller for sellers', async () => {
    const { transport } = routed({
      'GET /mock-a/api/sellers/x-seller': { status: 404, body: '<html>nope</html>' },
    })
    await expect(failureOf(adapterOver(transport).getSeller('x-seller'))).resolves.toMatchObject({
      code: 'unknown_seller',
      status: 404,
    })
  })

  it('refuses a robots-disallowed product before any request reaches the mock', async () => {
    const { transport, requests } = routed({
      'GET /robots.txt': { status: 200, body: 'User-agent: *\nDisallow: /mock-a/api/products' },
      [`GET ${PRODUCT_PATH}`]: { status: 200, body: PRODUCT },
    })
    await expect(failureOf(adapterOver(transport).getProduct('x-1'))).resolves.toMatchObject({
      code: 'robots_disallowed',
    })
    expect(requests).toEqual(['GET /robots.txt'])
  })
})

describe('chat error bodies', () => {
  it('maps a wrong_platform 400 to validation_error with status 400', async () => {
    const { transport } = routed({
      'POST /mock-a/api/conversations': {
        status: 400,
        body: { error: 'wrong_platform', message: 'seller or product is not on mock-a' },
      },
    })
    await expect(
      adapterOver(transport).chat.open({
        accountId: 'acct',
        platformSellerId: 'b-solid-factory',
        productId: 'x-1',
      })
    ).rejects.toMatchObject({ code: 'validation_error', status: 400 })
  })

  it('maps an unknown_chat 404 on send to unknown_chat, and a refused empty message to validation_error', async () => {
    const { transport } = routed({
      'POST /mock-a/api/conversations/chat-mock-a-9999/messages': {
        status: 404,
        body: { error: 'unknown_chat', message: 'unknown chat' },
      },
      'POST /mock-a/api/conversations/chat-mock-a-0001/messages': {
        status: 400,
        body: { error: 'empty_message', message: 'message is empty' },
      },
    })
    const adapter = adapterOver(transport)
    await expect(adapter.chat.send('chat-mock-a-9999', 'hi')).rejects.toMatchObject({
      code: 'unknown_chat',
      status: 404,
    })
    await expect(adapter.chat.send('chat-mock-a-0001', '   ')).rejects.toMatchObject({
      code: 'validation_error',
      status: 400,
    })
  })

  it('maps a seller the platform does not know on open to unknown_seller', async () => {
    const { transport } = routed({
      'POST /mock-a/api/conversations': { status: 404, body: { error: 'unknown_seller' } },
    })
    await expect(
      adapterOver(transport).chat.open({
        accountId: 'acct',
        platformSellerId: 'nobody',
        productId: 'x-1',
      })
    ).rejects.toMatchObject({ code: 'unknown_seller', status: 404 })
  })
})

describe('classifyMockError', () => {
  it.each([
    ['listing_not_found', 404, 'unknown_product'],
    ['unknown_product', 404, 'unknown_product'],
    ['vendor_not_found', 404, 'unknown_seller'],
    ['unknown_seller', 404, 'unknown_seller'],
    ['unknown_chat', 404, 'unknown_chat'],
    ['wrong_platform', 400, 'validation_error'],
    ['empty_message', 400, 'validation_error'],
    ['bad_request', 400, 'validation_error'],
    ['bad_query', 400, 'validation_error'],
  ])('maps %s to %s', (error, status, code) => {
    expect(classifyMockError(status, JSON.stringify({ error }))).toBe(code)
  })

  it('returns undefined for unknown codes, plain text and JSON that is not an error body', () => {
    expect(classifyMockError(404, JSON.stringify({ error: 'something_new' }))).toBeUndefined()
    expect(classifyMockError(404, 'not json')).toBeUndefined()
    expect(classifyMockError(404, JSON.stringify({ message: 'no error key' }))).toBeUndefined()
    expect(classifyMockError(404, 'null')).toBeUndefined()
  })
})

const EMPTY_METRICS: MockMetrics = {
  vendor_id: 'x-seller',
  registered_at: null,
  first_order_at: null,
  active_months_12: null,
  orders: { lifetime: null, last_12m: null },
  turnover_12m: null,
  repeat_customers_pct: null,
  catalog: { listings: null, churn_30d_pct: null, completeness_pct: null },
  feedback: {
    count: null,
    count_12m: null,
    score_0_100: null,
    rated_orders: null,
    verified_pct: null,
  },
  reply_rate_pct: null,
  badges: { kyc: null, buyer_protection: null, escrow: null },
  disputes_pct: null,
  refunds_pct: null,
}

function signalsWith(
  metrics: Partial<MockMetrics>,
  reviews: Parameters<typeof recentReviewsFrom>[0] = []
) {
  return signalsFrom(
    { ...EMPTY_METRICS, ...metrics },
    { vendor_id: 'x-seller', reviews },
    { platform: 'mock-a', sellerId: 'x-seller', clock, maxReviews: 10 }
  )
}

describe('signal conversions', () => {
  it('turns one-decimal percentages into exact ratios', () => {
    expect(ratioOf(12.3)).toBe(0.123)
    expect(ratioOf(41)).toBe(0.41)
    expect(ratioOf(0)).toBe(0)
    expect(ratioOf(null)).toBeNull()
  })

  it('recovers the 1 to 5 rating from the 0 to 100 scale', () => {
    expect(ratingOf(100)).toBe(5)
    expect(ratingOf(0)).toBe(1)
    expect(ratingOf(99.3)).toBe(4.97)
    expect(ratingOf(95)).toBe(4.8)
    expect(ratingOf(null)).toBeNull()
  })

  it('reports the age in whole days, and null when the registration is after the clock', () => {
    const now = clock.now()
    expect(accountAgeDays(Date.parse('2026-10-15T00:00:00Z') / 1000, now)).toBe(25)
    expect(accountAgeDays(Date.parse('2026-11-10T00:00:00Z') / 1000, now)).toBeNull()
    expect(accountAgeDays(null, now)).toBeNull()
  })

  it('keeps a published zero as 0, and an unpublished value as null', () => {
    const signals = signalsWith({ disputes_pct: 0, refunds_pct: null })
    expect(signals.dispute_rate).toBe(0)
    expect(signals.refund_rate).toBeNull()
  })

  it('maps a GMV without a supported currency to null, and a supported one to minor units', () => {
    expect(signalsWith({ turnover_12m: { amount: '1.00', currency: 'GBP' } }).gmv_12m).toBeNull()
    expect(signalsWith({ turnover_12m: { amount: '1.00', currency: null } }).gmv_12m).toBeNull()
    expect(signalsWith({ turnover_12m: { amount: '9.99', currency: 'USD' } }).gmv_12m).toEqual({
      amount_minor: 999,
      currency: 'USD',
    })
  })

  it('sorts reviews newest first, puts undated reviews last, and truncates long text', () => {
    const reviews = recentReviewsFrom(
      [
        { review_id: 'r1', stars: 4, comment: 'old', posted_at: 1000, verified_order: true },
        { review_id: 'r2', stars: 5, comment: null, posted_at: null, verified_order: false },
        {
          review_id: 'r3',
          stars: 3,
          comment: 'x'.repeat(2500),
          posted_at: 2000,
          verified_order: true,
        },
      ],
      10
    )
    expect(reviews.map((review) => review.rating)).toEqual([3, 4, 5])
    expect(reviews[0]?.created_at).toBe('1970-01-01T00:33:20.000Z')
    expect(reviews[0]?.text).toHaveLength(2000)
    expect(reviews[2]).toEqual({
      rating: 5,
      created_at: null,
      verified_purchase: false,
      text: null,
    })
  })

  it('returns no reviews when maxReviews is 0', () => {
    expect(
      recentReviewsFrom(
        [{ review_id: 'r1', stars: 4, comment: 'a', posted_at: 1, verified_order: true }],
        0
      )
    ).toEqual([])
  })
})

describe('registry with the flag off, against a crafted transport', () => {
  it('still refuses before any request when the platform flag is off', async () => {
    const { transport, requests } = routed({})
    const registry = new AdapterRegistry(
      [adapterOver(transport)],
      new StaticFlags({ 'platform.mock-a.enabled': false })
    )
    await expect(
      processJob(
        {
          kind: 'product',
          tenant_id: 'tenant-test',
          mission_id: 'mission-test',
          trace_id: 'trace-test',
          platform: 'mock-a',
          platform_offer_id: 'x-1',
        },
        registry
      )
    ).rejects.toMatchObject({ code: 'platform_disabled' })
    expect(requests).toEqual([])
  })
})
