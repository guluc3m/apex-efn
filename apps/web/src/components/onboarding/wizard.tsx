'use client'

import { Button, Chat, Icon, type ChatMessage } from '@apex/ui'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Bot, ChevronLeft, ChevronRight } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useEffect, useState } from 'react'

import { api } from '@/lib/api'
import { queryKeys, useCurrentOnboarding, useIntakeMessages, useOnboardingSession, useSendIntakeMessage } from '@/lib/api/hooks'
import { fromProfile, restoreDrafts, toProfilePatch } from '@/lib/onboarding-profile'
import { ensureSession } from '@/lib/onboarding-session'
import { useOnboarding } from '@/stores/onboarding'

import { AppLink } from '../app-link'

import { AccountsStep } from './accounts-step'
import { STEP_IDS, schemas, type FormStepId, type StepId } from './schemas'
import { BudgetStep, CompanyStep, FORM_ID, FinanceStep, NegotiationStep, PolicyStep, SectorStep, StepForm } from './steps'

const FORMS = { empresa: CompanyStep, sector: SectorStep, presupuesto: BudgetStep, politica: PolicyStep, negociacion: NegotiationStep }

type StepState = { kind: 'done' | 'warnings' | 'pending' | 'none'; count?: number }

// Server step names (contract) -> wizard steps. The others are tenant config, which the session does not track.
const SERVER_STEP: Partial<Record<StepId, string>> = { empresa: 'company', sector: 'sector', finanzas: 'finance' }

function stateOf(p?: { done: number; warnings: number; pending: number }): StepState {
  if (!p) return { kind: 'none' }
  if (p.pending > 0) return { kind: 'pending', count: p.pending }
  if (p.warnings > 0) return { kind: 'warnings', count: p.warnings }
  return { kind: 'done' }
}

/** Finds the tenant's current session after a reload and restores its saved draft. Completed onboarding leaves the wizard. */
function useSavedSession() {
  const router = useRouter()
  const locale = useLocale()
  const current = useCurrentOnboarding()
  const sessionId = useOnboarding((s) => s.sessionId)
  const session = useOnboardingSession(sessionId)
  useEffect(() => {
    const found = current.data
    const { sessionId: id, setSessionId, restore, drafts } = useOnboarding.getState()
    if (!found || id) return
    setSessionId(found.id)
    restore(restoreDrafts(found.company_profile, drafts))
  }, [current.data])
  useEffect(() => {
    if (session.data?.status === 'completed' && session.data.active_financial_snapshot_id) router.replace(`/${locale}/decisiones` as never)
  }, [session.data, router, locale])
  return session.data
}

function isForm(id: StepId): id is FormStepId {
  return id in schemas
}

function Assistant() {
  const t = useTranslations('onboarding.assistant')
  const sessionId = useOnboarding((s) => s.sessionId)
  const history = useIntakeMessages(sessionId)
  const send = useSendIntakeMessage()
  const messages: ChatMessage[] = (history.data?.items ?? []).map((m) => ({
    id: m.id,
    role: m.role === 'agent' ? 'agent' : 'human',
    author: t(m.role === 'agent' ? 'agent' : 'you'),
    text: m.text,
  }))
  const onSend = async (text: string): Promise<void> => {
    try {
      const id = await ensureSession()
      const { turn } = await send.mutateAsync({ sessionId: id, text })
      const { drafts, applyAgentDraft } = useOnboarding.getState()
      const filled = fromProfile(turn.session.company_profile, drafts.empresa)
      if (filled) applyAgentDraft('empresa', filled)
    } catch {
      // the error is shown from `send.isError`; nothing was added to the conversation
    }
  }
  return (
    <aside aria-label={t('title')} className="flex min-w-0 flex-col border-l border-line">
      <div className="border-b border-line p-4">
        <strong className="inline-flex items-center gap-2 font-semibold">
          <Icon icon={Bot} />
          {t('title')}
        </strong>
        <div className="text-[13px] text-ink-muted">{t('subtitle')}</div>
      </div>
      <div className="flex flex-1 flex-col gap-3 p-4">
        <Chat
          messages={messages}
          thinking={send.isPending}
          labels={{ input: t('input'), placeholder: t('placeholder'), send: t('send'), stop: t('stop') }}
          onSend={(text) => void onSend(text)}
        />
        {send.isError && (
          <p role="alert" className="m-0 text-bad">
            {t('error')}
          </p>
        )}
      </div>
    </aside>
  )
}

