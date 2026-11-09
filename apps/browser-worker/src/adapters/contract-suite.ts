/**
 * Contract suite that every PlatformAdapter must pass (D5-03). It runs against recorded fixtures, the mock
 * marketplace or an in-memory fake, and never against a real platform. The validators are pure and throw on
 * failure, so they can be tested directly with `expect(() => ...).toThrow()`.
 */
import type {
  JobRequest,
  Money,
  PriceTier,
  RawOffer,
  RawSeller,
  RawSellerSignals,
  WorkerErrorCode,
} from '@apex/shared-types/contracts/browser-worker'
import {
  zRawOffer,
  zRawSeller,
  zRawSellerSignals,
  zSkippedListing,
  zTransport,
} from '@apex/shared-types/contracts/browser-worker/zod'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { z } from 'zod'

import { WorkerError } from '../errors.js'
import { processJob } from '../jobs/processor.js'
import { StaticFlags, platformFlagName } from '../platform/flags.js'

import {
  AdapterRegistry,
  type ChatMessageRecord,
  type PlatformAdapter,
  type SearchOutput,
} from './index.js'

export interface AdapterContractSubject {
  adapter: PlatformAdapter
  search: { query: string; quantity: number | null }
  knownOfferId: string
  knownSellerId: string
  missingOfferId: string
  missingSellerId: string
  chat?: { platformSellerId: string; productId: string; accountId: string; message: string }
  teardown?: () => Promise<void>
}

const CURRENCIES = new Set(['EUR', 'USD', 'CNY'])
const RATIO_FIELDS = [
  'repeat_buyer_share',
  'catalog_churn_30d',
  'spec_completeness_avg',
  'verified_review_share',
  'response_rate',
  'dispute_rate',
  'refund_rate',
] as const
const SEARCH_WIDE = 200
const SEARCH_NARROW = 5
const REVIEW_LIMIT = 3

