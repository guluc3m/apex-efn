import type { SellerSignalSnapshot } from '@apex/shared-types/contracts'
import { loadVectorFiles, mismatch } from '@apex/test-vectors'
import { describe, expect, it } from 'vitest'

import {
  computeSellerConfidence,
  normalInvCdf,
  type Review,
  trustConfigFrom,
} from './seller/index.js'

type Engine = (input: unknown, config: unknown) => unknown

// Engine ids of packages/test-vectors/trust (D3-06). tests/domain/test_vectors.py runs the same files.
const ENGINES: Record<string, Engine> = {
  'trust.compute': (i, c) => {
    const { snapshot, now, reviews } = i as {
      snapshot: SellerSignalSnapshot
      now: string
      reviews?: Review[]
    }
    const { config_version, ...seller } = c as { config_version: string } & Record<string, unknown>
    return computeSellerConfidence(
      snapshot,
      trustConfigFrom(seller, config_version),
      now,
      reviews ?? null
    )
  },
  'trust.normal_inv_cdf': (i) => normalInvCdf((i as { p: number }).p),
}

for (const file of loadVectorFiles('trust')) {
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
