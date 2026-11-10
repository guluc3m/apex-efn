import type { FxRate } from '@apex/shared-types/contracts'
import type { Currency } from '@apex/shared-types/currency'
import { loadVectorFiles, mismatch, type VectorFile } from '@apex/test-vectors'
import { describe, expect, it } from 'vitest'

import { convert } from './fx.js'
import { Money } from './money.js'

type Engine = (input: unknown, config: unknown) => unknown
type In = { amount_minor: number; currency: Currency }

const money = (m: In) => new Money(m.amount_minor, m.currency)
const out = (m: Money) => ({ amount_minor: m.amountMinor, currency: m.currency })

// Engine ids of packages/test-vectors/money (ADR-301). tests/domain/test_vectors.py runs the same files.
const ENGINES: Record<string, Engine> = {
  'money.new': (i) => out(money(i as In)),
  'money.parse': (i) => {
    const { amount, currency } = i as { amount: string; currency: Currency }
    return out(Money.parse(amount, currency))
  },
  'money.to_decimal': (i) => money(i as In).toDecimalString(),
  'money.arithmetic': (i) => {
    const { op, a, b } = i as { op: 'add' | 'subtract'; a: In; b: In }
    return out(money(a)[op](money(b)))
  },
  'money.multiply': (i) => money(i as In).multiply((i as { factor: string }).factor).amountMinor,
  'money.divide': (i) => money(i as In).divide((i as { divisor: number }).divisor).amountMinor,
  'money.allocate': (i) =>
    money(i as In)
      .allocate((i as { ratios: number[] }).ratios)
      .map((m) => m.amountMinor),
  'fx.convert': (i, c) => {
    const {
      money: m,
      to,
      rates,
      now,
    } = i as { money: In; to: Currency; rates: FxRate[]; now: string }
    return convert(money(m), to, rates, now, {
      maxAgeHours: (c as { max_age_hours: number }).max_age_hours,
    })
  },
}

function run(files: VectorFile[]) {
  for (const file of files) {
    describe(file.file, () => {
      const engine = ENGINES[file.engine]
      it('has a TS adapter', () => expect(engine, `no adapter for ${file.engine}`).toBeDefined())
      if (!engine) return
      it.each(file.vectors.map((v) => [v.name, v] as const))('%s', (_name, v) => {
        expect(
          mismatch(engine(v.input, v.config), v.expected, v.tolerance ?? file.tolerance)
        ).toBeNull()
      })
      it.each(file.errors.map((v) => [v.name, v] as const))('%s raises', (_name, v) => {
        expect(() => engine(v.input, v.config)).toThrow(
          expect.objectContaining({ code: v.expected.error }) as Error
        )
      })
    })
  }
}

run(loadVectorFiles('money'))
run(loadVectorFiles('fx'))

describe('vector framework', () => {
  it('compares numbers within tolerance only', () => {
    expect(mismatch(0.1 + 0.2, 0.3, 1e-12)).toBeNull()
    expect(mismatch(0.1 + 0.2, 0.3)).not.toBeNull()
    expect(mismatch({ a: [1, 2] }, { a: [1, 2] })).toBeNull()
    expect(mismatch({ a: 1, b: 2 }, { a: 1 })).toBe('$.b: unexpected')
    expect(mismatch('1', 1)).not.toBeNull()
  })

  it('refuses to load the signing vectors', () => {
    expect(() => loadVectorFiles('signing')).toThrow(/signing/)
  })
})
