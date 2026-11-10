import type { SigningSession } from '@apex/shared-types/contracts'
import { create } from 'zustand'

import { clockOffsetMs } from '@/lib/signing/countdown'

interface SigningSessionStore {
  session: SigningSession | null
  offsetMs: number
  /** Call with the local time at which the response arrived, to correct the clock offset. */
  setSession: (session: SigningSession, localNowMs: number) => void
  clear: () => void
}

export const useSigningSession = create<SigningSessionStore>((set) => ({
  session: null,
  offsetMs: 0,
  setSession: (session, localNowMs) => set({ session, offsetMs: clockOffsetMs(session.server_time, localNowMs) }),
  clear: () => set({ session: null, offsetMs: 0 }),
}))
