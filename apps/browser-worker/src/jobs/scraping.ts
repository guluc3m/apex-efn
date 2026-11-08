/**
 * Scraping job processor
 */

import type { Job } from 'bullmq'

export interface ScrapingJobData {
  platform: string
  query: string
  filters?: Record<string, unknown>
  missionId: string
}

export interface ScrapingJobResult {
  offers: unknown[]
  sellerSignals: Record<string, unknown>
}

// eslint-disable-next-line @typescript-eslint/require-await -- stub hasta implementar el job
export async function processScrapingJob(job: Job<ScrapingJobData>): Promise<ScrapingJobResult> {
  const { platform, query, missionId } = job.data

  console.log(`Processing scraping job for ${platform}: ${query} (mission: ${missionId})`)

  // TODO: Implement actual scraping with PlatformAdapter
  // This is a scaffold - real implementation in Phase 1

  return {
    offers: [],
    sellerSignals: {},
  }
}
