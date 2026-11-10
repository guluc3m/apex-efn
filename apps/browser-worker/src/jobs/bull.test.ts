import { randomUUID } from 'node:crypto'

import type { JobRequest } from '@apex/shared-types/contracts/browser-worker'
import { Redis } from 'ioredis'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { AdapterRegistry } from '../adapters/index.js'
import { StaticFlags } from '../platform/flags.js'
import { FakePlatformAdapter } from '../testing/fakes.js'

import { BullJobService } from './bull.js'

const REDIS_URL = process.env.REDIS_INTEGRATION_URL ?? ''

describe.skipIf(!REDIS_URL)('BullJobService against Redis', () => {
  let connection: Redis
  let service: BullJobService

  beforeAll(() => {
    connection = new Redis(REDIS_URL, { maxRetriesPerRequest: null })
    const registry = new AdapterRegistry(
      [new FakePlatformAdapter('mock-a', 'http')],
      new StaticFlags({ 'platform.mock-a.enabled': true })
    )
    service = new BullJobService(registry, connection, { jobAttempts: 3, jobBackoffMs: 100 })
  })

  afterAll(async () => {
    await service.close()
    await connection.quit()
  })

  const request = (query: string): JobRequest => ({
    kind: 'search',
    tenant_id: 'tenant-1',
    mission_id: 'mission-1',
    trace_id: 'trace-1',
    platform: 'mock-a',
    query,
  })

  it('deduplicates a job by its idempotency key and finds it again by id', async () => {
    const key = `idem-key-${randomUUID()}`
    const first = await service.enqueue(request('steel'), key)
    const second = await service.enqueue(request('steel'), key)
    expect(first.deduplicated).toBe(false)
    expect(second).toEqual({ job_id: first.job_id, status: 'queued', deduplicated: true })

    const state = await service.get(first.job_id)
    expect(state).toMatchObject({
      job_id: first.job_id,
      kind: 'search',
      platform: 'mock-a',
      status: 'queued',
    })
  })

  it('rejects the same key with a different body', async () => {
    const key = `idem-key-${randomUUID()}`
    await service.enqueue(request('steel'), key)
    await expect(service.enqueue(request('copper'), key)).rejects.toMatchObject({
      code: 'idempotency_conflict',
      status: 409,
    })
  })
})
