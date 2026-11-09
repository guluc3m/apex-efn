'use client'

import { Button, Chat, Icon, Input, Label, MoneyDisplay, Select, type ChatMessage } from '@apex/ui'
import { ListChecks, Play, RefreshCw, TriangleAlert, Upload } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { useId } from 'react'

import { AppLink } from '@/components/app-link'
import type { sourcingRequest } from '@/fixtures/missions'

type Request = typeof sourcingRequest

function Field({ label, children, wide }: { label: string; children: (id: string) => React.ReactNode; wide?: boolean }) {
  const id = useId()
  return (
    <div className={`flex flex-col gap-1 ${wide ? 'col-span-full' : ''}`}>
      <Label htmlFor={id}>{label}</Label>
      {children(id)}
    </div>
  )
}

export function MissionRequest({ request, snapshotActive }: { request: Request; snapshotActive: boolean }) {
  const t = useTranslations('missions.request')
  const locale = useLocale()
  const messages: ChatMessage[] = [
    { id: 'u1', role: 'human', author: t('chat.you'), text: request.text },
    { id: 'a1', role: 'agent', author: t('chat.agent'), text: t('chat.reply') },
  ]
  const pending = t('pending')
  const opts = (key: string, ids: string[]) => ids.map((v) => ({ value: v, label: t(`${key}.${v}`) }))

  return (
    <div className="flex flex-wrap items-start gap-8">
      <section className="flex min-w-0 flex-[1_1_420px] flex-col gap-3" aria-labelledby="req-chat">
        <h2 id="req-chat" className="text-[13px] font-normal text-ink-muted">
          {t('chat.title')}
        </h2>
        {/* //todo_#155: enviar al IntakeAgent y mostrar «Interpretando…» (Thinking) mientras trabaja */}
        <Chat
          messages={messages}
          phrases={['interpreting', 'spec', 'budget', 'platforms', 'plan'].map((k) => t(`chat.phrases.${k}`))}
          labels={{ input: t('chat.title'), placeholder: t('chat.placeholder'), send: t('chat.send'), stop: t('chat.stop'), hint: t('chat.hint') }}
          onSend={() => undefined}
          disabledReason={t('chat.pending')}
        />
        <div>
          <Button disabledReason={pending}>
            <Icon icon={RefreshCw} />
            {t('reinterpret')}
          </Button>
        </div>
      </section>

      <section className="flex min-w-0 flex-[1_1_520px] flex-col gap-5" aria-labelledby="req-review">
        <h2 id="req-review" className="inline-flex items-center gap-1.5 text-[17px] font-semibold">
          <Icon icon={ListChecks} />
          {t('review.title')}
        </h2>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
          <Field label={t('review.product')}>{(id) => <Input id={id} defaultValue={request.fields.product} />}</Field>
          <Select label={t('review.category')} defaultValue="bearings" options={opts('review.categories', ['bearings'])} />
          <Field label={t('review.quantity')}>{(id) => <Input id={id} defaultValue={request.fields.quantity} />}</Field>
          <Field label={t('review.destination')}>{(id) => <Input id={id} defaultValue={request.fields.destination} />}</Field>
          <Field label={t('review.deadline')}>{(id) => <Input id={id} defaultValue={request.fields.deadline} />}</Field>
          <Select label={t('review.payment')} defaultValue="net60" options={opts('review.payments', ['net60'])} />
          <Field label={t('review.spec')} wide>{(id) => <Input id={id} defaultValue={request.fields.spec} />}</Field>
          <Field label={t('review.tolerances')} wide>
            {(id) => (
              <>
                <Input id={id} aria-invalid="true" aria-describedby={`${id}-err`} placeholder={t('review.tolerancesMissing')} className="border-warn" />
                <span id={`${id}-err`} className="text-[13px] text-warn">
                  {t('review.tolerancesHelp')}
                </span>
              </>
            )}
          </Field>
        </div>

        <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
          <legend className="mb-2 text-[13px] text-ink-muted">{t('platforms.title')}</legend>
          {request.platforms.map((p) => (
            <label key={p.id} className={`flex items-center gap-2 ${p.state === 'disabled' ? 'text-ink-muted' : ''}`}>
              <input type="checkbox" className="accent-accent" defaultChecked={p.state !== 'disabled'} disabled={p.state === 'disabled'} />
              {t(`platforms.${p.id}`)}
              {p.state !== 'on' && <span className="text-[13px] text-ink-muted">{t(`platforms.${p.state}`)}</span>}
            </label>
          ))}
        </fieldset>

        <div className="flex flex-wrap items-end gap-8 border border-line bg-panel p-4">
          <div>
            <div className="text-[13px] text-ink-muted">{t('envelope.label')}</div>
            <strong className="font-semibold">
              <MoneyDisplay amountMinor={request.envelope.amountMinor} currency={request.envelope.currency} locale={locale} /> {t('envelope.available')}
            </strong>
          </div>
          <Select label={t('profile.label')} defaultValue="operational" options={opts('profile', ['operational', 'cfo'])} className="w-52" />
        </div>

        {!snapshotActive && (
          <div className="border border-warn bg-warn-subtle p-4" role="alert">
            <strong className="inline-flex items-center gap-1.5 font-semibold text-warn">
              <Icon icon={TriangleAlert} />
              {t('noSnapshot.title')}
            </strong>
            <p className="mt-1 mb-2">{t('noSnapshot.body')}</p>
            {/* //todo_#155: el aviso depende del snapshot financiero activo */}
            <Button asChild>
              <AppLink href="/onboarding/finanzas">
                <Icon icon={Upload} />
                {t('noSnapshot.action')}
              </AppLink>
            </Button>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {/* //todo_#156: lanzar misión (POST /v1/missions) */}
          <Button variant="pri" disabledReason={snapshotActive ? pending : t('noSnapshot.reason')}>
            <Icon icon={Play} />
            {t('launch')}
          </Button>
          <span className="text-[13px] text-ink-muted">{t('launchHint')}</span>
        </div>
      </section>
    </div>
  )
}
