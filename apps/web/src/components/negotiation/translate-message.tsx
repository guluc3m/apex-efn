'use client'

import { Button, Icon } from '@apex/ui'
import { Languages } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'

import { ApiError, useTranslateMessage } from '@/lib/api'

type Language = 'es' | 'en' | 'zh' | 'he'

/** Translates one seller message into the UI language. The translation is shown, never stored or sent. */
export function TranslateMessage({ negotiationId, messageId }: { negotiationId: string; messageId: string }) {
  const t = useTranslations('negotiation')
  const locale = useLocale() as Language
  const tr = useTranslateMessage(negotiationId)
  const reason = tr.error instanceof ApiError ? tr.error.reason : undefined
  const error = tr.isError ? t.has(`errors.${reason}`) ? t(`errors.${reason}`) : t('errors.translation_unavailable') : null

  return (
    <div className="flex flex-col gap-1.5">
      {tr.data ? (
        <>
          <p lang={tr.data.target_language} className="m-0 whitespace-pre-wrap border-t border-line pt-1.5">
            <span className="text-[13px] text-ink-muted">{t('translate.label')}: </span>
            {tr.data.text}
          </p>
          <Button variant="ghost" className="self-start" onClick={() => tr.reset()}>
            {t('translate.hide')}
          </Button>
        </>
      ) : (
        <Button variant="ghost" className="self-start" disabled={tr.isPending} onClick={() => tr.mutate({ messageId, language: locale })}>
          <Icon icon={Languages} />
          {t('translate.action')}
        </Button>
      )}
      {error && <p role="alert" className="m-0 text-[13px] text-bad">{error}</p>}
    </div>
  )
}
