/** Seeded PRNG (mulberry32). The mock never uses Math.random, so transcripts are reproducible. */
export interface Rng {
  next(): number
  pick<T>(items: readonly T[]): T
}

export function hashString(value: string): number {
  let h = 2166136261
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

export function createRng(seed: number): Rng {
  let a = seed >>> 0
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  return {
    next,
    pick<T>(items: readonly T[]): T {
      if (items.length === 0) throw new Error('pick from empty list')
      return items[Math.floor(next() * items.length)] as T
    },
  }
}
