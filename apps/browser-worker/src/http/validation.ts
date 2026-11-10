import { zIdempotencyKey } from '@apex/shared-types/contracts/browser-worker/zod'
import type { ZodError, ZodTypeAny, z } from 'zod'

import { WorkerError } from '../errors.js'

const MAX_DETAIL_LENGTH = 500

/** The detail names the failing fields and the rule that failed. It never contains the submitted values. */
export function parseWith<S extends ZodTypeAny>(schema: S, value: unknown): z.output<S> {
  const result = schema.safeParse(value)
  if (!result.success) {
    throw new WorkerError('validation_error', 422, { detail: describeIssues(result.error) })
  }
  return result.data as z.output<S>
}

export function requireIdempotencyKey(value: unknown): string {
  const result = zIdempotencyKey.safeParse(value)
  if (!result.success) {
    throw new WorkerError('validation_error', 422, {
      detail: 'Idempotency-Key header is required (16 to 128 characters)',
    })
  }
  return result.data
}

function describeIssues(error: ZodError): string {
  const parts = error.issues.map((issue) => {
    if (issue.code === 'unrecognized_keys') {
      return `unknown field: ${issue.keys.join(', ')}`
    }
    const path = issue.path.length === 0 ? 'body' : issue.path.join('.')
    return `${path}: ${issue.code}`
  })
  return [...new Set(parts)].join('; ').slice(0, MAX_DETAIL_LENGTH)
}
