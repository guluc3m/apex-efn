import type { Decision } from '@apex/shared-types/contracts'

import { useSigningSession } from '@/stores/signing-session'

import { SigningUnsupportedError } from './open-session'

export class NoSigningSessionError extends Error {
  constructor() {
    super('Open a signing session before signing.')
  }
}

export class PayloadMismatchError extends Error {
  constructor() {
    super('The server payload hash does not match the payload it sent, so nothing was signed.')
  }
}

export interface SignDeps {
  keys: {
    load: (userId: string) => Promise<boolean>
    sign: (payload: unknown) => Promise<{ keyId: string; payloadHash: string; signature: string }>
  }
  isSupported: () => Promise<boolean>
  hash: (payload: unknown) => Promise<string>
  signDecision: (
    id: string,
    body: { key_id: string; payload_hash: string; signature: string; signing_session_id: string },
  ) => Promise<unknown>
}

/**
 * Signs the canonical payload the server built. We refuse if its hash does not match the server's, so a
 * tampered response is never signed. Needs an open window; a 428 goes through the global step-up handler.
 * The private key never leaves the browser.
 */
export async function signLoadedDecision(userId: string, decision: Decision, d: SignDeps): Promise<{ sessionId: string }> {
  if (!(await d.isSupported())) throw new SigningUnsupportedError()
  const session = useSigningSession.getState().session
  if (!session || session.status !== 'active') throw new NoSigningSessionError()
  if (!(await d.keys.load(userId))) throw new SigningUnsupportedError()

  const payload: unknown = JSON.parse(decision.payload_canonical)
  if ((await d.hash(payload)) !== decision.payload_hash) throw new PayloadMismatchError()
  const signed = await d.keys.sign(payload)
  await d.signDecision(decision.id, {
    key_id: signed.keyId,
    payload_hash: signed.payloadHash,
    signature: signed.signature,
    signing_session_id: session.id,
  })
  return { sessionId: session.id }
}
