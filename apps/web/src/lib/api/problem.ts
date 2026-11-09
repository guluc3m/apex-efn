import type { Problem, ReauthReason, ReauthRequired } from '@apex/shared-types/contracts'

/**
 * RFC 9457 `application/problem+json` mapped to a UI-friendly error.
 *
 * The orchestrator may add extension members (`reason`, `errors`, `error`); they are kept in
 * `extensions` untouched so screens can read the closed reason codes of the contract.
 */
export class ApiError extends Error {
  readonly status: number
  readonly type: string
  readonly title: string
  readonly detail: string | undefined
  readonly instance: string | undefined
  readonly extensions: Readonly<Record<string, unknown>>

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title)
    this.name = 'ApiError'
    this.status = problem.status
    this.type = problem.type
    this.title = problem.title
    this.detail = problem.detail
    this.instance = problem.instance
    const rest: Record<string, unknown> = { ...problem }
    for (const member of ['type', 'title', 'status', 'detail', 'instance']) delete rest[member]
    this.extensions = rest
  }

  /** Closed `reason` code carried by gate/dashboard 409s and by 428 responses, if any. */
  get reason(): string | undefined {
    const value = this.extensions.reason
    return typeof value === 'string' ? value : undefined
  }

  get isReauthRequired(): boolean {
    return this.status === 428
  }
}

const REAUTH_REASONS: ReadonlySet<string> = new Set<ReauthReason>([
  'session_missing',
  'session_expired',
  'session_revoked',
  'session_exhausted',
  'key_revoked',
  'key_rotated',
  'device_mismatch',
  'network_anomaly',
  'high_value_decision',
  'immediate_reauth_required',
  'risk_flagged',
  'step_up_required',
])

/** Narrows an error to a `428 reauth_required` with a reason from the closed contract enum. */
export function asReauthRequired(error: unknown): ReauthRequired | null {
  if (!(error instanceof ApiError) || !error.isReauthRequired) return null
  const reason = error.reason
  if (reason === undefined || !REAUTH_REASONS.has(reason)) return null
  return {
    type: error.type,
    title: error.title,
    status: 428,
    detail: error.detail,
    instance: error.instance,
    ...error.extensions,
    error: 'reauth_required',
    reason: reason as ReauthReason,
  }
}

function isProblemShape(value: unknown): value is Problem {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return typeof candidate.title === 'string' && typeof candidate.status === 'number'
}

/** Reads a failed response. Anything that is not problem+json still becomes an `ApiError`. */
export async function problemFromResponse(response: Response): Promise<ApiError> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    body = undefined
  }
  if (isProblemShape(body)) {
    return new ApiError({ ...body, type: typeof body.type === 'string' ? body.type : 'about:blank' })
  }
  return new ApiError({
    type: 'about:blank',
    title: response.statusText || 'Request failed',
    status: response.status,
  })
}
