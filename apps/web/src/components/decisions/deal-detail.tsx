'use client'

import type { Deal, DealAction, Money } from '@apex/shared-types/contracts'
import { Button, Dialog, DialogContent, Icon, Input, Label, MoneyDisplay, Select } from '@apex/ui'
import {
  ArrowDown, ChartBarStacked, Flag, Gauge, Hand, MessagesSquare, Package, Pause, PenLine, Receipt, Shield, Trash2, Upload,
  type LucideIcon,
} from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { useState, type ReactNode } from 'react'

import { AppLink } from '@/components/app-link'
import { PriceDistribution } from '@/components/compare/price-distribution'
import { useDealAction, useMissionOffers } from '@/lib/api'
import { blockedCodes, dealActionBody, DISCARD_REASONS, emptyActionForm } from '@/lib/decisions'

import { DealBadges } from './deal-badges'
import { DecisionFooter } from './decision-footer'

const ACTION_ICON: Record<DealAction, LucideIcon> = {
  follow: PenLine, renegotiate: MessagesSquare, takeover: Hand, hold: Pause, discard: Trash2,
}
const textarea = 'box-border w-full border border-control-border bg-bg px-2.5 py-2 text-ink focus:border-accent'

function Section({ icon, title, open, children }: { icon: LucideIcon; title: string; open?: boolean; children: ReactNode }) {
  return (
    <details open={open} className="border-t border-line py-3">
      <summary className="flex min-h-7 cursor-pointer items-center gap-2 font-semibold">
        <Icon icon={icon} />
        {title}
      </summary>
      <div className="pt-2">{children}</div>
    </details>
  )
}

const Row = ({ k, children }: { k: string; children: ReactNode }) => (
  <div className="flex justify-between gap-3 py-0.5">
    <span className="text-[13px] text-ink-muted">{k}</span>
    <span>{children}</span>
  </div>
)

