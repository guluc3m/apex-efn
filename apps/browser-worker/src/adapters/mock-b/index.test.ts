import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { WorkerError } from '../../errors.js'
import { describeAdapterContract } from '../contract-suite.js'
import type { HttpRequest, HttpResponse } from '../http.js'

import { createMockBAdapter, isoDay } from './index.js'

const FIXTURES = join(import.meta.dirname, 'fixtures')

function fixture(name: string): string {
  return readFileSync(join(FIXTURES, name), 'utf8')
}

function html(body: string, status = 200): HttpResponse {
  return { status, headers: { 'content-type': 'text/html; charset=utf-8' }, body }
}

function notFound(what: string): HttpResponse {
  return html(
    `<!doctype html><html><body><h1 data-testid="not-found">${what} not found</h1></body></html>`,
    404
  )
}

/**
 * Serves the recorded mock-b pages by URL. The routes mirror what the mock marketplace actually answers, including
 * the 404 pages, so the adapter is exercised through the same HTTP path it will use in production.
 */
class FixtureTransport {
  readonly calls: HttpRequest[] = []

  constructor(private readonly overrides: Record<string, HttpResponse> = {}) {}

  request(request: HttpRequest): Promise<HttpResponse> {
    this.calls.push(request)
    const url = new URL(request.url)
    const path = url.pathname
    const key = `${request.method} ${path}`
    const override = this.overrides[key]
    if (override !== undefined) {
      return Promise.resolve(override)
    }
    if (request.method === 'GET' && path === '/mock-b/search') {
      return Promise.resolve(html(fixture('search.html')))
    }
    if (request.method === 'GET' && path === '/mock-b/item/b-gloves-01') {
      return Promise.resolve(html(fixture('item.html')))
    }
    if (request.method === 'GET' && path === '/mock-b/shop/b-solid-factory') {
      return Promise.resolve(html(fixture('shop.html')))
    }
    if (request.method === 'POST' && path === '/mock-b/chat') {
      return Promise.resolve(html(fixture('chat.html')))
    }
    if (request.method === 'POST' && path === '/mock-b/chat/chat-mock-b-0002/send') {
      return Promise.resolve(html(fixture('chat.html')))
    }
    if (request.method === 'GET' && path === '/mock-b/chat/chat-mock-b-0002') {
      return Promise.resolve(html(fixture('chat.html')))
    }
    return Promise.resolve(notFound(path))
  }
}

function adapter(transport = new FixtureTransport()) {
  return createMockBAdapter({
    baseUrl: 'http://mock.test',
    transport,
    clock: { now: () => new Date('2026-11-10T12:00:00.000Z') },
    sleep: () => Promise.resolve(),
    random: () => 0.5,
    userAgent: 'APEX-EFN-test',
    minIntervalMs: 0,
    maxRetries: 0,
    timeoutMs: 1_000,
  })
}

