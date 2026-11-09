import type { SigningSession } from '@apex/shared-types/contracts'

/**
 * Pure helpers for the signing-window countdown (ADR-600). No clock is read here: callers pass
 * `localNowMs` so tests are deterministic. The window is fixed by the server `expires_at`.
 */

/** server_time - local now at the moment the response arrived. Add it to local time to get server time. */
export function clockOffsetMs(serverTime: string, localNowMs: number): number {
  return new Date(serverTime).getTime() - localNowMs
}

export function remainingMs(expiresAt: string, localNowMs: number, offsetMs: number): number {
  return new Date(expiresAt).getTime() - (localNowMs + offsetMs)
}

export function formatMmSs(ms: number): string {
  const s = Math.max(0, Math.ceil(ms / 1000))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export type SigningView = 'none' | 'active' | 'read_only'

/** Read-only when the window ended or the server says it is no longer active or has no decisions left. */
export function signingView(
  session: Pick<SigningSession, 'expires_at' | 'status' | 'remaining_decisions'> | null,
  localNowMs: number,
  offsetMs: number,
): SigningView {
  if (session === null) return 'none'
  if (session.status !== 'active' || session.remaining_decisions <= 0) return 'read_only'
  return remainingMs(session.expires_at, localNowMs, offsetMs) <= 0 ? 'read_only' : 'active'
}
