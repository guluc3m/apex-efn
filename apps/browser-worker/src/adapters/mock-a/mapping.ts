/**
 * Pure mapping from mock-a responses to contract DTOs. No I/O and no clock reads: the caller passes `now`.
 *
 * Signal mapping (mock-a field to RawSellerSignals field, with the unit conversion):
 *
 * | mock-a field                        | RawSellerSignals field       | Conversion                                        |
 * | ----------------------------------- | ---------------------------- | ------------------------------------------------- |
 * | metrics.registered_at (epoch s)     | account_age_days             | whole days between `now` and the epoch, null if negative |
 * | metrics.first_order_at (epoch s)    | first_sale_date              | UTC calendar date, YYYY-MM-DD                     |
 * | metrics.active_months_12            | months_active_last_12        | none                                              |
 * | metrics.orders.lifetime             | lifetime_transactions        | none                                              |
 * | metrics.orders.last_12m             | transactions_12m             | none                                              |
 * | metrics.turnover_12m {amount, cur.} | gmv_12m {amount_minor, cur.} | decimal string to minor units; null if cur. not EUR/USD/CNY |
 * | metrics.repeat_customers_pct        | repeat_buyer_share           | percent to ratio (one decimal, see ratioOf)       |
 * | metrics.catalog.listings            | published_products_count     | none                                              |
 * | metrics.catalog.churn_30d_pct       | catalog_churn_30d            | percent to ratio                                  |
 * | metrics.catalog.completeness_pct    | spec_completeness_avg        | percent to ratio                                  |
 * | metrics.feedback.count              | reviews_total                | none                                              |
 * | metrics.feedback.count_12m          | reviews_12m                  | none                                              |
 * | metrics.feedback.score_0_100        | rating_avg                   | 0 to 100 scale back to the 1 to 5 scale (see ratingOf) |
 * | metrics.feedback.rated_orders       | rating_count                 | none                                              |
 * | metrics.feedback.verified_pct       | verified_review_share        | percent to ratio                                  |
 * | metrics.reply_rate_pct              | response_rate                | percent to ratio                                  |
 * | metrics.badges.kyc                  | identity_verified            | none                                              |
 * | metrics.badges.buyer_protection     | trade_assurance              | none                                              |
 * | metrics.badges.escrow               | escrow_available             | none                                              |
 * | metrics.disputes_pct                | dispute_rate                 | percent to ratio                                  |
 * | metrics.refunds_pct                 | refund_rate                  | percent to ratio                                  |
 * | reviews[].stars / posted_at / verified_order / comment | recent_reviews | rating, created_at (ISO), verified_purchase, text (max 2000 chars) |
 *
 * Every mock field that is null stays null. A missing value is never turned into 0.
 */
import type {
  Currency,
  Incoterm,
  Money,
  PriceTier,
  RawOffer,
  RawReview,
  RawSeller,
  RawSellerSignals,
  SkipReason,
  SkippedListing,
  WorkerErrorCode,
} from '@apex/shared-types/contracts/browser-worker'

import type { Clock } from '../../clock.js'
import { WorkerError } from '../../errors.js'
import type { ChatMessageRecord } from '../index.js'
import { parseDecimalMinor, toContractCurrency } from '../money.js'

import type { MockMessage, MockMetrics, MockProduct, MockReviews, MockSeller } from './schemas.js'

const DAY_MS = 86_400_000
const MAX_REVIEW_TEXT = 2000
const INCOTERMS: readonly Incoterm[] = [
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
]

/** A listing whose price cannot become a Money. Search turns it into a `skipped` entry, getProduct into an error. */
export class ListingPriceError extends Error {
  constructor(
    readonly reason: SkipReason,
    readonly currencyRaw: string | null
  ) {
    super(reason)
    this.name = 'ListingPriceError'
  }
}

function minorOf(text: string): number {
  try {
    return parseDecimalMinor(text)
  } catch (error) {
    if (error instanceof WorkerError) {
      throw new ListingPriceError('parse_error', null)
    }
    throw error
  }
}

/** Decimal string plus platform currency to Money. Checks missing, then currency, then the amount text. */
export function moneyFrom(
  amount: string | null | undefined,
  currency: string | null | undefined
): Money {
  if (amount === null || amount === undefined || amount.trim() === '') {
    throw new ListingPriceError('missing_price', null)
  }
  const contractCurrency: Currency | null =
    currency === null || currency === undefined ? null : toContractCurrency(currency)
  if (contractCurrency === null) {
    throw new ListingPriceError('unsupported_currency', currency ?? null)
  }
  return { amount_minor: minorOf(amount), currency: contractCurrency }
}

/** Tells the caller which skip reason a listing price maps to. Null when the listing price is usable. */
export function listingPriceProblem(
  price: { amount: string | null; currency: string | null } | null
): ListingPriceError | null {
  try {
    moneyFrom(price?.amount, price?.currency)
    return null
  } catch (error) {
    if (error instanceof ListingPriceError) {
      return error
    }
    throw error
  }
}

