/**
 * Scraping health metrics (docs/observability/metrics.md, section 1). Instrument names and units are the OTel names
 * from the catalog. Labels come only from closed sets: a value outside its set is recorded as `other`.
 *
 * Never a label: tenant, mission, offer or seller ids, prices, URLs, tokens. `platform` is the adapter registry id,
 * which the registry already validates at startup.
 */
import type { RawSellerSignals } from '@apex/shared-types/contracts/browser-worker'
import type { Meter } from '@opentelemetry/api'

import { WorkerError } from './errors.js'

export const TRANSPORTS = ['http', 'browser'] as const
export type MetricTransport = (typeof TRANSPORTS)[number]

export const OUTCOMES = ['ok', 'error', 'blocked', 'captcha', 'timeout', 'session_invalid'] as const
export type Outcome = (typeof OUTCOMES)[number]

export const SIGNAL_NAMES = [
  'rating_count',
  'sales_count',
  'account_age',
  'reviews',
  'catalog',
] as const
export type SignalName = (typeof SIGNAL_NAMES)[number]

export interface QueueDepths {
  scraping: number
  negotiation: number
}

export interface RequestSample {
  platform: string
  transport: MetricTransport
  outcome: Outcome
  durationSeconds: number
}

export interface ScrapingMetrics {
  /** One call per logical request, after its retries, with the final outcome. */
  request(sample: RequestSample): void
  /** Counts each signal whose contract field is null (or absent). A value of 0 is a real value, not missing. */
  signalsMissing(platform: string, signals: RawSellerSignals): void
  /** Reads the queue backlog on each collection. Resolves after the first read. */
  registerQueueDepth(callback: () => Promise<QueueDepths>): Promise<void>
}

/** Maps a value to its closed label, or to `other` when it is outside the set. */
export function closedLabel<T extends string>(value: string, allowed: readonly T[]): T | 'other' {
  return (allowed as readonly string[]).includes(value) ? (value as T) : 'other'
}

/**
 * Outcome of one logical request. Call with no argument for a success. A failure maps from its WorkerError code;
 * anything that is not a WorkerError counts as `error`.
 */
export function outcomeOf(error?: unknown): Outcome {
  if (error === undefined) {
    return 'ok'
  }
  if (!(error instanceof WorkerError)) {
    return 'error'
  }
  switch (error.code) {
    case 'captcha':
      return 'captcha'
    case 'session_invalid':
      return 'session_invalid'
    case 'timeout':
      return 'timeout'
    case 'robots_disallowed':
    case 'rate_limited':
      return 'blocked'
    default:
      return 'error'
  }
}

function isMissing(value: unknown): boolean {
  return value === null || value === undefined
}

/**
 * Signals the platform did not publish. `sales_count` is missing only when both sales fields are missing.
 * A signal of 0 is a real value and is never counted.
 */
export function missingSignalsOf(signals: RawSellerSignals): SignalName[] {
  const missing: SignalName[] = []
  if (isMissing(signals.rating_count)) {
    missing.push('rating_count')
  }
  if (isMissing(signals.transactions_12m) && isMissing(signals.lifetime_transactions)) {
    missing.push('sales_count')
  }
  if (isMissing(signals.account_age_days)) {
    missing.push('account_age')
  }
  if (isMissing(signals.reviews_total)) {
    missing.push('reviews')
  }
  if (isMissing(signals.published_products_count)) {
    missing.push('catalog')
  }
  return missing
}

interface EmittedSample {
  platform: string
  transport: string
  outcome: string
  durationSeconds: number
}

function normalizedSample(sample: RequestSample): EmittedSample {
  return {
    platform: sample.platform,
    transport: closedLabel(sample.transport, TRANSPORTS),
    outcome: closedLabel(sample.outcome, OUTCOMES),
    durationSeconds: sample.durationSeconds,
  }
}

const QUEUE_NAMES = ['scraping', 'negotiation'] as const

