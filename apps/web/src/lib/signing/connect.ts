import { SigningClient } from '@apex/crypto-client'

import { api } from '@/lib/api'

import { openSigningSession } from './open-session'

const client = new SigningClient()

/** Stable per-browser reference the server compares to detect a device change (spec 5.10.4). */
function deviceFingerprintRef(): string {
  const key = 'apex.device'
  try {
    return localStorage.getItem(key) ?? (localStorage.setItem(key, crypto.randomUUID()), localStorage.getItem(key)!)
  } catch {
    return 'unknown'
  }
}

/** Opens a signing window for the signed-in user against the real API. */
export const openSigningSessionFor = (userId: string) =>
  openSigningSession(userId, {
    keys: client,
    isSupported: () => SigningClient.isSupported(),
    listKeys: () => api.listMySigningKeys(),
    registerKey: (body) => api.registerMySigningKey(body),
    openSession: (body) => api.openSigningSession(body),
    deviceFingerprintRef,
    nowMs: () => Date.now(),
  })
