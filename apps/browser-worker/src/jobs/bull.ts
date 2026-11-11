import type {
  JobAccepted,
  JobError,
  JobRequest,
  JobResult,
  JobState,
  JobStatus,
} from '@apex/shared-types/contracts/browser-worker'
import { Queue, UnrecoverableError, Worker, type Job } from 'bullmq'
import type { Redis } from 'ioredis'
import type { Logger } from 'pino'

import type { AdapterRegistry } from '../adapters/index.js'
import { sha256Hex } from '../hash.js'
import { bodyHash, idempotencyConflict } from '../idempotency.js'
import type { QueueDepths, ScrapingMetrics } from '../metrics.js'

import { jobErrorOf, processJob } from './processor.js'
import type { JobService } from './service.js'

const RETENTION_SECONDS = 7 * 24 * 60 * 60
const DEFAULT_PRIORITY = 5
const DEAD_LETTER_QUEUE = 'dead-letter'
const BACKLOG_STATES = ['waiting', 'active', 'delayed', 'prioritized'] as const

export interface QueuedJob {
  request: JobRequest
  bodyHash: string
  lastError?: JobError
  deadLettered?: boolean
}

type ScrapeJob = Job<QueuedJob, JobResult>
type ScrapeQueue = Queue<QueuedJob, JobResult>

export function scrapeQueueName(platform: string): string {
  return `scrape-${platform}`
}

function jobIndexKey(jobId: string): string {
  return `bw:jobs:${jobId}`
}

export interface BullJobOptions {
  jobAttempts: number
  jobBackoffMs: number
}

/** Production JobService. The job id is the SHA-256 of the Idempotency-Key, so BullMQ itself deduplicates. */
export class BullJobService implements JobService {
  private readonly queues = new Map<string, ScrapeQueue>()

  constructor(
    private readonly registry: AdapterRegistry,
    private readonly connection: Redis,
    private readonly options: BullJobOptions
  ) {}

  async enqueue(request: JobRequest, idempotencyKey: string): Promise<JobAccepted> {
    const jobId = sha256Hex(idempotencyKey)
    const hash = bodyHash(request)
    const existing = await this.find(jobId)
    if (existing !== undefined) {
      if (existing.data.bodyHash !== hash) {
        throw idempotencyConflict()
      }
      return {
        job_id: jobId,
        status: statusOf(await existing.getState(), existing.data),
        deduplicated: true,
      }
    }
    this.registry.require(request.platform)
    const queue = this.queueNamed(scrapeQueueName(request.platform))
    const job = await queue.add(
      request.kind,
      { request, bodyHash: hash },
      {
        jobId,
        priority: request.priority ?? DEFAULT_PRIORITY,
        attempts: this.options.jobAttempts,
        backoff: { type: 'exponential', delay: this.options.jobBackoffMs },
        removeOnComplete: { age: RETENTION_SECONDS },
        removeOnFail: { age: RETENTION_SECONDS },
      }
    )
    if (job.data.bodyHash !== hash) {
      throw idempotencyConflict()
    }
    await this.connection.set(jobIndexKey(jobId), queue.name, 'EX', RETENTION_SECONDS)
    return { job_id: jobId, status: 'queued', deduplicated: false }
  }

  async get(jobId: string): Promise<JobState | null> {
    const job = await this.find(jobId)
    if (job === undefined) {
      return null
    }
    const state = await job.getState()
    if (state === 'unknown') {
      return null
    }
    return toJobState(jobId, job, state)
  }

  async close(): Promise<void> {
    await Promise.all([...this.queues.values()].map((queue) => queue.close()))
  }

  private async find(jobId: string): Promise<ScrapeJob | undefined> {
    const queueName = await this.connection.get(jobIndexKey(jobId))
    if (queueName === null) {
      return undefined
    }
    return this.queueNamed(queueName).getJob(jobId)
  }

  private queueNamed(name: string): ScrapeQueue {
    let queue = this.queues.get(name)
    if (queue === undefined) {
      queue = new Queue<QueuedJob, JobResult>(name, { connection: this.connection })
      this.queues.set(name, queue)
    }
    return queue
  }
}

export interface JobWorkers {
  close(): Promise<void>
}

export interface QueueDepthReader {
  read(): Promise<QueueDepths>
  close(): Promise<void>
}

