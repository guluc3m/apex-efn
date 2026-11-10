import type { SellerSignalSnapshot } from '@apex/shared-types/contracts'
import { loadVectorFiles } from '@apex/test-vectors'
import fc from 'fast-check'
import { describe, expect, it } from 'vitest'

import { computeSellerConfidence, RAW_SIGNALS, trustConfigFrom } from './engine.js'

// Properties of the D3-06 mirror. Known answers live in packages/test-vectors/trust (vectors.test.ts).
const raw = loadVectorFiles('trust').find((f) => f.engine === 'trust.compute')!.vectors[0]!
  .config as {
  config_version: string
} & Record<string, unknown>
const { config_version, ...seller } = raw
const cfg = trustConfigFrom(seller, config_version)
const NOW = '2026-11-10T00:00:00Z'

const share = fc.option(fc.double({ min: 0, max: 1, noNaN: true }), { nil: null })
const count = fc.option(fc.integer({ min: 0, max: 1_000_000 }), { nil: null })
const flag = fc.option(fc.boolean(), { nil: null })
const snapshots = fc.record({
  account_age_days: count,
  months_active_last_12: fc.option(fc.integer({ min: 0, max: 12 }), { nil: null }),
  lifetime_transactions: count,
  transactions_12m: count,
  repeat_buyer_share: share,
  published_products_count: count,
  catalog_churn_30d: share,
  spec_completeness_avg: share,
  reviews_total: count,
  reviews_12m: count,
  rating_avg: fc.option(fc.double({ min: 1, max: 5, noNaN: true }), { nil: null }),
  rating_count: count,
  verified_review_share: share,
  response_rate: share,
  identity_verified: flag,
  trade_assurance: flag,
  escrow_available: flag,
  dispute_rate: share,
  refund_rate: share,
})
const snap = (f: Record<string, unknown>): SellerSignalSnapshot => ({
  id: 's',
  seller_id: 'x',
  data_completeness: 0,
  captured_at: NOW,
  ...f,
})

describe('computeSellerConfidence', () => {
  it('keeps score, band and flags consistent', () => {
    fc.assert(
      fc.property(snapshots, (f) => {
        const r = computeSellerConfidence(snap(f), cfg, NOW)
        const present = RAW_SIGNALS.filter((n) => (f as Record<string, unknown>)[n] != null).length
        if (present < cfg.minSignals) return r.band === 'insufficient_data' && r.score === null
        if (r.score === null || r.score < 0 || r.score > 100) return false
        if (Object.values(r.signals_normalized).some((v) => v < 0 || v > 1)) return false
        if (r.flags.length && (r.band === 'high' || r.band === 'medium')) return false
        return r.score >= cfg.bandLow || r.band === 'untrusted'
      })
    )
  })

  it('never lowers the score for an institutional guarantee', () => {
    fc.assert(
      fc.property(
        snapshots,
        fc.constantFrom('identity_verified', 'trade_assurance', 'escrow_available'),
        (f, k) => {
          const without = computeSellerConfidence(snap({ ...f, [k]: false }), cfg, NOW)
          const withIt = computeSellerConfidence(snap({ ...f, [k]: true }), cfg, NOW)
          return without.score === null || (withIt.score ?? -1) >= without.score
        }
      )
    )
  })

  it('is deterministic', () => {
    fc.assert(
      fc.property(snapshots, (f) => {
        expect(computeSellerConfidence(snap(f), cfg, NOW)).toEqual(
          computeSellerConfidence(snap(f), cfg, NOW)
        )
      })
    )
  })
})
