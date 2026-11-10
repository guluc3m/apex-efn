import type { Currency, FxRate } from '@apex/shared-types/currency'
import fc from 'fast-check'
import { describe, expect, it } from 'vitest'

import { FxConverter } from './fx.js'
import { Money } from './money.js'

const SAFE = Number.MAX_SAFE_INTEGER
const amount = fc.integer({ min: -SAFE, max: SAFE })
const currency = fc.constantFrom<Currency>('EUR', 'USD', 'CNY')

describe('Money', () => {
  it('rejects non-integer and unsafe minor units', () => {
    expect(() => new Money(10.5, 'EUR')).toThrow(/integer/)
    expect(() => new Money(SAFE + 1, 'EUR')).toThrow(
      expect.objectContaining({ code: 'amount_out_of_range' }) as Error
    )
  })

  it('refuses to mix currencies', () => {
    expect(() => Money.zero('EUR').add(Money.zero('USD'))).toThrow(/mismatch/)
    expect(() => Money.zero('EUR').compareTo(Money.zero('CNY'))).toThrow(/mismatch/)
  })

  it('compares, negates and formats without floats', () => {
    const a = new Money(-1234, 'EUR')
    expect(a.abs().equals(a.negate())).toBe(true)
    expect([a.isNegative(), a.isPositive(), a.isZero(), Money.zero('EUR').isZero()]).toEqual([
      true,
      false,
      false,
      true,
    ])
    expect(a.lessThan(Money.zero('EUR')) && a.lessThanOrEqual(a) && a.greaterThanOrEqual(a)).toBe(
      true
    )
    expect(a.greaterThan(Money.zero('EUR'))).toBe(false)
    expect(Money.fromMinor(SAFE, 'USD').format('en-US')).toBe('$90,071,992,547,409.91')
    expect(a.toJSON()).toEqual({ amountMinor: -1234, currency: 'EUR' })
  })

  it('round-trips through the decimal string', () => {
    fc.assert(
      fc.property(amount, currency, (a, c) => {
        expect(Money.parse(new Money(a, c).toDecimalString(), c).amountMinor).toBe(a)
      })
    )
  })

  it('rounds symmetrically around zero', () => {
    fc.assert(
      fc.property(fc.integer({ min: -1e9, max: 1e9 }), fc.integer({ min: 1, max: 1e6 }), (a, d) => {
        const m = new Money(a, 'EUR')
        expect(m.negate().divide(d).amountMinor).toBe(0 - m.divide(d).amountMinor + 0)
        expect(m.negate().multiply(`0.${d}`).amountMinor).toBe(
          0 - m.multiply(`0.${d}`).amountMinor + 0
        )
      })
    )
  })

  it('rounds to within half a minor unit of the exact quotient', () => {
    fc.assert(
      fc.property(fc.integer({ min: -1e9, max: 1e9 }), fc.integer({ min: 1, max: 1e6 }), (a, d) => {
        const q = BigInt(new Money(a, 'EUR').divide(d).amountMinor)
        const error = 2n * (q * BigInt(d) - BigInt(a))
        expect(error <= BigInt(d) && error >= -BigInt(d)).toBe(true)
      })
    )
  })

  it('allocates every minor unit, each part within one of its exact share', () => {
    fc.assert(
      fc.property(
        amount,
        fc.array(fc.integer({ min: 0, max: 1e6 }), { minLength: 1, maxLength: 12 }),
        (a, ratios) => {
          fc.pre(ratios.some((r) => r > 0))
          const parts = new Money(a, 'EUR').allocate(ratios).map((p) => BigInt(p.amountMinor))
          expect(parts.reduce((x, y) => x + y, 0n)).toBe(BigInt(a))
          const total = BigInt(ratios.reduce((x, y) => x + y, 0))
          parts.forEach((p, i) => {
            const diff = p * total - BigInt(a) * BigInt(ratios[i]!)
            expect(diff < total && diff > -total).toBe(true)
            if (ratios[i] === 0) expect(p).toBe(0n)
          })
        }
      )
    )
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
