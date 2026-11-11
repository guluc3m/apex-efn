/** Best-effort cleanup that runs when the user signs out (issue #272, item 2). */

export interface SignOutCleanupDeps {
  /** The local signing session store's current session id, or `null` when none is open. */
  activeSessionId: string | null
  /** `DELETE /v1/signing-sessions/{id}` through the generated client. */
  closeSession: (id: string) => Promise<unknown>
  /** Drops the session from the Zustand store so the indicator cannot keep counting down. */
  clearLocal: () => void
  /** Auth.js `signOut`. The only step that must run. */
  signOut: () => Promise<void>
}

export interface SignOutCleanupResult {
  /** `true` only when a session existed and the server acknowledged closing it. */
  remoteSessionClosed: boolean
  /** The swallowed close error, kept for logging in the caller. Never rethrown. */
  closeError?: unknown
}

/**
 * Closes the signing window on this device, then logs out. A failed close never blocks logout: the
 * session still expires on its own fixed 15-minute window, and a shared machine must not keep a web
 * session because a DELETE failed. Cross-device revocation needs a DEV-2 endpoint; the current
 * contract only closes one session at a time.
 */
export async function signOutWithCleanup(deps: SignOutCleanupDeps): Promise<SignOutCleanupResult> {
  let remoteSessionClosed = false
  let closeError: unknown

  if (deps.activeSessionId) {
    try {
      await deps.closeSession(deps.activeSessionId)
      remoteSessionClosed = true
    } catch (error) {
      closeError = error
    }
  }

  try {
    deps.clearLocal()
  } catch {
    // The store is local state: failing to clear it must not strand the user in a session.
  }

  await deps.signOut()
  return closeError === undefined ? { remoteSessionClosed } : { remoteSessionClosed, closeError }
}
