'use client'

import type { Offer, OfferState } from '@apex/shared-types/contracts'
import {
  FinancialVerdictBadge,
  Icon,
  MoneyDisplay,
  PriceBandBadge,
  Select,
  StatusBadge,
  Table,
  type StatusTone,
  type TableColumn,
} from '@apex/ui'
import { ArrowDown, ArrowUp, CircleCheck, CircleDot, CircleStop, MessagesSquare, ShieldAlert, type LucideIcon } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'

import { AppLink, renderLink } from '@/components/app-link'
import { QueryBoundary } from '@/components/query-boundary'
import { OfferConfidence } from '@/components/sellers/offer-confidence'
import { useMissionOffers } from '@/lib/api'

import { useUrlTable } from './use-url-table'

// Display-only tone per API offer state; the state itself is never derived here.
const STATE: Record<OfferState, { tone: StatusTone; icon: LucideIcon }> = {
  discovered: { tone: 'plano', icon: CircleDot },
  enriched: { tone: 'plano', icon: CircleDot },
  trust_scored: { tone: 'plano', icon: CircleDot },
  sanity_checked: { tone: 'plano', icon: CircleDot },
  financially_checked: { tone: 'plano', icon: CircleDot },
  gate_pending: { tone: 'warn', icon: ShieldAlert },
  gate_approved: { tone: 'ok', icon: CircleCheck },
  gate_rejected: { tone: 'bad', icon: CircleStop },
  negotiating: { tone: 'neutro', icon: MessagesSquare },
  negotiated: { tone: 'neutro', icon: MessagesSquare },
  sanity_rechecked: { tone: 'neutro', icon: CircleDot },
  scored: { tone: 'neutro', icon: CircleDot },
  awaiting_human: { tone: 'warn', icon: ShieldAlert },
  signed: { tone: 'ok', icon: CircleCheck },
  approved: { tone: 'ok', icon: CircleCheck },
  rejected: { tone: 'bad', icon: CircleStop },
  purchased: { tone: 'ok', icon: CircleCheck },
}
const STATES = Object.keys(STATE) as OfferState[]
const BANDS = ['normal', 'atypical', 'implausible', 'insufficient_reference'] as const
const VERDICTS = ['within_budget', 'stretch', 'out_of_budget'] as const
// Cada filtro es una columna: su id es también el parámetro de la URL.
const FILTERS = ['status', 'priceBand', 'verdict', 'platform'] as const

export function MissionOffers({ missionId }: { missionId: string }) {
  const query = useMissionOffers(missionId)
  return <QueryBoundary query={query}>{(page) => <OffersMatrix offers={page.items} more={page.next_cursor !== null} />}</QueryBoundary>
}

