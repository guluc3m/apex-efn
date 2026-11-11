import { afterAll, describe, expect, it } from 'vitest'

import { testServer } from './test-helpers.js'

const { app } = testServer()
afterAll(() => app.close())

describe('service', () => {
  it('reports health', async () => {
    const res = await app.inject({ method: 'GET', url: '/healthz' })
    expect(res.statusCode).toBe(200)
    expect(res.json()).toMatchObject({ status: 'ok', platforms: ['mock-a', 'mock-b', 'mock-c'] })
  })

  it('serves robots.txt that disallows the control surface', async () => {
    const res = await app.inject({ method: 'GET', url: '/robots.txt' })
    expect(res.body).toContain('Disallow: /__control/')
  })
})

describe('mock-a JSON API', () => {
  it('searches with its own vocabulary and decimal-string prices', async () => {
    const res = await app.inject({ method: 'GET', url: '/mock-a/api/search?q=nitrile%20gloves' })
    expect(res.statusCode).toBe(200)
    const body = res.json<{
      total: number
      results: Array<{
        listing_id: string
        price: { amount: string; currency: string }
        vendor: { vendor_id: string }
      }>
    }>()
    expect(body.total).toBeGreaterThanOrEqual(3)
    const first = body.results[0]
    expect(first?.listing_id).toBe('a-gloves-01')
    expect(first?.price.amount).toMatch(/^\d+\.\d{2}$/)
    expect(first?.price.currency).toBe('EUR')
    expect(first?.vendor.vendor_id).toBe('a-solid-veteran')
  })

  it('returns product details with bulk pricing', async () => {
    const res = await app.inject({ method: 'GET', url: '/mock-a/api/products/a-gloves-01' })
    expect(res.statusCode).toBe(200)
    const body = res.json<{ bulk_pricing: unknown[]; sku_group: string }>()
    expect(body.sku_group).toBe('nitrile-gloves-m-box100')
    expect(body.bulk_pricing.length).toBeGreaterThan(0)
  })

  it('exposes raw seller metrics, with nulls for signals the platform does not show', async () => {
    const solid = await app.inject({
      method: 'GET',
      url: '/mock-a/api/sellers/a-solid-veteran/metrics',
    })
    expect(solid.json()).toMatchObject({
      feedback: { count: 500, rated_orders: 500 },
      badges: { kyc: true },
    })
    const fresh = await app.inject({ method: 'GET', url: '/mock-a/api/sellers/a-new-shop/metrics' })
    expect(fresh.json()).toMatchObject({
      orders: { lifetime: null },
      feedback: { count: null },
      disputes_pct: null,
    })
  })

  it('returns 404 for unknown ids and for ids from the other platform', async () => {
    expect((await app.inject({ method: 'GET', url: '/mock-a/api/products/nope' })).statusCode).toBe(
      404
    )
    expect(
      (await app.inject({ method: 'GET', url: '/mock-a/api/products/b-gloves-01' })).statusCode
    ).toBe(404)
    expect(
      (await app.inject({ method: 'GET', url: '/mock-a/api/sellers/b-solid-factory' })).statusCode
    ).toBe(404)
  })

  it('runs a conversation over JSON', async () => {
    const open = await app.inject({
      method: 'POST',
      url: '/mock-a/api/conversations',
      payload: { vendor_id: 'a-solid-veteran', listing_id: 'a-gloves-01' },
    })
    expect(open.statusCode).toBe(201)
    const { conversation_id } = open.json<{ conversation_id: string }>()
    const sent = await app.inject({
      method: 'POST',
      url: `/mock-a/api/conversations/${conversation_id}/messages`,
      payload: { body: 'Hello, we need 5000 units. What volume tiers do you offer?' },
    })
    expect(sent.statusCode).toBe(201)
    const read = await app.inject({
      method: 'GET',
      url: `/mock-a/api/conversations/${conversation_id}/messages?after=1`,
    })
    const messages = read.json<{ messages: Array<{ from: string; body: string }> }>().messages
    expect(messages).toHaveLength(1)
    expect(messages[0]?.from).toBe('vendor')
    expect(messages[0]?.body).toMatch(/tiers/i)
  })

  it('rejects a conversation for a listing the vendor does not sell', async () => {
    const res = await app.inject({
      method: 'POST',
      url: '/mock-a/api/conversations',
      payload: { vendor_id: 'a-solid-veteran', listing_id: 'a-gloves-04' },
    })
    expect(res.statusCode).toBe(404)
  })
})

