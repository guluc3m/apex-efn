import type { FxRate } from '@apex/shared-types/currency'
import { describe, expect, it } from 'vitest'

import { FxConverter } from './fx.js'
import { Money } from './money.js'

describe('Money', () => {
  it('rejects non-integer minor units', () => {
    expect(() => new Money(10.5, 'EUR')).toThrow(/integer/)
  })

  it('avoids floating point errors when adding', () => {
    const sum = Money.fromMajor(0.1, 'EUR').add(Money.fromMajor(0.2, 'EUR'))
    expect(sum.amountMinor).toBe(30)
  })

  it('refuses to mix currencies', () => {
    expect(() => Money.zero('EUR').add(Money.zero('USD'))).toThrow(/mismatch/)
    expect(() => Money.zero('EUR').compareTo(Money.zero('CNY'))).toThrow(/mismatch/)
  })

  it.each([
    [100, [1, 1, 1]],
    [-100, [1, 1, 1]],
    [1, [1, 1]],
    [999, [70, 20, 10]],
  ])('allocates %i across %j without losing a cent', (amount, ratios) => {
    const parts = new Money(amount, 'EUR').allocate(ratios)
    expect(parts.reduce((sum, p) => sum + p.amountMinor, 0)).toBe(amount)
  })
})

describe('FxConverter', () => {
  const now = new Date('2026-01-02T00:00:00.000Z')
  const rate = (quote: FxRate['quote'], value: number, asOf = now.toISOString()): FxRate => ({
    base: 'EUR',
    quote,
    rate: value,
    asOf,
    source: 'test',
  })
  const fx = new FxConverter([rate('USD', 1.1), rate('CNY', 7.8)])

  it('converts with a direct rate', () => {
    expect(fx.convert(new Money(10000, 'EUR'), 'USD', now)?.money.amountMinor).toBe(11000)
  })

  it('inverts a rate when only the opposite pair exists', () => {
    expect(fx.convert(new Money(11000, 'USD'), 'EUR', now)?.money.amountMinor).toBe(10000)
  })

  it('triangulates through EUR', () => {
    const result = fx.convert(new Money(10000, 'USD'), 'CNY', now)
    expect(result?.money.amountMinor).toBe(70909)
    expect(result?.rate.source).toContain('triangulated')
  })

  it('does not convert with a stale rate', () => {
    const stale = new FxConverter([rate('USD', 1.1, '2025-12-30T00:00:00.000Z')])
    expect(stale.convert(new Money(100, 'EUR'), 'USD', now)).toBeNull()
  })

  it('keeps the same amount for the same currency', () => {
    const result = fx.convert(new Money(100, 'EUR'), 'EUR', now)
    expect(result?.converted).toBe(false)
    expect(result?.money.amountMinor).toBe(100)
    expect(result?.rate.asOf).toBe(now.toISOString())
  })

  it('stamps an identity rate with the injected clock', () => {
    expect(fx.getRate('USD', 'USD', now)?.asOf).toBe(now.toISOString())
  })

  it('only replaces a rate with a newer one', () => {
    const local = new FxConverter([rate('USD', 1.1)])
    local.updateRates([rate('USD', 1.0, '2026-01-01T00:00:00.000Z')])
    expect(local.getDirectRate('EUR', 'USD')?.rate).toBe(1.1)
    local.updateRates([rate('USD', 1.2, '2026-01-02T12:00:00.000Z')])
    expect(local.getDirectRate('EUR', 'USD')?.rate).toBe(1.2)
  })
})
