import type { ReauthReason } from '@apex/shared-types/contracts'
import { create } from 'zustand'

/**
 * Global `428 reauth_required` hook.
 *
 * D6-03 registers the real handler (passkey ceremony that opens a signing session). The client
 * calls it when the API answers 428, waits for the result and retries the request once. With no
 * handler registered, or when it resolves `false`, the original error is thrown: the UI never
 * signs silently and never degrades to an unauthenticated mode.
 */
export type ReauthHandler = (reason: ReauthReason) => Promise<boolean>

let handler: ReauthHandler | null = null

export function setReauthHandler(next: ReauthHandler | null): () => void {
  handler = next
  return () => {
    if (handler === next) handler = null
  }
}

export function getReauthHandler(): ReauthHandler | null {
  return handler
}

interface ReauthState {
  /** Reason of the reauthentication currently in progress, or null. For header/panel UI. */
  pending: ReauthReason | null
  begin: (reason: ReauthReason) => void
  end: () => void
}

export const useReauthStore = create<ReauthState>((set) => ({
  pending: null,
  begin: (reason) => set({ pending: reason }),
  end: () => set({ pending: null }),
}))
