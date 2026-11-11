/**
 * mock-c wire -> contract raw shapes.
 *
 * Everything here is a pure function of the parsed response and the injected clock, so the mapping is testable
 * against recorded fixtures and repeats exactly.
 */

import type {
  ChatRole,
  Incoterm,
  Money,
  PriceTier,
  RawOffer,
  RawReview,
  RawSeller,
  RawSellerSignals,
  SkippedListing,
} from '@apex/shared-types/contracts/browser-worker'
import type { WorkerErrorCode } from '@apex/shared-types/contracts/browser-worker'

import type { Item, Metrics, Supplier, Summary, WireMessage } from './schemas.js'

export const PLATFORM = 'mock-c'

const SUPPORTED = new Set(['EUR', 'USD', 'CNY'])
const INCOTERMS = new Set([
  'EXW',
  'FCA',
  'FAS',
  'FOB',
  'CFR',
  'CIF',
  'CPT',
  'CIP',
  'DAP',
  'DPU',
  'DDP',
])

const CLOSED_ERRORS: Record<string, WorkerErrorCode> = {
  unknown_item: 'unknown_product',
  unknown_supplier: 'unknown_seller',
  unknown_thread: 'unknown_chat',
  invalid_message: 'validation_error',
  invalid_request: 'validation_error',
}

export function classifyMockCError(_status: number, body: string): WorkerErrorCode | undefined {
  let parsed: unknown
  try {
    parsed = JSON.parse(body)
  } catch {
    return undefined
  }
  if (typeof parsed !== 'object' || parsed === null || !('error' in parsed)) {
    return undefined
  }
  const err = (parsed).error
  const code = typeof err === 'object' && err !== null ? (err as { code?: unknown }).code : err
  return typeof code === 'string' && Object.hasOwn(CLOSED_ERRORS, code)
    ? CLOSED_ERRORS[code]
    : undefined
}

function money(amount: { cents: number; currency: string }): Money {
  return { amount_minor: amount.cents, currency: amount.currency as Money['currency'] }
}

function incotermOf(term: string | null): Incoterm | null {
  return term !== null && INCOTERMS.has(term) ? (term as Incoterm) : null
}

/** Basis points -> ratio. `null` stays `null`: the platform did not report it. */
export function ratioOf(bps: number | null): number | null {
  return bps === null ? null : bps / 10_000
}

export interface OfferContext {
  capturedAt: Date
  baseUrl: string
}

export function offerFromSummary(
  summary: Summary,
  context: OfferContext
): { offer: RawOffer } | { skip: SkippedListing } {
  if (!SUPPORTED.has(summary.unit_price.currency)) {
    return {
      skip: {
        platform_offer_id: summary.item_id,
        reason: 'unsupported_currency',
        currency_raw: summary.unit_price.currency,
      },
    }
  }
  return {
    offer: {
      platform: PLATFORM,
      platform_offer_id: summary.item_id,
      product_id: summary.item_id,
      platform_seller_id: summary.supplier_id,
      seller_name: summary.supplier_name,
      title: summary.title,
      product_url: `${context.baseUrl}/mock-c/api/items/${summary.item_id}`,
      unit_price: money(summary.unit_price),
      list_price: null,
      price_tiers: [],
      moq: summary.min_order,
      specifications: {},
      certifications: [],
      captured_at: context.capturedAt.toISOString(),
    },
  }
}

export function offerFromItem(item: Item, context: OfferContext): RawOffer {
  const tiers: PriceTier[] = item.tiers.map((tier) => ({
    min_quantity: tier.from,
    max_quantity: tier.to,
    unit_price: money(tier.unit_price),
  }))
  return {
    platform: PLATFORM,
    platform_offer_id: item.item_id,
    product_id: item.item_id,
    platform_seller_id: item.supplier_id,
    seller_name: item.supplier.name,
    title: item.title,
    product_url: `${context.baseUrl}/mock-c/api/items/${item.item_id}`,
    unit_price: money(item.unit_price),
    list_price: null,
    price_tiers: tiers,
    moq: item.min_order,
    specifications: Object.fromEntries(item.specs.map((s) => [s.name, s.value])),
    certifications: item.certifications,
    seller_country: item.supplier.country,
    shipping:
      item.shipping === null
        ? null
        : {
            cost: money(item.shipping.cost),
            min_days: item.shipping.min_days,
            max_days: item.shipping.max_days,
          },
    incoterm: incotermOf(item.incoterm),
    lead_time_days: item.lead_time_days,
    captured_at: context.capturedAt.toISOString(),
  }
}

export function sellerFrom(supplier: Supplier, context: OfferContext): RawSeller {
  return {
    platform: PLATFORM,
    platform_seller_id: supplier.supplier_id,
    display_name: supplier.name,
    country: supplier.country,
    profile_url: `${context.baseUrl}/mock-c/api/suppliers/${supplier.supplier_id}`,
    captured_at: context.capturedAt.toISOString(),
  }
}

export function daysSince(day: string | null, now: Date): number | null {
  if (day === null) {
    return null
  }
  const then = Date.parse(`${day}T00:00:00Z`)
  if (Number.isNaN(then)) {
    return null
  }
  return Math.max(0, Math.floor((now.getTime() - then) / 86_400_000))
}

export function signalsFrom(
  metrics: Metrics,
  context: OfferContext,
  options: { maxReviews: number; now: Date }
): RawSellerSignals {
  const reviews: RawReview[] = metrics.recent_reviews
    .slice(0, options.maxReviews)
    .map((review) => ({
      rating: review.rating,
      created_at: `${review.date}T00:00:00Z`,
      verified_purchase: review.verified,
      text: review.text,
    }))

  return {
    platform: PLATFORM,
    platform_seller_id: metrics.supplier_id,
    captured_at: context.capturedAt.toISOString(),
    account_age_days: daysSince(metrics.member_since, options.now),
    first_sale_date: metrics.first_order_at,
    months_active_last_12: metrics.months_active_12,
    lifetime_transactions: metrics.orders.total,
    transactions_12m: metrics.orders.last_12m,
    gmv_12m: metrics.revenue_12m === null ? null : money(metrics.revenue_12m),
    repeat_buyer_share: ratioOf(metrics.repeat_rate_bp),
    published_products_count: metrics.catalog.listings,
    catalog_churn_30d: ratioOf(metrics.catalog.churn_30d_bp),
    spec_completeness_avg: ratioOf(metrics.catalog.completeness_bp),
    reviews_total: metrics.reviews.total,
    reviews_12m: metrics.reviews.last_12m,
    rating_avg: metrics.reviews.avg,
    rating_count: metrics.reviews.count,
    verified_review_share: ratioOf(metrics.reviews.verified_bp),
    response_rate: ratioOf(metrics.response_rate_bp),
    identity_verified: metrics.identity_verified,
    trade_assurance: metrics.trade_assurance,
    escrow_available: metrics.escrow,
    dispute_rate: ratioOf(metrics.dispute_bp),
    refund_rate: ratioOf(metrics.refund_bp),
    recent_reviews: reviews,
  }
}

export function roleOf(author: WireMessage['author']): ChatRole {
  return author === 'supplier' ? 'seller' : 'buyer'
}

export function messageOf(message: WireMessage): {
  seq: number
  role: ChatRole
  text: string
  at: Date
} {
  return {
    seq: message.seq,
    role: roleOf(message.author),
    text: message.body,
    at: new Date(message.sent_at),
  }
}
