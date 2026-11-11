import { payloadHash, SigningClient } from '@apex/crypto-client'

import { api } from '@/lib/api'

import { enrollKey, openSigningSession } from './open-session'
import { revokeKey } from './revoke-key'

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

export const enrollKeyFor = (userId: string) =>
  enrollKey(userId, {
    keys: client,
    isSupported: () => SigningClient.isSupported(),
    registerKey: (body) => api.registerMySigningKey(body),
  })

/** Signed `revoke_key` decision, then revocation. Needs an open window; a 428 triggers the step-up. */
export const revokeKeyFor = (userId: string, keyId: string) =>
  revokeKey(userId, keyId, {
    keys: client,
    isSupported: () => SigningClient.isSupported(),
    hash: payloadHash,
    createDecision: (body) => api.createDecision(body),
    signDecision: (id, body) => api.signDecision(id, { ...body, device_fingerprint_ref: deviceFingerprintRef() }),
    revokeKey: (id, body) => api.revokeSigningKey(id, body),
    getSession: (id) => api.getSigningSession(id),
    nowMs: () => Date.now(),
  })
