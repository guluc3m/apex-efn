import type { Offer, Recommendation } from '@apex/shared-types/contracts'
import { describe, expect, it } from 'vitest'

import { buildCompareModel } from './compare'

const offer = (id: string) => ({ id }) as Offer
const rec = {
  ranking: [
    { rank: 1, offer_id: 'a', score: 0.8, breakdown: [] },
    { rank: 2, offer_id: 'b', score: 0.6, breakdown: [] },
    { rank: 3, offer_id: 'gone', score: 0.5, breakdown: [] },
  ],
  alternatives: [
    { offer_id: 'b', versus_offer_id: 'a', summary: 'cheaper but slower' },
    { offer_id: 'b', versus_offer_id: 'c', summary: 'other pair' },
  ],
} as unknown as Recommendation

describe('buildCompareModel', () => {
  it('keeps the API order, attaches the trade-off versus #1 and reports missing offers', () => {
    const m = buildCompareModel(rec, [offer('b'), offer('a')])
    expect(m.rows.map((r) => r.offer.id)).toEqual(['a', 'b'])
    expect(m.rows.map((r) => r.vsFirst)).toEqual([null, 'cheaper but slower'])
    expect(m.missing).toEqual(['gone'])
  })
})
