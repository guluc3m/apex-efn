'use client'

import {
  Badge,
  Button,
  ConfidenceBandBadge,
  Dialog,
  DialogContent,
  Icon,
  PriceBandBadge,
  cn,
  type PriceBand,
} from '@apex/ui'
import { ArrowLeft, ArrowUpRight, Bot, Check, CircleStop, Hand, Images, Languages, RotateCcw, Send, Trash2, TriangleAlert } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useState, type ReactNode } from 'react'

import { AppLink } from '@/components/app-link'
import type { MessagePart, NegotiationFixture, TranscriptMessage } from '@/fixtures/negotiation'

import { PriceLadder } from './price-ladder'

type DialogKind = 'take' | 'resume' | 'abort' | 'reopen'

const BUBBLE = {
  agent: 'self-end border-accent-line bg-accent-subtle',
  seller: 'self-start border-line bg-panel',
  human: 'self-end border-line-strong bg-raised',
} as const

function Signals({ rows }: { rows: { k: string; v: string }[] }) {
  return (
    <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
      {rows.map((r) => (
        <div key={r.k} className="contents">
          <dt className="text-ink-muted">{r.k}</dt>
          <dd className="m-0">{r.v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function NegotiationView({ neg, missionId }: { neg: NegotiationFixture; missionId: string }) {
  const t = useTranslations('negotiation')
  const [showTr, setShowTr] = useState(true)
  const [dialog, setDialog] = useState<DialogKind | null>(null)
  const [reason, setReason] = useState('')

  const aborted = neg.state === 'aborted'
  const human = neg.state === 'human'
  const pending = t('pending')
  const band = (b: PriceBand) => t(`bands.price.${b}`)

  const part = (p: MessagePart, i: number): ReactNode =>
    'price' in p ? (
      <span key={i} className="mx-0.5 inline-block align-middle">
        <PriceBandBadge band={p.band} label={`${p.price} · ${band(p.band)}`} />
      </span>
    ) : (
      <span key={i} lang={p.lang}>{p.text}</span>
    )

  const bubble = (m: TranscriptMessage) => (
    <li key={m.id} className={cn('flex max-w-[80%] flex-col gap-1.5 border p-3', BUBBLE[m.role])}>
      <span className="inline-flex items-center gap-2 text-[13px] text-ink-muted">
        <span aria-hidden="true" className="inline-flex size-6 items-center justify-center border border-line-strong bg-bg text-[11px] text-ink-soft">{m.initials}</span>
        {m.author} · <time>{m.time}</time> · {m.platform}
      </span>
      <p className="m-0">{m.parts.map(part)}</p>
      {showTr && m.translation && (
        <span className="inline-flex items-start gap-2 text-ink-soft">
          <Icon icon={Languages} label={t('translationIcon')} className="mt-0.5" />
          <span aria-hidden="true">·</span>
          <span lang={m.translation.lang}>{m.translation.text}</span>
        </span>
      )}
    </li>
  )

  const dialogs: Record<DialogKind, { title: string; text: string; confirm: string; danger?: boolean; icon: typeof Hand }> = {
    take: { title: t('dialog.takeTitle'), text: t('dialog.takeText'), confirm: t('take'), icon: Hand },
    resume: { title: t('dialog.resumeTitle'), text: t('dialog.resumeText'), confirm: t('resume'), icon: Bot },
    abort: { title: t('dialog.abortTitle'), text: t('dialog.abortText'), confirm: t('abort'), danger: true, icon: CircleStop },
    reopen: { title: t('dialog.reopenTitle'), text: t('dialog.reopenText'), confirm: t('dialog.reopenConfirm'), icon: RotateCcw },
  }
  const d = dialog ? dialogs[dialog] : null

  const open = (kind: DialogKind, label: string, icon: typeof Hand, variant: 'sec' | 'ghost', blocked?: string) => (
    <Button variant={variant} disabledReason={blocked} onClick={() => setDialog(kind)}>
      <Icon icon={icon} />
      {label}
    </Button>
  )

  return (
    <main id="contenido">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-gutter-page py-5">
        <div>
          <div className="text-[13px] text-ink-muted">{t('context', { code: neg.missionCode, seller: neg.seller, platform: neg.platform })}</div>
          <h1 className="mt-1 mb-0 text-[22px] font-semibold tracking-tight">
            {t(aborted ? 'titleAborted' : 'title', { round: neg.round, max: neg.maxRounds })}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" asChild>
            <AppLink href={`/misiones/${missionId}`}>
              <Icon icon={ArrowLeft} />
              {t('back')}
            </AppLink>
          </Button>
          {!aborted && !human && open('take', t('take'), Hand, 'sec')}
          {human && open('resume', t('resume'), Bot, 'sec')}
          {!aborted && open('abort', t('abort'), CircleStop, 'ghost')}
          {aborted && open('reopen', t('reopen'), RotateCcw, 'sec', neg.reopenBlocked)}
        </div>
      </div>

      {human && (
        <div role="status" className="flex items-center gap-2 border-b border-line-strong bg-raised px-gutter-page py-2.5">
          <Icon icon={Hand} />
          {t('humanBanner')}
        </div>
      )}
      {aborted && (
        <div role="status" className="flex items-center gap-2 bg-bad-subtle px-gutter-page py-2.5 text-bad">
          <Icon icon={CircleStop} />
          {t('abortedBanner')}
        </div>
      )}

      <div className="flex flex-wrap items-start">
        <section className="box-border flex min-w-0 flex-[999_1_640px] flex-col gap-3 px-gutter-page py-gutter-panel">
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" disabledReason={pending}>
              <Icon icon={Languages} />
              {t('translationRequest')}
            </Button>
            <Button variant="ghost" size="sm" aria-pressed={showTr} onClick={() => setShowTr((v) => !v)}>
              <Icon icon={Languages} />
              {t(showTr ? 'translationHide' : 'translationShow')}
            </Button>
          </div>

          <ol role="log" aria-live="polite" aria-label={t('transcript')} className="m-0 flex list-none flex-col gap-3 p-0">
            {neg.messages.map(bubble)}
            {neg.reopened && (
              <li role="separator" className="flex items-center gap-3 text-[13px] text-ink-muted before:h-px before:flex-1 before:bg-line after:h-px after:flex-1 after:bg-line">
                {t('reopenedSeparator', { by: neg.reopened.by, time: neg.reopened.time })}
              </li>
            )}
            {!aborted && !human && (
              <li className="flex max-w-[80%] flex-col gap-3 self-end border border-dashed border-accent p-3">
                <span className="inline-flex items-center gap-2 text-[13px] text-ink-muted">
                  <span aria-hidden="true" className="inline-flex size-6 items-center justify-center border border-accent-line bg-bg text-[11px] text-ink-soft">{neg.draft.initials}</span>
                  {t('draft.title')}
                </span>
                <label className="flex flex-col gap-1">
                  {t('draft.textLabel')}
                  <textarea rows={3} defaultValue={neg.draft.text} className="box-border w-full border border-control-border bg-bg p-2.5 text-ink focus:border-accent" />
                </label>
                <div className="flex flex-col gap-1.5">
                  <span className="text-[13px] text-ink-muted">{t('draft.checked')}</span>
                  <span className="flex flex-wrap gap-1.5">
                    {neg.draft.guardrails.map((g) => (
                      <Badge key={g} tone="ok" icon={Check}>{g}</Badge>
                    ))}
                  </span>
                  <span className="text-[13px] text-ink-muted">{neg.draft.note}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {/* //todo_#158: aprobar y enviar vía POST approve-send; hasta entonces nada se muestra como enviado */}
                  <Button variant="pri" disabledReason={pending}>
                    <Icon icon={Send} />
                    {t('draft.approve')}
                  </Button>
                  <Button variant="sec" disabledReason={pending}>
                    <Icon icon={Trash2} />
                    {t('draft.discard')}
                  </Button>
                </div>
              </li>
            )}
          </ol>
          {/* //todo_#159: entrada de chat del humano (Chat de @apex/ui) cuando haya endpoint de envío en takeover */}
        </section>

        <aside className="box-border flex min-w-0 flex-[1_1_340px] flex-col gap-6 border-l border-line p-gutter-panel">
          <div>
            <div className="text-[13px] text-ink-muted">{t('side.current')}</div>
            <div className="text-[28px] leading-tight font-semibold">{neg.offer.current}</div>
            <div className="text-[13px] text-ink-muted">
              {t('side.summary', { initial: neg.offer.initial, delta: neg.offer.delta, target: neg.offer.target })}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <ConfidenceBandBadge
              band={neg.confidence.band}
              label={t('side.confidenceLabel', { band: t(`bands.confidence.${neg.confidence.band}`), score: neg.confidence.score })}
              breakdownTitle={t('side.confidenceTitle')}
              breakdown={<Signals rows={neg.confidence.signals} />}
            />
            <PriceBandBadge band={neg.price.band} label={t('side.priceLabel', { band: band(neg.price.band) })} />
          </div>
          <Signals rows={neg.limits} />
          <div className="border border-warn/40 bg-warn-subtle p-3">
            <strong className="inline-flex items-center gap-2 font-semibold text-warn">
              <Icon icon={TriangleAlert} />
              {t('side.escalationTitle')}
            </strong>
            <p className="mt-1 mb-2">{neg.escalation.reason}</p>
            <Button variant="sec" size="sm" asChild>
              <AppLink href={`/decisiones/${neg.escalation.dealId}`}>
                <Icon icon={ArrowUpRight} />
                {t('side.escalationOpen', { seller: neg.escalation.seller })}
              </AppLink>
            </Button>
          </div>
          <PriceLadder ladder={neg.ladder} />
          {/* //todo_#158: visor de capturas de pantalla (S3) */}
          <Button variant="ghost" size="sm" className="self-start" disabledReason={pending}>
            <Icon icon={Images} />
            {t('side.screenshots', { count: neg.screenshots })}
          </Button>
        </aside>
      </div>

      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        {d && (
          <DialogContent title={d.title} description={d.text} closeLabel={t('dialog.close')}>
            <div className="flex flex-col gap-4">
              {dialog === 'reopen' && (
                <label className="flex flex-col gap-1">
                  {t('dialog.reason')}
                  <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} className="box-border w-full border border-control-border bg-bg p-2.5 text-ink focus:border-accent" />
                </label>
              )}
              <div className="flex flex-wrap justify-end gap-2">
                <Button variant="sec" onClick={() => setDialog(null)}>{t('dialog.cancel')}</Button>
                {/* //todo_#159: takeover/resume/abort; //todo_#160: reabrir con motivo. Confirmación sin backend. */}
                <Button variant={d.danger ? 'danger' : 'pri'} disabledReason={pending}>
                  <Icon icon={d.icon} />
                  {d.confirm}
                </Button>
              </div>
            </div>
          </DialogContent>
        )}
      </Dialog>
    </main>
  )
}
