'use client'

import {
  Button, Dialog, DialogClose, DialogContent, Icon, Input, Label, MoneyDisplay, Select,
} from '@apex/ui'
import {
  ArrowDown, ChartBarStacked, Flag, Gauge, Hand, MessagesSquare, Package, Pause, PenLine, Receipt, Shield, Trash2, Upload, X,
  type LucideIcon,
} from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { useState, type ReactNode } from 'react'

import { AppLink } from '@/components/app-link'
import { discardReasons, type ActionKey, type Deal, type Profile } from '@/fixtures/decisions'

import { DealBadges } from './deal-badges'

const ACTION_ICON: Record<ActionKey, LucideIcon> = {
  follow: PenLine, renegotiate: MessagesSquare, takeover: Hand, hold: Pause, discard: Trash2,
  unblock: PenLine, override_discard: PenLine, sign2: PenLine,
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

export function DealDetail({ deal, profile }: { deal: Deal; profile: Profile }) {
  const t = useTranslations('decisions')
  const locale = useLocale()
  const [action, setAction] = useState<ActionKey | null>(null)
  const eur = (amountMinor: number) => <MoneyDisplay amountMinor={amountMinor} currency="EUR" locale={locale} />
  const sg = deal.signals

  if (deal.tenant) {
    return (
      <div className="px-6 py-6">
        <div className="text-[13px] text-ink-muted">{t(`cause.${deal.cause}`)} · {t('sla', { time: deal.sla ?? '' })}</div>
        <h1 className="my-1 mb-4 text-[22px] font-semibold tracking-tight">{deal.title}</h1>
        <p className="mb-2">{t('stale.body')}</p>
        <Button variant="pri" asChild>
          <AppLink href="/empresa/finanzas">
            <Icon icon={Upload} />
            {t('stale.cta')}
          </AppLink>
        </Button>
      </div>
    )
  }

  const confBreakdown = sg && (
    <div className="text-[13px]">
      <Row k={t('signal.age')}>{t('signal.ageV', { n: sg.ageDays })}</Row>
      <Row k={t('signal.sales')}>{t('signal.salesV', { n: sg.sales, pct: sg.repeatPct })}</Row>
      <Row k={t('signal.catalog')}>{t('signal.catalogV', { n: sg.products, pct: sg.listingPct })}</Row>
      <Row k={t('signal.reviews')}>{t('signal.reviewsV', { rating: sg.rating, n: sg.reviews, pct: sg.verifiedPct })}</Row>
      <Row k={t('signal.institutional')}>{t('signal.institutionalV', { kyc: String(sg.kyc), escrow: String(sg.escrow), pct: sg.disputesPct })}</Row>
    </div>
  )

  return (
    <>
      <div className="sticky top-0 z-1 border-b border-line bg-bg p-6">
        <div className="text-[13px] text-ink-muted">
          {t(`cause.${deal.cause}`)}
          {deal.sla && ` · ${t('sla', { time: deal.sla })}`}
        </div>
        <h1 className="my-1 mb-4 text-[22px] leading-tight font-semibold tracking-tight text-balance">{deal.title}</h1>
        <div className="flex flex-wrap items-start gap-4">
          <div className="box-border flex flex-[2_1_320px] flex-wrap gap-10 border border-line bg-panel px-6 py-5">
            <div>
              <div className="text-[13px] text-ink-muted">{t(deal.initialMinor === deal.unitMinor ? 'detail.priceInitial' : 'detail.priceNegotiated')}</div>
              <div className="my-1 flex items-baseline gap-1">
                {eur(deal.unitMinor ?? 0)}
                <span className="text-[13px] text-ink-muted">{t('perUnit')}</span>
              </div>
              <div className="flex flex-wrap items-center gap-x-1.5 text-[13px] text-ink-muted">
                {deal.deltaPct ? (
                  <>
                    {t('detail.initial')} {eur(deal.initialMinor ?? 0)} ·
                    <span className="inline-flex items-center gap-0.5 text-accent">
                      <Icon icon={ArrowDown} />−{deal.deltaPct} %
                    </span>
                  </>
                ) : (
                  t('detail.notNegotiated')
                )}
              </div>
            </div>
            <div>
              <div className="text-[13px] text-ink-muted">{t('detail.confidence')}</div>
              <div className="my-1 text-[40px] leading-[1.1] font-semibold tracking-tight tabular-nums">{deal.score}</div>
            </div>
          </div>
          <div className="flex flex-[1_1_200px] flex-col gap-2.5 pt-5">
            <div>
              <span className="text-[13px] text-ink-muted">{t('detail.landed')} </span>
              <strong>{eur(deal.totalMinor ?? 0)}</strong>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <DealBadges deal={deal} confidenceBreakdown={confBreakdown} />
            </div>
            <div className="text-[13px] text-ink-muted">
              {deal.seller} · {deal.platform} · {t('detail.expires', { n: deal.expiresDays ?? 0 })}
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {deal.actions.map((a, n) => (
            <Button
              key={a.key}
              variant={n === 0 && !a.reason ? 'pri' : 'sec'}
              disabledReason={a.reason ? t(`reason.${a.reason}`) : undefined}
              onClick={() => setAction(a.key)}
            >
              <Icon icon={ACTION_ICON[a.key]} />
              {t(`action.${a.key}`)}
              {a.passkey && ` (${t('passkey')})`}
            </Button>
          ))}
        </div>
        <ul className="mt-1.5 list-none p-0 text-[13px] text-ink-muted">
          {deal.actions.filter((a) => a.reason).map((a) => (
            <li key={a.key}>
              <strong>{t(`action.${a.key}`)}:</strong> {t(`reason.${a.reason}`)}
            </li>
          ))}
        </ul>
      </div>

      <div className="px-6 pt-2 pb-12">
        {deal.transcript ? (
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
          {confBreakdown}
        </Section>
        <Section icon={Gauge} title={t('detail.sanity')}>
          <p className="mb-2">{t(`sanity.${deal.sanity}`)}</p>
          {/* //todo_#148: gráfica de distribución de precios con la banda marcada (datos de GET /v1/missions/{id}/offers) */}
          <div className="flex h-24 items-center justify-center border border-line bg-bg text-[13px] text-ink-muted">{t('detail.chartPending')}</div>
        </Section>
        <Section icon={Receipt} title={t('detail.landedBreakdown')}>
          <Row k={t('detail.priceQty')}>{eur(deal.subtotalMinor ?? 0)}</Row>
          {deal.lines?.map((l) => (
            <Row key={l.key} k={t(`line.${l.key}`)}>{eur(l.minor)}</Row>
          ))}
          <div className="flex justify-between border-t border-line pt-1.5">
            <strong>{t('detail.total')}</strong>
            <strong>{eur(deal.totalMinor ?? 0)}</strong>
          </div>
        </Section>
        <Section icon={ChartBarStacked} title={t('detail.contribution')}>
          {deal.contrib ? (
            deal.contrib[profile].map((c) => (
              <div key={c.key} className="flex items-center gap-2 py-0.5">
                <span className="flex-none basis-44 text-[13px] text-ink-muted">{t(`criterion.${c.key}`)}</span>
                <div className="h-1.5 flex-1 overflow-hidden bg-raised" aria-hidden="true">
                  <div className="h-1.5 bg-accent" style={{ width: `${c.pct}%` }} />
                </div>
                <span className="tabular-nums">{(c.value / 100).toFixed(2)}</span>
              </div>
            ))
          ) : (
            <p className="text-[13px] text-ink-muted">{t('detail.unscored')}</p>
          )}
        </Section>
        <Section icon={Flag} title={t('detail.risks')}>
          {deal.risk?.length ? deal.risk.map((r) => <div key={r}>{t(`risk.${r}`)}</div>) : <div>{t('risk.none')}</div>}
        </Section>
        <Section icon={Package} title={t('detail.terms')}>
          {/* //todo_#148: especificación, plazo de entrega y condiciones de pago de la oferta */}
          <p className="text-[13px] text-ink-muted">{t('detail.termsPending')}</p>
        </Section>
      </div>

      <Dialog open={action !== null} onOpenChange={(o) => !o && setAction(null)}>
        {action && (
          <DialogContent title={t(`action.${action}`)} closeLabel={t('dialog.close')}>
            <div className="my-2 flex flex-wrap gap-3">
              {action === 'discard' && (
                <>
                  <Select label={t('dialog.reasonCode')} options={discardReasons.map((v) => ({ value: v, label: t(`discardReason.${v}`) }))} placeholder={t('dialog.choose')} />
                  <div className="flex flex-[1_1_240px] flex-col gap-1">
                    <Label htmlFor="d-comment">{t('dialog.commentRequired')}</Label>
                    <textarea id="d-comment" rows={2} className={textarea} />
                  </div>
                </>
              )}
              {action === 'hold' && (
                <div className="flex flex-col gap-1">
                  <Label htmlFor="d-date">{t('dialog.reviewDate')}</Label>
                  <Input id="d-date" type="date" />
                </div>
              )}
              {(action === 'renegotiate' || action === 'override_discard') && (
                <div className="flex flex-[1_1_320px] flex-col gap-1">
                  <Label htmlFor="d-text">{t(action === 'renegotiate' ? 'dialog.instructions' : 'dialog.overrideReason')}</Label>
                  <textarea id="d-text" rows={2} className={textarea} />
                </div>
              )}
            </div>
            <div className="text-[13px] text-ink-muted">{t('dialog.payloadIntro')}</div>
            <dl className="mt-2 mb-4 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
              {[
                [t('dialog.decision'), t(`action.${action}`)],
                [t('dialog.amount'), eur(deal.totalMinor ?? 0)],
                [t('dialog.offer'), deal.seller],
                [t('dialog.band'), deal.band && t(`band.${deal.band}`)],
                [t('dialog.confidence'), deal.conf && t('confLabel', { band: t(`conf.${deal.conf}`), score: deal.score ?? 0 })],
                [t('dialog.verdict'), deal.verdict && t(`verdict.${deal.verdict}`)],
              ].map(([k, v], i) => (
                <div key={i}>
                  <dt className="text-[13px] text-ink-muted">{k}</dt>
                  <dd className="m-0">{v}</dd>
                </div>
              ))}
            </dl>
            {deal.actions.find((a) => a.key === action)?.passkey && <p className="mb-3 text-ink-soft">{t('dialog.passkeyNote')}</p>}
            {/* //todo_#162: firmar la decisión (POST /v1/decisions + sign) y //todo_#151: reautenticación con passkey. Nunca simular firma. */}
            <div className="flex gap-2">
              <Button variant="pri" disabledReason={t('pending')}>
                <Icon icon={PenLine} />
                {t('dialog.sign')}
              </Button>
              <DialogClose asChild>
                <Button>
                  <Icon icon={X} />
                  {t('dialog.cancel')}
                </Button>
              </DialogClose>
            </div>
          </DialogContent>
        )}
      </Dialog>
    </>
  )
}
