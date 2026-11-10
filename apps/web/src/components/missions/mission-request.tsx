'use client'

import type { SourcingRequest } from '@apex/shared-types/contracts'
import { Button, Chat, Icon, Input, Label, type ChatMessage } from '@apex/ui'
import { ListChecks, Play, RefreshCw, TriangleAlert, Upload } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useId, useState } from 'react'

import { AppLink, toRoute } from '@/components/app-link'
import { ApiError, useCreateMission, useCreateSourcingRequest } from '@/lib/api'

function Field({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  const id = useId()
  return (
    <div className={`flex flex-col gap-1 ${wide ? 'col-span-full' : ''}`}>
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} readOnly />
    </div>
  )
}

export function MissionRequest() {
  const t = useTranslations('missions.request')
  const locale = useLocale()
  const router = useRouter()
  const countryId = useId()
  const [country, setCountry] = useState('')
  const [text, setText] = useState('')
  const [request, setRequest] = useState<SourcingRequest | null>(null)
  const interpret = useCreateSourcingRequest()
  const launch = useCreateMission()

  const send = (natural_language: string) => {
    setText(natural_language)
    setRequest(null)
    launch.reset()
    interpret.mutate({ natural_language, delivery_country: country.trim().toUpperCase() }, { onSuccess: setRequest })
  }

  const messages: ChatMessage[] = []
  if (text) messages.push({ id: 'u1', role: 'human', author: t('chat.you'), text })
  if (request) messages.push({ id: 'a1', role: 'agent', author: t('chat.agent'), text: t('chat.reply') })
  if (interpret.isError) messages.push({ id: 'e1', role: 'agent', author: t('chat.agent'), text: t('chat.error') })

  const blocked = launch.error instanceof ApiError && launch.error.status === 409
  const clarify = request?.needs_clarification ?? []
  const launchReason = !request ? t('launchNeedsRequest') : clarify.length > 0 ? t('launchNeedsClarification') : undefined
  const tiers = request?.quantity_tiers.map((q) => new Intl.NumberFormat(locale).format(q.quantity)).join(' · ') ?? ''
  const specs = Object.entries(request?.spec.specifications ?? {}).map(([k, v]) => `${k}: ${v}`).join(' · ')

  return (
    <div className="flex flex-wrap items-start gap-8">
      <section className="flex min-w-0 flex-[1_1_420px] flex-col gap-3" aria-labelledby="req-chat">
        <h2 id="req-chat" className="text-[13px] font-normal text-ink-muted">
          {t('chat.title')}
        </h2>
        <div className="flex flex-col gap-1">
          <Label htmlFor={countryId}>{t('review.country')}</Label>
          <Input id={countryId} value={country} onChange={(e) => setCountry(e.target.value)} maxLength={2} placeholder={t('review.countryHint')} className="w-24" />
        </div>
        <Chat
          messages={messages}
          thinking={interpret.isPending}
          phrases={['interpreting', 'spec', 'budget', 'platforms', 'plan'].map((k) => t(`chat.phrases.${k}`))}
          labels={{ input: t('chat.title'), placeholder: t('chat.placeholder'), send: t('chat.send'), stop: t('chat.stop'), hint: t('chat.hint') }}
          onSend={send}
          onStop={() => interpret.reset()}
          disabledReason={country.trim().length !== 2 ? t('chat.needsCountry') : undefined}
        />
        <div>
          <Button disabledReason={text ? (country.trim().length !== 2 ? t('chat.needsCountry') : undefined) : t('launchNeedsRequest')} onClick={() => send(text)}>
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
        {request ? (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
            <Field label={t('review.product')} value={request.spec.description} wide />
            <Field label={t('review.quantity')} value={tiers} />
            <Field label={t('review.destination')} value={request.delivery_country} />
            <Field label={t('review.deadline')} value={request.target_delivery_date ?? t('review.none')} />
            <Field label={t('review.spec')} value={specs || t('review.none')} wide />
          </div>
        ) : (
          <p className="text-ink-muted">{t('review.empty')}</p>
        )}
        {clarify.length > 0 && (
          <div className="border border-warn bg-warn-subtle p-4" role="alert">
            <strong className="font-semibold text-warn">{t('clarify')}</strong>
            <ul className="mt-1 list-disc pl-5">
              {clarify.map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
          </div>
        )}

        {blocked && (
          <div className="border border-warn bg-warn-subtle p-4" role="alert">
            <strong className="inline-flex items-center gap-1.5 font-semibold text-warn">
              <Icon icon={TriangleAlert} />
              {t('noSnapshot.title')}
            </strong>
            <p className="mt-1 mb-2">{launch.error instanceof ApiError ? (launch.error.detail ?? t('noSnapshot.body')) : t('noSnapshot.body')}</p>
            <Button asChild>
              <AppLink href="/onboarding/finanzas">
                <Icon icon={Upload} />
                {t('noSnapshot.action')}
              </AppLink>
            </Button>
          </div>
        )}
        {launch.isError && !blocked && (
          <p className="text-warn" role="alert">
            {t('launchError')}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="pri"
            disabledReason={launchReason ?? (launch.isPending ? t('launching') : undefined)}
            onClick={() => request && launch.mutate({ sourcing_request_id: request.id }, { onSuccess: (m) => router.push(toRoute(`/${locale}/misiones/${m.id}`)) })}
          >
            <Icon icon={Play} />
            {t('launch')}
          </Button>
          <span className="text-[13px] text-ink-muted">{t('launchHint')}</span>
        </div>
      </section>
    </div>
  )
}
