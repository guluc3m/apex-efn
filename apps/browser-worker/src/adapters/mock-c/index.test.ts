import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { WorkerError } from '../../errors.js'
import { describeAdapterContract } from '../contract-suite.js'
import type { HttpRequest, HttpResponse } from '../http.js'

import { createMockCAdapter } from './index.js'

const FIXTURES = join(import.meta.dirname, 'fixtures')

function fixture(name: string): string {
  return readFileSync(join(FIXTURES, name), 'utf8')
}

function json(body: string, status = 200): HttpResponse {
  return { status, headers: { 'content-type': 'application/json' }, body }
}

function apiError(code: string, status = 404): HttpResponse {
  return json(JSON.stringify({ error: { code, message: code } }), status)
}

const EMPTY_ROBOTS = json('User-agent: *\nAllow: /\n')

/**
 * Serves the recorded mock-c responses by URL, including the two error pages, so the adapter is exercised through
 * the same HTTP path it will use against a real platform.
 */
class FixtureTransport {
  readonly calls: HttpRequest[] = []

  constructor(private readonly overrides: Record<string, HttpResponse> = {}) {}

  request(request: HttpRequest): Promise<HttpResponse> {
    this.calls.push(request)
    const url = new URL(request.url)
    const key = `${request.method} ${url.pathname}`
    const override = this.overrides[key]
    if (override !== undefined) {
      return Promise.resolve(override)
    }
    if (url.pathname === '/robots.txt') {
      return Promise.resolve(EMPTY_ROBOTS)
    }
    switch (key) {
      case 'GET /mock-c/api/search':
        return Promise.resolve(json(fixture('search.json')))
      case 'GET /mock-c/api/items/c-gloves-01':
        return Promise.resolve(json(fixture('item.json')))
      case 'GET /mock-c/api/suppliers/c-solid-supplier':
        return Promise.resolve(json(fixture('supplier.json')))
      case 'GET /mock-c/api/suppliers/c-solid-supplier/metrics':
        return Promise.resolve(json(fixture('metrics-solid.json')))
      case 'GET /mock-c/api/suppliers/c-new-shop/metrics':
        return Promise.resolve(json(fixture('metrics-thin.json')))
      case 'POST /mock-c/api/threads':
        return Promise.resolve(json(fixture('thread-open.json'), 201))
      case 'POST /mock-c/api/threads/chat-mock-c-0001/messages':
        return Promise.resolve(json(fixture('thread-send.json'), 201))
      case 'GET /mock-c/api/threads/chat-mock-c-0001/messages':
        return Promise.resolve(json(fixture('thread-read.json')))
      default: {
        const code = url.pathname.includes('/suppliers/')
          ? 'unknown_supplier'
          : url.pathname.includes('/threads/')
            ? 'unknown_thread'
            : 'unknown_item'
        return Promise.resolve(apiError(code))
      }
    }
  }
}

function adapter(transport = new FixtureTransport()) {
  return createMockCAdapter({
    baseUrl: 'http://mock.test',
    transport,
    clock: { now: () => new Date('2026-11-11T12:00:00.000Z') },
    sleep: () => Promise.resolve(),
    random: () => 0.5,
    userAgent: 'APEX-EFN-bot/0.1 (+https://example.invalid/bot)',
    minIntervalMs: 0,
    maxRetries: 0,
    timeoutMs: 1_000,
  })
}

