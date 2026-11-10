/**
 * HTML -> raw contract shapes for `mock-b`.
 *
 * The mapping is deliberately dumb: it reports what the page says, in the platform's own units and currency, and
 * never converts, scores or band-checks. A listing whose currency the contract does not support is not an offer:
 * it is reported as skipped (spec 3.4.1).
 */

import type {
  ChatRole,
  Money,
  PriceTier,
  RawOffer,
  RawReview,
  RawSeller,
  RawSellerSignals,
  SkippedListing,
} from '@apex/shared-types/contracts/browser-worker'

import {
  allByTestId,
  attr,
  booleanOf,
  byTestId,
  domChanged,
  intAttr,
  numberValue,
  optionalIntAttr,
  parseHtml,
  priceOf,
  ratioOf,
  requireAttr,
  requireByTestId,
  text,
  type Html,
} from './html.js'

export const PLATFORM = 'mock-b'
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

export interface PageContext {
  baseUrl: string
  capturedAt: Date
}

function absolute(baseUrl: string, path: string): string {
  return new URL(path, baseUrl).toString()
}

function money(minor: number, currency: string): Money {
  return { amount_minor: minor, currency: currency as Money['currency'] }
}

/**
 * Dates on this platform come in two shapes: the shop stats use `DD/MM/YYYY` (on purpose different from mock-a),
 * while reviews are already `YYYY-MM-DD`. Both are normalised to `YYYY-MM-DD`; anything else is `null`.
 */
export function isoDay(value: string): string | null {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value
  }
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value)
  if (match === null) {
    return null
  }
  const [, day, month, year] = match
  return `${year}-${month}-${day}`
}

/** Review dates are `date-time` in the contract; the platform only knows the day. */
export function isoInstant(value: string): string | null {
  const day = isoDay(value)
  return day === null ? null : `${day}T00:00:00Z`
}

export interface SearchPage {
  offers: RawOffer[]
  skipped: SkippedListing[]
}

/**
 * Search result cards. A card carries the id, seller, title, price and MOQ; the item page adds the rest, which the
 * worker fetches through `getProduct` when it needs it.
 */
export function searchResults(html: string, context: PageContext): SearchPage {
  const root = parseHtml(html)
  const offers: RawOffer[] = []
  const skipped: SkippedListing[] = []

  for (const card of allByTestId(root, 'result')) {
    const offerId = attr(card, 'data-item-id')
    const sellerId = attr(card, 'data-seller-id')
    if (offerId === null || sellerId === null) {
      throw domChanged('result id')
    }
    const priceElement = byTestId(card, 'price')
    if (priceElement === null) {
      skipped.push({ platform_offer_id: offerId, reason: 'missing_price' })
      continue
    }
    const price = priceOf(priceElement, 'price')
    if (!SUPPORTED.has(price.currency)) {
      skipped.push({
        platform_offer_id: offerId,
        reason: 'unsupported_currency',
        currency_raw: price.currency,
      })
      continue
    }
    const titleLink = card.querySelector('a.title')
    offers.push({
      platform: PLATFORM,
      platform_offer_id: offerId,
      product_id: offerId,
      platform_seller_id: sellerId,
      seller_name: text(card.querySelector('a.shop') ?? card),
      title: titleLink === null ? offerId : text(titleLink),
      product_url: absolute(context.baseUrl, `/mock-b/item/${encodeURIComponent(offerId)}`),
      unit_price: money(price.minor, price.currency),
      list_price: null,
      price_tiers: [],
      moq: moqOf(card),
      specifications: {},
      certifications: [],
      captured_at: context.capturedAt.toISOString(),
    })
  }
  return { offers, skipped }
}

function moqOf(card: Html): number {
  const element = byTestId(card, 'moq')
  if (element === null) {
    return 1
  }
  const digits = /\d+/.exec(text(element))
  return digits === null ? 1 : Number(digits[0])
}

