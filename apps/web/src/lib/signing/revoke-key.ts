import type { Decision, SigningKey, SigningSession } from '@apex/shared-types/contracts'

import { useSigningSession } from '@/stores/signing-session'

import { SigningUnsupportedError } from './open-session'
import { NoSigningSessionError, signLoadedDecision, type SignDeps } from './sign-decision'

export { NoSigningSessionError, PayloadMismatchError } from './sign-decision'

export interface RevokeKeyDeps extends SignDeps {
  createDecision: (body: { type: 'revoke_key'; subject_ref: string; params: Record<string, unknown> }) => Promise<Decision>
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
  // Checked before creating anything: an unsupported browser or a closed window must not leave a pending decision.
  if (!(await d.isSupported())) throw new SigningUnsupportedError()
  const session = useSigningSession.getState().session
  if (!session || session.status !== 'active') throw new NoSigningSessionError()
  if (!(await d.keys.load(userId))) throw new SigningUnsupportedError()
  const decision = await d.createDecision({ type: 'revoke_key', subject_ref: keyId, params: { key_id: keyId } })
  await signLoadedDecision(userId, decision, d)
  const key = await d.revokeKey(keyId, { decision_id: decision.id })

  const fresh = await d.getSession(session.id)
  useSigningSession.getState().setSession(fresh, d.nowMs())
  return { key, decision }
}
