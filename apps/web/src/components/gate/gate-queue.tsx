'use client'

import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DisabledReason,
  Progress,
  Select,
  Table,
  type TableColumn,
} from '@apex/ui'
import { CircleHelp, Clock, ShieldQuestion } from 'lucide-react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useState } from 'react'

import { renderLink } from '@/components/app-link'
import type { GateAction, GateCause, GateItem } from '@/fixtures/gate'

const CAUSES: GateCause[] = ['negotiator', 'price', 'confidence', 'second_signature', 'high_amount', 'discard', 'company']
// //todo_#147: el rol saldrá de la sesión real
const OVERRIDE_ROLES: readonly string[] = ['finance', 'admin', 'owner']

export function GateQueue({ items, role }: { items: GateItem[]; role: string }) {
  const t = useTranslations('gate')
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const [dialog, setDialog] = useState<{ action: GateAction; item: GateItem } | null>(null)

  const cause = params.get('causa') ?? 'all'
  const mine = params.get('responsable') === 'yo'
  const today = params.get('hoy') === '1'

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params.toString())
    if (v) next.set(k, v)
    else next.delete(k)
    const qs = next.toString()
    router.replace(`${pathname}${qs ? `?${qs}` : ''}` as never, { scroll: false })
  }

  const rows = items.filter((r) => (cause === 'all' || r.cause === cause) && (!mine || r.mine) && (!today || r.dueToday))
  const canOverride = OVERRIDE_ROLES.includes(role)

  const columns: TableColumn<GateItem>[] = [
    {
      id: 'item',
      header: t('cols.item'),
      sortValue: (r) => r.title,
      cell: (r) => (
        <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
          <span>{r.title}</span>
          {r.sub && <span className="font-normal text-ink-muted">· {r.sub}</span>}
          {r.flag && (
            <Badge tone="plano" icon={r.flag === 'no_reference' ? CircleHelp : ShieldQuestion}>
              {t(`flags.${r.flag}`)}
            </Badge>
          )}
        </span>
      ),
    },
    { id: 'cause', header: t('cols.cause'), sortValue: (r) => t(`causes.${r.cause}`), cell: (r) => t(`causes.${r.cause}`) },
    { id: 'amount', header: t('cols.amount'), num: true, sortValue: (r) => r.amountMinor ?? -1, cell: (r) => r.amount ?? '—' },
    {
      id: 'sla',
      header: t('cols.sla'),
      num: true,
      sortValue: (r) => r.slaMinutes,
      cell: (r) =>
        r.slaTone ? (
          <span className="ml-auto flex w-fit flex-col items-end gap-1">
            <Badge tone={r.slaTone} icon={Clock}>
              {r.sla} · {t(`slaSoon.${r.slaTone}`)}
            </Badge>
            <Progress tone={r.slaTone} value={r.slaPct ?? 0} className="w-30" aria-label={t('slaBar')} />
          </span>
        ) : (
          r.sla
        ),
    },
    { id: 'assignee', header: t('cols.assignee'), sortValue: (r) => r.assignee, cell: (r) => <span className="text-ink-muted">{t(`assignee.${r.assignee}`)}</span> },
    { id: 'reminder', header: t('cols.reminder'), sortable: false, cell: (r) => <span className="text-ink-muted">{r.reminderAt ? t('reminderSent', { time: r.reminderAt }) : '—'}</span> },
    {
      id: 'actions',
      header: t('cols.actions'),
      hidden: true,
      cell: (r) => (
        <span className="inline-flex gap-2">
          {r.actions
            .filter((a) => a !== 'override_discard' || canOverride)
            .map((a) => (
              <Button key={a} variant="sec" size="sm" onClick={() => setDialog({ action: a, item: r })}>
                {t(`actions.${a}`)}
              </Button>
            ))}
        </span>
      ),
    },
  ]

  return (
    <main id="contenido">
      <div className="flex flex-wrap items-center justify-between gap-4 px-(--gutter-page) py-6">
        <div>
          <h1 className="m-0 text-[22px] font-semibold">{t('title', { count: items.length })}</h1>
          <p className="mt-1.5 mb-0 text-ink-soft">{t('subtitle')}</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <Select
            label={t('filters.cause')}
            value={cause}
            onValueChange={(v) => set('causa', v === 'all' ? null : v)}
            options={[{ value: 'all', label: t('filters.all') }, ...CAUSES.map((c) => ({ value: c, label: t(`causes.${c}`) }))]}
          />
          <Select
            label={t('filters.assignee')}
            value={mine ? 'yo' : 'all'}
            onValueChange={(v) => set('responsable', v === 'yo' ? 'yo' : null)}
            options={[
              { value: 'all', label: t('filters.all') },
              { value: 'yo', label: t('filters.me') },
            ]}
          />
          <label className="flex min-h-9 items-center gap-2">
            <input type="checkbox" checked={today} onChange={(e) => set('hoy', e.target.checked ? '1' : null)} />
            {t('filters.today')}
          </label>
        </div>
      </div>
      <div className="px-(--gutter-page) pb-10">
        <p className="mb-2 text-ink-muted">{t('order')}</p>
        <Table
          columns={columns}
          rows={rows}
          getRowId={(r) => r.id}
          getHref={(r) => `/decisiones/${r.dealId}`}
          renderLink={renderLink}
          caption={t('caption')}
          empty={t('empty')}
          defaultSorting={[{ id: 'sla', desc: false }]}
        />
        <p className="text-ink-muted">{t('legend')}</p>
      </div>

      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        {dialog && (
          <DialogContent title={t(`dialog.${dialog.action}.title`)} description={t(`dialog.${dialog.action}.body`, { item: dialog.item.title })} closeLabel={t('close')}>
            <p className="mt-0 mb-3 text-ink-muted">{t('pending')}</p>
            <div className="flex items-center justify-end gap-2">
              {/* //todo_#163: firmar la decisión (reautenticación inmediata) cuando exista el endpoint */}
              <DisabledReason reason={t('pending')}>
                <Button disabled>{t('confirm')}</Button>
              </DisabledReason>
              <Button variant="sec" onClick={() => setDialog(null)}>
                {t('cancel')}
              </Button>
            </div>
          </DialogContent>
        )}
      </Dialog>
    </main>
  )
}
