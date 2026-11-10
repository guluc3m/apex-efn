import type {
  RawOffer,
  RawSeller,
  RawSellerSignals,
} from '@apex/shared-types/contracts/browser-worker'

import type { AdapterContractSubject } from '../adapters/contract-suite.js'
import {
  type ChatAdapter,
  type ChatMessageRecord,
  type ChatOpenInput,
  type PlatformAdapter,
  type SearchInput,
  type SearchOutput,
} from '../adapters/index.js'
import { WorkerError } from '../errors.js'

export const CONTRACT_FAKE_PLATFORM = 'contract-fake'
const CAPTURED_AT = '2026-11-09T10:00:00.000Z'
const OFFER_COUNT = 7

function offerFor(index: number): RawOffer {
  const price = 1000 + index * 125
  return {
    platform: CONTRACT_FAKE_PLATFORM,
    platform_offer_id: `offer-${index}`,
    product_id: `product-${index}`,
    platform_seller_id: index % 2 === 0 ? 'seller-a' : 'seller-b',
    seller_name: index % 2 === 0 ? 'Seller A' : 'Seller B',
    title: `Steel widget ${index}`,
    product_url: null,
    unit_price: { amount_minor: price, currency: 'EUR' },
    list_price: null,
    price_tiers: [
      { min_quantity: 1, max_quantity: 9, unit_price: { amount_minor: price, currency: 'EUR' } },
      {
        min_quantity: 10,
        max_quantity: null,
        unit_price: { amount_minor: price - 50, currency: 'EUR' },
      },
    ],
    moq: 1,
    quantity_available: null,
    specifications: { material: 'steel' },
    certifications: [],
    seller_country: 'CN',
    shipping: null,
    incoterm: null,
    lead_time_days: null,
    captured_at: CAPTURED_AT,
  }
}

const OFFERS: RawOffer[] = Array.from({ length: OFFER_COUNT }, (_, index) => offerFor(index + 1))

const SELLERS: Record<string, RawSeller> = {
  'seller-a': {
    platform: CONTRACT_FAKE_PLATFORM,
    platform_seller_id: 'seller-a',
    display_name: 'Seller A',
    country: 'CN',
    profile_url: null,
    captured_at: CAPTURED_AT,
  },
  'seller-b': {
    platform: CONTRACT_FAKE_PLATFORM,
    platform_seller_id: 'seller-b',
    display_name: 'Seller B',
    country: 'CN',
    profile_url: null,
    captured_at: CAPTURED_AT,
  },
}

class InMemoryChat implements ChatAdapter {
  private readonly threads = new Map<string, ChatMessageRecord[]>()
  private chats = 0

  open(_input: ChatOpenInput): Promise<{ platformChatId: string }> {
    this.chats += 1
    const platformChatId = `chat-${this.chats}`
    this.threads.set(platformChatId, [])
    return Promise.resolve({ platformChatId })
  }

  send(platformChatId: string, text: string): Promise<{ platformSeq: number; at: Date }> {
    const thread = this.threadOf(platformChatId)
    const at = new Date(CAPTURED_AT)
    const buyer = thread.length + 1
    thread.push({ seq: buyer, role: 'buyer', text, at })
    thread.push({ seq: buyer + 1, role: 'seller', text: 'Thanks, we will reply shortly.', at })
    return Promise.resolve({ platformSeq: buyer, at })
  }

  read(platformChatId: string, afterSeq: number): Promise<ChatMessageRecord[]> {
    return Promise.resolve(
      this.threadOf(platformChatId).filter((message) => message.seq > afterSeq)
    )
  }

  screenshot(platformChatId: string): Promise<Uint8Array> {
    return Promise.resolve(new TextEncoder().encode(`PNG:${this.threadOf(platformChatId).length}`))
  }

  private threadOf(platformChatId: string): ChatMessageRecord[] {
    const thread = this.threads.get(platformChatId)
    if (thread === undefined) {
      throw new WorkerError('unknown_chat', 404)
    }
    return thread
  }
}

/** Well-behaved in-memory adapter. It must pass the whole contract suite, so the suite itself is exercised. */
export class InMemoryContractAdapter implements PlatformAdapter {
  readonly platform = CONTRACT_FAKE_PLATFORM
  readonly transport = 'http' as const
  readonly chat: ChatAdapter = new InMemoryChat()

  search(input: SearchInput): Promise<SearchOutput> {
    const matches = OFFERS.filter((offer) =>
      offer.title.toLowerCase().includes(input.query.toLowerCase())
    )
    return Promise.resolve({
      offers: matches.slice(0, input.maxResults),
      skipped: [
        { platform_offer_id: 'offer-x', reason: 'unsupported_currency', currency_raw: 'JPY' },
      ],
      truncated: matches.length > input.maxResults,
    })
  }

  getProduct(platformOfferId: string): Promise<RawOffer> {
    const offer = OFFERS.find((candidate) => candidate.platform_offer_id === platformOfferId)
    if (offer === undefined) {
      return Promise.reject(new WorkerError('unknown_product', 404))
    }
    return Promise.resolve(offer)
  }

  getSeller(platformSellerId: string): Promise<RawSeller> {
    const seller = SELLERS[platformSellerId]
    if (seller === undefined) {
      return Promise.reject(new WorkerError('unknown_seller', 404))
    }
    return Promise.resolve(seller)
  }

  getSellerSignals(
    platformSellerId: string,
    options: { maxReviews: number }
  ): Promise<RawSellerSignals> {
    if (SELLERS[platformSellerId] === undefined) {
      return Promise.reject(new WorkerError('unknown_seller', 404))
    }
    const reviews = [5, 5, 4, 5, 3].map((rating) => ({ rating, verified_purchase: true }))
    return Promise.resolve({
      platform: CONTRACT_FAKE_PLATFORM,
      platform_seller_id: platformSellerId,
      captured_at: CAPTURED_AT,
      account_age_days: 400,
      rating_avg: 4.6,
      rating_count: 5,
      verified_review_share: 1,
      recent_reviews: reviews.slice(0, options.maxReviews),
    })
  }
}

/** Subject for `describeAdapterContract` built on the in-memory fake. */
export function contractFakeSubject(): AdapterContractSubject {
  return {
    adapter: new InMemoryContractAdapter(),
    search: { query: 'steel', quantity: null },
    knownOfferId: 'offer-1',
    knownSellerId: 'seller-a',
    missingOfferId: 'offer-missing',
    missingSellerId: 'seller-missing',
    chat: {
      platformSellerId: 'seller-a',
      productId: 'product-1',
      accountId: 'account-1',
      message: 'Hello, could you quote 500 units?',
    },
  }
}
