import type { FastifyInstance } from 'fastify'
import { z } from 'zod'

import { findProduct, findSeller, search, sellerProducts } from '../catalog.js'
import { ChatError, type ChatEngine, type ChatMessage } from '../chat/engine.js'
import type { Catalog, Product, Seller } from '../fixtures/schema.js'

/**
 * mock-a: a JSON API with its own snake_case vocabulary (not our contract's). Money is a decimal
 * string plus currency, dates are epoch seconds, ratings are on a 0-100 scale. Adapters must map it.
 */

const P = 'mock-a'

function decimal(minor: number): string {
  return (minor / 100).toFixed(2)
}

function epoch(iso: string | undefined): number | null {
  return iso === undefined ? null : Math.floor(Date.parse(`${iso}T00:00:00Z`) / 1000)
}

function listing(p: Product, seller: Seller | undefined) {
  return {
    listing_id: p.id,
    name: p.title,
    url: `/mock-a/api/products/${p.id}`,
    price: { amount: decimal(p.unitPriceMinor), currency: p.currency },
    min_order_qty: p.moq,
    vendor: { vendor_id: p.sellerId, display_name: seller?.name ?? null },
  }
}

function productDetail(p: Product, seller: Seller | undefined) {
  return {
    ...listing(p, seller),
    sku_group: p.productKey,
    details: p.description,
    attributes: Object.entries(p.specifications).map(([key, value]) => ({ key, value })),
    certs: p.certifications,
    images: p.imageUrls,
    bulk_pricing: p.priceTiers.map((t) => ({
      from_qty: t.minQuantity,
      to_qty: t.maxQuantity,
      price: decimal(t.unitPriceMinor),
    })),
    delivery: p.shipping
      ? {
          fee: decimal(p.shipping.costMinor),
          currency: p.currency,
          eta_days: [p.shipping.minDays, p.shipping.maxDays],
        }
      : null,
    trade_term: p.incoterm,
    production_days: p.leadTimeDays,
  }
}

function vendorMetrics(s: Seller) {
  const g = s.signals
  const pct = (v: number | undefined) => (v === undefined ? null : Math.round(v * 1000) / 10)
  return {
    vendor_id: s.id,
    registered_at: epoch(g.memberSince),
    first_order_at: epoch(g.firstSaleDate),
    active_months_12: g.monthsActiveLast12 ?? null,
    orders: { lifetime: g.lifetimeTransactions ?? null, last_12m: g.transactions12m ?? null },
    turnover_12m:
      g.gmv12mMinor === undefined
        ? null
        : { amount: decimal(g.gmv12mMinor), currency: g.gmvCurrency ?? null },
    repeat_customers_pct: pct(g.repeatBuyerShare),
    catalog: {
      listings: g.publishedProductsCount ?? null,
      churn_30d_pct: pct(g.catalogChurn30d),
      completeness_pct: pct(g.specCompletenessAvg),
    },
    feedback: {
      count: g.reviewsTotal ?? null,
      count_12m: g.reviews12m ?? null,
      score_0_100:
        g.ratingAvg === undefined ? null : Math.round(((g.ratingAvg - 1) / 4) * 1000) / 10,
      rated_orders: g.ratingCount ?? null,
      verified_pct: pct(g.verifiedReviewShare),
    },
    reply_rate_pct: pct(g.responseRate),
    badges: {
      kyc: g.identityVerified ?? null,
      buyer_protection: g.tradeAssurance ?? null,
      escrow: g.escrowAvailable ?? null,
    },
    disputes_pct: pct(g.disputeRate),
    refunds_pct: pct(g.refundRate),
  }
}

function message(m: ChatMessage) {
  return {
    id: m.seq,
    from: m.role === 'buyer' ? 'buyer' : 'vendor',
    body: m.text,
    sent_at: Math.floor(Date.parse(m.at) / 1000),
  }
}

function chatError(e: unknown) {
  if (e instanceof ChatError) {
    const status = e.code === 'empty_message' || e.code === 'wrong_platform' ? 400 : 404
    return { status, body: { error: e.code, message: e.message } }
  }
  throw e
}