/** Closed skip entry for a listing that cannot become an offer. */
export function skippedFrom(platformOfferId: string, error: ListingPriceError): SkippedListing {
  if (error.reason === 'unsupported_currency') {
    return {
      platform_offer_id: platformOfferId,
      reason: 'unsupported_currency',
      currency_raw: error.currencyRaw,
    }
  }
  return { platform_offer_id: platformOfferId, reason: error.reason }
}

/** getProduct cannot skip, so an unusable listing becomes a WorkerError with a closed code. */
export function workerErrorFor(error: ListingPriceError): WorkerError {
  if (error.reason === 'unsupported_currency') {
    return new WorkerError('upstream_error', 502, {
      retryable: false,
      detail: 'listing currency is not EUR, USD or CNY',
    })
  }
  if (error.reason === 'missing_price') {
    return new WorkerError('dom_changed', 502, { retryable: false, detail: 'listing has no price' })
  }
  return new WorkerError('dom_changed', 502, {
    retryable: false,
    detail: 'price text is not a decimal amount with at most 2 decimals',
  })
}

/**
 * The tier that applies to `quantity`, read from the platform's bulk pricing. Without a quantity, or when no tier
 * covers it (quantity below the first tier), the listed price is returned.
 */
export function unitPriceFor(tiers: PriceTier[], quantity: number | null, listed: Money): Money {
  if (quantity === null) {
    return listed
  }
  const tier = tiers.find(
    (candidate) =>
      quantity >= candidate.min_quantity &&
      quantity <= (candidate.max_quantity ?? Number.POSITIVE_INFINITY)
  )
  return tier?.unit_price ?? listed
}

export function incotermOf(term: string | null): Incoterm | null {
  return INCOTERMS.find((code) => code === term) ?? null
}

function shippingFrom(delivery: MockProduct['delivery']): RawOffer['shipping'] {
  if (delivery === null) {
    return null
  }
  const currency = toContractCurrency(delivery.currency)
  if (currency === null) {
    return null
  }
  return {
    cost: { amount_minor: minorOf(delivery.fee), currency },
    min_days: delivery.eta_days[0],
    max_days: delivery.eta_days[1],
    carrier: null,
  }
}

export interface OfferContext {
  platform: string
  baseUrl: string
  clock: Clock
  quantity: number | null
}

/** Full offer from a product detail. Throws ListingPriceError when a price cannot be represented. */
export function offerFrom(detail: MockProduct, context: OfferContext): RawOffer {
  const listed = moneyFrom(detail.price?.amount, detail.price?.currency)
  const priceTiers: PriceTier[] = detail.bulk_pricing
    .map((tier) => ({
      min_quantity: tier.from_qty,
      max_quantity: tier.to_qty,
      unit_price: moneyFrom(tier.price, listed.currency),
    }))
    .sort((a, b) => a.min_quantity - b.min_quantity)
  return {
    platform: context.platform,
    platform_offer_id: detail.listing_id,
    product_id: detail.listing_id,
    platform_seller_id: detail.vendor.vendor_id,
    seller_name: detail.vendor.display_name,
    title: detail.name,
    product_url: new URL(detail.url, context.baseUrl).toString(),
    unit_price: unitPriceFor(priceTiers, context.quantity, listed),
    list_price: null,
    price_tiers: priceTiers,
    moq: detail.min_order_qty,
    quantity_available: null,
    specifications: Object.fromEntries(detail.attributes.map((attr) => [attr.key, attr.value])),
    certifications: detail.certs,
    seller_country: null,
    shipping: shippingFrom(detail.delivery),
    incoterm: incotermOf(detail.trade_term),
    lead_time_days: detail.production_days,
    captured_at: context.clock.now().toISOString(),
  }
}

export function sellerFrom(seller: MockSeller, platform: string, clock: Clock): RawSeller {
  return {
    platform,
    platform_seller_id: seller.vendor_id,
    display_name: seller.display_name,
    country: seller.location,
    profile_url: null,
    captured_at: clock.now().toISOString(),
  }
}

function isoDateOf(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toISOString().slice(0, 10)
}

function isoDateTimeOf(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toISOString()
}

/** Whole days between the registration and `now`. Null when the registration lies in the future of the clock. */
export function accountAgeDays(registeredAt: number | null, now: Date): number | null {
  if (registeredAt === null) {
    return null
  }
  const days = Math.floor((now.getTime() - registeredAt * 1000) / DAY_MS)
  return days >= 0 ? days : null
}

/**
 * The mock publishes percentages with one decimal (`Math.round(share * 1000) / 10`), so multiplying by 10 gives an
 * integer and dividing by 1000 gives the ratio exactly.
 */
