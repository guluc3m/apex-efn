import type { RawOffer, RawSellerSignals } from '@apex/shared-types/contracts/browser-worker'
import { beforeAll, describe, expect, it } from 'vitest'

import { WorkerError } from '../errors.js'
import {
  contractFakeSubject,
  CONTRACT_FAKE_PLATFORM,
  InMemoryContractAdapter,
} from '../testing/contract-fake.js'

import {
  assertMinorMoney,
  assertValidOffer,
  assertValidSearchResult,
  assertValidSeller,
  assertValidSignals,
  assertValidThread,
  assertWorkerError,
  describeAdapterContract,
} from './contract-suite.js'

import type { PlatformAdapter, SearchInput, SearchOutput } from './index.js'

describeAdapterContract('in-memory contract fake', () => Promise.resolve(contractFakeSubject()))

/** Deliberately wrong in the two ways the contract forbids: a float price and a raw Error. */
class BrokenAdapter implements Pick<PlatformAdapter, 'platform' | 'transport' | 'getProduct'> {
  readonly platform = CONTRACT_FAKE_PLATFORM
  readonly transport = 'http' as const

  getProduct(platformOfferId: string): Promise<RawOffer> {
    if (platformOfferId === 'missing') {
      return Promise.reject(new Error('product not found'))
    }
    const offer = {
      ...validOfferFixture,
      unit_price: { amount_minor: 12.5, currency: 'EUR' as const },
    }
    return Promise.resolve(offer)
  }
}

let validOfferFixture: RawOffer

beforeAll(async () => {
  validOfferFixture = await new InMemoryContractAdapter().getProduct('offer-1')
})

describe('contract validators', () => {
  it('accept the well-behaved fake', async () => {
    const offer = await new InMemoryContractAdapter().getProduct('offer-1')
    expect(() => assertValidOffer(offer, CONTRACT_FAKE_PLATFORM)).not.toThrow()
  })

  it('reject a float price from a broken adapter', async () => {
    const adapter = new BrokenAdapter()
    const offer: unknown = await adapter.getProduct('offer-1')
    expect(() => assertValidOffer(offer, CONTRACT_FAKE_PLATFORM)).toThrow(/amount_minor/)
  })

  it('reject a raw Error where a WorkerError is required', async () => {
    const adapter = new BrokenAdapter()
    const error = await adapter.getProduct('missing').catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(Error)
    expect(() => assertWorkerError(error, 'unknown_product')).toThrow(/expected a WorkerError/)
  })

  it('reject a WorkerError with the wrong code', () => {
    expect(() =>
      assertWorkerError(new WorkerError('unknown_seller', 404), 'unknown_product')
    ).toThrow(/expected WorkerError code "unknown_product", got "unknown_seller"/)
    expect(() =>
      assertWorkerError(new WorkerError('unknown_product', 404), 'unknown_product')
    ).not.toThrow()
  })

  it.each([
    ['a negative amount', { amount_minor: -1, currency: 'EUR' }],
    ['an unsafe integer', { amount_minor: Number.MAX_SAFE_INTEGER + 2, currency: 'EUR' }],
    ['a string amount', { amount_minor: '1250', currency: 'EUR' }],
    ['an unsupported currency', { amount_minor: 1250, currency: 'JPY' }],
    ['a missing currency', { amount_minor: 1250 }],
  ])('reject money with %s', (_label, money) => {
    expect(() => assertMinorMoney(money, 'price')).toThrow()
  })

  it('reject an offer from another platform', () => {
    const offer = { ...validOfferFixture, platform: 'other-platform' }
    expect(() => assertValidOffer(offer, CONTRACT_FAKE_PLATFORM)).toThrow(
      /expected "contract-fake"/
    )
  })

  it.each([
    [
      'overlapping ranges',
      [
        { min_quantity: 1, max_quantity: 10 },
        { min_quantity: 10, max_quantity: null },
      ],
      /overlapping/,
    ],
    [
      'unsorted tiers',
      [
        { min_quantity: 10, max_quantity: null },
        { min_quantity: 1, max_quantity: 9 },
      ],
      /not sorted/,
    ],
    [
      'a tier after an open-ended one',
      [
        { min_quantity: 1, max_quantity: null },
        { min_quantity: 10, max_quantity: null },
      ],
      /after an open-ended/,
    ],
  ])('reject price tiers with %s', (_label, ranges, message) => {
    const tiers = ranges.map((range) => ({
      ...range,
      unit_price: { amount_minor: 1000, currency: 'EUR' as const },
    }))
    expect(() =>
      assertValidOffer({ ...validOfferFixture, price_tiers: tiers }, CONTRACT_FAKE_PLATFORM)
    ).toThrow(message)
  })

  it('reject a search result above maxResults', () => {
    const result: SearchOutput = {
      offers: [validOfferFixture, { ...validOfferFixture, platform_offer_id: 'offer-2' }],
      skipped: [],
      truncated: false,
    }
    expect(() => assertValidSearchResult(result, CONTRACT_FAKE_PLATFORM, 1)).toThrow(
      /above maxResults/
    )
  })

  it('reject duplicate platform_offer_id values', () => {
    const result: SearchOutput = {
      offers: [validOfferFixture, validOfferFixture],
      skipped: [],
      truncated: false,
    }
    expect(() => assertValidSearchResult(result, CONTRACT_FAKE_PLATFORM, 5)).toThrow(/duplicate/)
  })

  it('reject a skipped listing with a reason outside the closed enum', () => {
    const result = {
      offers: [],
      skipped: [{ platform_offer_id: 'x', reason: 'made_up_reason' }],
      truncated: false,
    }
    expect(() => assertValidSearchResult(result, CONTRACT_FAKE_PLATFORM, 5)).toThrow(
      /skipped listing/
    )
  })

  it('reject a search result that is not an object', () => {
    expect(() => assertValidSearchResult('offers', CONTRACT_FAKE_PLATFORM, 5)).toThrow(
      /not an object/
    )
  })

  it('reject a seller from another platform', async () => {
    const seller = await new InMemoryContractAdapter().getSeller('seller-a')
    expect(() =>
      assertValidSeller({ ...seller, platform: 'other' }, CONTRACT_FAKE_PLATFORM)
    ).toThrow(/expected "contract-fake"/)
  })

  it('reject more reviews than maxReviews and ratios outside [0, 1]', async () => {
    const signals: RawSellerSignals = await new InMemoryContractAdapter().getSellerSignals(
      'seller-a',
      {
        maxReviews: 5,
      }
    )
    expect(() => assertValidSignals(signals, CONTRACT_FAKE_PLATFORM, 3)).toThrow(/maxReviews/)
    expect(() =>
      assertValidSignals({ ...signals, verified_review_share: 1.5 }, CONTRACT_FAKE_PLATFORM, 5)
    ).toThrow()
  })

  it('reject a chat thread whose seq values do not increase', () => {
    const at = new Date('2026-11-09T10:00:00.000Z')
    expect(() =>
      assertValidThread([
        { seq: 2, role: 'buyer', text: 'a', at },
        { seq: 2, role: 'seller', text: 'b', at },
      ])
    ).toThrow(/strictly increasing/)
  })

  it('the fake truncates to maxResults and says so', async () => {
    const adapter = new InMemoryContractAdapter()
    const input: SearchInput = { query: 'steel', quantity: null, maxResults: 5 }
    const output = await adapter.search(input)
    expect(output.offers.length).toBeLessThanOrEqual(5)
    expect(output.truncated).toBe(true)
  })
})
