'use client'

import type { AuditEvent } from '@apex/shared-types/contracts'
import { Badge, Button, Icon, Input, Label, Table, type TableColumn } from '@apex/ui'
import { BadgeCheck, Link2, OctagonAlert, SearchCheck, ShieldAlert } from 'lucide-react'
import { useFormatter, useLocale, useTranslations } from 'next-intl'
import { useState } from 'react'

import { ApiError, useAuditEvents, useAuditVerification, useVerifyDecision } from '@/lib/api'

/** The audit endpoints are admin/owner on the server; this only avoids showing a screen that would answer 403. */
const AUDIT_ROLES = ['admin', 'owner']

const short = (hash: string) => `${hash.slice(0, 6)}…${hash.slice(-4)}`

function NoAccess() {
  const t = useTranslations('company.audit')
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

export function AuditView({ role }: { role: string }) {
  if (!AUDIT_ROLES.includes(role)) return <NoAccess />
  return <AuditBody />
}

function AuditBody() {
  const t = useTranslations('company.audit')
  const locale = useLocale()
  const format = useFormatter()
  const events = useAuditEvents()
  const chain = useAuditVerification()
  const verifyDecision = useVerifyDecision()
  const [decisionId, setDecisionId] = useState('')

  if (events.error instanceof ApiError && events.error.status === 403) return <NoAccess />

  const columns: TableColumn<AuditEvent>[] = [
    {
      id: 'time',
      header: t('when'),
      sortable: false,
      cell: (r) => <span className="text-ink-muted">{format.dateTime(new Date(r.created_at), { dateStyle: 'short', timeStyle: 'medium' })}</span>,
    },
    { id: 'actor', header: t('actor'), sortable: false, cell: (r) => `${t(`actorTypes.${r.actor.type}`)} · ${r.actor.id}` },
    { id: 'event', header: t('event'), sortable: false, cell: (r) => <span className="font-mono">{r.event_type}</span> },
    { id: 'subject', header: t('subject'), sortable: false, cell: (r) => <span className="font-mono text-ink-muted">{r.subject_ref}</span> },
    { id: 'hash', header: t('hash'), sortable: false, cell: (r) => <span className="font-mono text-ink-muted">{short(r.hash)}</span> },
  ]

  const c = chain.data
  return (
    <div className="flex flex-col gap-7 px-(--gutter-page) py-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
          <p className="m-0 mt-1.5 text-ink-soft">{t('intro')}</p>
        </div>
        <Button variant="sec" disabledReason={chain.isFetching ? t('verifying') : undefined} onClick={() => void chain.refetch()}>
          <Icon icon={Link2} />
          {t('verifyChain')}
        </Button>
      </div>

      <div className="flex flex-wrap gap-10 border border-line bg-panel p-4" aria-live="polite">
        <div>
          <div className="text-ink-muted">{t('status')}</div>
          {chain.isError ? (
            <Badge tone="bad" icon={OctagonAlert}>{t('verifyFailed')}</Badge>
          ) : !c ? (
            <span className="text-ink-muted">{t('verifying')}</span>
          ) : c.valid ? (
            <Badge tone="ok">{t('intact')}</Badge>
          ) : (
            <Badge tone="bad" icon={OctagonAlert}>{c.first_broken_seq != null ? t('brokenAt', { seq: c.first_broken_seq }) : t('broken')}</Badge>
          )}
        </div>
        <div><div className="text-ink-muted">{t('events')}</div><strong>{c ? c.checked_events.toLocaleString(locale) : '—'}</strong></div>
        <div>
          <div className="text-ink-muted">{t('lastVerified')}</div>
          <strong>{c ? format.dateTime(new Date(c.verified_at), { dateStyle: 'short', timeStyle: 'medium' }) : '—'}</strong>
        </div>
        <div>
          <div className="text-ink-muted">{t('anchor')}</div>
          <span className="font-mono">{c?.anchored_head_hash ? short(c.anchored_head_hash) : t('noAnchor')}</span>
        </div>
      </div>

      <div className="flex flex-wrap items-start gap-8">
        <section className="min-w-0 flex-[2_1_640px]">
          {events.isError ? (
            <p role="alert" className="m-0 text-bad">{t('loadFailed')}</p>
          ) : (
            <Table
              columns={columns}
              rows={events.data?.items ?? []}
              getRowId={(r) => r.id}
              caption={t('caption')}
              empty={events.isPending ? t('loading') : t('empty')}
            />
          )}
        </section>
        <section className="flex min-w-0 flex-[1_1_320px] flex-col gap-3 border border-line bg-panel p-4">
          <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={BadgeCheck} />{t('verifyTitle')}</h2>
          <div className="flex flex-col gap-1">
            <Label htmlFor="audit-verify-id">{t('verifyLabel')}</Label>
            <Input id="audit-verify-id" className="font-mono" placeholder={t('verifyPlaceholder')} value={decisionId} onChange={(e) => setDecisionId(e.target.value)} />
          </div>
          <Button
            variant="sec"
            disabledReason={!decisionId.trim() ? t('verifyNeedsId') : verifyDecision.isPending ? t('verifying') : undefined}
            onClick={() => verifyDecision.mutate(decisionId.trim())}
          >
            <Icon icon={SearchCheck} />
            {t('verify')}
          </Button>
          {verifyDecision.data ? (
            <div role="status" className="flex flex-col gap-1">
              <Badge tone={verifyDecision.data.valid ? 'ok' : 'bad'}>{verifyDecision.data.valid ? t('decisionValid') : t('decisionInvalid')}</Badge>
              <ul className="m-0 list-none p-0 text-[13px] text-ink-muted">
                {verifyDecision.data.checks.map((k) => (
                  <li key={k.name}>{`${k.ok ? '✓' : '✗'} ${k.name}${k.detail ? `: ${k.detail}` : ''}`}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {verifyDecision.isError ? (
            <p role="alert" className="m-0 text-bad">
              {verifyDecision.error instanceof ApiError && verifyDecision.error.status === 404 ? t('decisionNotFound') : t('verifyFailed')}
            </p>
          ) : null}
        </section>
      </div>
    </div>
  )
}
