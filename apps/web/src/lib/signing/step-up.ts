import type { ReauthReason } from '@apex/shared-types/contracts'

import { setReauthHandler } from '@/lib/api/reauth'

/**
 * Keycloak step-up (ADR-900 Q11, ADR-600). Resolves true when a fresh strong authentication was
 * obtained and the signing session was reopened.
 * TODO(D1-05): the real implementation redirects to Keycloak with the step-up ACR; until it merges
 * the default fails closed (false), so a 428 is surfaced and nothing is ever signed silently.
 */
export type StartStepUp = (reason?: ReauthReason) => Promise<boolean>

let impl: StartStepUp = () => Promise.resolve(false)

export function setStepUp(next: StartStepUp): void {
  impl = next
}

export const startStepUp: StartStepUp = (reason) => impl(reason)

/** Makes the API client answer 428 with step-up and a single retry (the retry lives in client.ts). */
export function installStepUpOn428(): () => void {
  return setReauthHandler((reason) => startStepUp(reason))
}