export function ratioOf(percent: number | null): number | null {
  return percent === null ? null : Math.round(percent * 10) / 1000
}

/**
 * The mock publishes `score_0_100 = round(((rating - 1) / 4) * 1000) / 10`. The error of that inverse is at most
 * 0.002, so rounding to two decimals returns the original rating for any rating with two decimals.
 */
export function ratingOf(score: number | null): number | null {
  return score === null ? null : Math.round((1 + (score * 4) / 100) * 100) / 100
}

/** Money for the GMV signal. A currency outside EUR/USD/CNY cannot be represented, so the signal is null. */
function gmvFrom(turnover: MockMetrics['turnover_12m']): Money | null {
  if (turnover === null) {
    return null
  }
  const currency = turnover.currency === null ? null : toContractCurrency(turnover.currency)
  if (currency === null) {
    return null
  }
  return { amount_minor: minorOf(turnover.amount), currency }
}

/** The most recent reviews first, undated reviews last. Ties keep the platform order. */
export function recentReviewsFrom(
  reviews: MockReviews['reviews'],
  maxReviews: number
): RawReview[] {
  return [...reviews]
    .sort((a, b) => (b.posted_at ?? -1) - (a.posted_at ?? -1))
    .slice(0, maxReviews)
    .map((review) => ({
      rating: review.stars,
      created_at: review.posted_at === null ? null : isoDateTimeOf(review.posted_at),
      verified_purchase: review.verified_order,
      text: review.comment === null ? null : review.comment.slice(0, MAX_REVIEW_TEXT),
    }))
}

export function signalsFrom(
  metrics: MockMetrics,
  reviews: MockReviews,
  context: { platform: string; sellerId: string; clock: Clock; maxReviews: number }
): RawSellerSignals {
  const now = context.clock.now()
  return {
    platform: context.platform,
    platform_seller_id: context.sellerId,
    captured_at: now.toISOString(),
    account_age_days: accountAgeDays(metrics.registered_at, now),
    first_sale_date: metrics.first_order_at === null ? null : isoDateOf(metrics.first_order_at),
    months_active_last_12: metrics.active_months_12,
    lifetime_transactions: metrics.orders.lifetime,
    transactions_12m: metrics.orders.last_12m,
    gmv_12m: gmvFrom(metrics.turnover_12m),
    repeat_buyer_share: ratioOf(metrics.repeat_customers_pct),
    published_products_count: metrics.catalog.listings,
    catalog_churn_30d: ratioOf(metrics.catalog.churn_30d_pct),
    spec_completeness_avg: ratioOf(metrics.catalog.completeness_pct),
    reviews_total: metrics.feedback.count,
    reviews_12m: metrics.feedback.count_12m,
    rating_avg: ratingOf(metrics.feedback.score_0_100),
    rating_count: metrics.feedback.rated_orders,
    verified_review_share: ratioOf(metrics.feedback.verified_pct),
    response_rate: ratioOf(metrics.reply_rate_pct),
    identity_verified: metrics.badges.kyc,
    trade_assurance: metrics.badges.buyer_protection,
    escrow_available: metrics.badges.escrow,
    dispute_rate: ratioOf(metrics.disputes_pct),
    refund_rate: ratioOf(metrics.refunds_pct),
    recent_reviews: recentReviewsFrom(reviews.reviews, context.maxReviews),
  }
}

/** The mock's `from` is `buyer` or `vendor`. Our contract calls the counterpart `seller`. */
export function chatRecordFrom(message: MockMessage): ChatMessageRecord {
  return {
    seq: message.id,
    role: message.from === 'buyer' ? 'buyer' : 'seller',
    text: message.body,
    at: new Date(message.sent_at * 1000),
  }
}

const CLOSED_ERRORS: Readonly<Record<string, WorkerErrorCode>> = {
  listing_not_found: 'unknown_product',
  unknown_product: 'unknown_product',
  vendor_not_found: 'unknown_seller',
  unknown_seller: 'unknown_seller',
  unknown_chat: 'unknown_chat',
  wrong_platform: 'validation_error',
  empty_message: 'validation_error',
  bad_request: 'validation_error',
  bad_query: 'validation_error',
}

/**
 * Maps the mock's `{"error": "..."}` body to a closed code. Unknown bodies return undefined, so the HTTP client uses its
 * default mapping. The body is read here and never copied into the error.
 */
export function classifyMockError(_status: number, body: string): WorkerErrorCode | undefined {
  let parsed: unknown
  try {
    parsed = JSON.parse(body)
  } catch {
    return undefined
  }
  if (typeof parsed !== 'object' || parsed === null || !('error' in parsed)) {
    return undefined
  }
  const code = parsed.error
  return typeof code === 'string' && Object.hasOwn(CLOSED_ERRORS, code)
    ? CLOSED_ERRORS[code]
    : undefined
}
