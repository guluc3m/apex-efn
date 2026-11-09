'use client'

import {
  ConfidenceBandBadge,
  FinancialVerdictBadge,
  Icon,
  MoneyDisplay,
  PriceBandBadge,
  Select,
  SignatureStatusBadge,
  StatusBadge,
  Table,
  type StatusTone,
  type TableColumn,
} from '@apex/ui'
import { ArrowDown, ArrowUp, CircleStop, MessageSquareDot, MessagesSquare, ShieldAlert, Filter, type LucideIcon } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'

import { renderLink } from '@/components/app-link'
import type { OfferRow } from '@/fixtures/missions'

import { useUrlTable } from './use-url-table'

type Status = OfferRow['status']['kind']
const STATUS: Record<Status, { tone: StatusTone; icon: LucideIcon }> = {
  awaiting_approval: { tone: 'warn', icon: MessageSquareDot },
  negotiating: { tone: 'neutro', icon: MessagesSquare },
  aborted: { tone: 'bad', icon: CircleStop },
  gate_low_confidence: { tone: 'warn', icon: ShieldAlert },
  filtered_implausible: { tone: 'plano', icon: Filter },
}
const STATUSES = Object.keys(STATUS) as Status[]
const BANDS = ['normal', 'atypical', 'implausible', 'insufficient_reference'] as const
const VERDICTS = ['within_budget', 'stretch', 'out_of_budget'] as const
const PLATFORMS = ['p1', 'p2'] as const
// Cada filtro es una columna: su id es también el parámetro de la URL.
const FILTERS = ['status', 'priceBand', 'verdict', 'platform'] as const

export function MissionOffers({ offers, total }: { offers: readonly OfferRow[]; total: number }) {
  const t = useTranslations('missions.detail.offers')
  const locale = useLocale()
  const url = useUrlTable(FILTERS)
  const pct = new Intl.NumberFormat(locale, { style: 'percent', signDisplay: 'exceptZero' })

  const columns: TableColumn<OfferRow>[] = [
    { id: 'seller', header: t('cols.seller'), sortValue: (o) => o.seller, cell: (o) => <span className="whitespace-nowrap">{o.seller}</span> },
    { id: 'platform', header: t('cols.platform'), sortValue: (o) => o.platform, cell: (o) => <span className="whitespace-nowrap text-ink-muted">{t(`platform.${o.platform}`)}</span> },
    {
      id: 'price',
      header: t('cols.price'),
      num: true,
      sortValue: (o) => o.priceMinor,
      cell: (o) => (
        <span className="inline-flex items-center justify-end gap-2">
          <strong className="font-semibold">
            <MoneyDisplay amountMinor={o.priceMinor} currency="EUR" locale={locale} />
          </strong>
          {o.deltaPct !== 0 && (
            <span className={`inline-flex items-center gap-0.5 text-[13px] ${o.deltaPct > 0 ? 'text-bad' : 'text-good'}`}>
              <Icon icon={o.deltaPct > 0 ? ArrowUp : ArrowDown} />
              {pct.format(o.deltaPct / 100)}
            </span>
          )}
        </span>
      ),
    },
    { id: 'priceBand', header: t('cols.band'), sortValue: (o) => o.priceBand, cell: (o) => <PriceBandBadge band={o.priceBand} label={t(`band.${o.priceBand}`)} /> },
    {
      id: 'confidence',
      header: t('cols.confidence'),
      sortValue: (o) => o.confidence.score,
      cell: (o) => <ConfidenceBandBadge band={o.confidence.band} label={t(`confidence.${o.confidence.band}`, { score: o.confidence.score })} />,
    },
    { id: 'verdict', header: t('cols.verdict'), sortValue: (o) => o.verdict, cell: (o) => <FinancialVerdictBadge verdict={o.verdict} label={t(`verdict.${o.verdict}`)} /> },
    { id: 'signature', header: t('cols.signature'), sortable: false, cell: (o) => <SignatureStatusBadge status={o.signature} label={t(`signature.${o.signature}`)} /> },
    {
      id: 'status',
      header: t('cols.status'),
      sortValue: (o) => o.status.kind,
      cell: (o) => <StatusBadge tone={STATUS[o.status.kind].tone} icon={STATUS[o.status.kind].icon} label={t(`status.${o.status.kind}`, { round: o.status.round ?? 0 })} />,
    },
    {
      id: 'landed',
      header: t('cols.landed'),
      num: true,
      sortValue: (o) => o.landedMinor,
      cell: (o) => <MoneyDisplay amountMinor={o.landedMinor} currency="EUR" locale={locale} />,
    },
  ]

  const select = (id: (typeof FILTERS)[number], label: string, values: readonly string[], key: string) => (
    <Select
      key={id}
      className="w-44"
      label={label}
      value={url.value(id)}
      onValueChange={(v) => url.setFilter(id, v)}
      options={[{ value: 'all', label: t('filters.all') }, ...values.map((v) => ({ value: v, label: t(`${key}.${v}`, { round: '–' }) }))]}
    />
  )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2">
        {select('status', t('filters.status'), STATUSES, 'status')}
        {select('priceBand', t('filters.band'), BANDS, 'band')}
        {select('verdict', t('filters.verdict'), VERDICTS, 'verdict')}
        {select('platform', t('filters.platform'), PLATFORMS, 'platform')}
      </div>
      <Table
        caption={t('caption')}
        empty={t('empty')}
        columns={columns}
        rows={[...offers]}
        getRowId={(o) => o.id}
        getHref={(o) => o.href}
        renderLink={renderLink}
        sorting={url.sorting}
        onSortingChange={url.onSortingChange}
        columnFilters={url.columnFilters}
        onColumnFiltersChange={url.onColumnFiltersChange}
      />
      <p className="text-[13px] text-ink-muted">{t('footer', { shown: offers.length, total })}</p>
    </div>
  )
}
