import type { IncomingHttpHeaders } from 'node:http'

import type { FastifyInstance, FastifyReply } from 'fastify'
import { z } from 'zod'

import { findProduct, findSeller, search } from '../catalog.js'
import { ChatError, type ChatEngine, type ChatMessage } from '../chat/engine.js'
import { createLlmPhraser, type ChatPhraser } from '../chat/phraser.js'
import type { Catalog, Product, Seller } from '../fixtures/schema.js'

/**
 * mock-c: an API-first B2B marketplace.
 *
 * Where mock-a speaks decimal strings and epoch seconds and mock-b is a form-driven HTML site, mock-c is the
 * shape we would consume from a *sanctioned* platform API: search and item endpoints with integer cents, seller
 * metrics in basis points, and a **threads/messages** resource for negotiation — the buyer asks, the supplier
 * answers, no browser and no login involved.
 *
 * The seller side is the same persona engine as the other platforms, so the negotiation, adversarial and
 * autonomous-mode suites can run against it.
 */

const P = 'mock-c'
const PREFIX = '/mock-c/api'

const OpenThread = z.object({ item_id: z.string().min(1), buyer_id: z.string().min(1).optional() }).strict()
const SendMessage = z.object({ body: z.string().min(1).max(2000) }).strict()

interface Thread {
  id: string
  chatId: string
  itemId: string
  supplierId: string
  /** Empty string for a caller that does not identify its buyer (the adapter path). */
  buyerId: string
}

function money(minor: number, currency: string) {
  return { cents: minor, currency }
}

function bp(share: number | undefined): number | null {
  return share === undefined ? null : Math.round(share * 10_000)
}

function error(reply: FastifyReply, code: string, status: number): FastifyReply {
  return reply.code(status).send({ error: { code, message: code.replaceAll('_', ' ') } })
}

function summary(p: Product, seller: Seller | undefined) {
  return {
    item_id: p.id,
    title: p.title,
    unit_price: money(p.unitPriceMinor, p.currency),
    min_order: p.moq,
    supplier_id: p.sellerId,
    supplier_name: seller?.name ?? null,
    url: `${PREFIX}/items/${p.id}`,
  }
}

function itemDetail(p: Product, seller: Seller | undefined) {
  return {
    ...summary(p, seller),
    description: p.description,
    supplier: {
      supplier_id: p.sellerId,
      name: seller?.name ?? null,
      country: seller?.country ?? null,
    },
    tiers: p.priceTiers.map((t) => ({
      from: t.minQuantity,
      to: t.maxQuantity,
      unit_price: money(t.unitPriceMinor, p.currency),
    })),
    specs: Object.entries(p.specifications).map(([name, value]) => ({ name, value })),
    certifications: p.certifications,
    shipping: p.shipping
      ? {
          cost: money(p.shipping.costMinor, p.currency),
          min_days: p.shipping.minDays,
          max_days: p.shipping.maxDays,
        }
      : null,
    incoterm: p.incoterm,
    lead_time_days: p.leadTimeDays,
  }
}

function supplier(s: Seller) {
  return {
    supplier_id: s.id,
    name: s.name,
    country: s.country,
    member_since: s.signals.memberSince ?? null,
    profile_url: `${PREFIX}/suppliers/${s.id}`,
  }
}

function metrics(s: Seller) {
  const g = s.signals
  return {
    supplier_id: s.id,
    member_since: g.memberSince ?? null,
    first_order_at: g.firstSaleDate ?? null,
    months_active_12: g.monthsActiveLast12 ?? null,
    orders: {
      total: g.lifetimeTransactions ?? null,
      last_12m: g.transactions12m ?? null,
    },
    revenue_12m:
      g.gmv12mMinor === undefined ? null : money(g.gmv12mMinor, g.gmvCurrency ?? 'EUR'),
    repeat_rate_bp: bp(g.repeatBuyerShare),
    catalog: {
      listings: g.publishedProductsCount ?? null,
      churn_30d_bp: bp(g.catalogChurn30d),
      completeness_bp: bp(g.specCompletenessAvg),
    },
    reviews: {
      total: g.reviewsTotal ?? null,
      last_12m: g.reviews12m ?? null,
      avg: g.ratingAvg ?? null,
      count: g.ratingCount ?? null,
      verified_bp: bp(g.verifiedReviewShare),
    },
    response_rate_bp: bp(g.responseRate),
    identity_verified: g.identityVerified ?? null,
    trade_assurance: g.tradeAssurance ?? null,
    escrow: g.escrowAvailable ?? null,
    dispute_bp: bp(g.disputeRate),
    refund_bp: bp(g.refundRate),
    recent_reviews: s.reviews.map((r) => ({
      rating: r.rating,
      date: r.date,
      verified: r.verified,
      text: r.text,
    })),
  }
}

function wire(m: ChatMessage) {
  return {
    seq: m.seq,
    author: m.role === 'seller' ? 'supplier' : 'buyer',
    body: m.text,
    sent_at: Date.parse(m.at),
  }
}

/** First value of a request header, trimmed; `undefined` when absent or blank. */
function headerText(value: string | string[] | undefined): string | undefined {
  const first = Array.isArray(value) ? value[0] : value
  const text = first?.trim()
  return text === undefined || text.length === 0 ? undefined : text
}

