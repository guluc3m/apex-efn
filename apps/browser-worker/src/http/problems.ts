import type { WorkerProblem } from '@apex/shared-types/contracts/browser-worker'
import type { FastifyReply } from 'fastify'

import { toProblem, WorkerError } from '../errors.js'

const CLIENT_ERROR_DETAIL = 'request body or parameters could not be parsed'

export function problemFor(error: unknown, instance: string): WorkerProblem {
  if (error instanceof WorkerError) {
    return { ...toProblem(error), instance }
  }
  if (isFrameworkClientError(error)) {
    return {
      ...toProblem(new WorkerError('validation_error', 422, { detail: CLIENT_ERROR_DETAIL })),
      instance,
    }
  }
  return { ...toProblem(error), instance }
}

export function sendProblem(reply: FastifyReply, problem: WorkerProblem): FastifyReply {
  if (problem.retry_after_seconds !== undefined && problem.retry_after_seconds !== null) {
    reply.header('Retry-After', String(problem.retry_after_seconds))
  }
  return reply.status(problem.status).type('application/problem+json').send(problem)
}

/** Fastify raises 4xx errors for malformed JSON, wrong content type and oversized bodies. */
function isFrameworkClientError(error: unknown): boolean {
  if (typeof error !== 'object' || error === null || !('statusCode' in error)) {
    return false
  }
  const { statusCode } = error
  return typeof statusCode === 'number' && statusCode >= 400 && statusCode < 500
}