describe('mock-c adapter', () => {
  it('declares the platform and the http transport', () => {
    const subject = adapter()
    expect(subject.platform).toBe('mock-c')
    expect(subject.transport).toBe('http')
  })

  it('maps integer cents to contract money and keeps the supplier', async () => {
    const result = await adapter().search({ query: 'nitrile gloves', quantity: 5000, maxResults: 50 })

    expect(result.offers).toHaveLength(4)
    expect(result.skipped).toEqual([])
    const first = result.offers[0]
    expect(first?.platform_offer_id).toBe('c-gloves-01')
    expect(first?.unit_price).toEqual({ amount_minor: 432, currency: 'EUR' })
    expect(first?.platform_seller_id).toBe('c-solid-supplier')
    expect(first?.moq).toBe(1000)
  })

  it('skips a listing in a currency the contract does not support', async () => {
    const transport = new FixtureTransport({
      'GET /mock-c/api/search': json(
        JSON.stringify({
          query: 'x',
          count: 1,
          items: [
            {
              item_id: 'c-gbp-1',
              title: 'Thing',
              unit_price: { cents: 100, currency: 'GBP' },
              min_order: 1,
              supplier_id: 'c-solid-supplier',
              supplier_name: 'Supplier',
            },
          ],
        })
      ),
    })

    const result = await adapter(transport).search({ query: 'x', quantity: null, maxResults: 10 })

    expect(result.offers).toEqual([])
    expect(result.skipped).toEqual([
      { platform_offer_id: 'c-gbp-1', reason: 'unsupported_currency', currency_raw: 'GBP' },
    ])
  })

  it('maps item detail: tiers, specs, shipping, incoterm and lead time', async () => {
    const offer = await adapter().getProduct('c-gloves-01')

    expect(offer.price_tiers).toHaveLength(2)
    expect(offer.price_tiers[1]).toEqual({
      min_quantity: 5000,
      max_quantity: null,
      unit_price: { amount_minor: 402, currency: 'EUR' },
    })
    expect(offer.specifications.material).toBe('nitrile')
    expect(offer.shipping).toEqual({
      cost: { amount_minor: 900, currency: 'EUR' },
      min_days: 7,
      max_days: 12,
    })
    expect(offer.incoterm).toBe('FOB')
    expect(offer.lead_time_days).toBe(12)
    expect(offer.certifications).toEqual(['EN 455', 'CE'])
  })

  it('maps seller signals with basis points as ratios and keeps missing values null', async () => {
    const subject = adapter()
    const solid = await subject.getSellerSignals('c-solid-supplier', { maxReviews: 2 })
    expect(solid.repeat_buyer_share).toBeCloseTo(0.52)
    expect(solid.response_rate).toBeCloseTo(0.97)
    expect(solid.rating_avg).toBeCloseTo(4.8)
    expect(solid.identity_verified).toBe(true)
    expect(solid.recent_reviews).toHaveLength(2)
    expect(solid.recent_reviews[0]?.created_at).toBe('2026-09-18T00:00:00Z')

    const thin = await subject.getSellerSignals('c-new-shop', { maxReviews: 3 })
    expect(thin.repeat_buyer_share).toBeNull()
    expect(thin.rating_avg).toBeNull()
    expect(thin.recent_reviews).toEqual([])
    expect(thin.account_age_days).toBeGreaterThan(0)
  })

  it('opens a thread, sends and reads the supplier answer', async () => {
    const chat = adapter().chat
    if (chat === undefined) {
      throw new Error('mock-c must expose a chat adapter')
    }

    const { platformChatId } = await chat.open({
      accountId: 'acct-1',
      platformSellerId: 'c-solid-supplier',
      productId: 'c-gloves-01',
    })
    expect(platformChatId).toBe('chat-mock-c-0001')

    const sent = await chat.send(platformChatId, 'Can you do EUR 4.10 for 5000 boxes?')
    expect(sent.platformSeq).toBe(1)

    const thread = await chat.read(platformChatId, 0)
    expect(thread.map((m) => m.role)).toEqual(['buyer', 'seller'])
    expect(thread[0]?.text).toContain('EUR 4.10')
    expect(await chat.read(platformChatId, 2)).toEqual([])
  })

  it('refuses a thread for an item that belongs to another supplier', async () => {
    const chat = adapter().chat
    if (chat === undefined) {
      throw new Error('mock-c must expose a chat adapter')
    }
    await expect(
      chat.open({ accountId: 'acct-1', platformSellerId: 'c-chinese-trader', productId: 'c-gloves-01' })
    ).rejects.toMatchObject({ code: 'unknown_seller' })
  })

  it('maps the platform error codes to the closed worker codes', async () => {
    const subject = adapter()
    await expect(subject.getProduct('nope')).rejects.toMatchObject({ code: 'unknown_product' })
    await expect(subject.getSeller('nope')).rejects.toMatchObject({ code: 'unknown_seller' })
  })

  it('answers a screenshot honestly', async () => {
    const chat = adapter().chat
    if (chat === undefined) {
      throw new Error('mock-c must expose a chat adapter')
    }
    await expect(chat.screenshot('chat-mock-c-0001')).rejects.toBeInstanceOf(WorkerError)
  })

  it('goes through robots.txt before the first request', async () => {
    const transport = new FixtureTransport()
    await adapter(transport).search({ query: 'nitrile', quantity: null, maxResults: 5 })
    expect(transport.calls[0]?.url).toContain('/robots.txt')
  })
})

describeAdapterContract('mock-c', () =>
  Promise.resolve({
    adapter: adapter(),
    search: { query: 'nitrile gloves', quantity: 5000 },
    knownOfferId: 'c-gloves-01',
    knownSellerId: 'c-solid-supplier',
    missingOfferId: 'does-not-exist',
    missingSellerId: 'does-not-exist',
    chat: {
      platformSellerId: 'c-solid-supplier',
      productId: 'c-gloves-01',
      accountId: 'acct-1',
      message: 'Can you do EUR 4.10 for 5000 boxes?',
    },
  })
)
