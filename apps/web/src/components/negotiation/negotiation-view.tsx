'use client'

import type { NegotiationMessage } from '@apex/shared-types/contracts'
import { Badge, Button, Dialog, DialogContent, Icon, MoneyDisplay, PriceBandBadge, cn } from '@apex/ui'
import { ArrowLeft, Bot, Check, CircleStop, Hand, RotateCcw, Send, ShieldAlert, Trash2 } from 'lucide-react'
import { useFormatter, useLocale, useTranslations } from 'next-intl'
import { useState } from 'react'

import { AppLink } from '@/components/app-link'
import { ErrorPanel } from '@/components/error-panel'
import { TranslateMessage } from '@/components/negotiation/translate-message'
import { OfferConfidence } from '@/components/sellers/offer-confidence'
import { ApiError, useMissionOffers, useNegotiation, useNegotiationAction, useNegotiationMessages } from '@/lib/api'

type DialogKind = 'take' | 'resume' | 'abort' | 'reopen'

const BUBBLE = {
  agent: 'self-end border-accent-line bg-accent-subtle',
  seller: 'self-start border-line bg-panel',
  human: 'self-end border-line-strong bg-raised',
} as const

const TERMINAL = new Set(['completed', 'aborted'])

export function NegotiationView({ negotiationId, missionId }: { negotiationId: string; missionId: string }) {
  const t = useTranslations('negotiation')
  const tc = useTranslations('compare')
  const locale = useLocale()
  const format = useFormatter()
  const neg = useNegotiation(negotiationId)
  const msgs = useNegotiationMessages(negotiationId)
  const act = useNegotiationAction(negotiationId)
  const offers = useMissionOffers(missionId)
  const [dialog, setDialog] = useState<DialogKind | null>(null)
  const [reason, setReason] = useState('')
  const [text, setText] = useState('')

  if (neg.isPending) return <main id="contenido" role="status" className="px-gutter-page py-8 text-ink-muted">{t('loading')}</main>
  if (neg.isError) {
    const notFound = neg.error instanceof ApiError && neg.error.status === 404
    return <ErrorPanel kind={notFound ? 'notFound' : 'error'} onRetry={notFound ? undefined : () => void neg.refetch()} />
  }

  const n = neg.data
  const aborted = n.state === 'aborted'
  const human = n.state === 'human_control'
  const done = TERMINAL.has(n.state)
  const offer = offers.data?.items.find((o) => o.id === n.offer_id)
  const draft = n.pending_draft ?? null
  const error = act.error
  const errorText = error ? errorMessage(error, (k) => t.has(k) ? t(k) : t('errors.generic')) : null
  const time = (iso: string) => format.dateTime(new Date(iso), { hour: '2-digit', minute: '2-digit' })

  const bubble = (m: NegotiationMessage) => (
    <li key={m.id} className={cn('flex max-w-[80%] flex-col gap-1.5 border p-3', BUBBLE[m.role])}>
      <span className="text-[13px] text-ink-muted">
        {t(`roles.${m.role}`)} · <time dateTime={m.at}>{time(m.at)}</time>
      </span>
      <p className="m-0 whitespace-pre-wrap">{m.content}</p>
      {m.role === 'seller' && <TranslateMessage negotiationId={negotiationId} messageId={m.id} />}
    </li>
  )

  const dialogs: Record<DialogKind, { title: string; text: string; confirm: string; danger?: boolean; icon: typeof Hand; action: 'takeover' | 'resume' | 'abort' | 'reopen' }> = {
    take: { title: t('dialog.takeTitle'), text: t('dialog.takeText'), confirm: t('take'), icon: Hand, action: 'takeover' },
    resume: { title: t('dialog.resumeTitle'), text: t('dialog.resumeText'), confirm: t('resume'), icon: Bot, action: 'resume' },
    reopen: { title: t('dialog.reopenTitle'), text: t('dialog.reopenText'), confirm: t('reopen'), icon: RotateCcw, action: 'reopen' },
    abort: { title: t('dialog.abortTitle'), text: t('dialog.abortText'), confirm: t('abort'), danger: true, icon: CircleStop, action: 'abort' },
  }
  const d = dialog ? dialogs[dialog] : null

  const open = (kind: DialogKind, label: string, icon: typeof Hand, variant: 'sec' | 'ghost') => (
    <Button
      variant={variant}
      onClick={() => {
        act.reset()
        setReason('')
        setDialog(kind)
      }}
    >
      <Icon icon={icon} />
      {label}
    </Button>
  )

  const confirm = () => {
    if (!d) return
    act.mutate({ action: d.action, reason: reason.trim() || undefined }, { onSuccess: () => setDialog(null) })
  }

  const sendHuman = () => {
    const content = text.trim()
    if (content) act.mutate({ action: 'send', text: content }, { onSuccess: () => setText('') })
  }

  return (
    <main id="contenido">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-gutter-page py-5">
        <div>
          <div className="text-[13px] text-ink-muted">{t('context', { offer: n.offer_id })}</div>
          <h1 className="mt-1 mb-1 text-[22px] font-semibold tracking-tight">
            {t(n.max_rounds === null ? 'titleNoMax' : 'title', { round: n.rounds, max: n.max_rounds ?? 0 })}
          </h1>
          <Badge tone="neutro">{t(`states.${n.state}`)}</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" asChild>
            <AppLink href={`/misiones/${missionId}`}>
              <Icon icon={ArrowLeft} />
              {t('back')}
            </AppLink>
          </Button>
          {!done && !human && open('take', t('take'), Hand, 'sec')}
          {human && open('resume', t('resume'), Bot, 'sec')}
          {!done && open('abort', t('abort'), CircleStop, 'ghost')}
          {aborted && open('reopen', t('reopen'), RotateCcw, 'sec')}
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
      {errorText && !dialog && (
        <div role="alert" className="flex items-center gap-2 bg-bad-subtle px-gutter-page py-2.5 text-bad">
          <Icon icon={ShieldAlert} />
          {errorText}
        </div>
      )}

      <div className="flex flex-wrap items-start">
        <section className="box-border flex min-w-0 flex-[999_1_640px] flex-col gap-3 px-gutter-page py-gutter-panel">
          {msgs.isError && <p role="alert" className="m-0 text-bad">{t('errors.messages')}</p>}
          <ol role="log" aria-live="polite" aria-label={t('transcript')} className="m-0 flex list-none flex-col gap-3 p-0">
            {msgs.data?.items.map(bubble)}
            {msgs.data?.items.length === 0 && <li className="text-ink-muted">{t('empty')}</li>}
            {draft && !human && !done && (
              <li className="flex max-w-[80%] flex-col gap-3 self-end border border-dashed border-accent p-3">
                <span className="text-[13px] text-ink-muted">
                  {t('draft.title')} · {t(`draft.source.${draft.source}`)}
                </span>
                {/* The approved text is exactly this text; the contract has no edit endpoint, so it is read-only. */}
                <label className="flex flex-col gap-1">
                  {t('draft.textLabel')}
                  <textarea readOnly rows={3} value={draft.text} className="box-border w-full border border-control-border bg-bg p-2.5 text-ink" />
                </label>
                <span className="text-[13px] text-ink-muted">{t('draft.notSent')}</span>
                <div className="flex flex-wrap gap-2">
                  <Button variant="pri" disabled={act.isPending} onClick={() => act.mutate({ action: 'approve', draftId: draft.id })}>
                    <Icon icon={Send} />
                    {t('draft.approve')}
                  </Button>
                  <Button variant="sec" disabled={act.isPending} onClick={() => act.mutate({ action: 'reject', draftId: draft.id })}>
                    <Icon icon={Trash2} />
                    {t('draft.reject')}
                  </Button>
                </div>
              </li>
            )}
          </ol>
          {human && (
            <form
              className="flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                sendHuman()
              }}
            >
              <label className="flex flex-col gap-1">
                {t('human.label')}
                <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} className="box-border w-full border border-control-border bg-bg p-2.5 text-ink focus:border-accent" />
              </label>
              <Button type="submit" variant="pri" className="self-end" disabled={act.isPending || text.trim() === ''}>
                <Icon icon={Send} />
                {t('human.send')}
              </Button>
            </form>
          )}
        </section>

        <aside className="box-border flex min-w-0 flex-[1_1_340px] flex-col gap-6 border-l border-line p-gutter-panel">
          <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt className="text-ink-muted">{t('side.rounds')}</dt>
            <dd className="m-0">{n.max_rounds === null ? n.rounds : t('side.roundsOf', { round: n.rounds, max: n.max_rounds })}</dd>
            <dt className="text-ink-muted">{t('side.strategy')}</dt>
            <dd className="m-0">{n.strategy}</dd>
          </dl>
          <div>
            <strong className="font-semibold">{t('side.guardrails')}</strong>
            {n.guardrail_hits.length === 0 ? (
              <p className="mt-1 mb-0 text-ink-muted">{t('side.noGuardrails')}</p>
            ) : (
              <ul className="mt-1 mb-0 flex list-none flex-col gap-1.5 p-0">
                {n.guardrail_hits.map((g) => (
                  <li key={`${g.code}-${g.at}`}>
                    <Badge tone="warn" icon={Check}>{t(`guardrails.${g.code}`)}</Badge>{' '}
                    <time dateTime={g.at} className="text-[13px] text-ink-muted">{time(g.at)}</time>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {offer ? (
            <dl className="m-0 grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2">
              <dt className="text-ink-muted">{t('side.unitPrice')}</dt>
              <dd className="m-0"><MoneyDisplay amountMinor={offer.unit_price.amount_minor} currency={offer.unit_price.currency} locale={locale} /></dd>
              <dt className="text-ink-muted">{t('side.priceBand')}</dt>
              <dd className="m-0">{offer.price_sanity_check ? <PriceBandBadge band={offer.price_sanity_check.band} label={tc(`price.${offer.price_sanity_check.band}`)} /> : '—'}</dd>
              <dt className="text-ink-muted">{t('side.sellerConfidence')}</dt>
              <dd className="m-0"><OfferConfidence confidence={offer.seller_confidence} /></dd>
            </dl>
          ) : (
            !offers.isPending && <p className="m-0 text-[13px] text-ink-muted">{t('side.offerMissing')}</p>
          )}
        </aside>
      </div>

      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        {d && (
          <DialogContent title={d.title} description={d.text} closeLabel={t('dialog.close')}>
            <div className="flex flex-col gap-4">
              <label className="flex flex-col gap-1">
                {t('dialog.reason')}
                <textarea rows={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} className="box-border w-full border border-control-border bg-bg p-2.5 text-ink focus:border-accent" />
              </label>
              {errorText && <p role="alert" className="m-0 text-bad">{errorText}</p>}
              <div className="flex flex-wrap justify-end gap-2">
                <Button variant="sec" onClick={() => setDialog(null)}>{t('dialog.cancel')}</Button>
                <Button variant={d.danger ? 'danger' : 'pri'} disabled={act.isPending} onClick={confirm}>
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

/** Maps a failed write to a message key: the closed 409 `reason` when we have text for it, otherwise the generic one. */
export function errorMessage(error: unknown, text: (key: string) => string): string {
  return text(error instanceof ApiError && error.reason ? `errors.${error.reason}` : 'errors.generic')
}