describe('mock-b adapter', () => {
  it('declares the http transport and the platform id', () => {
    const subject = adapter()
    expect(subject.platform).toBe('mock-b')
    expect(subject.transport).toBe('http')
  })

  it('parses search cards into raw offers with the platform currency', async () => {
    const result = await adapter().search({ query: 'nitrile gloves', quantity: 5000, maxResults: 50 })

    expect(result.offers).toHaveLength(7)
    expect(result.truncated).toBe(false)
    expect(result.skipped).toEqual([])
    const first = result.offers[0]
    expect(first?.platform_offer_id).toBe('b-gloves-01')
    expect(first?.platform_seller_id).toBe('b-solid-factory')
    expect(first?.unit_price).toEqual({ amount_minor: 3380, currency: 'CNY' })
    expect(first?.moq).toBe(5000)
    expect(first?.title).toContain('Nitrile Gloves')
    expect(first?.product_url).toBe('http://mock.test/mock-b/item/b-gloves-01')
  })

  it('honours maxResults and reports truncation', async () => {
    const result = await adapter().search({ query: 'nitrile gloves', quantity: null, maxResults: 5 })
    expect(result.offers).toHaveLength(5)
    expect(result.truncated).toBe(true)
  })

  it('skips a listing whose currency the contract does not support, with the raw code', async () => {
    const transport = new FixtureTransport({
      'GET /mock-b/search': html(`<ul data-testid="results">
        <li data-testid="result" data-item-id="x-1" data-seller-id="s-1">
          <a class="title">Thing</a>
          <span data-testid="price" data-minor="100" data-currency="GBP">£1.00</span>
          <span data-testid="moq">Min. order: 1 units</span>
          <a class="shop">Shop</a>
        </li>
        <li data-testid="result" data-item-id="x-2" data-seller-id="s-1">
          <a class="title">No price here</a>
        </li>
      </ul>`),
    })

    const result = await adapter(transport).search({ query: 'x', quantity: null, maxResults: 10 })

    expect(result.offers).toEqual([])
    expect(result.skipped).toEqual([
      { platform_offer_id: 'x-1', reason: 'unsupported_currency', currency_raw: 'GBP' },
      { platform_offer_id: 'x-2', reason: 'missing_price' },
    ])
  })

  it('parses the item page: specs, tiers, shipping, incoterm and lead time', async () => {
    const offer = await adapter().getProduct('b-gloves-01')

    expect(offer.unit_price).toEqual({ amount_minor: 3380, currency: 'CNY' })
    expect(offer.moq).toBe(5000)
    expect(offer.specifications.material).toBe('nitrile')
    expect(offer.price_tiers).toHaveLength(2)
    expect(offer.price_tiers[1]?.unit_price.amount_minor).toBe(3150)
    expect(offer.price_tiers[1]?.max_quantity).toBeNull()
    expect(offer.shipping).toEqual({
      cost: { amount_minor: 4000, currency: 'CNY' },
      min_days: 15,
      max_days: 25,
    })
    expect(offer.incoterm).toBe('FOB')
    expect(offer.lead_time_days).toBe(25)
    expect(offer.certifications).toEqual(['EN 455', 'CE'])
    expect(offer.platform_seller_id).toBe('b-solid-factory')
  })

  it('parses the shop page into a raw seller', async () => {
    const seller = await adapter().getSeller('b-solid-factory')
    expect(seller.display_name).toContain('Hangzhou Lotus')
    expect(seller.country).toBe('CN')
    expect(seller.profile_url).toBe('http://mock.test/mock-b/shop/b-solid-factory')
  })

  it('parses seller signals, including percentages, the platform date format and reviews', async () => {
    const signals = await adapter().getSellerSignals('b-solid-factory', { maxReviews: 3 })

    expect(signals.repeat_buyer_share).toBeCloseTo(0.45)
    expect(signals.verified_review_share).toBeCloseTo(0.88)
    expect(signals.rating_avg).toBeCloseTo(4.7)
    expect(signals.identity_verified).toBe(true)
    expect(signals.trade_assurance).toBe(true)
    expect(signals.gmv_12m).toEqual({ amount_minor: 2_600_000_000, currency: 'CNY' })
    expect(signals.first_sale_date).toBe('2018-06-01')
    // Account age is computed against the injected clock: 2020-09-01 -> 2026-11-10.
    expect(signals.account_age_days).toBeGreaterThan(2200)
    expect(signals.recent_reviews.length).toBeLessThanOrEqual(3)
    expect(String(signals.recent_reviews[0]?.created_at)).toMatch(
      /^\d{4}-\d{2}-\d{2}T00:00:00Z$/,
    )
  })

  it('opens a chat, sends a message and reads the thread in order', async () => {
    const subject = adapter()
    const chat = subject.chat
    if (chat === undefined) {
      throw new Error('mock-b must expose a chat adapter')
    }

    const { platformChatId } = await chat.open({
      accountId: 'acct-1',
      platformSellerId: 'b-solid-factory',
      productId: 'b-gloves-01',
    })
    expect(platformChatId).toBe('chat-mock-b-0002')

    const sent = await chat.send(platformChatId, 'Can you do 30 CNY?')
    expect(sent.platformSeq).toBe(1)
    expect(sent.at.toISOString()).toBe('2026-11-10T20:26:10.685Z')

    const thread = await chat.read(platformChatId, 0)
    expect(thread.map((message) => message.role)).toEqual(['buyer', 'seller'])
    expect(thread[0]?.text).toBe('Can you do 30 CNY?')
    expect(await chat.read(platformChatId, 2)).toEqual([])
  })

  it('rejects a screenshot honestly instead of pretending', async () => {
    const chat = adapter().chat
    if (chat === undefined) {
      throw new Error('mock-b must expose a chat adapter')
    }
    await expect(chat.screenshot('chat-mock-b-0002')).rejects.toMatchObject({
      code: 'upstream_error',
    })
  })

  it('answers unknown_product and unknown_seller from the 404 page', async () => {
    const subject = adapter()
    await expect(subject.getProduct('does-not-exist')).rejects.toMatchObject({
      code: 'unknown_product',
    })
    await expect(subject.getSeller('does-not-exist')).rejects.toMatchObject({
      code: 'unknown_seller',
    })
  })

  it('answers dom_changed, naming only the selector, when the page loses its shape', async () => {
    const transport = new FixtureTransport({
      'GET /mock-b/item/b-gloves-01': html('<html><body><p>nothing useful</p></body></html>'),
    })
    const error = await adapter(transport)
      .getProduct('b-gloves-01')
      .catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(WorkerError)
    expect((error as WorkerError).code).toBe('dom_changed')
    expect((error as WorkerError).detail).not.toContain('nothing useful')
  })

  it('normalises both date formats the platform uses and rejects anything else', () => {
    expect(isoDay('05/10/2020')).toBe('2020-10-05')
    expect(isoDay('2020-10-05')).toBe('2020-10-05')
    expect(isoDay('October 5, 2020')).toBeNull()
  })
})

describeAdapterContract('mock-b', () =>
  Promise.resolve({
    adapter: adapter(),
    search: { query: 'nitrile gloves', quantity: 5000 },
    knownOfferId: 'b-gloves-01',
    knownSellerId: 'b-solid-factory',
    missingOfferId: 'does-not-exist',
    missingSellerId: 'does-not-exist',
    chat: {
      platformSellerId: 'b-solid-factory',
      productId: 'b-gloves-01',
      accountId: 'acct-1',
      message: 'Can you do 30 CNY?',
    },
  })
)
