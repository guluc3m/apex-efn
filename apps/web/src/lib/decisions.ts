import type { ActionAvailability, DealAction, DealActionRequest, DiscardReasonCode } from '@apex/shared-types/contracts'

export const DISCARD_REASONS: DiscardReasonCode[] = [
  'price_too_high',
  'seller_not_trusted',
  'spec_mismatch',
  'lead_time',
  'out_of_budget',
  'duplicate',
  'other',
]

export interface ActionForm {
  discardReason: DiscardReasonCode | ''
  comment: string
  instructions: string
  holdUntil: string
}

export const emptyActionForm: ActionForm = { discardReason: '', comment: '', instructions: '', holdUntil: '' }

/** Request body for a deal action, or null while the form misses what the contract requires (discard: code + comment). */
export function dealActionBody(action: DealAction, form: ActionForm): DealActionRequest | null {
  const comment = form.comment.trim()
  switch (action) {
    case 'discard':
      return form.discardReason && comment ? { action, discard_reason: form.discardReason, comment } : null
    case 'renegotiate':
      return { action, instructions: form.instructions.trim() || null }
    case 'hold':
      return { action, hold_until: form.holdUntil || null }
    default:
      return { action }
  }
}

/** Why a button is disabled, straight from the API. Null when the action is allowed. */
export function blockedCodes(a: ActionAvailability): string[] | null {
  if (a.allowed) return null
  return a.blocked_by.length ? a.blocked_by.map((b) => b.code) : ['unknown']
}

/** Time left until `dueAt` as `h:mm`. Display only: the API owns the due date. */
export function remaining(dueAt: string, nowMs: number): { label: string; overdue: boolean } {
  const ms = Date.parse(dueAt) - nowMs
  const abs = Math.abs(ms)
  const h = Math.floor(abs / 3_600_000)
  const m = Math.floor((abs % 3_600_000) / 60_000)
  return { label: `${h}:${String(m).padStart(2, '0')}`, overdue: ms < 0 }
}
