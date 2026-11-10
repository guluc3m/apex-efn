import type { Currency } from '@apex/shared-types/currency'
import fc from 'fast-check'
import { describe, expect, it } from 'vitest'

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
