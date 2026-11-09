import type { Redis } from 'ioredis'
import { describe, expect, it, vi } from 'vitest'

import { createQueueDepthReader } from './bull.js'

const fake = vi.hoisted(() => ({
  counts: new Map<string, Record<string, number>>(),
  requestedStates: [] as string[][],
  closed: [] as string[],
}))

vi.mock('bullmq', async (importOriginal) => {
  const actual = await importOriginal<typeof import('bullmq')>()
  class FakeQueue {
    constructor(readonly name: string) {}

    getJobCounts(...types: string[]): Promise<Record<string, number>> {
      fake.requestedStates.push(types)
      return Promise.resolve(fake.counts.get(this.name) ?? {})
    }

    close(): Promise<void> {
      fake.closed.push(this.name)
      return Promise.resolve()
    }
  }
  return { ...actual, Queue: FakeQueue }
})

const connection = {} as Redis

describe('createQueueDepthReader', () => {
  it('sums waiting, active, delayed and prioritized jobs across the scrape queues', async () => {
    fake.counts.set('scrape-mock-a', {
      waiting: 2,
      active: 1,
      delayed: 3,
      prioritized: 4,
      completed: 100,
      failed: 9,
    })
    fake.counts.set('scrape-mock-b', { waiting: 5 })
    const reader = createQueueDepthReader(['mock-a', 'mock-b'], connection)
    await expect(reader.read()).resolves.toEqual({ scraping: 15, negotiation: 0 })
    expect(fake.requestedStates).toEqual([
      ['waiting', 'active', 'delayed', 'prioritized'],
      ['waiting', 'active', 'delayed', 'prioritized'],
    ])
    await reader.close()
  })

  it('reports zero for both queues when no platform is registered', async () => {
    const reader = createQueueDepthReader([], connection)
    await expect(reader.read()).resolves.toEqual({ scraping: 0, negotiation: 0 })
  })

  it('closes every queue handle it created', async () => {
    fake.closed.length = 0
    const reader = createQueueDepthReader(['mock-a', 'mock-b'], connection)
    await reader.close()
    expect(fake.closed).toEqual(['scrape-mock-a', 'scrape-mock-b'])
  })
})