export function DealDetail({ deal, role }: { deal: Deal; role: string }) {
  const missionOffers = useMissionOffers(deal.mission_id)
  const t = useTranslations('decisions')
  const locale = useLocale()
  const [action, setAction] = useState<DealAction | null>(null)
  const [form, setForm] = useState(emptyActionForm)
  const mutation = useDealAction()
  const money = (m: Money) => <MoneyDisplay amountMinor={m.amount_minor} currency={m.currency} locale={locale} />
  /** Translation when the key exists, the raw code otherwise (the API's vocabularies can grow). */
  const known = (ns: string, code: string) => (t.has(`${ns}.${code}`) ? t(`${ns}.${code}`) : code)

  const { offer } = deal
  const conf = offer.seller_confidence
  const sanity = offer.price_sanity_check
  const fit = offer.financial_fit
  const unit = deal.outcome?.final_price ?? offer.unit_price
  const initial = deal.outcome?.initial_price
  const discountPct = deal.outcome ? deal.outcome.discount_bp / 100 : 0
  const canCreate = role !== 'viewer'
  const open = (a: DealAction) => {
    mutation.reset()
    setForm(emptyActionForm)
    setAction(a)
  }
  const body = action ? dealActionBody(action, form) : null

  const confBreakdown = conf && (
    <div className="text-[13px]">
      {Object.entries(conf.signals_normalized).map(([k, v]) => (
        <Row key={k} k={known('signal', k)}>{(v * 100).toFixed(0)} %</Row>
      ))}
      {conf.penalties.map((p) => (
        <Row key={p} k={t('detail.penalty')}>{known('signal', p)}</Row>
      ))}
    </div>
  )
  const staleFit = fit?.financials_stale
  const terms = [
    ...Object.entries(offer.specifications ?? {}),
    ...(offer.lead_time_days != null ? [[t('detail.leadTime'), t('detail.leadTimeV', { n: offer.lead_time_days })]] : []),
    ...(offer.payment_terms_days != null
      ? [[t('detail.payment'), offer.payment_terms_days === 0 ? t('detail.prepayment') : t('detail.leadTimeV', { n: offer.payment_terms_days })]]
      : []),
    ...(offer.incoterm ? [['Incoterm', offer.incoterm]] : []),
    [t('detail.moq'), String(offer.moq)],
  ]

  return (
    <>
      <div className="sticky top-0 z-1 border-b border-line bg-bg p-6">
        <div className="text-[13px] text-ink-muted">{t(`state.${deal.state}`)}</div>
        <h1 className="my-1 mb-4 text-[22px] leading-tight font-semibold tracking-tight text-balance">{offer.title}</h1>
        <div className="flex flex-wrap items-start gap-4">
          <div className="box-border flex flex-[2_1_320px] flex-wrap gap-10 border border-line bg-panel px-6 py-5">
            <div>
              <div className="text-[13px] text-ink-muted">{t(deal.outcome ? 'detail.priceNegotiated' : 'detail.priceInitial')}</div>
              <div className="my-1 flex items-baseline gap-1">
                {money(unit)}
                <span className="text-[13px] text-ink-muted">{t('perUnit')}</span>
              </div>
              <div className="flex flex-wrap items-center gap-x-1.5 text-[13px] text-ink-muted">
                {initial ? (
                  <>
                    {t('detail.initial')} {money(initial)} ·
                    <span className="inline-flex items-center gap-0.5 text-accent">
                      <Icon icon={ArrowDown} />−{discountPct} %
                    </span>
                  </>
                ) : (
                  t('detail.notNegotiated')
                )}
              </div>
            </div>
            <div>
              <div className="text-[13px] text-ink-muted">{t('detail.confidence')}</div>
              <div className="my-1 text-[40px] leading-[1.1] font-semibold tracking-tight tabular-nums">{conf?.score ?? '—'}</div>
            </div>
          </div>
          <div className="flex flex-[1_1_200px] flex-col gap-2.5 pt-5">
            <div>
              <span className="text-[13px] text-ink-muted">{t('detail.landed')} </span>
              <strong>{fit ? money(fit.landed_cost.total) : '—'}</strong>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <DealBadges deal={deal} confidenceBreakdown={confBreakdown} />
            </div>
            <div className="text-[13px] text-ink-muted">
              {offer.seller_name} · {offer.platform}
              {offer.expires_at && ` · ${t('detail.expires', { date: new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(offer.expires_at)) })}`}
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {deal.actions.map((a, n) => {
            const codes = blockedCodes(a)
            const reason = codes?.map((c) => a.blocked_by.find((b) => b.code === c)?.message ?? t(`block.${c}`)).join(' ')
            return (
              <Button key={a.action} variant={n === 0 && !reason ? 'pri' : 'sec'} disabledReason={reason} onClick={() => open(a.action)}>
                <Icon icon={ACTION_ICON[a.action]} />
                {t(`action.${a.action}`)}
              </Button>
            )
          })}
        </div>
        <ul className="mt-1.5 list-none p-0 text-[13px] text-ink-muted">
          {deal.actions.filter((a) => !a.allowed).map((a) => (
            <li key={a.action}>
              <strong>{t(`action.${a.action}`)}:</strong>{' '}
              {(blockedCodes(a) ?? []).map((c) => a.blocked_by.find((b) => b.code === c)?.message ?? t(`block.${c}`)).join(' ')}
            </li>
          ))}
        </ul>
        {staleFit && (
          <p className="mt-2 text-[13px]">
            {t('stale.body')}{' '}
            <AppLink href="/empresa/finanzas" className="inline-flex items-center gap-1 text-accent underline">
              <Icon icon={Upload} />
              {t('stale.cta')}
            </AppLink>
          </p>
        )}
      </div>

      <div className="px-6 pt-2 pb-12">
        {deal.negotiation ? (
          <p>
            <Button asChild>
              <AppLink href={`/decisiones/${deal.id}/transcripcion`}>
                <Icon icon={MessagesSquare} />
                {t('detail.fullTranscript')}
              </AppLink>
            </Button>
          </p>
        ) : (
          <p className="text-[13px] text-ink-muted">{t('detail.noNegotiation')}</p>
        )}
        <Section icon={Shield} title={t('detail.whyConfidence')} open>
          {confBreakdown ?? <p className="text-[13px] text-ink-muted">{t('detail.noConfidence')}</p>}
        </Section>
        <Section icon={Gauge} title={t('detail.sanity')}>
          {sanity ? (
            <>
              <Row k={t('detail.reference')}>{money(sanity.reference_price_eur)}</Row>
              <Row k={t('detail.median')}>{money(sanity.median)}</Row>
              <Row k={t('detail.sample')}>{sanity.sample_size}</Row>
              <Row k={t('detail.deviation')}>{(sanity.relative_deviation * 100).toFixed(1)} %</Row>
              {sanity.explanations.map((e) => (
                <div key={e.code} className="py-0.5 text-[13px]">{known('explanation', e.code)}</div>
              ))}
            </>
          ) : (
            <p className="text-[13px] text-ink-muted">{t('detail.noSanity')}</p>
          )}
          <div className="mt-2">
            {missionOffers.data ? (
              <PriceDistribution offers={missionOffers.data.items} />
            ) : (
              <div className="flex h-24 items-center justify-center border border-line bg-bg text-[13px] text-ink-muted">{t('detail.chartPending')}</div>
            )}
          </div>
        </Section>
        <Section icon={Receipt} title={t('detail.landedBreakdown')}>
          {fit ? (
            <>
              {fit.landed_cost.lines.map((l) => (
                <Row key={l.code} k={t(`line.${l.code}`)}>{money(l.amount)}</Row>
              ))}
              <div className="flex justify-between border-t border-line pt-1.5">
                <strong>{t('detail.total')}</strong>
                <strong>{money(fit.landed_cost.total)}</strong>
              </div>
              {fit.reasons.map((r) => (
                <p key={r} className="mt-1 text-[13px] text-ink-muted">{r}</p>
              ))}
            </>
          ) : (
            <p className="text-[13px] text-ink-muted">{t('detail.noLanded')}</p>
          )}
        </Section>
        <Section icon={ChartBarStacked} title={t('detail.contribution')}>
          {/* //todo_#148: contribución por criterio desde GET /v1/missions/{id}/recommendation (necesita el id del perfil de ranking) */}
          <p className="text-[13px] text-ink-muted">{t('detail.unscored')}</p>
        </Section>
        <Section icon={Flag} title={t('detail.risks')}>
          {deal.flags?.length || conf?.flags.length ? (
            <>
              {deal.flags?.map((r) => <div key={r}>{known('risk', r)}</div>)}
              {conf?.flags.map((f, i) => <div key={i}>{known('risk', f.type)}</div>)}
            </>
          ) : (
            <div>{t('risk.none')}</div>
          )}
        </Section>
        <Section icon={Package} title={t('detail.terms')}>
          {terms.map(([k, v]) => (
            <Row key={k} k={k!}>{v}</Row>
          ))}
        </Section>
      </div>

      <Dialog open={action !== null} onOpenChange={(o) => !o && setAction(null)}>
        {action && (
          <DialogContent title={t(`action.${action}`)} closeLabel={t('dialog.close')}>
            <div className="my-2 flex flex-wrap gap-3">
              {action === 'discard' && (
                <>
                  <Select
                    label={t('dialog.reasonCode')}
                    value={form.discardReason}
                    onValueChange={(v) => setForm({ ...form, discardReason: v as typeof form.discardReason })}
                    options={DISCARD_REASONS.map((v) => ({ value: v, label: t(`discardReason.${v}`) }))}
                    placeholder={t('dialog.choose')}
                  />
                  <div className="flex flex-[1_1_240px] flex-col gap-1">
                    <Label htmlFor="d-comment">{t('dialog.commentRequired')}</Label>
                    <textarea id="d-comment" rows={2} className={textarea} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
                  </div>
                </>
              )}
              {action === 'hold' && (
                <div className="flex flex-col gap-1">
                  <Label htmlFor="d-date">{t('dialog.reviewDate')}</Label>
                  <Input id="d-date" type="date" value={form.holdUntil} onChange={(e) => setForm({ ...form, holdUntil: e.target.value })} />
                </div>
              )}
              {action === 'renegotiate' && (
                <div className="flex flex-[1_1_320px] flex-col gap-1">
                  <Label htmlFor="d-text">{t('dialog.instructions')}</Label>
                  <textarea id="d-text" rows={2} className={textarea} value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} />
                </div>
              )}
            </div>
            <div className="text-[13px] text-ink-muted">{t('dialog.payloadIntro')}</div>
            <dl className="mt-2 mb-4 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
              {[
                [t('dialog.decision'), t(`action.${action}`)],
                [t('dialog.amount'), fit ? money(fit.landed_cost.total) : '—'],
                [t('dialog.offer'), offer.seller_name],
                [t('dialog.band'), t(`band.${deal.price_band}`)],
                [t('dialog.confidence'), t('confLabel', { band: t(`conf.${deal.confidence_band}`), score: conf?.score ?? '—' })],
                [t('dialog.verdict'), t(`verdict.${deal.financial_verdict}`)],
              ].map(([k, v], i) => (
                <div key={i}>
                  <dt className="text-[13px] text-ink-muted">{k}</dt>
                  <dd className="m-0">{v}</dd>
                </div>
              ))}
            </dl>
            <DecisionFooter
              disabledReason={!canCreate ? t('block.role_not_allowed') : body === null ? t('dialog.incomplete') : mutation.isPending ? t('dialog.creating') : undefined}
              busy={mutation.isPending}
              error={mutation.error}
              accepted={mutation.data}
              onCreate={() => body && mutation.mutate({ id: deal.id, body })}
              onClose={() => setAction(null)}
            />
          </DialogContent>
        )}
      </Dialog>
    </>
  )
}
