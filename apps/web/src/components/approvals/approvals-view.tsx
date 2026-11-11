'use client'

import type { ApprovalDocument, ApprovalInboxStatus, ApprovalView, Signature } from '@apex/shared-types/contracts'
import { Button, Icon, MoneyDisplay, SignatureStatusBadge, Table, cn, type TableColumn } from '@apex/ui'
import { ArrowLeft, Download, FileText, Send, Truck } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'
import { useState } from 'react'

import { AppLink, renderLink } from '@/components/app-link'
import { QueryBoundary } from '@/components/query-boundary'
import { SignDecisionButton } from '@/components/signing/sign-decision-button'
import { api, useApproval, useApprovals, useNotifyFinance } from '@/lib/api'

export const APPROVAL_TABS: readonly ApprovalInboxStatus[] = ['sign', 'progress', 'closed']

function useWhen() {
  const locale = useLocale()
  const fmt = new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short' })
  return (iso: string) => fmt.format(new Date(iso))
}

function Amount({ a }: { a: ApprovalView }) {
  const locale = useLocale()
  return a.amount ? <MoneyDisplay amountMinor={a.amount.amount_minor} currency={a.amount.currency} locale={locale} /> : <>—</>
}

/** Bandeja: el filtro `?estado=` vive en la URL; las pestañas son enlaces. */
export function ApprovalsList({ status }: { status: ApprovalInboxStatus }) {
  const t = useTranslations('approvals')
  const query = useApprovals({ status })

  const columns: TableColumn<ApprovalView>[] = [
    { id: 'title', header: t('colDocument'), sortable: false, cell: (a) => a.subject_ref },
    { id: 'seller', header: t('colWho'), sortable: false, cell: (a) => a.seller_ref ?? '—' },
    { id: 'amount', header: t('colDetail'), sortable: false, num: true, cell: (a) => <Amount a={a} /> },
    {
      id: 'sigs',
      header: t('colState'),
      sortable: false,
      cell: (a) => t('signaturesOf', { done: a.signatures.length, needed: a.required_signers }),
    },
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
      <QueryBoundary query={query}>
        {(page) => (
          <Table
            columns={columns}
            rows={page.items}
            getRowId={(a) => a.id}
            getHref={(a) => `/aprobaciones/${a.id}`}
            caption={t(`tabs.${status}`)}
            empty={t('empty')}
            renderLink={renderLink}
          />
        )}
      </QueryBoundary>
    </div>
  )
}

function SignatureRow({ slot, s }: { slot: number; s?: Signature }) {
  const t = useTranslations('approvals')
  const when = useWhen()
  return (
    <tr>
      <th scope="row" className="py-2 pr-4 text-left font-medium">
        {t(slot === 0 ? 'first' : 'second')}
      </th>
      <td className="py-2 pr-4">{s ? s.signer_id : slot === 1 ? t('secondWho') : '—'}</td>
      <td className="py-2 pr-4">{s ? when(s.signed_at) : '—'}</td>
      <td className="py-2">
        <SignatureStatusBadge status={s ? 'signed' : 'pending'} label={s ? t('signed') : t('notSigned')} />
      </td>
    </tr>
  )
}

function DocRow({ id, d }: { id: string; d: ApprovalDocument }) {
  const t = useTranslations('approvals')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const download = async (): Promise<void> => {
    setBusy(true)
    setFailed(false)
    try {
      const url = URL.createObjectURL(await api.downloadApprovalDocument(id, d.kind))
      const a = document.createElement('a')
      a.href = url
      a.download = `${d.kind}-${id}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <tr>
      <th scope="row" className="py-2 pr-4 text-left font-medium">
        {t(`docs.${d.kind}`)}
      </th>
      <td className="py-2 pr-4 text-ink-muted">{d.sha256 ? `sha256 ${d.sha256.slice(0, 8)}…` : ''}</td>
      <td className="py-2 text-right">
        <Button size="sm" disabled={busy} disabledReason={d.available ? undefined : t('docUnavailable')} onClick={() => void download()}>
          <Icon icon={Download} />
          {t('download')}
        </Button>
        {failed && <p role="alert" className="m-0 mt-1 text-[13px] text-bad">{t('downloadFailed')}</p>}
      </td>
    </tr>
  )
}

function NotifyFinance({ id }: { id: string }) {
  const t = useTranslations('approvals')
  const notify = useNotifyFinance(id)
  return (
    <div className="flex flex-col gap-1">
      <div>
        <Button disabled={notify.isPending || notify.isSuccess} onClick={() => notify.mutate()}>
          <Icon icon={Send} />
          {t('askFinance')}
        </Button>
      </div>
      {notify.isSuccess && <p role="status" className="m-0 text-[13px] text-ink-muted">{t('notified')}</p>}
      {notify.isError && <p role="alert" className="m-0 text-[13px] text-bad">{t('notifyFailed')}</p>}
    </div>
  )
}

function Detail({ a }: { a: ApprovalView }) {
  const t = useTranslations('approvals')
  const when = useWhen()
  const missing = a.status === 'sign' && a.signatures.length < a.required_signers
  return (
    <div className="flex max-w-240 flex-col gap-7 px-(--gutter-page) py-6">
      <AppLink href={`/aprobaciones?estado=${a.status}`} className="inline-flex w-fit items-center gap-1.5 text-ink-soft">
        <Icon icon={ArrowLeft} />
        {t('back')}
      </AppLink>
      <div>
        <div className="text-ink-muted">{t('kind')}</div>
        <h1 className="mt-1 mb-0 text-2xl font-semibold">
          {a.subject_ref} · <Amount a={a} />
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
          {Array.from({ length: a.required_signers }, (_, i) => (
            <SignatureRow key={i} slot={i} s={a.signatures[i]} />
          ))}
        </tbody>
      </table>

      {missing ? (
        <div className="flex flex-col gap-3">
          {/* El servidor exige otra persona para la segunda firma (409 already_signed_by_signer) y una sesión de firma abierta. */}
          <SignDecisionButton decisionId={a.id} reasonWithout={t('addSecondReason')}>
            {t(a.signatures.length === 0 ? 'first' : 'addSecond')}
          </SignDecisionButton>
          <NotifyFinance id={a.id} />
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
              <DocRow key={d.kind} id={a.id} d={d} />
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
                <tr key={`${e.event}-${e.at}`}>
                  <th scope="row" className="w-40 py-2 pr-4 text-left font-medium">{when(e.at)}</th>
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

export function ApprovalDetail({ id }: { id: string }) {
  const query = useApproval(id)
  return <QueryBoundary query={query}>{(a) => <Detail a={a} />}</QueryBoundary>
}
