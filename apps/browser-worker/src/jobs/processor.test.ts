import type { JobRequest } from '@apex/shared-types/contracts/browser-worker'
import { describe, expect, it } from 'vitest'

import { AdapterRegistry } from '../adapters/index.js'
import { RecordingScrapingMetrics } from '../metrics.js'
import { StaticFlags } from '../platform/flags.js'
import { FakePlatformAdapter } from '../testing/fakes.js'

import { processJob } from './processor.js'

const registry = new AdapterRegistry(
  [new FakePlatformAdapter('mock-a', 'http')],
  new StaticFlags({ 'platform.mock-a.enabled': true })
)

const base = {
  tenant_id: 'tenant-1',
  mission_id: 'mission-1',
  trace_id: 'trace-1',
  platform: 'mock-a',
}

describe('processJob metrics', () => {
  it('records the signals the platform did not publish for a seller_signals job', async () => {
    const metrics = new RecordingScrapingMetrics()
    const request: JobRequest = {
      ...base,
      kind: 'seller_signals',
      platform_seller_id: 'seller-1',
    }
    const result = await processJob(request, registry, metrics)
    expect(result.kind).toBe('seller_signals')
    // The fake publishes rating_count and account_age_days, and omits the sales, review and catalog fields.
    expect(metrics.missingSignals).toEqual([
      { platform: 'mock-a', signal: 'sales_count' },
      { platform: 'mock-a', signal: 'reviews' },
      { platform: 'mock-a', signal: 'catalog' },
    ])
  })

  it('records no signal metrics for other kinds of job', async () => {
    const metrics = new RecordingScrapingMetrics()
    await processJob({ ...base, kind: 'search', query: 'steel' }, registry, metrics)
    expect(metrics.missingSignals).toEqual([])
  })

  it('processes a seller_signals job the same way without a metrics dependency', async () => {
    const result = await processJob(
      { ...base, kind: 'seller_signals', platform_seller_id: 'seller-1' },
      registry
    )
    expect(result).toMatchObject({ kind: 'seller_signals', signals: { rating_count: 500 } })
  })
})
