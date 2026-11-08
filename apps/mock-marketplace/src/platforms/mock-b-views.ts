import type { ChatMessage, ChatSnapshot } from '../chat/engine.js'
import type { Product, Seller } from '../fixtures/schema.js'
import { formatMinor } from '../money.js'

/**
 * mock-b renders server-side HTML with no client JavaScript, so it is crawlable by a plain HTTP crawler
 * and drivable by Playwright through ordinary forms. Data lives in the markup and in stable
 * `data-testid` / `data-*` hooks. Text formats differ from mock-a on purpose (dates as DD/MM/YYYY,
 * prices with a symbol), so adapters must do real parsing.
 */

const SYMBOL: Readonly<Record<string, string>> = { EUR: '€', USD: '$', CNY: '¥', GBP: '£' }

export function esc(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function price(minor: number, currency: string): string {
  return `${SYMBOL[currency] ?? `${currency} `}${formatMinor(minor)}`
}

function euDate(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}`
}

function page(title: string, body: string): string {
  return `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>${esc(title)} | MockBazaar</title></head>
<body>
<header><a href="/mock-b/">MockBazaar</a> <em>synthetic test marketplace</em></header>
<main>
${body}
</main>
</body>
</html>`
}

export function homePage(): string {
  return page(
    'Home',
    `<form action="/mock-b/search" method="get" data-testid="search-form">
  <input name="q" data-testid="search-input" placeholder="Search products">
  <button type="submit" data-testid="search-submit">Search</button>
</form>`
  )
}

export function searchPage(
  query: string,
  products: readonly Product[],
  sellers: ReadonlyMap<string, Seller>
): string {
  const items = products
    .map((p) => {
      const s = sellers.get(p.sellerId)
      return `  <li class="result" data-testid="result" data-item-id="${esc(p.id)}" data-seller-id="${esc(p.sellerId)}">
    <a class="title" href="/mock-b/item/${esc(p.id)}">${esc(p.title)}</a>
    <span class="price" data-testid="price" data-minor="${p.unitPriceMinor}" data-currency="${esc(p.currency)}">${esc(price(p.unitPriceMinor, p.currency))}</span>
    <span class="moq" data-testid="moq">Min. order: ${p.moq} units</span>
    <a class="shop" href="/mock-b/shop/${esc(p.sellerId)}">${esc(s?.name ?? p.sellerId)}</a>
  </li>`
    })
    .join('\n')
  return page(
    `Search: ${query}`,
    `<h1>Results for "${esc(query)}"</h1>
<p data-testid="result-count">${products.length} results</p>
<ul class="results" data-testid="results">
${items}
</ul>`
  )
}

export function itemPage(p: Product, seller: Seller): string {
  const specs = Object.entries(p.specifications)
    .map(([k, v]) => `    <tr data-spec="${esc(k)}"><th>${esc(k)}</th><td>${esc(v)}</td></tr>`)
    .join('\n')
  const tiers = p.priceTiers
    .map(
      (t) =>
        `    <tr data-testid="tier" data-min="${t.minQuantity}" data-max="${t.maxQuantity ?? ''}" data-minor="${t.unitPriceMinor}"><td>${t.minQuantity}${t.maxQuantity === null ? '+' : ` - ${t.maxQuantity}`}</td><td>${esc(price(t.unitPriceMinor, p.currency))}</td></tr>`
    )
    .join('\n')
  const shipping = p.shipping
    ? `<p data-testid="shipping" data-minor="${p.shipping.costMinor}" data-min-days="${p.shipping.minDays}" data-max-days="${p.shipping.maxDays}">Shipping: ${esc(price(p.shipping.costMinor, p.currency))}, ${p.shipping.minDays}-${p.shipping.maxDays} days</p>`
    : '<p data-testid="shipping" data-none="true">Shipping: contact seller</p>'
  return page(
    p.title,
    `<article data-testid="item" data-item-id="${esc(p.id)}" data-product-key="${esc(p.productKey)}">
  <h1 data-testid="title">${esc(p.title)}</h1>
  <p data-testid="price" data-minor="${p.unitPriceMinor}" data-currency="${esc(p.currency)}">${esc(price(p.unitPriceMinor, p.currency))} / unit</p>
  <p data-testid="moq" data-value="${p.moq}">Min. order: ${p.moq} units</p>
  <p data-testid="description">${esc(p.description)}</p>
  <table data-testid="specs">
${specs}
  </table>
  <table data-testid="tiers">
${tiers}
  </table>
  ${shipping}
  <p data-testid="incoterm" data-value="${esc(p.incoterm ?? '')}">Incoterm: ${esc(p.incoterm ?? 'n/a')}</p>
  <p data-testid="lead-time" data-value="${p.leadTimeDays ?? ''}">Lead time: ${p.leadTimeDays === null ? 'ask seller' : `${p.leadTimeDays} days`}</p>
  <ul data-testid="certifications">${p.certifications.map((c) => `<li>${esc(c)}</li>`).join('')}</ul>
  <p>Sold by <a data-testid="seller-link" href="/mock-b/shop/${esc(seller.id)}">${esc(seller.name)}</a></p>
  <form action="/mock-b/chat" method="post" data-testid="contact-form">
    <input type="hidden" name="seller" value="${esc(seller.id)}">
    <input type="hidden" name="item" value="${esc(p.id)}">
    <button type="submit" data-testid="contact-seller">Contact seller</button>
  </form>
</article>`
  )
}

function stat(testId: string, label: string, value: string | number | boolean | undefined): string {
  if (value === undefined) return ''
  return `    <dt>${esc(label)}</dt><dd data-testid="${testId}" data-value="${esc(String(value))}">${esc(String(value))}</dd>\n`
}

export function shopPage(seller: Seller, products: readonly Product[]): string {
  const s = seller.signals
  const pct = (v: number | undefined) =>
    v === undefined ? undefined : `${Math.round(v * 1000) / 10}%`
  const stats =
    stat('member-since', 'Member since', s.memberSince ? euDate(s.memberSince) : undefined) +
    stat('first-sale', 'First sale', s.firstSaleDate ? euDate(s.firstSaleDate) : undefined) +
    stat('months-active', 'Active months (last 12)', s.monthsActiveLast12) +
    stat('orders-total', 'Orders (lifetime)', s.lifetimeTransactions) +
    stat('orders-12m', 'Orders (12 months)', s.transactions12m) +
    stat(
      'gmv-12m',
      'Sales volume (12 months)',
      s.gmv12mMinor === undefined ? undefined : price(s.gmv12mMinor, s.gmvCurrency ?? 'EUR')
    ) +
    stat('repeat-buyers', 'Repeat buyers', pct(s.repeatBuyerShare)) +
    stat('listings', 'Listings', s.publishedProductsCount) +
    stat('catalog-churn', 'Catalog changes (30 days)', pct(s.catalogChurn30d)) +
    stat('spec-completeness', 'Listing completeness', pct(s.specCompletenessAvg)) +
    stat('reviews-total', 'Reviews', s.reviewsTotal) +
    stat('reviews-12m', 'Reviews (12 months)', s.reviews12m) +
    stat(
      'rating',
      'Rating',
      s.ratingAvg === undefined ? undefined : `${s.ratingAvg.toFixed(2)} / 5`
    ) +
    stat('rating-count', 'Ratings', s.ratingCount) +
    stat('verified-reviews', 'Verified reviews', pct(s.verifiedReviewShare)) +
    stat('response-rate', 'Response rate', pct(s.responseRate)) +
    stat(
      'identity-verified',
      'Identity verified',
      s.identityVerified === undefined ? undefined : s.identityVerified ? 'yes' : 'no'
    ) +
    stat(
      'trade-assurance',
      'Trade assurance',
      s.tradeAssurance === undefined ? undefined : s.tradeAssurance ? 'yes' : 'no'
    ) +
    stat(
      'escrow',
      'Escrow',
      s.escrowAvailable === undefined ? undefined : s.escrowAvailable ? 'yes' : 'no'
    ) +
    stat('dispute-rate', 'Dispute rate', pct(s.disputeRate)) +
    stat('refund-rate', 'Refund rate', pct(s.refundRate))
  const reviews = seller.reviews
    .map(
      (r) =>
        `    <li data-testid="review" data-review-id="${esc(r.id)}" data-rating="${r.rating}" data-date="${esc(r.date)}" data-verified="${r.verified}">
      <span class="stars">${'★'.repeat(r.rating)}${'☆'.repeat(5 - r.rating)}</span> <time>${esc(euDate(r.date))}</time>${r.verified ? ' <b>Verified purchase</b>' : ''}
      <p>${esc(r.text)}</p>
    </li>`
    )
    .join('\n')
  const listings = products
    .map(
      (p) =>
        `    <li><a data-testid="listing" href="/mock-b/item/${esc(p.id)}">${esc(p.title)}</a></li>`
    )
    .join('\n')
  return page(
    seller.name,
    `<section data-testid="shop" data-seller-id="${esc(seller.id)}">
  <h1 data-testid="shop-name">${esc(seller.name)}</h1>
  <p data-testid="country" data-value="${esc(seller.country ?? '')}">Location: ${esc(seller.country ?? 'not disclosed')}</p>
  <dl data-testid="stats">
${stats}  </dl>
  <h2>Listings</h2>
  <ul data-testid="listings">
${listings}
  </ul>
  <h2>Reviews</h2>
  <ul data-testid="reviews">
${reviews}
  </ul>
</section>`
  )
}

function messageItem(m: ChatMessage): string {
  return `    <li data-testid="message" data-seq="${m.seq}" data-role="${m.role}" data-at="${esc(m.at)}"><b>${m.role === 'buyer' ? 'You' : 'Seller'}:</b> <span data-testid="message-text">${esc(m.text)}</span></li>`
}

export function chatPage(chat: ChatSnapshot, sellerName: string, productTitle: string): string {
  return page(
    `Chat with ${sellerName}`,
    `<section data-testid="chat" data-chat-id="${esc(chat.id)}" data-seller-id="${esc(chat.sellerId)}" data-item-id="${esc(chat.productId)}">
  <h1>Chat with ${esc(sellerName)}</h1>
  <p>About: <a href="/mock-b/item/${esc(chat.productId)}">${esc(productTitle)}</a></p>
  <ol data-testid="messages">
${chat.messages.map(messageItem).join('\n')}
  </ol>
  <form action="/mock-b/chat/${esc(chat.id)}/send" method="post" data-testid="chat-form">
    <textarea name="text" data-testid="chat-input" rows="3" cols="60"></textarea>
    <button type="submit" data-testid="chat-send">Send</button>
  </form>
</section>`
  )
}

export function notFoundPage(what: string): string {
  return page('Not found', `<h1 data-testid="not-found">${esc(what)} not found</h1>`)
}
