'use client'

import { Button, Icon, Input, Label, Logo } from '@apex/ui'
import { Fingerprint, LogIn } from 'lucide-react'
import { useTranslations } from 'next-intl'

import { AppLanguageSwitcher } from './language-switcher'

/** Acceso (LoginRD). //todo_#147: login real contra el BFF; mientras tanto nada se simula. */
export function LoginPanel() {
  const t = useTranslations('shell.login')
  const reason = t('pending')
  return (
    <main id="contenido" className="flex min-h-screen flex-col justify-between px-14 py-10">
      <div className="flex items-center justify-between gap-4">
        <Logo size="sm" />
        <AppLanguageSwitcher />
      </div>
      <div className="flex max-w-100 flex-col gap-6 py-12">
        <div>
          <h1 className="mb-2 text-[28px] leading-tight font-semibold tracking-tight text-balance">{t('title')}</h1>
          <p className="text-ink-soft text-pretty">{t('lead')}</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email" className="text-ink-soft">{t('email')}</Label>
          <Input id="email" type="email" autoComplete="username" placeholder={t('emailPlaceholder')} className="min-h-11" />
        </div>
        <Button variant="pri" size="lg" disabledReason={reason}>
          <Icon icon={LogIn} />
          {t('continue')}
        </Button>
        <Button variant="sec" size="lg" disabledReason={reason}>
          <Icon icon={Fingerprint} />
          {t('passkey')}
        </Button>
        <p role="status" className="text-[13px] text-ink-muted">{reason}</p>
        <p className="text-[13px] text-ink-muted">{t('sso')}</p>
      </div>
      <p className="text-[13px] text-ink-muted">{t('ed25519')}</p>
    </main>
  )
}
