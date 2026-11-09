import { describe, expect, it } from 'vitest'

import { bodyHash, InMemoryIdempotencyStore, withIdempotency } from './idempotency.js'
import { FixedClock } from './testing/fakes.js'

const START = '2026-11-09T10:00:00.000Z'

describe('bodyHash', () => {
  it('ignores object key order', () => {
    expect(bodyHash({ a: 1, b: { c: 2, d: [3, { e: 4, f: 5 }] } })).toBe(
      bodyHash({ b: { d: [3, { f: 5, e: 4 }], c: 2 }, a: 1 })
    )
  })

  it('changes when a value changes', () => {
    expect(bodyHash({ a: 1 })).not.toBe(bodyHash({ a: 2 }))
  })
})

describe('InMemoryIdempotencyStore', () => {
  it('returns a stored response until its TTL has passed', async () => {
    const clock = new FixedClock(START)
    const store = new InMemoryIdempotencyStore(clock)
    await store.put('scope', 'key-1', { bodyHash: 'h', status: 201, body: { ok: true } }, 60)

    clock.advance(59_000)
    expect(await store.get('scope', 'key-1')).toMatchObject({ status: 201 })

    clock.advance(1_000)
    expect(await store.get('scope', 'key-1')).toBeNull()
  })

  it('keeps scopes apart', async () => {
    const store = new InMemoryIdempotencyStore(new FixedClock(START))
    await store.put('send:a', 'key-1', { bodyHash: 'h', status: 201, body: {} }, 60)
    expect(await store.get('send:b', 'key-1')).toBeNull()
  })
})

describe('withIdempotency', () => {
  it('runs once and replays the stored response for the same body', async () => {
    const store = new InMemoryIdempotencyStore(new FixedClock(START))
    let runs = 0
    const run = (): Promise<{ status: number; body: { n: number } }> => {
      runs += 1
      return Promise.resolve({ status: 201, body: { n: runs } })
    }
    const first = await withIdempotency(
      store,
      'open-chat',
      'key-aaaaaaaaaaaaaaaa',
      { x: 1 },
      60,
      run
    )
    const second = await withIdempotency(
      store,
      'open-chat',
      'key-aaaaaaaaaaaaaaaa',
      { x: 1 },
      60,
      run
    )
    expect(second).toEqual(first)
    expect(runs).toBe(1)
  })

  it('rejects a replay with a different body', async () => {
    const store = new InMemoryIdempotencyStore(new FixedClock(START))
    const run = (): Promise<{ status: number; body: unknown }> =>
      Promise.resolve({ status: 201, body: {} })
    await withIdempotency(store, 'open-chat', 'key-bbbbbbbbbbbbbbbb', { x: 1 }, 60, run)
    await expect(
      withIdempotency(store, 'open-chat', 'key-bbbbbbbbbbbbbbbb', { x: 2 }, 60, run)
    ).rejects.toMatchObject({ code: 'idempotency_conflict', status: 409 })
  })

  it('runs at most once for concurrent calls with the same key', async () => {
    const store = new InMemoryIdempotencyStore(new FixedClock(START))
    let runs = 0
    const run = async (): Promise<{ status: number; body: unknown }> => {
      runs += 1
      await new Promise((resolve) => setImmediate(resolve))
      return { status: 201, body: { runs } }
    }
    const results = await Promise.all([
      withIdempotency(store, 'send:chat', 'key-cccccccccccccccc', { t: 'hi' }, 60, run),
      withIdempotency(store, 'send:chat', 'key-cccccccccccccccc', { t: 'hi' }, 60, run),
    ])
    expect(runs).toBe(1)
    expect(results[0]).toEqual(results[1])
  })

  it('does not store a failed run, so a retry runs again', async () => {
    const store = new InMemoryIdempotencyStore(new FixedClock(START))
    let attempts = 0
    const run = (): Promise<{ status: number; body: unknown }> => {
      attempts += 1
      if (attempts === 1) {
        return Promise.reject(new Error('upstream down'))
      }
      return Promise.resolve({ status: 201, body: { ok: true } })
    }
    await expect(
      withIdempotency(store, 'send:chat', 'key-dddddddddddddddd', { t: 'hi' }, 60, run)
    ).rejects.toThrow('upstream down')
    await expect(
      withIdempotency(store, 'send:chat', 'key-dddddddddddddddd', { t: 'hi' }, 60, run)
    ).resolves.toEqual({ status: 201, body: { ok: true } })
    expect(attempts).toBe(2)
  })
})