/**
 * Per-request provider configuration for the seller wording (`x-sim-llm-*`).
 *
 * The orchestrator sim sends these so one demo can use a real model without restarting the marketplace.
 * No URL header means the process-wide `SIM_LLM_*` phraser the engine was built with. The key is only
 * handed to the provider: never logged, never echoed in a response or an error.
 */
function requestPhraser(headers: IncomingHttpHeaders): ChatPhraser | undefined {
  const url = headerText(headers['x-sim-llm-url'])
  if (url === undefined) return undefined
  const apiKey = headerText(headers['x-sim-llm-key'])
  const model = headerText(headers['x-sim-llm-model'])
  return createLlmPhraser(url, {
    apiKey,
    model,
    scenario: apiKey ? null : 'sim-negotiation',
    timeoutMs: apiKey ? 8000 : undefined,
  })
}

export function registerMockC(app: FastifyInstance, catalog: Catalog, chats: ChatEngine): void {
  const threads = new Map<string, Thread>()

  app.get<{ Querystring: { q?: string; limit?: string } }>(`${PREFIX}/search`, (req) => {
    const q = typeof req.query.q === 'string' ? req.query.q : ''
    const limit = Math.min(Math.max(Number(req.query.limit ?? 20) || 20, 1), 50)
    const found = search(catalog, P, q)
    return {
      query: q,
      count: found.length,
      items: found.slice(0, limit).map((p) => summary(p, findSeller(catalog, P, p.sellerId))),
    }
  })

  app.get<{ Params: { id: string } }>(`${PREFIX}/items/:id`, async (req, reply) => {
    const product = findProduct(catalog, P, req.params.id)
    if (product === undefined) return error(reply, 'unknown_item', 404)
    return itemDetail(product, findSeller(catalog, P, product.sellerId))
  })

  app.get<{ Params: { id: string } }>(`${PREFIX}/suppliers/:id`, async (req, reply) => {
    const seller = findSeller(catalog, P, req.params.id)
    if (seller === undefined) return error(reply, 'unknown_supplier', 404)
    return supplier(seller)
  })

  app.get<{ Params: { id: string } }>(`${PREFIX}/suppliers/:id/metrics`, async (req, reply) => {
    const seller = findSeller(catalog, P, req.params.id)
    if (seller === undefined) return error(reply, 'unknown_supplier', 404)
    return metrics(seller)
  })

  /** Opens (or returns) the negotiation thread for an item. One thread per item; the buyer is the caller. */
  app.post(`${PREFIX}/threads`, async (req, reply) => {
    const parsed = OpenThread.safeParse(req.body)
    if (!parsed.success) return error(reply, 'invalid_request', 400)
    const product = findProduct(catalog, P, parsed.data.item_id)
    if (product === undefined) return error(reply, 'unknown_item', 404)
    // A thread belongs to one buyer: two buyers negotiating the same item are two conversations.
    const buyer = parsed.data.buyer_id ?? ''
    const existing = [...threads.values()].find(
      (t) => t.itemId === product.id && t.buyerId === buyer
    )
    if (existing !== undefined) {
      return reply.code(200).send({ thread_id: existing.id, supplier_id: existing.supplierId, item_id: product.id })
    }
    try {
      const chat = chats.open(P, product.sellerId, product.id)
      const thread: Thread = {
        id: chat.id,
        chatId: chat.id,
        itemId: product.id,
        supplierId: product.sellerId,
        buyerId: buyer,
      }
      threads.set(thread.id, thread)
      return reply.code(201).send({ thread_id: thread.id, supplier_id: thread.supplierId, item_id: product.id })
    } catch (e) {
      if (e instanceof ChatError) return error(reply, e.code, 404)
      throw e
    }
  })

  app.get<{ Params: { id: string }; Querystring: { after_seq?: string } }>(
    `${PREFIX}/threads/:id/messages`,
    async (req, reply) => {
      const thread = threads.get(req.params.id)
      if (thread === undefined) return error(reply, 'unknown_thread', 404)
      const after = Number(req.query.after_seq ?? 0) || 0
      const snapshot = chats.snapshot(thread.chatId)
      return {
        thread_id: thread.id,
        messages: snapshot.messages.filter((m) => m.seq > after).map(wire),
      }
    }
  )

  app.post<{ Params: { id: string } }>(`${PREFIX}/threads/:id/messages`, async (req, reply) => {
    const thread = threads.get(req.params.id)
    if (thread === undefined) return error(reply, 'unknown_thread', 404)
    const parsed = SendMessage.safeParse(req.body)
    if (!parsed.success) return error(reply, 'invalid_message', 400)
    // Built per request and passed by value: no shared state, so one session's key never reaches another.
    const phraser = requestPhraser(req.headers)
    try {
      const produced = await chats.send(thread.chatId, parsed.data.body, phraser)
      const [sent] = produced
      const received = produced.slice(1)
      return reply.code(201).send({
        sent: sent === undefined ? null : wire(sent),
        received: received.map(wire),
      })
    } catch (e) {
      if (e instanceof ChatError) return error(reply, e.code, 400)
      throw e
    }
  })
}
