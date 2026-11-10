import type { Currency, FxRate } from '@apex/shared-types/contracts'
import fc from 'fast-check'
import { describe, expect, it } from 'vitest'

import { convert } from './fx.js'
import { divideHalfAwayFromZero, Money } from './money.js'

const AS_OF = '2026-01-01T15:00:00Z'
const NOW = '2026-01-02T12:00:00Z'
const CFG = { maxAgeHours: 36 }
const rate = (base: Currency, quote: Currency, value: string): FxRate => ({
  base,
  quote,
  rate: value,
  as_of: AS_OF,
  source: 'ecb',
})
// A rate between 0.0001 and 99.9999 as a decimal string plus its exact numerator over 10^4
const rates = fc.integer({ min: 1, max: 999_999 }).map((n) => ({
  text: `${Math.floor(n / 10_000)}.${String(n % 10_000).padStart(4, '0')}`,
  num: BigInt(n),
}))
const amounts = fc.integer({ min: -1e9, max: 1e9 }) // times a rate up to 1e6 stays below 2^53

describe('convert', () => {
  it('round-trips within the two roundings', () => {
    fc.assert(
      fc.property(amounts, rates, (a, r) => {
        const fx = [rate('EUR', 'USD', r.text)]
        const there = convert(new Money(a, 'EUR'), 'USD', fx, NOW, CFG)
        const back = convert(new Money(there.amount_minor, 'USD'), 'EUR', fx, NOW, CFG)
        // |b - a·r| <= 1/2 and |back - b/r| <= 1/2, so 2·|back - a|·num <= num + den
        const error = BigInt(back.amount_minor - a)
        expect(2n * (error < 0n ? -error : error) * r.num <= r.num + 10_000n).toBe(true)
      })
    )
  })

  it('triangulates with a single rounding', () => {
    fc.assert(
      fc.property(amounts, rates, rates, (a, usd, cny) => {
        const fx = [rate('EUR', 'USD', usd.text), rate('EUR', 'CNY', cny.text)]
        const result = convert(new Money(a, 'USD'), 'CNY', fx, NOW, CFG)
        expect(BigInt(result.amount_minor)).toBe(
          divideHalfAwayFromZero(BigInt(a) * cny.num, usd.num)
        )
        expect(result.fx_source).toBe('ecb')
      })
    )
  })

  it('flags a rate as provisional only once it is older than the maximum age', () => {
    const fx = [rate('EUR', 'USD', '1.1')]
    const at = (hours: number) => new Date(Date.parse(AS_OF) + hours * 3_600_000).toISOString()
    expect(convert(Money.zero('EUR'), 'USD', fx, at(36), CFG).fx_provisional).toBe(false)
    expect(convert(Money.zero('EUR'), 'USD', fx, at(36.001), CFG).fx_provisional).toBe(true)
  })
})
