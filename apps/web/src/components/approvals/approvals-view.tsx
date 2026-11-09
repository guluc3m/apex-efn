'use client'

import { Badge, Button, Icon, SignatureStatusBadge, Table, cn, type TableColumn } from '@apex/ui'
import { ArrowLeft, Download, FileText, PenLine, Send, Truck } from 'lucide-react'
import { useTranslations } from 'next-intl'

import { AppLink, renderLink } from '@/components/app-link'
import type { ApprovalDocument, ApprovalFixture, ApprovalSignature, ApprovalStatus } from '@/fixtures/approvals'

export const APPROVAL_TABS: readonly ApprovalStatus[] = ['sign', 'progress', 'closed']

/** Bandeja: el filtro `?estado=` vive en la URL; las pestañas son enlaces. */
export function ApprovalsList({ rows, status }: { rows: ApprovalFixture[]; status: ApprovalStatus }) {
  const t = useTranslations('approvals')
  const shown = rows.filter((a) => a.status === status)

  const columns: TableColumn<ApprovalFixture>[] = [
    { id: 'title', header: t('colDocument'), sortable: false, cell: (a) => a.title },
    { id: 'seller', header: t('colWho'), sortable: false, cell: (a) => a.seller },
    { id: 'amount', header: t('colDetail'), sortable: false, num: true, cell: (a) => a.amount },
    { id: 'note', header: t('colState'), sortable: false, cell: (a) => <Badge tone="plano">{t(`notes.${a.note}`)}</Badge> },
  ]

  return (
    <div className="flex flex-col gap-4 px-(--gutter-page) py-6">
      <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
      <nav aria-label={t('tabsLabel')} className="flex gap-1 border-b border-line">
        {APPROVAL_TABS.map((s) => (
          <AppLink
            key={s}
            href={`/aprobaciones?estado=${s}`}
            aria-current={s === status ? 'page' : undefined}
            className={cn(
              'inline-flex min-h-9 items-center px-3 font-medium no-underline transition-[color] duration-(--fast) ease-apex',
              s === status ? 'border-b-2 border-accent text-ink' : 'text-ink-soft',
            )}
          >
            {t(`tabs.${s}`)}
          </AppLink>
        ))}
      </nav>
      <Table
        columns={columns}
        rows={shown}
        getRowId={(a) => a.id}
        getHref={(a) => `/aprobaciones/${a.id}`}
        caption={t(`tabs.${status}`)}
        empty={t('empty')}
        renderLink={renderLink}
      />
    </div>
  )
}

function SignatureRow({ s }: { s: ApprovalSignature }) {
  const t = useTranslations('approvals')
  return (
    <tr>
      <th scope="row" className="py-2 pr-4 text-left font-medium">
        {t(s.slot)}
      </th>
      <td className="py-2 pr-4">{s.signed ? s.who : s.slot === 'second' ? t('secondWho') : '—'}</td>
      <td className="py-2 pr-4">{s.signed ? s.when : '—'}</td>
      <td className="py-2">
        <SignatureStatusBadge status={s.signed ? 'signed' : 'pending'} label={s.signed ? t('signed') : t('notSigned')} />
      </td>
    </tr>
  )
}

function DocRow({ d }: { d: ApprovalDocument }) {
  const t = useTranslations('approvals')
  return (
    <tr>
      <th scope="row" className="py-2 pr-4 text-left font-medium">
        {t(`docs.${d.kind}`)}
      </th>
      <td className="py-2 pr-4 text-ink-muted">{d.hash ?? (d.kind === 'rfq' ? '' : t(`docPending.${d.kind}`))}</td>
      <td className="py-2 text-right">
        {/* //todo_#165: descarga del PDF (RFQ, orden de compra, certificado) cuando D2-11 esté conectado */}
        <Button size="sm" disabledReason={d.available ? t('pending') : t(`docPending.${d.kind === 'rfq' ? 'po' : d.kind}`)}>
          <Icon icon={Download} />
          {t('download')}
        </Button>
      </td>
    </tr>
  )
}

export function ApprovalDetail({ a }: { a: ApprovalFixture }) {
  const t = useTranslations('approvals')
  const dual = a.signatures.some((s) => !s.signed) && a.signatures.some((s) => s.signed)
  return (
    <div className="flex max-w-240 flex-col gap-7 px-(--gutter-page) py-6">
      <AppLink href={`/aprobaciones?estado=${a.status}`} className="inline-flex w-fit items-center gap-1.5 text-ink-soft">
        <Icon icon={ArrowLeft} />
        {t('back')}
      </AppLink>
      <div>
        <div className="text-ink-muted">{t('kind')}</div>
        <h1 className="mt-1 mb-0 text-2xl font-semibold">
          {a.title} · {a.amount}
        </h1>
      </div>

      <table className="w-full border-collapse">
        <caption className="sr-only">{t('sigCaption')}</caption>
        <thead>
          <tr className="text-left text-ink-muted">
            <th scope="col" className="pb-2 font-normal">{t('colSignature')}</th>
            <th scope="col" className="pb-2 font-normal">{t('colWho')}</th>
            <th scope="col" className="pb-2 font-normal">{t('colWhen')}</th>
            <th scope="col" className="pb-2 font-normal">{t('colState')}</th>
          </tr>
        </thead>
        <tbody>
          {a.signatures.map((s) => (
            <SignatureRow key={s.slot} s={s} />
          ))}
        </tbody>
      </table>

      {a.status === 'sign' ? (
        <div className="flex flex-col gap-3">
          <div>
            {/* //todo_#165: la segunda firma exige otra persona con rol finance|admin|owner y sesión de firma abierta */}
            <Button disabledReason={dual ? t('addSecondReason') : t('pending')}>
              <Icon icon={PenLine} />
              {t('addSecond')}
            </Button>
          </div>
          <div>
            {/* //todo_#165: notificar a Finanzas para que firme */}
            <Button disabledReason={t('pending')}>
              <Icon icon={Send} />
              {t('askFinance')}
            </Button>
          </div>
        </div>
      ) : null}

      <section className="flex flex-col gap-2">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold">
          <Icon icon={FileText} />
          {t('docsHeading')}
        </h2>
        <table className="w-full border-collapse">
          <caption className="sr-only">{t('docsCaption')}</caption>
          <thead>
            <tr className="text-left text-ink-muted">
              <th scope="col" className="pb-2 font-normal">{t('colDocument')}</th>
              <th scope="col" className="pb-2 font-normal">{t('colDetail')}</th>
              <th scope="col" className="pb-2 text-right font-normal">{t('colAction')}</th>
            </tr>
          </thead>
          <tbody>
            {a.documents.map((d) => (
              <DocRow key={d.kind} d={d} />
            ))}
          </tbody>
        </table>
      </section>

      {a.tracking.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className="m-0 flex items-center gap-2 text-base font-semibold">
            <Icon icon={Truck} />
            {t('trackHeading')}
          </h2>
          <table className="w-full border-collapse">
            <caption className="sr-only">{t('trackCaption')}</caption>
            <thead>
              <tr className="text-left text-ink-muted">
                <th scope="col" className="pb-2 font-normal">{t('colWhen')}</th>
                <th scope="col" className="pb-2 font-normal">{t('colEvent')}</th>
              </tr>
            </thead>
            <tbody>
              {a.tracking.map((e) => (
                <tr key={e.event}>
                  <th scope="row" className="w-40 py-2 pr-4 text-left font-medium">{e.when}</th>
                  <td className="py-2">{t(`track.${e.event}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </div>
  )
}
