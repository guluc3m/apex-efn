import type { JobError, JobRequest, JobResult } from '@apex/shared-types/contracts/browser-worker'

import type { AdapterRegistry } from '../adapters/index.js'
import { WorkerError } from '../errors.js'
import type { ScrapingMetrics } from '../metrics.js'

const DEFAULT_MAX_RESULTS = 50
const DEFAULT_MAX_REVIEWS = 200
const MAX_MESSAGE_LENGTH = 1000

export async function processJob(
  request: JobRequest,
  registry: AdapterRegistry,
  metrics?: ScrapingMetrics
): Promise<JobResult> {
  const adapter = registry.require(request.platform)
  switch (request.kind) {
    case 'search': {
      const output = await adapter.search({
        query: request.query,
        quantity: request.quantity ?? null,
        maxResults: request.max_results ?? DEFAULT_MAX_RESULTS,
      })
      return {
        kind: 'search',
        offers: output.offers,
        skipped: output.skipped,
        truncated: output.truncated,
      }
    }
    case 'product':
      return { kind: 'product', offer: await adapter.getProduct(request.platform_offer_id) }
    case 'seller':
      return { kind: 'seller', seller: await adapter.getSeller(request.platform_seller_id) }
    case 'seller_signals': {
      const signals = await adapter.getSellerSignals(request.platform_seller_id, {
        maxReviews: request.max_reviews ?? DEFAULT_MAX_REVIEWS,
      })
      metrics?.signalsMissing(adapter.platform, signals)
      return { kind: 'seller_signals', signals }
    }
  }
}

/** Closed code and a bounded message. Unknown errors are reported as `internal` and retryable, without their text. */
export function jobErrorOf(error: unknown): JobError {
  if (error instanceof WorkerError) {
    return {
      code: error.code,
      message: error.message.slice(0, MAX_MESSAGE_LENGTH),
      retryable: error.retryable,
    }
  }
  return { code: 'internal', message: 'internal error', retryable: true }
}
