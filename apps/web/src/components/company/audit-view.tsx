'use client'

import { Badge, Button, Icon, Input, Label, Table, type TableColumn } from '@apex/ui'
import { BadgeCheck, Link2, OctagonAlert, SearchCheck, ShieldAlert } from 'lucide-react'
import { useTranslations } from 'next-intl'

import { auditData, auditRoles, type AuditRow } from '@/fixtures/company'

export function AuditView({ role }: { role: string }) {
  const t = useTranslations('company.audit')
  const pending = t('pending')

  if (!auditRoles.includes(role)) {
    return (
      <div className="px-(--gutter-page) py-6">
        <div role="status" className="flex items-start gap-2 border border-line bg-panel p-4">
          <Icon icon={ShieldAlert} />
          <div>
            <strong>{t('noAccessTitle')}</strong>
            <p className="m-0 text-ink-soft">{t('noAccessBody')}</p>
          </div>
        </div>
      </div>
    )
  }

  const columns: TableColumn<AuditRow>[] = [
    { id: 'time', header: t('when'), sortable: false, cell: (r) => <span className="text-ink-muted">{r.time}</span> },
    { id: 'actor', header: t('actor'), sortable: false, cell: (r) => t(`actors.${r.actor}`) },
    { id: 'event', header: t('event'), sortable: false, cell: (r) => r.text },
    { id: 'hash', header: t('hash'), sortable: false, cell: (r) => <span className="font-mono text-ink-muted">{r.hash}</span> },
  ]

  return (
    <div className="flex flex-col gap-7 px-(--gutter-page) py-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
          <p className="m-0 mt-1.5 text-ink-soft">{t('intro')}</p>
        </div>
        {/* //todo_#166: GET /v1/audit/verify */}
        <Button variant="sec" disabledReason={pending}><Icon icon={Link2} />{t('verifyChain')}</Button>
      </div>

      <div className="flex flex-wrap gap-10 border border-line bg-panel p-4">
        <div>
          <div className="text-ink-muted">{t('status')}</div>
          {auditData.chain === 'intact' ? (
            <Badge tone="ok">{t('intact')}</Badge>
          ) : (
            <Badge tone="bad" icon={OctagonAlert}>{t('broken')}</Badge>
          )}
        </div>
        <div><div className="text-ink-muted">{t('events')}</div><strong>{auditData.events.toLocaleString('es-ES')}</strong></div>
        <div><div className="text-ink-muted">{t('lastVerified')}</div><strong>{auditData.lastVerified}</strong></div>
        <div><div className="text-ink-muted">{t('anchor')}</div><span className="font-mono">{auditData.anchor}</span></div>
      </div>

      <div className="flex flex-wrap items-start gap-8">
        <section className="min-w-0 flex-[2_1_640px]">
          <Table columns={columns} rows={auditData.rows} getRowId={(r) => r.id} caption={t('caption')} empty={t('empty')} />
        </section>
        <section className="flex min-w-0 flex-[1_1_320px] flex-col gap-3 border border-line bg-panel p-4">
          <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={BadgeCheck} />{t('verifyTitle')}</h2>
          <div className="flex flex-col gap-1">
            <Label htmlFor="audit-verify-id">{t('verifyLabel')}</Label>
            <Input id="audit-verify-id" className="font-mono" placeholder="dec_…" />
          </div>
          {/* //todo_#166: POST /v1/decisions/{id}/verify */}
          <Button variant="sec" disabledReason={pending}><Icon icon={SearchCheck} />{t('verify')}</Button>
        </section>
      </div>
    </div>
  )
}