const SearchQuery = z.object({
  q: z.string().default(''),
  page: z.coerce.number().int().min(1).default(1),
})
const OpenChat = z.object({ vendor_id: z.string(), listing_id: z.string() })
const SendMessage = z.object({ body: z.string() })
const ReadQuery = z.object({ after: z.coerce.number().int().min(0).default(0) })
const PAGE_SIZE = 20

export function registerMockA(app: FastifyInstance, catalog: Catalog, chats: ChatEngine): void {
  const sellers = new Map(catalog.sellers.map((s) => [s.id, s]))

  app.get('/mock-a/api/search', async (req, reply) => {
    const parsed = SearchQuery.safeParse(req.query)
    if (!parsed.success) return reply.code(400).send({ error: 'bad_query' })
    const all = search(catalog, P, parsed.data.q)
    const start = (parsed.data.page - 1) * PAGE_SIZE
    return {
      query: parsed.data.q,
      total: all.length,
      page: parsed.data.page,
      results: all.slice(start, start + PAGE_SIZE).map((p) => listing(p, sellers.get(p.sellerId))),
    }
  })

  app.get<{ Params: { id: string } }>('/mock-a/api/products/:id', async (req, reply) => {
    const p = findProduct(catalog, P, req.params.id)
    if (!p) return reply.code(404).send({ error: 'listing_not_found' })
    return productDetail(p, sellers.get(p.sellerId))
  })

  app.get<{ Params: { id: string } }>('/mock-a/api/sellers/:id', async (req, reply) => {
    const s = findSeller(catalog, P, req.params.id)
    if (!s) return reply.code(404).send({ error: 'vendor_not_found' })
    return {
      vendor_id: s.id,
      display_name: s.name,
      location: s.country,
      listings: sellerProducts(catalog, s.id).map((p) => p.id),
    }
  })

  app.get<{ Params: { id: string } }>('/mock-a/api/sellers/:id/metrics', async (req, reply) => {
    const s = findSeller(catalog, P, req.params.id)
    if (!s) return reply.code(404).send({ error: 'vendor_not_found' })
    return vendorMetrics(s)
  })

  app.get<{ Params: { id: string } }>('/mock-a/api/sellers/:id/reviews', async (req, reply) => {
    const s = findSeller(catalog, P, req.params.id)
    if (!s) return reply.code(404).send({ error: 'vendor_not_found' })
    return {
      vendor_id: s.id,
      reviews: s.reviews.map((r) => ({
        review_id: r.id,
        stars: r.rating,
        comment: r.text,
        posted_at: epoch(r.date),
        verified_order: r.verified,
      })),
    }
  })

  app.post('/mock-a/api/conversations', async (req, reply) => {
    const parsed = OpenChat.safeParse(req.body)
    if (!parsed.success) return reply.code(400).send({ error: 'bad_request' })
    try {
      const chat = chats.open(P, parsed.data.vendor_id, parsed.data.listing_id)
      return reply.code(201).send({ conversation_id: chat.id })
    } catch (e) {
      const { status, body } = chatError(e)
      return reply.code(status).send(body)
    }
  })

  app.post<{ Params: { id: string } }>(
    '/mock-a/api/conversations/:id/messages',
    async (req, reply) => {
      const parsed = SendMessage.safeParse(req.body)
      if (!parsed.success) return reply.code(400).send({ error: 'bad_request' })
      try {
        if (chats.get(req.params.id).platform !== P)
          return reply.code(404).send({ error: 'unknown_chat' })
        const [sent] = chats.send(req.params.id, parsed.data.body)
        return reply.code(201).send({ message: sent ? message(sent) : null })
      } catch (e) {
        const { status, body } = chatError(e)
        return reply.code(status).send(body)
      }
    }
  )

  app.get<{ Params: { id: string } }>(
    '/mock-a/api/conversations/:id/messages',
    async (req, reply) => {
      const parsed = ReadQuery.safeParse(req.query)
      if (!parsed.success) return reply.code(400).send({ error: 'bad_query' })
      try {
        if (chats.get(req.params.id).platform !== P)
          return reply.code(404).send({ error: 'unknown_chat' })
        return {
          conversation_id: req.params.id,
          messages: chats.read(req.params.id, parsed.data.after).map(message),
        }
      } catch (e) {
        const { status, body } = chatError(e)
        return reply.code(status).send(body)
      }
    }
  )
}
