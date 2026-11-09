import type { RawSellerSignals } from '@apex/shared-types/contracts/browser-worker'
import {
  AggregationTemporality,
  DataPointType,
  InMemoryMetricExporter,
  MeterProvider,
  PeriodicExportingMetricReader,
} from '@opentelemetry/sdk-metrics'
import { describe, expect, it } from 'vitest'

import { WorkerError } from './errors.js'
import {
  createOtelScrapingMetrics,
  missingSignalsOf,
  outcomeOf,
  RecordingScrapingMetrics,
  type MetricTransport,
  type Outcome,
} from './metrics.js'

const BASE: RawSellerSignals = {
  platform: 'mock-a',
  platform_seller_id: 'seller-1',
  captured_at: '2026-11-09T10:00:00.000Z',
  account_age_days: 400,
  lifetime_transactions: 120,
  transactions_12m: 80,
  published_products_count: 12,
  reviews_total: 300,
  rating_count: 250,
  recent_reviews: [],
}

describe('outcomeOf', () => {
  it.each([
    ['captcha', 'captcha'],
    ['session_invalid', 'session_invalid'],
    ['timeout', 'timeout'],
    ['robots_disallowed', 'blocked'],
    ['rate_limited', 'blocked'],
    ['dom_changed', 'error'],
    ['upstream_error', 'error'],
    ['internal', 'error'],
    ['unknown_product', 'error'],
    ['unknown_seller', 'error'],
    ['validation_error', 'error'],
  ] as const)('maps WorkerError code %s to %s', (code, expected) => {
    expect(outcomeOf(new WorkerError(code, 500))).toBe(expected)
  })

  it('counts a success as ok when called with no error', () => {
    expect(outcomeOf()).toBe('ok')
  })

  it('counts an error that is not a WorkerError as error', () => {
    expect(outcomeOf(new Error('boom'))).toBe('error')
  })
})

describe('missingSignalsOf', () => {
  it('reports nothing when every field is published, including zeros', () => {
    const zeros: RawSellerSignals = {
      ...BASE,
      account_age_days: 0,
      lifetime_transactions: 0,
      transactions_12m: 0,
      published_products_count: 0,
      reviews_total: 0,
      rating_count: 0,
    }
    expect(missingSignalsOf(zeros)).toEqual([])
  })

  it('reports rating_count when it is null', () => {
    expect(missingSignalsOf({ ...BASE, rating_count: null })).toEqual(['rating_count'])
  })

  it('reports sales_count only when both sales fields are null', () => {
    expect(missingSignalsOf({ ...BASE, transactions_12m: null })).toEqual([])
    expect(missingSignalsOf({ ...BASE, lifetime_transactions: null })).toEqual([])
    expect(
      missingSignalsOf({ ...BASE, transactions_12m: null, lifetime_transactions: null })
    ).toEqual(['sales_count'])
  })

  it('reports account_age, reviews and catalog from their own fields', () => {
    expect(
      missingSignalsOf({
        ...BASE,
        account_age_days: null,
        reviews_total: null,
        published_products_count: null,
      })
    ).toEqual(['account_age', 'reviews', 'catalog'])
  })

  it('treats a field that the platform did not return at all as missing', () => {
    const { reviews_total: _omitted, ...withoutReviews } = BASE
    expect(missingSignalsOf(withoutReviews)).toEqual(['reviews'])
  })
})

describe('RecordingScrapingMetrics', () => {
  it('counts a captcha outcome on the captcha side counter as well', () => {
    const metrics = new RecordingScrapingMetrics()
    metrics.request({
      platform: 'mock-a',
      transport: 'http',
      outcome: 'captcha',
      durationSeconds: 1,
    })
    expect(metrics.captchas).toEqual(['mock-a'])
    expect(metrics.sessionInvalidations).toEqual([])
    expect(metrics.requests).toHaveLength(1)
  })

  it('counts a session_invalid outcome on the invalidation counter as well', () => {
    const metrics = new RecordingScrapingMetrics()
    metrics.request({
      platform: 'mock-a',
      transport: 'http',
      outcome: 'session_invalid',
      durationSeconds: 0,
    })
    expect(metrics.sessionInvalidations).toEqual(['mock-a'])
    expect(metrics.captchas).toEqual([])
  })

  it('does not touch the side counters for other outcomes', () => {
    const metrics = new RecordingScrapingMetrics()
    metrics.request({ platform: 'mock-a', transport: 'http', outcome: 'ok', durationSeconds: 0.5 })
    metrics.request({
      platform: 'mock-a',
      transport: 'http',
      outcome: 'blocked',
      durationSeconds: 0,
    })
    expect(metrics.captchas).toEqual([])
    expect(metrics.sessionInvalidations).toEqual([])
  })

  it('records a value outside its closed set as other', () => {
    const metrics = new RecordingScrapingMetrics()
    metrics.request({
      platform: 'mock-a',
      transport: 'ftp' as MetricTransport,
      outcome: 'paid-for-a-captcha' as Outcome,
      durationSeconds: 2,
    })
    expect(metrics.requests).toEqual([
      { platform: 'mock-a', transport: 'other', outcome: 'other', durationSeconds: 2 },
    ])
  })

  it('records missing signals per platform and signal name', () => {
    const metrics = new RecordingScrapingMetrics()
    metrics.signalsMissing('mock-a', { ...BASE, rating_count: null, reviews_total: null })
    expect(metrics.missingSignals).toEqual([
      { platform: 'mock-a', signal: 'rating_count' },
      { platform: 'mock-a', signal: 'reviews' },
    ])
  })

  it('reads the queue depth through the registered callback', async () => {
    const metrics = new RecordingScrapingMetrics()
    await expect(metrics.readQueueDepth()).rejects.toThrow('not registered')
    await metrics.registerQueueDepth(() => Promise.resolve({ scraping: 7, negotiation: 0 }))
    await expect(metrics.readQueueDepth()).resolves.toEqual({ scraping: 7, negotiation: 0 })
  })
})

