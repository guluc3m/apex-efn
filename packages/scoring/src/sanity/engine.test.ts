import { describe, expect, it } from 'vitest'

import { PriceSanityEngine } from './engine.js'

// median 1000, MAD 50
const TIGHT = [900, 950, 1000, 1050, 1100]
// median 1000, MAD 400: the index stays low even for very cheap prices
const WIDE = [200, 600, 1000, 1400, 1800]

const NOW = '2026-01-01T00:00:00.000Z'
const engine = new PriceSanityEngine()

describe('PriceSanityEngine', () => {
  it.each([
    [1000, 'normal', 'negotiate'],
    [1100, 'normal', 'negotiate'],
    [1300, 'atypical', 'human_gate'],
    [1500, 'implausible', 'discard'],
    [200, 'implausible', 'discard'],
  ])('classifies %i against a tight sample as %s', (price, band, decision) => {
    const result = engine.check('o1', price, TIGHT, NOW)
    expect(result.band).toBe(band)
    expect(result.decision).toBe(decision)
  })

  it('is stricter on the cheap side for the same distance to the median', () => {
    expect(engine.check('o1', 790, TIGHT, NOW).band).toBe('atypical')
    expect(engine.check('o1', 1210, TIGHT, NOW).band).toBe('normal')
  })

  it('never treats a cheaper price more leniently than a less cheap one', () => {
    const severity = { normal: 0, insufficient_reference: 0, atypical: 1, implausible: 2 }
    let previous = 0
    for (let price = 1000; price >= 0; price -= 10) {
      const current = severity[engine.check('o1', price, WIDE, NOW).band]
      expect(current).toBeGreaterThanOrEqual(previous)
      previous = current
    }
  })

  it('sends a price far out of range but with a low index to the human gate', () => {
    expect(engine.check('o1', 300, WIDE, NOW).decision).toBe('human_gate')
    expect(engine.check('o1', 600, WIDE, NOW).decision).toBe('human_gate')
  })

  it('keeps more than 60% below the median atypical even with a permissive drop', () => {
    const permissive = new PriceSanityEngine({ maxRelativeDrop: 0.9 })
    expect(permissive.check('o1', 500, WIDE, NOW).band).toBe('normal')
    expect(permissive.check('o1', 300, WIDE, NOW).band).toBe('atypical')
  })

  it('reports the median as reference and the real sample size', () => {
    const result = engine.check('o1', 1100, TIGHT, NOW)
    expect(result.referencePriceEur).toBe(1000)
    expect(result.median).toBe(1000)
    expect(result.sampleSize).toBe(5)
  })

  it('falls back to the IQR for the index when MAD is 0', () => {
    const result = engine.check('o1', 1100, [900, 900, 900, 1000, 1000, 1000, 1000, 1000], NOW)
    expect(result.dispersionMeasure).toBe('iqr')
    expect(result.indexScore).toBeCloseTo(0.6745)
  })

  it('uses only the relative deviation when every reference is identical', () => {
    const same = [1000, 1000, 1000, 1000, 1000]
    expect(engine.check('o1', 1000, same, NOW).indexScore).toBeNull()
    expect(engine.check('o1', 1000, same, NOW).band).toBe('normal')
    expect(engine.check('o1', 700, same, NOW).band).toBe('atypical')
  })

  it('applies absolute bounds over the statistics', () => {
    const bounded = new PriceSanityEngine({ floorPerUnit: 950, ceilingPerUnit: 1050 })
    expect(bounded.check('o1', 940, TIGHT, NOW).band).toBe('implausible')
    expect(bounded.check('o1', 1060, TIGHT, NOW).decision).toBe('discard')
  })

  it('gates offers without enough reference prices', () => {
    const result = engine.check('o1', 1000, [1000, 1000], NOW)
    expect(result.band).toBe('insufficient_reference')
    expect(result.decision).toBe('human_gate')
    expect(result.sampleSize).toBe(2)
  })
})
