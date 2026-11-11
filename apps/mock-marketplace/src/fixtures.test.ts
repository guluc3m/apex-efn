import { describe, expect, it } from 'vitest'

import { loadCatalog, validateCatalog } from './fixtures/load.js'
import { PERSONA_IDS, SELLER_PROFILES, type Catalog } from './fixtures/schema.js'

const catalog = loadCatalog()
const SUPPORTED = new Set(['EUR', 'USD', 'CNY'])

/** Same fixed rates the personas use; enough to compare fixture prices, not business FX. */
const EUR_PER_UNIT: Record<string, number> = { EUR: 1, USD: 0.92, CNY: 0.128, GBP: 1.17 }
const eur = (minor: number, currency: string) => minor * (EUR_PER_UNIT[currency] ?? Number.NaN)

function median(values: number[]): number {
  const s = [...values].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? (s[mid] as number) : ((s[mid - 1] as number) + (s[mid] as number)) / 2
}

describe('fixtures', () => {
  it('cover every seller profile and every persona', () => {
    expect(new Set(catalog.sellers.map((s) => s.profile))).toEqual(new Set(SELLER_PROFILES))
    expect(new Set(catalog.sellers.map((s) => s.persona))).toEqual(new Set(PERSONA_IDS))
  })

  it('contain the solid-seller pair from criterion 7: 1 review at 5.0 vs 500 at 4.8', () => {
    const single = catalog.sellers.find((s) => s.profile === 'single_perfect_review')
    const veteran = catalog.sellers.find((s) => s.id === 'a-solid-veteran')
    expect(single?.signals).toMatchObject({ ratingCount: 1, ratingAvg: 5 })
    expect(veteran?.signals).toMatchObject({ ratingCount: 500, ratingAvg: 4.8 })
  })

  it('contain a manipulated-review seller with a burst right after account creation', () => {
    const s = catalog.sellers.find((x) => x.profile === 'manipulated_reviews')
    expect(s).toBeDefined()
    const created = Date.parse(s?.signals.memberSince ?? '')
    const days = (s?.reviews ?? []).map((r) => (Date.parse(r.date) - created) / 86_400_000)
    expect(days.length).toBeGreaterThanOrEqual(8)
    expect(Math.max(...days)).toBeLessThanOrEqual(14)
    expect((s?.reviews ?? []).every((r) => r.rating === 5)).toBe(true)
    const texts = (s?.reviews ?? []).map((r) => r.text)
    expect(new Set(texts).size).toBeLessThan(texts.length)
    expect(s?.signals.verifiedReviewShare).toBeLessThan(0.2)
  })

  it('contain an insufficient-data seller with almost no signals', () => {
    const s = catalog.sellers.find((x) => x.profile === 'insufficient_data')
    expect(Object.keys(s?.signals ?? {}).length).toBeLessThan(3)
    expect(s?.reviews).toEqual([])
  })

  it('contain -90% and +200% outliers against the median of the same product key', () => {
    const gloves = catalog.products.filter(
      (p) =>
        p.productKey === 'nitrile-gloves-m-box100' &&
        SUPPORTED.has(p.currency) &&
        p.tags.length === 0
    )
    const ref = median(gloves.map((p) => eur(p.unitPriceMinor, p.currency)))
    const low = catalog.products.find((p) => p.tags.includes('outlier_low'))
    const high = catalog.products.find((p) => p.tags.includes('outlier_high'))
    expect(low && eur(low.unitPriceMinor, low.currency) / ref).toBeCloseTo(0.1, 1)
    expect(high && eur(high.unitPriceMinor, high.currency) / ref).toBeGreaterThan(2.9)
  })

  it('contain an offer in an unsupported currency', () => {
    const p = catalog.products.find((x) => x.tags.includes('unsupported_currency'))
    expect(p && SUPPORTED.has(p.currency)).toBe(false)
  })

  it('give at least 3 offers from at least 2 platforms for the main query (criterion 3)', () => {
    const gloves = catalog.products.filter((p) => p.productKey === 'nitrile-gloves-m-box100')
    expect(new Set(gloves.map((p) => p.platform)).size).toBeGreaterThanOrEqual(2)
    for (const platform of ['mock-a', 'mock-b', 'mock-c'] as const) {
      expect(gloves.filter((p) => p.platform === platform).length).toBeGreaterThanOrEqual(3)
    }
  })

  it('rejects broken cross references', () => {
    const first = catalog.products[0]
    if (!first) throw new Error('no products')
    const broken: Catalog = {
      sellers: catalog.sellers,
      products: [{ ...first, sellerId: 'nobody' }],
    }
    expect(() => validateCatalog(broken)).toThrow(/unknown seller/)
  })
})