interface EmittedMetric {
  name: string
  unit: string
  dataPointType: DataPointType
  points: Array<{ attributes: Record<string, unknown>; value?: unknown }>
}

function otelHarness() {
  const exporter = new InMemoryMetricExporter(AggregationTemporality.CUMULATIVE)
  const reader = new PeriodicExportingMetricReader({ exporter, exportIntervalMillis: 60_000 })
  const provider = new MeterProvider({ readers: [reader] })
  const metrics = createOtelScrapingMetrics(provider.getMeter('apex-browser-worker'))
  async function collect(): Promise<Map<string, EmittedMetric>> {
    await reader.forceFlush()
    const batches = exporter.getMetrics()
    const latest = batches[batches.length - 1]
    const emitted = new Map<string, EmittedMetric>()
    for (const scope of latest?.scopeMetrics ?? []) {
      for (const metric of scope.metrics) {
        emitted.set(metric.descriptor.name, {
          name: metric.descriptor.name,
          unit: metric.descriptor.unit,
          dataPointType: metric.dataPointType,
          points: metric.dataPoints.map((point) => ({
            attributes: point.attributes,
            value: 'value' in point ? point.value : undefined,
          })),
        })
      }
    }
    return emitted
  }
  return {
    metrics,
    collect,
    shutdown: () => provider.shutdown(),
  }
}

describe('createOtelScrapingMetrics (OpenTelemetry API and SDK, in-memory reader)', () => {
  it('emits the catalog instrument names, units and types from docs/observability/metrics.md', async () => {
    const h = otelHarness()
    try {
      await h.metrics.registerQueueDepth(() => Promise.resolve({ scraping: 3, negotiation: 0 }))
      h.metrics.request({
        platform: 'mock-a',
        transport: 'http',
        outcome: 'captcha',
        durationSeconds: 1.5,
      })
      h.metrics.request({
        platform: 'mock-a',
        transport: 'http',
        outcome: 'session_invalid',
        durationSeconds: 0.25,
      })
      h.metrics.signalsMissing('mock-a', { ...BASE, rating_count: null })

      const emitted = await h.collect()

      const unitsByName = Object.fromEntries(
        [...emitted.values()].map((metric) => [metric.name, metric.unit])
      )
      expect(unitsByName).toEqual({
        'apex.scraping.requests': '{request}',
        'apex.scraping.request.duration': 's',
        'apex.scraping.captchas': '{captcha}',
        'apex.scraping.session.invalidations': '{session}',
        'apex.scraping.signals.missing': '{signal}',
        'apex.scraping.queue.depth': '{job}',
      })
      expect(emitted.get('apex.scraping.request.duration')?.dataPointType).toBe(
        DataPointType.HISTOGRAM
      )
      expect(emitted.get('apex.scraping.queue.depth')?.dataPointType).toBe(DataPointType.GAUGE)
      expect(emitted.get('apex.scraping.requests')?.dataPointType).toBe(DataPointType.SUM)
    } finally {
      await h.shutdown()
    }
  })

  it('uses the closed label sets and records out-of-set values as other', async () => {
    const h = otelHarness()
    try {
      h.metrics.request({
        platform: 'mock-a',
        transport: 'ftp' as MetricTransport,
        outcome: 'weird' as Outcome,
        durationSeconds: 1,
      })
      const emitted = await h.collect()
      const requests = emitted.get('apex.scraping.requests')
      expect(requests?.points).toEqual([
        {
          attributes: { platform: 'mock-a', transport: 'other', outcome: 'other' },
          value: 1,
        },
      ])
    } finally {
      await h.shutdown()
    }
  })

  it('reports the queue depth per queue', async () => {
    const h = otelHarness()
    try {
      await h.metrics.registerQueueDepth(() => Promise.resolve({ scraping: 5, negotiation: 0 }))
      const emitted = await h.collect()
      const depth = emitted.get('apex.scraping.queue.depth')
      expect(depth?.points).toEqual(
        expect.arrayContaining([
          { attributes: { queue: 'scraping' }, value: 5 },
          { attributes: { queue: 'negotiation' }, value: 0 },
        ])
      )
    } finally {
      await h.shutdown()
    }
  })

  it('shows no queue depth when the read fails, instead of a stale value', async () => {
    const h = otelHarness()
    try {
      await h.metrics.registerQueueDepth(() => Promise.reject(new Error('redis down')))
      const emitted = await h.collect()
      expect(emitted.get('apex.scraping.queue.depth')).toBeUndefined()
    } finally {
      await h.shutdown()
    }
  })
})
