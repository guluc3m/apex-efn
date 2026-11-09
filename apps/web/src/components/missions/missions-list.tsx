'use client'

import { Button, EmptyState, Icon, Select, StatusBadge, Table, type StatusTone, type TableColumn } from '@apex/ui'
import { CircleCheck, CircleX, Inbox, LoaderCircle, Plus, Scale, type LucideIcon } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'

import { AppLink, renderLink } from '@/components/app-link'
import type { MissionRow, MissionState } from '@/fixtures/missions'

import { useUrlTable } from './use-url-table'

const STATE: Record<MissionState, { tone: StatusTone; icon: LucideIcon }> = {
  running: { tone: 'neutro', icon: LoaderCircle },
  valuation: { tone: 'neutro', icon: Scale },
  closed: { tone: 'ok', icon: CircleCheck },
  cancelled: { tone: 'plano', icon: CircleX },
}
const STATES = Object.keys(STATE) as MissionState[]

export function MissionsList({ missions }: { missions: MissionRow[] }) {
  const t = useTranslations('missions.list')
  const locale = useLocale()
  const url = useUrlTable(['state'])
  const date = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Madrid' })

  if (missions.length === 0) {
    return (
      <EmptyState
        icon={Inbox}
        title={t('emptyTitle')}
        description={t('emptyBody')}
        actions={
          <Button variant="pri" asChild>
            <AppLink href="/misiones/nueva">
              <Icon icon={Plus} />
              {t('new')}
            </AppLink>
          </Button>
        }
      />
    )
  }

  const columns: TableColumn<MissionRow>[] = [
    {
      id: 'title',
      header: t('cols.mission'),
      sortValue: (m) => m.title,
      cell: (m) => (
        <span className="inline-flex flex-wrap items-baseline gap-2">
          {m.title}
          <span className="text-[13px] font-normal text-ink-muted">{m.id}</span>
        </span>
      ),
    },
    {
      id: 'state',
      header: t('cols.state'),
      sortValue: (m) => m.state,
      cell: (m) => <StatusBadge tone={STATE[m.state].tone} icon={STATE[m.state].icon} label={t(`state.${m.state}`)} />,
    },
    { id: 'phase', header: t('cols.phase'), sortValue: (m) => m.phase, cell: (m) => t(`phase.${m.phase}`) },
    { id: 'offers', header: t('cols.offers'), num: true, sortValue: (m) => m.offers, cell: (m) => m.offers },
    { id: 'finalists', header: t('cols.finalists'), num: true, sortValue: (m) => m.finalists, cell: (m) => m.finalists },
    {
      id: 'launched',
      header: t('cols.launched'),
      sortValue: (m) => m.launchedAt,
      cell: (m) => <span className="text-ink-muted">{date.format(new Date(m.launchedAt))}</span>,
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <Select
        className="w-48"
        label={t('filters.state')}
        value={url.value('state')}
        onValueChange={(v) => url.setFilter('state', v)}
        options={[{ value: 'all', label: t('filters.all') }, ...STATES.map((s) => ({ value: s, label: t(`state.${s}`) }))]}
      />
      <Table
        caption={t('caption')}
        empty={t('noMatch')}
        columns={columns}
        rows={missions}
        getRowId={(m) => m.id}
        getHref={(m) => `/misiones/${m.id}`}
        renderLink={renderLink}
        sorting={url.sorting}
        onSortingChange={url.onSortingChange}
        columnFilters={url.columnFilters}
        onColumnFiltersChange={url.onColumnFiltersChange}
      />
    </div>
  )
}
