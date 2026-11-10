'use client'

import type { Offer, Recommendation } from '@apex/shared-types/contracts'
import { Button, EmptyState, FinancialVerdictBadge, Icon, Input, Label, MoneyDisplay, PriceBandBadge } from '@apex/ui'
import { ArrowDown, ArrowLeft, ArrowUp, Download, PiggyBank, Scale, SlidersHorizontal } from 'lucide-react'
import { useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'

import { AppLink } from '@/components/app-link'
import { QueryBoundary } from '@/components/query-boundary'
import { OfferConfidence } from '@/components/sellers/offer-confidence'
import { useMissionOffers, useMissionRecommendation } from '@/lib/api'
import { buildCompareModel } from '@/lib/compare'

import { PriceDistribution } from './price-distribution'
import { ScoreChart } from './score-chart'

export function CompareView({ missionId }: { missionId: string }) {
  const t = useTranslations('compare')
  const profile = useSearchParams().get('profile')?.trim() || undefined
  const offers = useMissionOffers(missionId)
  const rec = useMissionRecommendation(missionId, profile)

  return (
    <main id="contenido" className="flex flex-col">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line px-(--gutter-page) py-6">
        <div className="flex flex-col gap-1">
          <AppLink href={`/misiones/${missionId}`} className="inline-flex items-center gap-1 text-ink-soft">
            <Icon icon={ArrowLeft} label="" /> {t('back')}
          </AppLink>
          <div className="text-[13px] text-ink-muted">{t('context', { code: missionId })}</div>
        </div>
        {/* Plain GET form: the profile lives in the URL, so the comparison can be shared and re-ranks in place. */}
        <form method="get" className="flex items-end gap-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="profile">{t('profile')}</Label>
            <Input id="profile" name="profile" defaultValue={profile ?? ''} key={profile ?? ''} className="w-56" />
          </div>
          <Button type="submit" variant="sec">
            <Icon icon={SlidersHorizontal} label="" /> {t('applyProfile')}
          </Button>
        </form>
      </header>

      <div className="flex flex-col gap-8 px-(--gutter-page) py-6">
        {!profile ? (
          <EmptyState icon={SlidersHorizontal} title={t('noProfile.title')} description={t('noProfile.body')} />
        ) : (
          <QueryBoundary query={offers}>
            {(page) => <QueryBoundary query={rec}>{(r) => <Comparison rec={r} offers={page.items} />}</QueryBoundary>}
          </QueryBoundary>
        )}
      </div>
    </main>
  )
}

function Comparison({ rec, offers }: { rec: Recommendation; offers: readonly Offer[] }) {
  const t = useTranslations('compare')
  const locale = useLocale()
  const score = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const pct = new Intl.NumberFormat(locale, { style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 0 })
  const { rows, missing } = buildCompareModel(rec, offers)
  const first = rows[0]
  const nameOf = (id: string) => offers.find((o) => o.id === id)?.seller_name ?? id
  const th = 'border-b border-line px-3 py-2 text-left font-normal text-ink-muted'
  const td = 'border-b border-line px-3 py-2 align-top'
  const dash = <span className="text-ink-muted">—</span>
  const money = (m: { amount_minor: number; currency: 'EUR' | 'USD' | 'CNY' } | null) =>
    m ? <MoneyDisplay amountMinor={m.amount_minor} currency={m.currency} locale={locale} /> : dash

  if (!first)
    return (
      <>
        <EmptyState icon={Scale} title={t('empty.title')} description={t('empty.body')} />
        <Excluded rec={rec} nameOf={nameOf} />
      </>
    )

  return (
    <>
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="m-0 text-xl font-semibold">{t('headline', { name: first.offer.seller_name })}</h1>
          {first.ranked.narrative && <p className="m-0 text-ink-soft">{first.ranked.narrative}</p>}
          <p className="m-0 text-[13px] text-ink-muted">{t('versions', { config: rec.config_version, model: rec.model_version })}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* //todo_#164: exportar la comparativa cuando exista el endpoint */}
          <Button variant="sec" disabledReason={t('pending')}>
            <Icon icon={Download} label="" /> {t('export')}
          </Button>
          {/* //todo_#164: decidir (decisión firmada) cuando exista el backend */}
          <Button variant="pri" disabledReason={t('pending')}>
            <Icon icon={Scale} label="" /> {t('decide', { name: first.offer.seller_name })}
          </Button>
        </div>
      </section>

      <table className="w-full table-fixed border-collapse">
        <caption className="sr-only">{t('tableCaption')}</caption>
        <thead>
          <tr>
            <th scope="col" className={th}>{t('rows.criterion')}</th>
            {rows.map((r) => (
              <th key={r.offer.id} scope="col" className={th}>
                <AppLink href={`/decisiones/${r.offer.id}`} className="text-ink underline">{r.offer.seller_name}</AppLink> · {t('rank', { n: r.rank })}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row" className={th}>{t('rows.price')}</th>
            {rows.map(({ offer: o }) => {
              const dev = o.price_sanity_check?.relative_deviation
              return (
                <td key={o.id} className={td}>
                  <strong className="font-semibold">{money(o.unit_price)}</strong>{' '}
                  {dev !== undefined && dev !== 0 && (
                    <span className={dev < 0 ? 'inline-flex items-center text-good' : 'inline-flex items-center text-bad'}>
                      <Icon icon={dev < 0 ? ArrowDown : ArrowUp} label={t(dev < 0 ? 'delta.down' : 'delta.up')} />
                      {pct.format(dev)}
                    </span>
                  )}
                </td>
              )
            })}
          </tr>
          <tr>
            <th scope="row" className={th}>{t('rows.band')}</th>
            {rows.map(({ offer: o }) => (
              <td key={o.id} className={td}>
                {o.price_sanity_check ? <PriceBandBadge band={o.price_sanity_check.band} label={t(`price.${o.price_sanity_check.band}`)} /> : dash}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className={th}>{t('rows.confidence')}</th>
            {rows.map(({ offer: o }) => <td key={o.id} className={td}><OfferConfidence confidence={o.seller_confidence} /></td>)}
          </tr>
          <tr>
            <th scope="row" className={th}>{t('rows.verdict')}</th>
            {rows.map(({ offer: o }) => (
              <td key={o.id} className={td}>
                {o.financial_fit ? <FinancialVerdictBadge verdict={o.financial_fit.verdict} label={t(`verdict.${o.financial_fit.verdict}`)} /> : dash}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className={th}>{t('rows.landed')}</th>
            {rows.map(({ offer: o }) => <td key={o.id} className={td}>{money(o.financial_fit?.landed_cost.total ?? null)}</td>)}
          </tr>
          <tr>
            <th scope="row" className={th}>{t('rows.lead')}</th>
            {rows.map(({ offer: o }) => (
              <td key={o.id} className={td}>{o.lead_time_days === null || o.lead_time_days === undefined ? dash : t('days', { n: o.lead_time_days })}</td>
            ))}
          </tr>
          <tr>
            <th scope="row" className={th}>{t('rows.score')}</th>
            {rows.map((r) => <td key={r.offer.id} className={td}>{score.format(r.ranked.score)}</td>)}
          </tr>
          <tr>
            <th scope="row" className={th}>{t('rows.vsFirst')}</th>
            {rows.map((r) => <td key={r.offer.id} className={td}>{r.vsFirst ?? dash}</td>)}
          </tr>
        </tbody>
      </table>
      <p className="m-0 text-[13px] text-ink-muted">{t('deltaNote')}</p>
      {missing.length > 0 && <p className="m-0 text-[13px] text-ink-muted" role="status">{t('missing', { n: missing.length })}</p>}

      <div className="flex flex-wrap gap-8">
        <div className="min-w-0 flex-[2_1_560px]">
          <ScoreChart rows={rows.map((r) => ({ name: r.offer.seller_name, ranked: r.ranked }))} />
        </div>
        <section className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
          <h2 className="m-0 inline-flex items-center gap-2 text-base font-semibold"><Icon icon={PiggyBank} label="" /> {t('savings.title')}</h2>
          <dl className="m-0 flex flex-col gap-4">
            <div>
              <dt className="text-[13px] text-ink-muted">{t('savings.list')}</dt>
              <dd className="m-0 text-xl">{money(rec.savings.vs_list_price)}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-ink-muted">{t('savings.median')}</dt>
              <dd className="m-0 text-xl">{money(rec.savings.vs_market_median)}</dd>
            </div>
          </dl>
        </section>
      </div>

      <PriceDistribution offers={offers} />
      <Excluded rec={rec} nameOf={nameOf} />
    </>
  )
}

function Excluded({ rec, nameOf }: { rec: Recommendation; nameOf: (id: string) => string }) {
  const t = useTranslations('compare')
  if (rec.excluded.length === 0) return null
  return (
    <section className="flex flex-col gap-2">
      <h2 className="m-0 text-base font-semibold">{t('excluded.title')}</h2>
      <ul className="m-0 flex flex-col gap-1 pl-4">
        {rec.excluded.map((e) => (
          <li key={e.offer_id}>
            <strong className="font-semibold">{nameOf(e.offer_id)}</strong>: {e.reasons.join('; ')}
          </li>
        ))}
      </ul>
    </section>
  )
}