export function OnboardingWizard({ step }: { step: StepId }) {
  const t = useTranslations('onboarding')
  const locale = useLocale()
  const router = useRouter()
  const index = STEP_IDS.indexOf(step)
  const prev = STEP_IDS[index - 1]
  const next = STEP_IDS[index + 1]
  const [saveError, setSaveError] = useState(false)
  const qc = useQueryClient()
  const saved = useSavedSession()
  const revision = useOnboarding((s) => s.draftsRevision)
  const financialImport = useOnboarding((s) => s.financialImport)
  const go = () => next && router.push(`/${locale}/onboarding/${next}` as never)
  // empresa and sector persist to the session; a failed save keeps the user on the step.
  const goNext = async (): Promise<void> => {
    if (step !== 'empresa' && step !== 'sector') {
      go()
      return
    }
    try {
      const id = await ensureSession()
      await api.updateOnboardingSession(id, { company_profile: toProfilePatch(step, useOnboarding.getState().drafts) })
      void qc.invalidateQueries({ queryKey: queryKeys.onboardingSession(id) })
      setSaveError(false)
      go()
    } catch {
      setSaveError(true)
    }
  }

  const body = isForm(step) ? (
    (() => {
      const Body = FORMS[step]
      return (
        <StepForm key={`${step}-${revision}`} id={step} onValid={goNext}>
          <Body />
        </StepForm>
      )
    })()
  ) : step === 'cuentas' ? (
    <AccountsStep />
  ) : (
    <FinanceStep />
  )

  return (
    <>
      <main id="contenido" tabIndex={-1} className="grid min-h-[calc(100vh-57px)] grid-cols-[260px_minmax(0,1fr)_380px]">
        <nav aria-label={t('stepsLabel')} className="flex flex-col border-r border-line py-4">
          <p className="m-0 px-4 pb-2 text-[13px] text-ink-muted">{t('header.title', { n: index + 1, total: STEP_IDS.length })}</p>
          <ol className="m-0 list-none p-0">
            {STEP_IDS.map((id, i) => {
              const server = SERVER_STEP[id]
              const s = stateOf(server ? saved?.steps?.find((x) => x.step === server) : undefined)
              return (
                <li key={id}>
                  <AppLink
                    href={`/onboarding/${id}`}
                    aria-current={id === step ? 'step' : undefined}
                    className="flex items-baseline gap-3 border-l-2 border-transparent px-4 py-2.5 text-ink-soft no-underline transition-[background-color,color] duration-(--fast) hover:bg-panel hover:text-ink aria-[current=step]:border-accent aria-[current=step]:bg-raised aria-[current=step]:text-ink"
                  >
                    <span className="w-4 text-[13px] text-ink-muted tabular-nums">{i + 1}</span>
                    <span className="flex-1">{t(`steps.${id}.label`)}</span>
                    {s.kind !== 'none' && <span className="text-[13px] text-ink-muted">{t(`stepState.${s.kind}`, { count: s.count ?? 0 })}</span>}
                  </AppLink>
                </li>
              )
            })}
          </ol>
          <p className="m-4 text-[13px] text-ink-muted">{t('blocking')}</p>
        </nav>

        <div className="min-w-0 px-10 py-8">
          <div className="flex max-w-160 flex-col gap-6">
            <div>
              <h1 className="m-0 text-[22px] font-semibold tracking-tight">{t(`steps.${step}.title`)}</h1>
              <p className="mt-1.5 mb-0 text-ink-soft">{t(`steps.${step}.lead`)}</p>
            </div>
            {body}
            {saveError && (
              <p role="alert" className="m-0 text-bad">
                {t('errors.save')}
              </p>
            )}
            <div className="flex gap-2 border-t border-line pt-4">
              {prev ? (
                <Button asChild variant="sec">
                  <AppLink href={`/onboarding/${prev}`}>
                    <Icon icon={ChevronLeft} />
                    {t('nav.prev')}
                  </AppLink>
                </Button>
              ) : (
                <Button variant="sec" disabledReason={t('nav.firstStep')}>
                  <Icon icon={ChevronLeft} />
                  {t('nav.prev')}
                </Button>
              )}
              {step === 'finanzas' ? (
                financialImport ? (
                  <Button asChild variant="pri">
                    <AppLink href={`/onboarding/finanzas/${financialImport.id}`}>
                      <Icon icon={ArrowRight} />
                      {t('nav.toImport')}
                    </AppLink>
                  </Button>
                ) : (
                  <Button variant="pri" disabledReason={t('nav.noImport')}>
                    <Icon icon={ArrowRight} />
                    {t('nav.toImport')}
                  </Button>
                )
              ) : isForm(step) ? (
                <Button type="submit" form={FORM_ID} variant="pri">
                  {t('nav.next')}
                  <Icon icon={ChevronRight} />
                </Button>
              ) : (
                <Button asChild variant="pri">
                  <AppLink href={`/onboarding/${next}`}>
                    {t('nav.next')}
                    <Icon icon={ChevronRight} />
                  </AppLink>
                </Button>
              )}
            </div>
          </div>
        </div>

        <Assistant />
      </main>
    </>
  )
}
