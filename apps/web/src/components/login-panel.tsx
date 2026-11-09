'use client'

import { Badge, Button, Icon, Input, Label, Logo } from '@apex/ui'
import { Clock, Fingerprint, LogIn, ShieldAlert, ShieldCheck } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useCallback, useRef } from 'react'

import { loginSampleDeals } from '@/fixtures/login'

import { AppLanguageSwitcher } from './language-switcher'
import type { LoginField } from './login-field'
import { LoginFieldCanvas } from './login-field-canvas'

/** Acceso (LoginRD). //todo_#147: login real contra el BFF; mientras tanto nada se simula. */
export function LoginPanel() {
  const t = useTranslations('shell.login')
  const reason = t('pending')
  const field = useRef<LoginField | null>(null)
  const onField = useCallback((f: LoginField | null) => {
    field.current = f
  }, [])
  const hover = (on: boolean) => () => {
    if (field.current) field.current.hoverT = on ? 1 : 0
  }
  return (
    <main
      id="contenido"
      className="flex min-h-screen flex-wrap overflow-hidden bg-linear-to-b from-bg from-75% to-accent-subtle"
    >
      <div className="flex min-w-0 flex-[1_1_420px] flex-col justify-between px-14 py-10">
        <div className="flex min-h-9.5 items-center justify-between gap-4">
          <Logo size="md" />
          <AppLanguageSwitcher />
        </div>
        <div className="flex max-w-100 flex-col gap-6 py-12">
          <div>
            <h1 className="mb-2 text-[28px] leading-tight font-semibold tracking-tight text-balance">{t('title')}</h1>
            <p className="text-ink-soft text-pretty">{t('lead')}</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email" className="text-ink-soft">{t('email')}</Label>
            <Input id="email" type="email" autoComplete="username" onChange={(e) => field.current?.morph(e.target.value.trim().toLowerCase() === 'macarrones')} placeholder={t('emailPlaceholder')} className="min-h-11" />
          </div>
          <Button
            variant="pri"
            size="lg"
            disabledReason={reason}
            onMouseEnter={hover(true)}
            onMouseLeave={hover(false)}
            onFocus={hover(true)}
            onBlur={hover(false)}
          >
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
      </div>

      <div className="relative flex min-h-225 min-w-0 flex-[1_1_560px] flex-col justify-end border-l border-line">
        <LoginFieldCanvas onField={onField} />
        <div className="relative mx-14 mb-10 max-w-130 border border-line bg-panel p-2">
          <div className="flex justify-between gap-3 px-3 pt-3 pb-2 text-[13px] text-ink-muted">
            <span>{t('queue.title')}</span>
            <span>{t('queue.count', { count: loginSampleDeals.length })}</span>
          </div>
          {loginSampleDeals.map((d, i) => (
            <div key={d.id} className={i === 0 ? 'mb-1 bg-raised p-3' : 'p-3'}>
              <div className="flex justify-between gap-3 text-[13px] text-ink-muted">
                <span>{t(`queue.${d.id}`)}</span>
                <span>{d.sla ? t('queue.sla', { time: d.sla }) : t('queue.seller', { name: d.seller })}</span>
              </div>
              <div className="mt-0.5 mb-2 font-medium">{d.product}</div>
              <div className="flex flex-wrap items-center gap-1.5">
                <strong className="mr-1 font-semibold">{d.price}</strong>
                <Badge tone={d.confidence === 'high' ? 'ok' : 'warn'} icon={d.confidence === 'high' ? ShieldCheck : ShieldAlert}>
                  {t(`queue.confidence.${d.confidence}`, { score: d.score })}
                </Badge>
                <Badge tone="ok">{t('queue.priceNormal')}</Badge>
                <Badge tone="neutro" icon={Clock}>{t('queue.pending')}</Badge>
              </div>
            </div>
          ))}
          <p className="px-3 pb-2 text-[13px] text-ink-muted">{t('queue.sample')}</p>
        </div>
      </div>
    </main>
  )
}
