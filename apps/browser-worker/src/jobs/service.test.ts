import type { JobRequest } from '@apex/shared-types/contracts/browser-worker'
import { describe, expect, it } from 'vitest'

import { WorkerError } from '../errors.js'
import { createHarness } from '../testing/harness.js'

const KEY = 'idem-key-job-0000000001'

function searchRequest(overrides: Partial<JobRequest> = {}): JobRequest {
  return {
    kind: 'search',
    tenant_id: 'tenant-1',
    mission_id: 'mission-1',
    trace_id: 'trace-1',
    platform: 'mock-a',
    priority: 5,
    query: 'steel bolts',
    quantity: 500,
    max_results: 50,
    ...overrides,
  } as JobRequest
}

describe('InMemoryJobService', () => {
  it('deduplicates by idempotency key and reports the same job', async () => {
    const { jobs } = createHarness()
    const first = await jobs.enqueue(searchRequest(), KEY)
    const second = await jobs.enqueue(searchRequest(), KEY)
    expect(first).toEqual({ job_id: first.job_id, status: 'queued', deduplicated: false })
    expect(second).toEqual({ job_id: first.job_id, status: 'queued', deduplicated: true })
  })

  it('rejects the same key with a different body', async () => {
    const { jobs } = createHarness()
    await jobs.enqueue(searchRequest(), KEY)
    await expect(jobs.enqueue(searchRequest({ query: 'other' }), KEY)).rejects.toMatchObject({
      code: 'idempotency_conflict',
      status: 409,
    })
  })

  it('fails enqueue for an unknown platform and does not store the job', async () => {
    const { jobs } = createHarness()
    await expect(jobs.enqueue(searchRequest({ platform: 'nope' }), KEY)).rejects.toMatchObject({
      code: 'unknown_platform',
    })
    expect(await jobs.get('anything')).toBeNull()
  })

  it('never calls a disabled platform', async () => {
    const { jobs, disabled } = createHarness()
    await expect(jobs.enqueue(searchRequest({ platform: 'mock-c' }), KEY)).rejects.toMatchObject({
      code: 'platform_disabled',
      status: 409,
    })
    await jobs.runAll()
    expect(disabled.calls).toEqual([])
  })

  it('runs each kind and returns a typed result', async () => {
    const { jobs } = createHarness()
    const requests: JobRequest[] = [
      searchRequest(),
      {
        kind: 'product',
        tenant_id: 'tenant-1',
        mission_id: 'mission-1',
        trace_id: 'trace-1',
        platform: 'mock-a',
        platform_offer_id: 'offer-9',
      },
      {
        kind: 'seller',
        tenant_id: 'tenant-1',
        mission_id: 'mission-1',
        trace_id: 'trace-1',
        platform: 'mock-a',
        platform_seller_id: 'seller-9',
      },
      {
        kind: 'seller_signals',
        tenant_id: 'tenant-1',
        mission_id: 'mission-1',
        trace_id: 'trace-1',
        platform: 'mock-a',
        platform_seller_id: 'seller-9',
      },
    ]
    const ids = await Promise.all(
      requests.map((request, index) => jobs.enqueue(request, `${KEY}-${index}`))
    )
    await jobs.runAll()
    const states = await Promise.all(ids.map((accepted) => jobs.get(accepted.job_id)))

    expect(states.map((state) => state?.status)).toEqual([
      'succeeded',
      'succeeded',
      'succeeded',
      'succeeded',
    ])
    expect(states.map((state) => state?.result?.kind)).toEqual([
      'search',
      'product',
      'seller',
      'seller_signals',
    ])
    expect(states[0]?.result).toMatchObject({ kind: 'search', truncated: false })
    expect(states[0]?.result).toMatchObject({
      skipped: [{ reason: 'unsupported_currency', currency_raw: 'JPY' }],
    })
    expect(states[0]?.attempts).toBe(1)
    expect(states[0]?.finished_at).toBe('2026-11-09T10:00:00.000Z')
    expect(states[0]?.error).toBeNull()
  })

  it('reports a retryable platform failure with its closed code', async () => {
    const harness = createHarness()
    harness.sourcing.failSearchWith = new WorkerError('captcha', 502, { retryable: true })
    const accepted = await harness.jobs.enqueue(searchRequest(), KEY)
    await harness.jobs.runAll()
    const state = await harness.jobs.get(accepted.job_id)
    expect(state).toMatchObject({
      status: 'failed',
      result: null,
      error: { code: 'captcha', retryable: true },
    })
  })

  it('reports an unexpected error as internal without its message', async () => {
    const harness = createHarness()
    harness.sourcing.failSearchWith = new Error('secret upstream detail')
    const accepted = await harness.jobs.enqueue(searchRequest(), KEY)
    await harness.jobs.runAll()
    const state = await harness.jobs.get(accepted.job_id)
    expect(state?.status).toBe('failed')
    expect(state?.error).toEqual({ code: 'internal', message: 'internal error', retryable: true })
    expect(JSON.stringify(state)).not.toContain('secret upstream detail')
  })

  it('returns null for an unknown job', async () => {
    const { jobs } = createHarness()
    expect(await jobs.get('missing')).toBeNull()
  })
})