/**
 * Backlog of the `scrape-<platform>` queues, reported as `scraping`: waiting, active, delayed and prioritized jobs.
 * The `negotiation` queue no longer exists in the worker (negotiation runs in the orchestrator), so it is always 0.
 * Queue handles are created once here and closed by `close()`.
 */
export function createQueueDepthReader(
  platforms: readonly string[],
  connection: Redis
): QueueDepthReader {
  const queues = platforms.map((platform) => new Queue(scrapeQueueName(platform), { connection }))
  return {
    async read() {
      const counts = await Promise.all(queues.map((queue) => queue.getJobCounts(...BACKLOG_STATES)))
      const scraping = counts.reduce(
        (total, byState) =>
          total + BACKLOG_STATES.reduce((sum, state) => sum + (byState[state] ?? 0), 0),
        0
      )
      return { scraping, negotiation: 0 }
    },
    async close() {
      await Promise.all(queues.map((queue) => queue.close()))
    },
  }
}

/**
 * One BullMQ worker per registered platform. Retries exhausted → copy to the dead-letter queue.
 *
 * Workers are started for platforms whose flag is currently off as well: the flag is a per-call gate in
 * ``AdapterRegistry.require`` and ``BullJobService`` never enqueues for a disabled platform, so an idle
 * worker consumes nothing. Filtering here instead made a flag turned on *after* boot a silent lie — the
 * job was accepted and then polled until the orchestrator gave up, with no consumer on the queue.
 */
export function startJobWorkers(
  registry: AdapterRegistry,
  options: { scrapingConcurrency: number },
  connection: Redis,
  logger: Logger,
  metrics?: ScrapingMetrics
): JobWorkers {
  const deadLetter = new Queue<QueuedJob, JobResult>(DEAD_LETTER_QUEUE, { connection })
  const workers = registry
    .status()
    .map(({ platform }) => {
      const worker = new Worker<QueuedJob, JobResult>(
        scrapeQueueName(platform),
        (job) => runJob(job, registry, deadLetter, metrics),
        { connection, concurrency: options.scrapingConcurrency }
      )
      worker.on('failed', (job, error) => {
        logger.warn(
          {
            platform,
            jobId: job?.id,
            kind: job?.data.request.kind,
            code: job?.data.lastError?.code ?? 'internal',
            errorName: error.name,
          },
          'scraping job attempt failed'
        )
      })
      worker.on('error', (error) => {
        logger.error({ platform, errorName: error.name }, 'scraping worker error')
      })
      return worker
    })
  return {
    async close() {
      await Promise.all(workers.map((worker) => worker.close()))
      await deadLetter.close()
    },
  }
}

async function runJob(
  job: ScrapeJob,
  registry: AdapterRegistry,
  deadLetter: ScrapeQueue,
  metrics?: ScrapingMetrics
): Promise<JobResult> {
  try {
    return await processJob(job.data.request, registry, metrics)
  } catch (error) {
    const outcome = jobErrorOf(error)
    const deadLettered = outcome.retryable && job.attemptsStarted >= (job.opts.attempts ?? 1)
    const data: QueuedJob = { ...job.data, lastError: outcome, deadLettered }
    await job.updateData(data)
    if (deadLettered) {
      await deadLetter.add(job.name, data, { jobId: job.id })
    }
    if (!outcome.retryable) {
      throw new UnrecoverableError(outcome.message)
    }
    throw error
  }
}

function statusOf(state: string, data: QueuedJob): JobStatus {
  switch (state) {
    case 'active':
      return 'running'
    case 'completed':
      return 'succeeded'
    case 'failed':
      return data.deadLettered === true ? 'dead_lettered' : 'failed'
    default:
      return 'queued'
  }
}

function toJobState(jobId: string, job: ScrapeJob, state: string): JobState {
  const data = job.data
  const status = statusOf(state, data)
  const failed = status === 'failed' || status === 'dead_lettered'
  return {
    job_id: jobId,
    kind: data.request.kind,
    platform: data.request.platform,
    mission_id: data.request.mission_id,
    trace_id: data.request.trace_id,
    status,
    attempts: job.attemptsStarted,
    created_at: new Date(job.timestamp).toISOString(),
    finished_at: job.finishedOn === undefined ? null : new Date(job.finishedOn).toISOString(),
    result: status === 'succeeded' ? job.returnvalue : null,
    error: failed
      ? (data.lastError ?? { code: 'internal', message: 'job failed', retryable: false })
      : null,
  }
}
