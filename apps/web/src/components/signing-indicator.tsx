'use client'

import { SigningSessionIndicator } from '@apex/ui'
import { useTranslations } from 'next-intl'
import { useEffect, useState } from 'react'

import { openSigningSessionFor } from '@/lib/signing/connect'
import { signingView } from '@/lib/signing/countdown'
import { installStepUpOn428, startStepUp } from '@/lib/signing/step-up'
import { useSigningSession } from '@/stores/signing-session'

/** Signer shown is the session user id until D1-05 exposes a display name. */
export function ConnectedSigningIndicator({ userId }: { userId?: string }) {
  const t = useTranslations('shell')
  const { session, offsetMs } = useSigningSession()
  const [local, setLocal] = useState<number | null>(null)

  useEffect(() => installStepUpOn428(), [])
  useEffect(() => {
    if (!session) return
    setLocal(Date.now())
    const id = setInterval(() => setLocal(Date.now()), 1000)
    return () => clearInterval(id)
  }, [session])

  // Read-only on expiry is derived from the clock tick: no reload, the rest of the page keeps its state.
  // A revoked/closed session has no live window: force the indicator's expired state.
  const view = session && local !== null ? signingView(session, local, offsetMs) : 'none'
  const dead = view === 'read_only' && session?.status !== 'active'
  const expiresAt = session ? (dead ? new Date(0).toISOString() : session.expires_at) : undefined

  // Strong authentication first (Keycloak step-up); the window opens with the fresh token. Without a
  // known user (D1-05 web not merged) only the step-up runs and fails closed.
  const reauth = async () => {
    if (!(await startStepUp()) || !userId) return
    await openSigningSessionFor(userId)
  }

  return (
    <SigningSessionIndicator
      expiresAt={expiresAt}
      now={local === null ? undefined : local + offsetMs}
      signer={session?.user_id}
      signaturesLeft={session?.remaining_decisions}
      signaturesLabel={session ? t('signing.left', { count: session.remaining_decisions }) : undefined}
      action={{ href: '#' }}
      renderLink={({ className, children }) => (
        <button type="button" className={className} onClick={() => void reauth().catch(console.error)}>
          {children}
        </button>
      )}
      labels={{
        signing: t('signing.label'),
        noSession: t('signing.none'),
        expiring: t('signing.expiring'),
        expired: t('signing.expired'),
        exhausted: t('signing.exhausted'),
        openSession: t('signing.open'),
        reauth: t('signing.reauth'),
        timerLabel: (time) => t('signing.timer', { time }),
      }}
    />
  )
}
