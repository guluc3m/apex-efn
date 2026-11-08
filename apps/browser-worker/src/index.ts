/**
 * Browser Worker - Scraping and chat automation
 *
 * Handles browser automation for:
 * - Platform scraping (product search, seller info)
 * - Chat-based negotiation
 *
 * Uses Puppeteer with stealth plugin for anti-bot evasion.
 */

import { Worker } from 'bullmq'
import { Redis } from 'ioredis'

import { config } from './config.js'
import { processNegotiationJob, type NegotiationJobData } from './jobs/negotiation.js'
import { processScrapingJob, type ScrapingJobData } from './jobs/scraping.js'

const redis = new Redis(config.redisUrl, {
  maxRetriesPerRequest: null,
})

const scrapingWorker = new Worker<ScrapingJobData>(
  'scraping',
  async (job) => {
    return processScrapingJob(job)
  },
  {
    connection: redis,
    concurrency: config.scrapingConcurrency,
  }
)

const negotiationWorker = new Worker<NegotiationJobData>(
  'negotiation',
  async (job) => {
    return processNegotiationJob(job)
  },
  {
    connection: redis,
    concurrency: config.negotiationConcurrency,
  }
)

scrapingWorker.on('completed', (job) => {
  console.log(`Scraping job ${job.id} completed`)
})

scrapingWorker.on('failed', (job, err) => {
  console.error(`Scraping job ${job?.id} failed:`, err)
})

negotiationWorker.on('completed', (job) => {
  console.log(`Negotiation job ${job.id} completed`)
})

negotiationWorker.on('failed', (job, err) => {
  console.error(`Negotiation job ${job?.id} failed:`, err)
})

console.log('Browser worker started')
