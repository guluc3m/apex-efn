import type {
  ChatRole,
  RawOffer,
  RawSeller,
  RawSellerSignals,
} from '@apex/shared-types/contracts/browser-worker'

import {
  type ChatAdapter,
  type ChatMessageRecord,
  type ChatOpenInput,
  type PlatformAdapter,
  type SearchInput,
  type SearchOutput,
  type TransportType,
} from '../adapters/index.js'
import type { Clock } from '../clock.js'
import { settle } from '../concurrency.js'

export class FixedClock implements Clock {
  private ms: number

  constructor(iso: string) {
    this.ms = Date.parse(iso)
  }

  now(): Date {
    return new Date(this.ms)
  }

  advance(ms: number): void {
    this.ms += ms
  }
}

export class FakeChatAdapter implements ChatAdapter {
  readonly opened: ChatOpenInput[] = []
  readonly sent: Array<{ platformChatId: string; text: string }> = []
  readonly screenshots: string[] = []
  failSendWith: Error | null = null
  private readonly thread: ChatMessageRecord[] = []
  private nextSeq = 1

  constructor(private readonly clock: Clock) {}

  open(input: ChatOpenInput): Promise<{ platformChatId: string }> {
    this.opened.push(input)
    return Promise.resolve({ platformChatId: `pc-${this.opened.length}` })
  }

  send(platformChatId: string, text: string): Promise<{ platformSeq: number; at: Date }> {
    if (this.failSendWith !== null) {
      return Promise.reject(this.failSendWith)
    }
    this.sent.push({ platformChatId, text })
    const seq = this.append('buyer', text)
    return Promise.resolve({ platformSeq: seq, at: this.clock.now() })
  }

  read(_platformChatId: string, afterSeq: number): Promise<ChatMessageRecord[]> {
    return Promise.resolve(
      this.thread.filter((message) => message.seq > afterSeq).map((m) => ({ ...m }))
    )
  }

  screenshot(platformChatId: string): Promise<Uint8Array> {
    this.screenshots.push(platformChatId)
    return Promise.resolve(new TextEncoder().encode(`PNG:${platformChatId}`))
  }

  seedSellerMessage(text: string): number {
    return this.append('seller', text)
  }

  private append(role: ChatRole, text: string): number {
    const seq = this.nextSeq
    this.nextSeq += 1
    this.thread.push({ seq, role, text, at: this.clock.now() })
    return seq
  }
}

/** Records every call in `calls`, so tests can assert that a disabled or locked adapter was never reached. */
export class FakePlatformAdapter implements PlatformAdapter {
  readonly calls: string[] = []
  failSearchWith: Error | null = null
  readonly chat?: ChatAdapter

  constructor(
    readonly platform: string,
    readonly transport: TransportType,
    chat?: ChatAdapter
  ) {
    this.chat = chat
  }

  search(input: SearchInput): Promise<SearchOutput> {
    this.calls.push('search')
    return settle(() => {
      if (this.failSearchWith !== null) {
        throw this.failSearchWith
      }
      return {
        offers: [rawOffer(this.platform, 'offer-1', input.query)],
        skipped: [
          { platform_offer_id: 'offer-x', reason: 'unsupported_currency', currency_raw: 'JPY' },
        ],
        truncated: false,
      }
    })
  }

  getProduct(platformOfferId: string): Promise<RawOffer> {
    this.calls.push('getProduct')
    return Promise.resolve(rawOffer(this.platform, platformOfferId, 'product'))
  }

  getSeller(platformSellerId: string): Promise<RawSeller> {
    this.calls.push('getSeller')
    return Promise.resolve({
      platform: this.platform,
      platform_seller_id: platformSellerId,
      display_name: 'Seller',
      country: 'CN',
      profile_url: null,
      captured_at: '2026-11-09T10:00:00.000Z',
    })
  }

  getSellerSignals(
    platformSellerId: string,
    options: { maxReviews: number }
  ): Promise<RawSellerSignals> {
    this.calls.push(`getSellerSignals:${options.maxReviews}`)
    return Promise.resolve({
      platform: this.platform,
      platform_seller_id: platformSellerId,
      captured_at: '2026-11-09T10:00:00.000Z',
      account_age_days: 400,
      rating_avg: 4.8,
      rating_count: 500,
      recent_reviews: [{ rating: 5, verified_purchase: true }],
    })
  }
}

function rawOffer(platform: string, platformOfferId: string, title: string): RawOffer {
  return {
    platform,
    platform_offer_id: platformOfferId,
    product_id: platformOfferId,
    platform_seller_id: 'seller-1',
    seller_name: 'Seller',
    title,
    product_url: null,
    unit_price: { amount_minor: 1250, currency: 'EUR' },
    list_price: null,
    price_tiers: [
      { min_quantity: 1, max_quantity: null, unit_price: { amount_minor: 1250, currency: 'EUR' } },
    ],
    moq: 1,
    quantity_available: null,
    specifications: { material: 'steel' },
    certifications: [],
    seller_country: 'CN',
    shipping: null,
    incoterm: null,
    lead_time_days: null,
    captured_at: '2026-11-09T10:00:00.000Z',
  }
}