function ensure(condition: boolean, message: string): asserts condition {
  if (!condition) {
    throw new Error(message)
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function ensureSchema(schema: z.ZodTypeAny, value: unknown, label: string): void {
  const result = schema.safeParse(value)
  if (!result.success) {
    const paths = result.error.issues.map((issue) => issue.path.join('.') || '(root)').join(', ')
    throw new Error(`${label} does not match the contract at: ${paths}`)
  }
}

/** Money is an integer count of minor units in a closed currency. `number` is required, not a coerced bigint. */
export function assertMinorMoney(money: unknown, label: string): asserts money is Money {
  ensure(isRecord(money), `${label} is not an object`)
  const { amount_minor: amount, currency } = money
  ensure(
    typeof amount === 'number' && Number.isSafeInteger(amount) && amount >= 0,
    `${label}.amount_minor must be a non-negative safe integer`
  )
  ensure(
    typeof currency === 'string' && CURRENCIES.has(currency),
    `${label}.currency must be EUR, USD or CNY`
  )
}

export function assertPriceTiers(tiers: PriceTier[], label: string): void {
  let previous: PriceTier | undefined
  for (const [index, tier] of tiers.entries()) {
    assertMinorMoney(tier.unit_price, `${label}[${index}].unit_price`)
    const max = tier.max_quantity ?? null
    ensure(
      max === null || max >= tier.min_quantity,
      `${label}[${index}] max_quantity is below min_quantity`
    )
    if (previous !== undefined) {
      ensure(tier.min_quantity > previous.min_quantity, `${label} is not sorted by min_quantity`)
      const previousMax = previous.max_quantity ?? null
      ensure(previousMax !== null, `${label} has a tier after an open-ended tier`)
      ensure(tier.min_quantity > previousMax, `${label} has overlapping ranges`)
    }
    previous = tier
  }
}

export function assertValidOffer(value: unknown, platform: string): asserts value is RawOffer {
  ensureSchema(zRawOffer, value, 'offer')
  const offer = value as RawOffer
  ensure(
    offer.platform === platform,
    `offer.platform is "${offer.platform}", expected "${platform}"`
  )
  assertMinorMoney(offer.unit_price, 'offer.unit_price')
  if (offer.list_price !== undefined && offer.list_price !== null) {
    assertMinorMoney(offer.list_price, 'offer.list_price')
  }
  assertPriceTiers(offer.price_tiers, 'offer.price_tiers')
  ensure(Number.isInteger(offer.moq) && offer.moq >= 1, 'offer.moq must be at least 1')
}

export function assertValidSearchResult(
  value: unknown,
  platform: string,
  maxResults: number
): asserts value is SearchOutput {
  ensure(isRecord(value), 'search result is not an object')
  ensure(Array.isArray(value.offers), 'search result.offers is not an array')
  ensure(Array.isArray(value.skipped), 'search result.skipped is not an array')
  ensure(typeof value.truncated === 'boolean', 'search result.truncated is not a boolean')
  for (const skipped of value.skipped) {
    ensureSchema(zSkippedListing, skipped, 'skipped listing')
  }
  const seen = new Set<string>()
  for (const offer of value.offers) {
    assertValidOffer(offer, platform)
    ensure(
      !seen.has(offer.platform_offer_id),
      `duplicate platform_offer_id "${offer.platform_offer_id}"`
    )
    seen.add(offer.platform_offer_id)
  }
  ensure(
    value.offers.length <= maxResults,
    `search returned ${value.offers.length} offers, above maxResults`
  )
}

export function assertValidSeller(value: unknown, platform: string): asserts value is RawSeller {
  ensureSchema(zRawSeller, value, 'seller')
  const seller = value as RawSeller
  ensure(
    seller.platform === platform,
    `seller.platform is "${seller.platform}", expected "${platform}"`
  )
}

export function assertValidSignals(
  value: unknown,
  platform: string,
  maxReviews: number
): asserts value is RawSellerSignals {
  ensureSchema(zRawSellerSignals, value, 'seller signals')
  const signals = value as RawSellerSignals
  ensure(
    signals.platform === platform,
    `signals.platform is "${signals.platform}", expected "${platform}"`
  )
  ensure(signals.recent_reviews.length <= maxReviews, 'recent_reviews exceeds maxReviews')
  for (const field of RATIO_FIELDS) {
    const ratio = signals[field]
    ensure(
      ratio === undefined || ratio === null || (ratio >= 0 && ratio <= 1),
      `${field} is outside [0, 1]`
    )
  }
  if (signals.gmv_12m !== undefined && signals.gmv_12m !== null) {
    assertMinorMoney(signals.gmv_12m, 'signals.gmv_12m')
  }
}

export function assertWorkerError(
  error: unknown,
  code: WorkerErrorCode
): asserts error is WorkerError {
  ensure(error instanceof WorkerError, `expected a WorkerError, got ${typeof error}`)
  ensure(error.code === code, `expected WorkerError code "${code}", got "${error.code}"`)
}

export function assertValidThread(messages: ChatMessageRecord[]): void {
  let previousSeq = 0
  for (const message of messages) {
    ensure(
      Number.isSafeInteger(message.seq) && message.seq >= 1,
      'chat seq must be a positive integer'
    )
    ensure(message.seq > previousSeq, 'chat seqs must be strictly increasing')
    ensure(
      message.role === 'buyer' || message.role === 'seller',
      'chat role must be buyer or seller'
    )
    ensure(typeof message.text === 'string', 'chat text must be a string')
    ensure(!Number.isNaN(message.at.getTime()), 'chat message time is invalid')
    previousSeq = message.seq
  }
}

async function rejectionOf(action: () => Promise<unknown>): Promise<unknown> {
  try {
    await action()
  } catch (error) {
    return error
  }
  throw new Error('expected the call to reject, but it resolved')
}

/** Counts every adapter method call, so the disabled-platform test can prove that nothing reached the adapter. */
function countingProxy(adapter: PlatformAdapter, calls: string[]): PlatformAdapter {
  return new Proxy(adapter, {
    get(target, property) {
      const value = Reflect.get(target, property, target) as unknown
      if (typeof value !== 'function') {
        return value
      }
      return (...args: unknown[]) => {
        calls.push(String(property))
        return (value as (...params: unknown[]) => unknown).apply(target, args)
      }
    },
  })
}

function searchRequest(
  subject: AdapterContractSubject,
  platform: string,
  maxResults: number
): JobRequest {
  return {
    kind: 'search',
    tenant_id: 'tenant-contract',
    mission_id: 'mission-contract',
    trace_id: 'trace-contract',
    platform,
    query: subject.search.query,
    quantity: subject.search.quantity,
    max_results: maxResults,
  }
}

/** Runs the whole contract against one adapter. `setup` is called once, before all tests. */
export function describeAdapterContract(
  name: string,
  setup: () => Promise<AdapterContractSubject>
): void {
  describe(`PlatformAdapter contract: ${name}`, () => {
    let subject: AdapterContractSubject | undefined
    const ready = (): AdapterContractSubject => {
      ensure(subject !== undefined, 'contract subject was not set up')
      return subject
    }

    beforeAll(async () => {
      subject = await setup()
    })

    afterAll(async () => {
      await subject?.teardown?.()
    })

    it('declares a platform id and a valid transport', () => {
      const { adapter } = ready()
      expect(adapter.platform.length).toBeGreaterThan(0)
      expect(zTransport.safeParse(adapter.transport).success).toBe(true)
    })

    it('search returns valid raw offers and skipped listings', async () => {
      const { adapter, search } = ready()
      const result = await adapter.search({ ...search, maxResults: SEARCH_WIDE })
      assertValidSearchResult(result, adapter.platform, SEARCH_WIDE)
      expect(result.offers.length).toBeGreaterThan(0)
    })

    it('search honours maxResults and reports truncation', async () => {
      const { adapter, search } = ready()
      const wide = await adapter.search({ ...search, maxResults: SEARCH_WIDE })
      const narrow = await adapter.search({ ...search, maxResults: SEARCH_NARROW })
      assertValidSearchResult(narrow, adapter.platform, SEARCH_NARROW)
      if (wide.offers.length > SEARCH_NARROW) {
        expect(narrow.truncated).toBe(true)
      }
    })

    it('getProduct returns the requested offer', async () => {
      const { adapter, knownOfferId } = ready()
      const offer: unknown = await adapter.getProduct(knownOfferId)
      assertValidOffer(offer, adapter.platform)
      expect(offer.platform_offer_id).toBe(knownOfferId)
    })

    it('getProduct rejects an unknown offer with unknown_product', async () => {
      const { adapter, missingOfferId } = ready()
      const error = await rejectionOf(() => adapter.getProduct(missingOfferId))
      assertWorkerError(error, 'unknown_product')
    })

    it('getSeller returns the requested seller', async () => {
      const { adapter, knownSellerId } = ready()
      const seller: unknown = await adapter.getSeller(knownSellerId)
      assertValidSeller(seller, adapter.platform)
      expect(seller.platform_seller_id).toBe(knownSellerId)
    })

    it('getSeller rejects an unknown seller with unknown_seller', async () => {
      const { adapter, missingSellerId } = ready()
      const error = await rejectionOf(() => adapter.getSeller(missingSellerId))
      assertWorkerError(error, 'unknown_seller')
    })

    it('getSellerSignals returns valid signals bounded by maxReviews', async () => {
      const { adapter, knownSellerId } = ready()
      const signals: unknown = await adapter.getSellerSignals(knownSellerId, {
        maxReviews: REVIEW_LIMIT,
      })
      assertValidSignals(signals, adapter.platform, REVIEW_LIMIT)
      expect(signals.platform_seller_id).toBe(knownSellerId)
    })

    it('getSellerSignals rejects an unknown seller with unknown_seller', async () => {
      const { adapter, missingSellerId } = ready()
      const error = await rejectionOf(() =>
        adapter.getSellerSignals(missingSellerId, { maxReviews: REVIEW_LIMIT })
      )
      assertWorkerError(error, 'unknown_seller')
    })

    it('chat keeps seq order, records the buyer message and gets a seller reply', async (context) => {
      const { adapter, chat } = ready()
      if (chat === undefined || adapter.chat === undefined) {
        context.skip()
        return
      }
      const chatAdapter = adapter.chat
      const { platformChatId } = await chatAdapter.open({
        accountId: chat.accountId,
        platformSellerId: chat.platformSellerId,
        productId: chat.productId,
      })
      await chatAdapter.send(platformChatId, chat.message)
      const thread = await chatAdapter.read(platformChatId, 0)
      assertValidThread(thread)
      const buyer = thread.find(
        (message) => message.role === 'buyer' && message.text === chat.message
      )
      ensure(buyer !== undefined, 'the sent buyer message is missing from the thread')
      expect(thread.some((message) => message.role === 'seller' && message.seq > buyer.seq)).toBe(
        true
      )
      const lastSeq = Math.max(...thread.map((message) => message.seq))
      expect(await chatAdapter.read(platformChatId, lastSeq)).toEqual([])
    })

    it('a disabled platform is refused before any adapter method is called', async () => {
      const subjectUnderTest = ready()
      const { adapter } = subjectUnderTest
      const calls: string[] = []
      const flags = new StaticFlags({ [platformFlagName(adapter.platform)]: false })
      const registry = new AdapterRegistry([countingProxy(adapter, calls)], flags)
      const error = await rejectionOf(() =>
        processJob(searchRequest(subjectUnderTest, adapter.platform, SEARCH_NARROW), registry)
      )
      assertWorkerError(error, 'platform_disabled')
      expect(calls).toEqual([])
    })
  })
}
