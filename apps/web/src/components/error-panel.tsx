'use client'

import { Button, Icon } from '@apex/ui'
import { Gavel, RotateCcw, SearchX, ShieldX, TriangleAlert, type LucideIcon } from 'lucide-react'
import { useTranslations } from 'next-intl'

import { AppLink } from './app-link'

const KINDS: Record<'forbidden' | 'notFound' | 'error', LucideIcon> = { forbidden: ShieldX, notFound: SearchX, error: TriangleAlert }

/** Página de error con siguiente paso siempre (NAVIGATION §1.6). `onRetry` solo en errores recuperables. */
export function ErrorPanel({ kind, onRetry }: { kind: keyof typeof KINDS; onRetry?: () => void }) {
  const t = useTranslations('shell.errors')
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4 px-gutter-page py-16">
      <h1 className="flex items-center gap-2.5 text-[22px] font-semibold tracking-tight">
        <Icon icon={KINDS[kind]} size={20} />
        {t(`${kind}.title`)}
      </h1>
      <p className="text-ink-soft">{t(`${kind}.body`)}</p>
      <div className="flex gap-2">
        {onRetry && (
          <Button variant="pri" onClick={onRetry}>
            <Icon icon={RotateCcw} />
            {t('retry')}
          </Button>
        )}
        <Button variant={onRetry ? 'sec' : 'pri'} asChild>
          <AppLink href="/decisiones">
            <Icon icon={Gavel} />
            {t('home')}
          </AppLink>
        </Button>
      </div>
    </div>
  )
}