function OffersMatrix({ offers, more }: { offers: readonly Offer[]; more: boolean }) {
  const t = useTranslations('missions.detail.offers')
  const locale = useLocale()
  const url = useUrlTable(FILTERS)
  const pct = new Intl.NumberFormat(locale, { style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 0 })
  const platforms = [...new Set(offers.map((o) => o.platform))].sort()
  const none = <span className="text-ink-muted">{t('pending')}</span>

  const columns: TableColumn<Offer>[] = [
    { id: 'seller', header: t('cols.seller'), sortValue: (o) => o.seller_name, cell: (o) => <span className="whitespace-nowrap">{o.seller_name}</span> },
    { id: 'platform', header: t('cols.platform'), sortValue: (o) => o.platform, cell: (o) => <span className="whitespace-nowrap text-ink-muted">{o.platform}</span> },
    {
      id: 'price',
      header: t('cols.price'),
      num: true,
      sortValue: (o) => o.unit_price.amount_minor,
      cell: (o) => {
        const dev = o.price_sanity_check?.relative_deviation
        return (
          <span className="inline-flex items-center justify-end gap-2">
            <strong className="font-semibold">
              <MoneyDisplay amountMinor={o.unit_price.amount_minor} currency={o.unit_price.currency} locale={locale} />
            </strong>
            {dev !== undefined && dev !== 0 && (
              <span className={`inline-flex items-center gap-0.5 text-[13px] ${dev > 0 ? 'text-bad' : 'text-good'}`}>
                <Icon icon={dev > 0 ? ArrowUp : ArrowDown} label={t(dev > 0 ? 'above' : 'below')} />
                {pct.format(dev)}
              </span>
            )}
          </span>
        )
      },
    },
    {
      id: 'priceBand',
      header: t('cols.band'),
      sortValue: (o) => o.price_sanity_check?.band ?? '',
      cell: (o) => (o.price_sanity_check ? <PriceBandBadge band={o.price_sanity_check.band} label={t(`band.${o.price_sanity_check.band}`)} /> : none),
    },
    {
      id: 'confidence',
      header: t('cols.confidence'),
      sortValue: (o) => o.seller_confidence?.score ?? -1,
      cell: (o) => <OfferConfidence confidence={o.seller_confidence} />,
    },
    {
      id: 'verdict',
      header: t('cols.verdict'),
      sortValue: (o) => o.financial_fit?.verdict ?? '',
      cell: (o) => (o.financial_fit ? <FinancialVerdictBadge verdict={o.financial_fit.verdict} label={t(`verdict.${o.financial_fit.verdict}`)} /> : none),
    },
    {
      id: 'status',
      header: t('cols.status'),
      sortValue: (o) => o.state,
      cell: (o) => <StatusBadge tone={STATE[o.state].tone} icon={STATE[o.state].icon} label={t(`status.${o.state}`)} />,
    },
    {
      id: 'negotiation',
      header: t('cols.negotiation'),
      cell: (o) =>
        o.negotiation_id ? (
          <AppLink
            className="whitespace-nowrap text-accent underline-offset-4 hover:underline"
            href={`/misiones/${o.mission_id}/negociaciones/${o.negotiation_id}`}
          >
            {t('open')}
          </AppLink>
        ) : (
          none
        ),
    },
    {
      id: 'landed',
      header: t('cols.landed'),
      num: true,
      sortValue: (o) => o.financial_fit?.landed_cost.total.amount_minor ?? -1,
      cell: (o) =>
        o.financial_fit ? (
          <MoneyDisplay amountMinor={o.financial_fit.landed_cost.total.amount_minor} currency={o.financial_fit.landed_cost.total.currency} locale={locale} />
        ) : (
          none
        ),
    },
  ]

  const select = (id: (typeof FILTERS)[number], label: string, values: readonly string[], key: string | null) => (
    <Select
      key={id}
      className="w-44"
      label={label}
      value={url.value(id)}
      onValueChange={(v) => url.setFilter(id, v)}
      options={[{ value: 'all', label: t('filters.all') }, ...values.map((v) => ({ value: v, label: key ? t(`${key}.${v}`) : v }))]}
    />
  )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2">
        {select('status', t('filters.status'), STATES, 'status')}
        {select('priceBand', t('filters.band'), BANDS, 'band')}
        {select('verdict', t('filters.verdict'), VERDICTS, 'verdict')}
        {select('platform', t('filters.platform'), platforms, null)}
      </div>
      <Table
        caption={t('caption')}
        empty={t('empty')}
        columns={columns}
        rows={[...offers]}
        getRowId={(o) => o.id}
        getHref={(o) => `/decisiones/${o.id}`}
        renderLink={renderLink}
        sorting={url.sorting}
        onSortingChange={url.onSortingChange}
        columnFilters={url.columnFilters}
        onColumnFiltersChange={url.onColumnFiltersChange}
      />
      <p className="text-[13px] text-ink-muted">{t('footer', { shown: offers.length })}</p>
      {more && <p className="text-[13px] text-ink-muted">{t('more')}</p>}
    </div>
  )
}