/** The item page: everything the contract's `RawOffer` carries. */
export function offerFromItemPage(html: string, context: PageContext): RawOffer {
  const root = parseHtml(html)
  const article = requireByTestId(root, 'item')
  const offerId = requireAttr(article, 'data-item-id', 'item')
  const price = priceOf(requireByTestId(root, 'price'), 'price')
  if (!SUPPORTED.has(price.currency)) {
    throw domChanged('supported currency on item')
  }
  const sellerLink = requireByTestId(root, 'seller-link')
  const sellerPath = requireAttr(sellerLink, 'href', 'seller-link')
  const sellerId = sellerPath.split('/').filter(Boolean).at(-1)
  if (sellerId === undefined) {
    throw domChanged('seller id on seller-link')
  }

  const specifications: Record<string, string> = {}
  for (const row of root.querySelectorAll('tr[data-spec]')) {
    const key = attr(row, 'data-spec')
    const value = row.querySelector('td')
    if (key !== null && value !== null) {
      specifications[key] = text(value)
    }
  }

  const tiers: PriceTier[] = []
  for (const tier of allByTestId(root, 'tier')) {
    const min = intAttr(tier, 'data-min', 'tier')
    const max = optionalIntAttr(tier, 'data-max')
    const minor = intAttr(tier, 'data-minor', 'tier')
    tiers.push({
      min_quantity: min,
      max_quantity: max,
      unit_price: money(minor, price.currency),
    })
  }

  const incotermRaw = attr(requireByTestId(root, 'incoterm'), 'data-value') ?? ''
  const certifications = allByTestId(root, 'certifications')
    .flatMap((list) => list.querySelectorAll('li'))
    .map((item) => text(item))

  return {
    platform: PLATFORM,
    platform_offer_id: offerId,
    product_id: offerId,
    platform_seller_id: sellerId,
    seller_name: text(sellerLink),
    title: text(requireByTestId(root, 'title')),
    product_url: absolute(context.baseUrl, `/mock-b/item/${encodeURIComponent(offerId)}`),
    unit_price: money(price.minor, price.currency),
    list_price: null,
    price_tiers: tiers,
    moq: numberValue(requireByTestId(root, 'moq')) ?? 1,
    specifications,
    certifications,
    shipping: shippingOf(root, price.currency),
    incoterm: INCOTERMS.has(incotermRaw)
      ? (incotermRaw as RawOffer['incoterm'])
      : null,
    lead_time_days: numberValue(requireByTestId(root, 'lead-time')),
    captured_at: context.capturedAt.toISOString(),
  }
}

function shippingOf(root: Html, currency: string): RawOffer['shipping'] {
  const element = requireByTestId(root, 'shipping')
  if (attr(element, 'data-none') === 'true') {
    return null
  }
  return {
    cost: money(intAttr(element, 'data-minor', 'shipping'), currency),
    min_days: intAttr(element, 'data-min-days', 'shipping'),
    max_days: intAttr(element, 'data-max-days', 'shipping'),
  }
}

export function sellerFromShopPage(html: string, context: PageContext): RawSeller {
  const root = parseHtml(html)
  const shop = requireByTestId(root, 'shop')
  const sellerId = requireAttr(shop, 'data-seller-id', 'shop')
  return {
    platform: PLATFORM,
    platform_seller_id: sellerId,
    display_name: text(requireByTestId(root, 'shop-name')),
    country: attr(requireByTestId(root, 'country'), 'data-value') || null,
    profile_url: absolute(context.baseUrl, `/mock-b/shop/${encodeURIComponent(sellerId)}`),
    captured_at: context.capturedAt.toISOString(),
  }
}

/**
 * Seller signals from the shop page. Percentages are the platform's own ("30%"), dates are `DD/MM/YYYY`, and the
 * account age is computed against the clock the caller injected; nothing here guesses a missing value.
 */
