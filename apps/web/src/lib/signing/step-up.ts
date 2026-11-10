import type { ReauthReason } from '@apex/shared-types/contracts'

import { setReauthHandler } from '@/lib/api/reauth'

/**
 * Keycloak step-up (ADR-900 Q11, ADR-600). Resolves true when the browser has been sent to the
 * sign-in entry with the step-up parameters and a fresh authentication is on its way; the page
 * reloads, so any failure remains fail-closed (nothing is ever signed silently).
 *
 * The entry point is `app/api/auth/signin/route.ts`: with `stepUp=1` it calls Auth.js `signIn` with
 * `acr_values=STEP_UP_ACR`, `max_age=0` and `prompt=login`. The server side of the signature
 * (D2-08) still decides whether the resulting token is fresh enough; this function never assumes
 * that a step-up succeeded.
 */
export type StartStepUp = (reason?: ReauthReason) => Promise<boolean>

/** Default destination of the step-up: the current page, queried string included. */
function currentPath(): string {
  return `${window.location.pathname}${window.location.search}`
}

/**
 * Fails closed outside a browser (SSR, unit tests without a DOM): returns false so callers surface
 * the 428 instead of pretending a step-up happened.
 */
function redirectToStepUp(): Promise<boolean> {
  if (typeof window === 'undefined' || !window.location) return Promise.resolve(false)

  try {
    const params = new URLSearchParams({ stepUp: '1', callbackUrl: currentPath() })
    window.location.assign(`/api/auth/signin?${params.toString()}`)
    return Promise.resolve(true)
  } catch {
    // Navigation blocked (sandboxed iframe, jsdom): the caller surfaces the 428 instead.
    return Promise.resolve(false)
  }
}

let impl: StartStepUp = () => redirectToStepUp()

export function setStepUp(next: StartStepUp): void {
  impl = next
}

export const startStepUp: StartStepUp = (reason) => impl(reason)

/** Makes the API client answer 428 with step-up and a single retry (the retry lives in client.ts). */
export function installStepUpOn428(): () => void {
  return setReauthHandler((reason) => startStepUp(reason))
}
