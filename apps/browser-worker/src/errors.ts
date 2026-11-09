import type { WorkerErrorCode, WorkerProblem } from '@apex/shared-types/contracts/browser-worker'

const TITLES: Record<WorkerErrorCode, string> = {
  validation_error: 'Request does not match the contract',
  unauthorized: 'Missing or invalid service token',
  unknown_job: 'Unknown job',
  unknown_chat: 'Unknown chat',
  unknown_platform: 'Unknown platform',
  unknown_account: 'Unknown account',
  unknown_seller: 'Unknown seller',
  unknown_product: 'Unknown product',
  platform_disabled: 'Platform disabled by feature flag',
  idempotency_conflict: 'Idempotency-Key was used with a different request',
  chat_locked: 'Chat is locked by a human',
  lock_held: 'Chat lock is held by another user',
  not_lock_holder: 'Caller does not hold the chat lock',
  rate_limited: 'Rate limit exceeded',
  session_invalid: 'Platform session is invalid',
  captcha: 'Platform challenge blocked the request',
  dom_changed: 'Platform page structure changed',
  robots_disallowed: 'Disallowed by robots.txt',
  upstream_error: 'Platform returned an error',
  timeout: 'Platform timed out',
  internal: 'Internal error',
}

export interface WorkerErrorOptions {
  detail?: string
  retryable?: boolean
  retryAfterSeconds?: number | null
}

export class WorkerError extends Error {
  readonly code: WorkerErrorCode
  readonly status: number
  readonly retryable: boolean
  readonly retryAfterSeconds: number | null
  readonly detail: string | undefined

  constructor(code: WorkerErrorCode, status: number, options: WorkerErrorOptions = {}) {
    super(options.detail ?? TITLES[code])
    this.name = 'WorkerError'
    this.code = code
    this.status = status
    this.retryable = options.retryable ?? false
    this.retryAfterSeconds = options.retryAfterSeconds ?? null
    this.detail = options.detail
  }
}

export function toProblem(error: unknown): WorkerProblem {
  if (error instanceof WorkerError) {
    return {
      type: 'about:blank',
      title: TITLES[error.code],
      status: error.status,
      detail: error.detail,
      code: error.code,
      retryable: error.retryable,
      retry_after_seconds: error.retryAfterSeconds,
    }
  }
  return {
    type: 'about:blank',
    title: TITLES.internal,
    status: 500,
    code: 'internal',
    retryable: false,
    retry_after_seconds: null,
  }
}