export function signalsFromShopPage(
  html: string,
  context: PageContext,
  options: { maxReviews: number; now: Date }
): RawSellerSignals {
  const root = parseHtml(html)
  const sellerId = requireAttr(requireByTestId(root, 'shop'), 'data-seller-id', 'shop')
  const memberSince = attr(requireByTestId(root, 'member-since'), 'data-value')
  const firstSale = attr(requireByTestId(root, 'first-sale'), 'data-value')
  const ratingText = attr(requireByTestId(root, 'rating'), 'data-value') ?? ''
  const ratingMatch = /^(\d+(?:\.\d+)?)\s*\/\s*5$/.exec(ratingText)

  const reviews: RawReview[] = []
  for (const item of allByTestId(root, 'review').slice(0, options.maxReviews)) {
    const rating = Number(attr(item, 'data-rating'))
    const date = attr(item, 'data-date')
    const verified = attr(item, 'data-verified')
    const body = item.querySelector('p')
    reviews.push({
      rating: Number.isFinite(rating) ? rating : 0,
      created_at: date === null ? null : isoInstant(date),
      verified_purchase: verified === null ? null : verified === 'true',
      text: body === null ? null : text(body),
    })
  }

  return {
    platform: PLATFORM,
    platform_seller_id: sellerId,
    captured_at: context.capturedAt.toISOString(),
    account_age_days: memberSince === null ? null : daysSince(isoDay(memberSince), options.now),
    first_sale_date: firstSale === null ? null : isoDay(firstSale),
    months_active_last_12: numberValue(requireByTestId(root, 'months-active')),
    lifetime_transactions: numberValue(requireByTestId(root, 'orders-total')),
    transactions_12m: numberValue(requireByTestId(root, 'orders-12m')),
    gmv_12m: gmvOf(root),
    repeat_buyer_share: ratioOf(requireByTestId(root, 'repeat-buyers'), 'repeat-buyers'),
    published_products_count: numberValue(requireByTestId(root, 'listings')),
    catalog_churn_30d: ratioOf(requireByTestId(root, 'catalog-churn'), 'catalog-churn'),
    spec_completeness_avg: ratioOf(
      requireByTestId(root, 'spec-completeness'),
      'spec-completeness'
    ),
    reviews_total: numberValue(requireByTestId(root, 'reviews-total')),
    reviews_12m: numberValue(requireByTestId(root, 'reviews-12m')),
    rating_avg: ratingMatch?.[1] === undefined ? null : Number(ratingMatch[1]),
    rating_count: numberValue(requireByTestId(root, 'rating-count')),
    verified_review_share: ratioOf(
      requireByTestId(root, 'verified-reviews'),
      'verified-reviews'
    ),
    response_rate: ratioOf(requireByTestId(root, 'response-rate'), 'response-rate'),
    identity_verified: booleanOf(requireByTestId(root, 'identity-verified')),
    trade_assurance: booleanOf(requireByTestId(root, 'trade-assurance')),
    escrow_available: booleanOf(requireByTestId(root, 'escrow')),
    dispute_rate: ratioOf(requireByTestId(root, 'dispute-rate'), 'dispute-rate'),
    refund_rate: ratioOf(requireByTestId(root, 'refund-rate'), 'refund-rate'),
    recent_reviews: reviews,
  }
}

function gmvOf(root: Html): Money | null {
  const element = byTestId(root, 'gmv-12m')
  if (element === null) {
    return null
  }
  const raw = attr(element, 'data-value')
  if (raw === null) {
    return null
  }
  const currency = raw.startsWith('€')
    ? 'EUR'
    : raw.startsWith('$')
      ? 'USD'
      : raw.startsWith('¥')
        ? 'CNY'
        : null
  const amount = Number(raw.replace(/[^0-9.]/g, ''))
  if (currency === null || !Number.isFinite(amount)) {
    return null
  }
  return { amount_minor: Math.round(amount * 100), currency: currency }
}

function daysSince(day: string | null, now: Date): number | null {
  if (day === null) {
    return null
  }
  const then = Date.parse(`${day}T00:00:00Z`)
  if (Number.isNaN(then)) {
    return null
  }
  return Math.max(0, Math.floor((now.getTime() - then) / 86_400_000))
}

export interface ChatSnapshot {
  platformChatId: string
  messages: Array<{ seq: number; role: ChatRole; text: string; at: Date }>
}

export function chatFromPage(html: string): ChatSnapshot {
  const root = parseHtml(html)
  const section = requireByTestId(root, 'chat')
  const messages = allByTestId(root, 'message').map((item) => {
    const role: ChatRole =
      requireAttr(item, 'data-role', 'message') === 'seller' ? 'seller' : 'buyer'
    return {
      seq: intAttr(item, 'data-seq', 'message'),
      role,
      text: text(requireByTestId(item, 'message-text')),
      at: new Date(requireAttr(item, 'data-at', 'message')),
    }
  })
  return {
    platformChatId: requireAttr(section, 'data-chat-id', 'chat'),
    messages,
  }
}