describe('mock-b HTML', () => {
  it('renders search results with stable hooks', async () => {
    const res = await app.inject({ method: 'GET', url: '/mock-b/search?q=nitrile+gloves' })
    expect(res.statusCode).toBe(200)
    expect(res.headers['content-type']).toMatch(/text\/html/)
    expect(res.body.match(/data-testid="result"/g)?.length ?? 0).toBeGreaterThanOrEqual(3)
    expect(res.body).toContain('data-currency="CNY"')
  })

  it('renders item and shop pages, omitting signals the seller does not expose', async () => {
    const item = await app.inject({ method: 'GET', url: '/mock-b/item/b-gloves-01' })
    expect(item.body).toContain('data-testid="tier"')
    expect(item.body).toContain('data-testid="contact-seller"')
    const shop = await app.inject({ method: 'GET', url: '/mock-b/shop/b-high-disputes' })
    expect(shop.body).toContain('data-testid="dispute-rate"')
    expect(shop.body).toMatch(/data-testid="member-since" data-value="\d{2}\/\d{2}\/\d{4}"/)
  })

  it('escapes HTML from fixtures and queries', async () => {
    const res = await app.inject({ method: 'GET', url: '/mock-b/search?q=%3Cscript%3E' })
    expect(res.body).not.toContain('<script>')
    expect(res.body).toContain('&lt;script&gt;')
  })

  it('runs a chat through plain HTML forms (post, redirect, render)', async () => {
    const open = await app.inject({
      method: 'POST',
      url: '/mock-b/chat',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      payload: 'seller=b-standard-coop&item=b-gloves-03',
    })
    expect(open.statusCode).toBe(303)
    const location = String(open.headers.location)
    expect(location).toMatch(/^\/mock-b\/chat\/chat-mock-b-\d{4}$/)
    const send = await app.inject({
      method: 'POST',
      url: `${location}/send`,
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      payload: 'text=Hello%2C+price+for+1000+units%3F',
    })
    expect(send.statusCode).toBe(303)
    const page = await app.inject({ method: 'GET', url: location })
    expect(page.body.match(/data-testid="message"/g)).toHaveLength(2)
    expect(page.body).toContain('data-role="seller"')
  })

  it('returns 404 pages for unknown items', async () => {
    const res = await app.inject({ method: 'GET', url: '/mock-b/item/a-gloves-01' })
    expect(res.statusCode).toBe(404)
    expect(res.body).toContain('data-testid="not-found"')
  })
})

describe('criterion 3 data', () => {
  it('a single query yields at least 3 offers from at least 2 platforms', async () => {
    const a = (
      await app.inject({ method: 'GET', url: '/mock-a/api/search?q=nitrile+gloves' })
    ).json<{
      total: number
    }>().total
    const b = (
      await app.inject({ method: 'GET', url: '/mock-b/search?q=nitrile+gloves' })
    ).body.match(/data-testid="result"/g)?.length
    expect(a).toBeGreaterThanOrEqual(3)
    expect(b).toBeGreaterThanOrEqual(3)
  })
})


