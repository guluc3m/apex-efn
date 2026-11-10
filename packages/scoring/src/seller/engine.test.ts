import type { RawSellerSignals } from '@apex/shared-types/seller'
import { describe, expect, it } from 'vitest'

import { SellerConfidenceEngine } from './engine.js'

const NOW = '2026-01-01T00:00:00.000Z'

const META = {
  capturedAt: '2026-01-01T00:00:00.000Z',
  platform: 'test',
  platformSellerId: 's1',
}

const STRONG: RawSellerSignals = {
  ...META,
  accountAgeDays: 1500,
  monthsActiveLast12: 12,
  lifetimeTransactions: 20000,
  publishedProductsCount: 2000,
  reviewsTotal: 1000,
  reviews12m: 120,
  ratingAvg: 4.7,
  ratingCount: 1000,
  verifiedReviewShare: 0.9,
  identityVerified: true,
  tradeAssurance: true,
  escrowAvailable: true,
  disputeRate: 0,
  refundRate: 0,
}

const engine = new SellerConfidenceEngine()

describe('SellerConfidenceEngine', () => {
  it('is deterministic and carries the model version', () => {
    const first = engine.compute('s1', STRONG, 'snap', NOW)
    expect(engine.compute('s1', STRONG, 'snap', NOW)).toEqual(first)
    expect(first.computedAt).toBe(NOW)
    expect(first.modelVersion).toBe('1.0.0')
  })

  it('rates a strong seller as high', () => {
    expect(engine.compute('s1', STRONG, 'snap', NOW).band).toBe('high')
  })

  it('returns insufficient_data below the minimum of signals', () => {
    const result = engine.compute('s1', { ...META, accountAgeDays: 100 }, 'snap', NOW)
    expect(result.band).toBe('insufficient_data')
    expect(result.score).toBe(0)
  })

  it('caps the band to low when reviews look manipulated', () => {
    const result = engine.compute('s1', { ...STRONG, verifiedReviewShare: 0.05 }, 'snap', NOW)
    expect(result.band).toBe('low')
    expect(result.flags.map((f) => f.type)).toContain('low_verified_share')
  })

  it('penalises disputes and refunds', () => {
    const clean = engine.compute('s1', STRONG, 'snap', NOW)
    const risky = engine.compute(
      's1',
      { ...STRONG, disputeRate: 0.2, refundRate: 0.3 },
      'snap',
      NOW
    )
    expect(risky.score).toBeLessThan(clean.score)
    expect(risky.penalties).toHaveLength(2)
  })

  it('rejects weights that do not sum to 1', () => {
    expect(
      () =>
        new SellerConfidenceEngine({
          weights: { age: 0.5, sales: 0.5, catalog: 0.5, reviews: 0, institutional: 0 },
        })
    ).toThrow(/sum to 1/)
  })
})
