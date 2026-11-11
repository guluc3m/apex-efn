'use client'

import type { Mission, MissionState } from '@apex/shared-types/contracts'
import { Button, EmptyState, Icon, Select, StatusBadge, Table, type StatusTone, type TableColumn } from '@apex/ui'
import { CircleCheck, CircleX, Inbox, LoaderCircle, Pause, Plus, TriangleAlert, type LucideIcon } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'

import { AppLink, renderLink } from '@/components/app-link'
import { ErrorPanel } from '@/components/error-panel'
import { useMissions } from '@/lib/api'

import { useUrlTable } from './use-url-table'

const ICON: Partial<Record<MissionState, { tone: StatusTone; icon: LucideIcon }>> = {
  completed: { tone: 'ok', icon: CircleCheck },
  cancelled: { tone: 'plano', icon: CircleX },
  failed: { tone: 'plano', icon: TriangleAlert },
}
const RUNNING = { tone: 'neutro', icon: LoaderCircle } as const
const STATES: MissionState[] = ['created', 'planning', 'sourcing', 'enriching', 'evaluating', 'negotiating', 'awaiting_decision', 'completed', 'cancelled', 'failed']

export function MissionsList() {
  const t = useTranslations('missions.list')
  const td = useTranslations('missions.detail.state')
  const { data, error, isPending, refetch } = useMissions()
  const locale = useLocale()
  const url = useUrlTable(['state'])
  const date = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Madrid' })

  if (isPending) return <p className="text-ink-muted" role="status">{t('loading')}</p>
  if (error) return <ErrorPanel kind="error" onRetry={() => void refetch()} />
  const missions = data.items

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

  const columns: TableColumn<Mission>[] = [
    { id: 'id', header: t('cols.mission'), sortValue: (m) => m.id, cell: (m) => m.id },
    {
      id: 'state',
      header: t('cols.state'),
      sortValue: (m) => m.state,
      cell: (m) => {
        const { tone, icon } = m.paused ? { tone: 'plano' as const, icon: Pause } : (ICON[m.state] ?? RUNNING)
        return <StatusBadge tone={tone} icon={icon} label={td(m.state)} />
      },
    },
    { id: 'offers', header: t('cols.offers'), num: true, sortValue: (m) => m.offers_discovered, cell: (m) => m.offers_discovered },
    { id: 'inGate', header: t('cols.inGate'), num: true, sortValue: (m) => m.offers_in_gate, cell: (m) => m.offers_in_gate },
    {
      id: 'launched',
      header: t('cols.launched'),
      sortValue: (m) => m.started_at,
      cell: (m) => <span className="text-ink-muted">{date.format(new Date(m.started_at))}</span>,
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <Select
        className="w-48"
        label={t('filters.state')}
        value={url.value('state')}
        onValueChange={(v) => url.setFilter('state', v)}
        options={[{ value: 'all', label: t('filters.all') }, ...STATES.map((s) => ({ value: s, label: td(s) }))]}
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
