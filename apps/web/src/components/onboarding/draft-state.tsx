'use client'

import { useFormatter, useTranslations } from 'next-intl'

import { useOnboardingSession } from '@/lib/api/hooks'
import { useOnboarding } from '@/stores/onboarding'

/** Real save state: the session's `updated_at` once the server holds a draft, a local-draft notice before. */
export function DraftState() {
  const t = useTranslations('onboarding.header')
  const format = useFormatter()
  const session = useOnboardingSession(useOnboarding((s) => s.sessionId))
  const at = session.data?.updated_at
  return (
    <span className="ml-auto text-[13px] text-ink-muted">
      {at ? t('saved', { time: format.dateTime(new Date(at), { dateStyle: 'short', timeStyle: 'short' }) }) : t('draft')}
    </span>
  )
}
