import { loadVectorFiles, mismatch, type VectorFile } from '@apex/test-vectors'
import { describe, expect, it } from 'vitest'

// D3-01 framework sample. D3-02 replaces these adapters with the real money engine.
class CodedError extends Error {
  constructor(readonly code: string) {
    super(code)
  }
}

type Engine = (input: unknown, config: unknown) => unknown

const ENGINES: Record<string, Engine> = {
  'sample.half_away_division': (input) => {
    const { numerator, denominator } = input as {
      numerator: number | string
      denominator: number | string
    }
    const n = BigInt(numerator)
    const d = BigInt(denominator)
    if (d === 0n) throw new CodedError('division_by_zero')
    const abs = (x: bigint) => (x < 0n ? -x : x)
    let q = abs(n) / abs(d)
    if (2n * (abs(n) % abs(d)) >= abs(d)) q += 1n
    if (n < 0n !== d < 0n) q = -q
    return typeof numerator === 'string' ? q.toString() : Number(q)
  },
  'sample.mean': (input) => {
    const xs = input as number[]
    if (xs.length === 0) throw new CodedError('empty_sample')
    return xs.reduce((a, b) => a + b, 0) / xs.length
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

run(loadVectorFiles('sample'))

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