/** OpenTelemetry implementation. Instrument names and units follow docs/observability/metrics.md section 1. */
export function createOtelScrapingMetrics(meter: Meter): ScrapingMetrics {
  const requests = meter.createCounter('apex.scraping.requests', {
    unit: '{request}',
    description: 'Logical scraping requests by platform, transport and outcome',
  })
  const duration = meter.createHistogram('apex.scraping.request.duration', {
    unit: 's',
    description: 'Duration of a logical scraping request, including its retries',
  })
  const captchas = meter.createCounter('apex.scraping.captchas', {
    unit: '{captcha}',
    description: 'CAPTCHA challenges met while scraping',
  })
  const invalidations = meter.createCounter('apex.scraping.session.invalidations', {
    unit: '{session}',
    description: 'Platform sessions reported invalid',
  })
  const missingSignals = meter.createCounter('apex.scraping.signals.missing', {
    unit: '{signal}',
    description: 'Seller signals the platform did not publish',
  })
  const queueDepth = meter.createObservableGauge('apex.scraping.queue.depth', {
    unit: '{job}',
    description: 'Jobs waiting, active, delayed or prioritized, by queue',
  })

  // Collection callbacks in the OTel SDK are synchronous. The value is read asynchronously on each collection and
  // shown on the next one. A failed read clears the value, so the gauge shows no data rather than a stale depth.
  let latest: QueueDepths | null = null
  let read: (() => Promise<QueueDepths>) | null = null
  const refresh = (): Promise<void> => {
    if (read === null) {
      return Promise.resolve()
    }
    return read().then(
      (depths) => {
        latest = depths
      },
      () => {
        latest = null
      }
    )
  }
  queueDepth.addCallback((result) => {
    if (latest !== null) {
      for (const queue of QUEUE_NAMES) {
        result.observe(latest[queue], { queue })
      }
    }
    void refresh()
  })

  return {
    request(sample) {
      const { platform, transport, outcome, durationSeconds } = normalizedSample(sample)
      requests.add(1, { platform, transport, outcome })
      duration.record(durationSeconds, { platform, transport })
      if (outcome === 'captcha') {
        captchas.add(1, { platform })
      }
      if (outcome === 'session_invalid') {
        invalidations.add(1, { platform })
      }
    },
    signalsMissing(platform, signals) {
      for (const signal of missingSignalsOf(signals)) {
        missingSignals.add(1, { platform, signal })
      }
    },
    registerQueueDepth(callback) {
      read = callback
      return refresh()
    },
  }
}

export interface RecordedRequest {
  platform: string
  transport: string
  outcome: string
  durationSeconds: number
}

/** Test double. Stores the labels as they would be emitted, after the closed-set mapping. */
export class RecordingScrapingMetrics implements ScrapingMetrics {
  readonly requests: RecordedRequest[] = []
  readonly captchas: string[] = []
  readonly sessionInvalidations: string[] = []
  readonly missingSignals: Array<{ platform: string; signal: string }> = []
  private depthCallback: (() => Promise<QueueDepths>) | null = null

  request(sample: RequestSample): void {
    const normalized = normalizedSample(sample)
    this.requests.push({ ...normalized })
    if (normalized.outcome === 'captcha') {
      this.captchas.push(normalized.platform)
    }
    if (normalized.outcome === 'session_invalid') {
      this.sessionInvalidations.push(normalized.platform)
    }
  }

  signalsMissing(platform: string, signals: RawSellerSignals): void {
    for (const signal of missingSignalsOf(signals)) {
      this.missingSignals.push({ platform, signal })
    }
  }

  registerQueueDepth(callback: () => Promise<QueueDepths>): Promise<void> {
    this.depthCallback = callback
    return Promise.resolve()
  }

  readQueueDepth(): Promise<QueueDepths> {
    if (this.depthCallback === null) {
      return Promise.reject(new Error('queue depth was not registered'))
    }
    return this.depthCallback()
  }
}
