import type { Decision, SigningKey, SigningSession } from '@apex/shared-types/contracts'

import { useSigningSession } from '@/stores/signing-session'

import { SigningUnsupportedError } from './open-session'

export class NoSigningSessionError extends Error {
  constructor() {
    super('Open a signing session before revoking a key.')
  }
}

export class PayloadMismatchError extends Error {
  constructor() {
    super('The server payload hash does not match the payload it sent, so nothing was signed.')
  }
}

export interface RevokeKeyDeps {
  keys: {
    load: (userId: string) => Promise<boolean>
    sign: (payload: unknown) => Promise<{ keyId: string; payloadHash: string; signature: string }>
  }
  isSupported: () => Promise<boolean>
  hash: (payload: unknown) => Promise<string>
  createDecision: (body: { type: 'revoke_key'; subject_ref: string; params: Record<string, unknown> }) => Promise<Decision>
  signDecision: (
    id: string,
    body: { key_id: string; payload_hash: string; signature: string; signing_session_id: string },
  ) => Promise<unknown>
  revokeKey: (id: string, body: { decision_id: string }) => Promise<SigningKey>
  /** Revoking a key may close the session that used it: refresh instead of assuming. */
  getSession: (id: string) => Promise<SigningSession>
  nowMs: () => number
}

/**
 * Revocation is a signed `revoke_key` decision (immediate reauth: a 428 here goes through the global
 * step-up handler). The device key signs the canonical payload the server built; we refuse to sign if
 * its hash does not match the server's. The private key never leaves the browser.
 */
export async function revokeKey(userId: string, keyId: string, d: RevokeKeyDeps): Promise<{ key: SigningKey; decision: Decision }> {
  if (!(await d.isSupported())) throw new SigningUnsupportedError()
  const session = useSigningSession.getState().session
  if (!session || session.status !== 'active') throw new NoSigningSessionError()
  if (!(await d.keys.load(userId))) throw new SigningUnsupportedError()

  const decision = await d.createDecision({ type: 'revoke_key', subject_ref: keyId, params: { key_id: keyId } })
  const payload: unknown = JSON.parse(decision.payload_canonical)
  if ((await d.hash(payload)) !== decision.payload_hash) throw new PayloadMismatchError()

  const signed = await d.keys.sign(payload)
  await d.signDecision(decision.id, {
    key_id: signed.keyId,
    payload_hash: signed.payloadHash,
    signature: signed.signature,
    signing_session_id: session.id,
  })
  const key = await d.revokeKey(keyId, { decision_id: decision.id })

  const fresh = await d.getSession(session.id)
  useSigningSession.getState().setSession(fresh, d.nowMs())
  return { key, decision }
}