describe('mock-c API-first marketplace', () => {
  it('searches with integer cents and a supplier block', async () => {
    const res = await app.inject({ method: 'GET', url: '/mock-c/api/search?q=nitrile%20gloves' })
    expect(res.statusCode).toBe(200)
    const body = res.json<{
      count: number
      items: Array<{
        item_id: string
        unit_price: { cents: number; currency: string }
        supplier_id: string
        min_order: number
      }>
    }>()
    expect(body.count).toBeGreaterThanOrEqual(3)
    const first = body.items[0]
    expect(first?.item_id).toBe('c-gloves-01')
    expect(first?.unit_price).toEqual({ cents: 432, currency: 'EUR' })
    expect(first?.supplier_id).toBe('c-solid-supplier')
    expect(first?.min_order).toBe(1000)
  })

  it('serves item detail with tiers and specs as name/value pairs', async () => {
    const res = await app.inject({ method: 'GET', url: '/mock-c/api/items/c-gloves-03' })
    expect(res.statusCode).toBe(200)
    const body = res.json<{
      tiers: Array<{ from: number; to: number | null; unit_price: { cents: number } }>
      specs: Array<{ name: string; value: string }>
      shipping: { cost: { cents: number } } | null
      incoterm: string | null
    }>()
    expect(body.tiers).toHaveLength(2)
    expect(body.tiers[1]?.unit_price.cents).toBe(421)
    expect(body.specs).toContainEqual({ name: 'material', value: 'nitrile' })
    expect(body.shipping?.cost.cents).toBe(1100)
    expect(body.incoterm).toBe('DAP')
  })

  it('reports seller metrics in basis points and keeps missing values null', async () => {
    const solid = await app.inject({ method: 'GET', url: '/mock-c/api/suppliers/c-solid-supplier/metrics' })
    expect(solid.statusCode).toBe(200)
    expect(solid.json()).toMatchObject({
      supplier_id: 'c-solid-supplier',
      repeat_rate_bp: 5200,
      response_rate_bp: 9700,
      reviews: { avg: 4.8, verified_bp: 9000 },
    })

    const thin = await app.inject({ method: 'GET', url: '/mock-c/api/suppliers/c-new-shop/metrics' })
    expect(thin.statusCode).toBe(200)
    expect(thin.json()).toMatchObject({
      supplier_id: 'c-new-shop',
      repeat_rate_bp: null,
      reviews: { avg: null },
    })
  })

  it('opens a thread, sends a message and returns the supplier answer', async () => {
    const open = await app.inject({
      method: 'POST',
      url: '/mock-c/api/threads',
      payload: { item_id: 'c-gloves-01' },
    })
    expect(open.statusCode).toBe(201)
    const { thread_id: threadId } = open.json<{ thread_id: string }>()
    expect(threadId).toMatch(/^chat-mock-c-/)

    const send = await app.inject({
      method: 'POST',
      url: `/mock-c/api/threads/${threadId}/messages`,
      payload: { body: 'Can you do EUR 4.10 for 5000 boxes?' },
    })
    expect(send.statusCode).toBe(201)
    const sent = send.json<{ sent: { seq: number; author: string }; received: Array<{ author: string }> }>()
    expect(sent.sent).toMatchObject({ seq: 1, author: 'buyer' })
    expect(sent.received.length).toBeGreaterThanOrEqual(1)
    expect(sent.received[0]?.author).toBe('supplier')

    const read = await app.inject({
      method: 'GET',
      url: `/mock-c/api/threads/${threadId}/messages?after_seq=1`,
    })
    const thread = read.json<{ messages: Array<{ seq: number; author: string }> }>()
    expect(thread.messages.length).toBeGreaterThanOrEqual(1)
    expect(thread.messages.every((m) => m.seq > 1)).toBe(true)
  })

  it('answers closed error codes for an unknown item, supplier or thread', async () => {
    const item = await app.inject({ method: 'GET', url: '/mock-c/api/items/nope' })
    expect(item.statusCode).toBe(404)
    expect(item.json()).toMatchObject({ error: { code: 'unknown_item' } })

    const supplier = await app.inject({ method: 'GET', url: '/mock-c/api/suppliers/nope/metrics' })
    expect(supplier.statusCode).toBe(404)
    expect(supplier.json()).toMatchObject({ error: { code: 'unknown_supplier' } })

    const thread = await app.inject({ method: 'GET', url: '/mock-c/api/threads/nope/messages' })
    expect(thread.statusCode).toBe(404)
    expect(thread.json()).toMatchObject({ error: { code: 'unknown_thread' } })
  })
})
