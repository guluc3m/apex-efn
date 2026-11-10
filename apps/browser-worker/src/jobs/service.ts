import type {
  JobAccepted,
  JobError,
  JobRequest,
  JobResult,
  JobState,
  JobStatus,
} from '@apex/shared-types/contracts/browser-worker'

import type { AdapterRegistry } from '../adapters/index.js'
import type { Clock } from '../clock.js'
import { settle } from '../concurrency.js'
import { bodyHash, idempotencyConflict } from '../idempotency.js'

import { processJob, jobErrorOf } from './processor.js'

export interface JobService {
  enqueue(request: JobRequest, idempotencyKey: string): Promise<JobAccepted>
  get(jobId: string): Promise<JobState | null>
  close(): Promise<void>
}

interface JobRecord {
  jobId: string
  hash: string
  request: JobRequest
  status: JobStatus
  attempts: number
  createdAt: string
  finishedAt: string | null
  result: JobResult | null
  error: JobError | null
}

/** Test double: keeps jobs in memory and runs them only when `runAll` is called. Same contract as BullJobService. */
export class InMemoryJobService implements JobService {
  private readonly jobs = new Map<string, JobRecord>()
  private readonly jobIdByKey = new Map<string, string>()

  constructor(
    private readonly registry: AdapterRegistry,
    private readonly clock: Clock,
    private readonly newId: () => string
  ) {}

  enqueue(request: JobRequest, idempotencyKey: string): Promise<JobAccepted> {
    return settle(() => this.accept(request, idempotencyKey))
  }

  get(jobId: string): Promise<JobState | null> {
    const record = this.jobs.get(jobId)
    return Promise.resolve(record === undefined ? null : toJobState(record))
  }

  close(): Promise<void> {
    return Promise.resolve()
  }

  async runAll(): Promise<void> {
    for (const record of this.jobs.values()) {
      if (record.status !== 'queued') {
        continue
      }
      record.status = 'running'
      record.attempts += 1
      try {
        record.result = await processJob(record.request, this.registry)
        record.status = 'succeeded'
      } catch (error) {
        record.error = jobErrorOf(error)
        record.status = 'failed'
      }
      record.finishedAt = this.clock.now().toISOString()
    }
  }

  private accept(request: JobRequest, idempotencyKey: string): JobAccepted {
    const hash = bodyHash(request)
    const existingId = this.jobIdByKey.get(idempotencyKey)
    const existing = existingId === undefined ? undefined : this.jobs.get(existingId)
    if (existing !== undefined) {
      if (existing.hash !== hash) {
        throw idempotencyConflict()
      }
      return { job_id: existing.jobId, status: existing.status, deduplicated: true }
    }
    this.registry.require(request.platform)
    const jobId = this.newId()
    this.jobs.set(jobId, {
      jobId,
      hash,
      request,
      status: 'queued',
      attempts: 0,
      createdAt: this.clock.now().toISOString(),
      finishedAt: null,
      result: null,
      error: null,
    })
    this.jobIdByKey.set(idempotencyKey, jobId)
    return { job_id: jobId, status: 'queued', deduplicated: false }
  }
}

function toJobState(record: JobRecord): JobState {
  return {
    job_id: record.jobId,
    kind: record.request.kind,
    platform: record.request.platform,
    mission_id: record.request.mission_id,
    trace_id: record.request.trace_id,
    status: record.status,
    attempts: record.attempts,
    created_at: record.createdAt,
    finished_at: record.finishedAt,
    result: record.result,
    error: record.error,
  }
}
