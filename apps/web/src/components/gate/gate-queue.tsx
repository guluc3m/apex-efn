'use client'

import type { GateQueueAction, GateQueueItem, GateReason } from '@apex/shared-types/contracts'
import { Badge, Button, Dialog, DialogContent, Label, MoneyDisplay, Select, Table, type TableColumn } from '@apex/ui'
import { Clock } from 'lucide-react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useState } from 'react'

import { renderLink } from '@/components/app-link'
import { DecisionFooter } from '@/components/decisions/decision-footer'
import { useDeals, useGateAction, useGateQueue } from '@/lib/api'
import { remaining } from '@/lib/decisions'

const REASONS: GateReason[] = [
  'price_atypical',
  'price_insufficient_reference',
  'seller_low',
  'seller_insufficient_data',
  'out_of_budget',
  'stretch_above_threshold',
  'negotiator_escalated',
  'financials_stale',
  'fx_provisional',
  'dual_control_pending',
]
const ACTIONS: GateQueueAction[] = ['unblock', 'override_discard']
const OVERRIDE_ROLES: readonly string[] = ['finance', 'admin', 'owner']
const textarea = 'box-border w-full border border-control-border bg-bg px-2.5 py-2 text-ink focus:border-accent'

export function GateQueue({ role }: { role: string }) {
  const t = useTranslations('gate')
  const td = useTranslations('decisions')
  const locale = useLocale()
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const [dialog, setDialog] = useState<{ action: GateQueueAction; item: GateQueueItem } | null>(null)
  const [comment, setComment] = useState('')
  const mutation = useGateAction()

  const cause = params.get('causa') ?? 'all'
  const queue = useGateQueue({ status: 'open', ...(cause !== 'all' ? { type: cause as GateReason } : {}) })
  const deals = useDeals()
  const dealByOffer = new Map((deals.data?.items ?? []).map((d) => [d.offer.id, d]))
  const rows = queue.data?.items ?? []
  const nowMs = Date.now()

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params.toString())
    if (v) next.set(k, v)
    else next.delete(k)
    const qs = next.toString()
    router.replace(`${pathname}${qs ? `?${qs}` : ''}` as never, { scroll: false })
  }

  const mayOverride = OVERRIDE_ROLES.includes(role)
  const open = (action: GateQueueAction, item: GateQueueItem) => {
    mutation.reset()
    setComment('')
    setDialog({ action, item })
  }

  const columns: TableColumn<GateQueueItem>[] = [
    {
      id: 'item',
      header: t('cols.item'),
      sortValue: (r) => dealByOffer.get(r.offer_id)?.offer.title ?? r.offer_id,
      cell: (r) => {
        const d = dealByOffer.get(r.offer_id)
        return (
          <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{d?.offer.title ?? r.offer_id}</span>
            {d && <span className="font-normal text-ink-muted">· {d.offer.seller_name}</span>}
          </span>
        )
      },
    },
    {
      id: 'cause',
      header: t('cols.cause'),
      sortValue: (r) => r.causes.map((c) => t(`reasons.${c}`)).join(', '),
      cell: (r) => r.causes.map((c) => t(`reasons.${c}`)).join(' · '),
    },
    {
      id: 'amount',
      header: t('cols.amount'),
      num: true,
      sortValue: (r) => dealByOffer.get(r.offer_id)?.offer.financial_fit?.landed_cost.total.amount_minor ?? -1,
      cell: (r) => {
        const total = dealByOffer.get(r.offer_id)?.offer.financial_fit?.landed_cost.total
        return total ? <MoneyDisplay amountMinor={total.amount_minor} currency={total.currency} locale={locale} className="whitespace-nowrap" /> : '—'
      },
    },
    {
      id: 'sla',
      header: t('cols.sla'),
      num: true,
      sortValue: (r) => Date.parse(r.sla_due_at),
      cell: (r) => {
        const sla = remaining(r.sla_due_at, nowMs)
        return sla.overdue ? (
          <Badge tone="bad" icon={Clock}>
            {sla.label} · {t('overdue')}
          </Badge>
        ) : (
          sla.label
        )
      },
    },
    {
      id: 'actions',
      header: t('cols.actions'),
      hidden: true,
      cell: (r) => (
        <span className="inline-flex gap-2">
          {ACTIONS.filter((a) => a !== 'override_discard' || mayOverride).map((a) => (
            <Button key={a} variant="sec" size="sm" onClick={() => open(a, r)}>
              {t(`actions.${a}`)}
            </Button>
          ))}
        </span>
      ),
    },
  ]

  const itemTitle = (i: GateQueueItem) => dealByOffer.get(i.offer_id)?.offer.title ?? i.offer_id

  return (
    <main id="contenido">
      <div className="flex flex-wrap items-center justify-between gap-4 px-(--gutter-page) py-6">
        <div>
          <h1 className="m-0 text-[22px] font-semibold">{t('title', { count: rows.length })}</h1>
          <p className="mt-1.5 mb-0 text-ink-soft">{t('subtitle')}</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <Select
            label={t('filters.cause')}
            value={cause}
            onValueChange={(v) => set('causa', v === 'all' ? null : v)}
            options={[{ value: 'all', label: t('filters.all') }, ...REASONS.map((c) => ({ value: c, label: t(`reasons.${c}`) }))]}
          />
        </div>
      </div>
      <div className="px-(--gutter-page) pb-10">
        {queue.isError && (
          <p role="alert" className="text-bad">
            {t('loadError')} <Button onClick={() => void queue.refetch()}>{t('retry')}</Button>
          </p>
        )}
        {queue.isPending && <p className="text-ink-soft">{t('loading')}</p>}
        {queue.isSuccess && (
          <>
            <p className="mb-2 text-ink-muted">{t('order')}</p>
            <Table
              columns={columns}
              rows={rows}
              getRowId={(r) => r.id}
              getHref={(r) => `/decisiones/${dealByOffer.get(r.offer_id)?.id ?? ''}`}
              renderLink={renderLink}
              caption={t('caption')}
              empty={t('empty')}
              defaultSorting={[{ id: 'sla', desc: false }]}
            />
            <p className="text-ink-muted">{t('legend')}</p>
          </>
        )}
      </div>

      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        {dialog && (
          <DialogContent title={t(`dialog.${dialog.action}.title`)} description={t(`dialog.${dialog.action}.body`, { item: itemTitle(dialog.item) })} closeLabel={t('close')}>
            <div className="my-2 flex flex-col gap-1">
              <Label htmlFor="g-comment">{t('comment')}</Label>
              <textarea id="g-comment" rows={2} className={textarea} value={comment} onChange={(e) => setComment(e.target.value)} />
            </div>
            <DecisionFooter
              disabledReason={role === 'viewer' ? td('block.role_not_allowed') : undefined}
              busy={mutation.isPending}
              error={mutation.error}
              accepted={mutation.data}
              onCreate={() =>
                mutation.mutate({ id: dialog.item.id, body: { action: dialog.action, comment: comment.trim() || null } })
              }
              onClose={() => setDialog(null)}
            />
          </DialogContent>
        )}
      </Dialog>
    </main>
  )
}
