'use client'

import { Button, Icon } from '@apex/ui'
import { ArrowLeft, ArrowRight, FileCheck, PenLine, Upload } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useState } from 'react'

import { AppLink } from '@/components/app-link'
import { api } from '@/lib/api'
import { useOnboarding } from '@/stores/onboarding'

import { ImportReport } from './import-report'
import { SummaryView } from './summary-view'

/** The import the upload returned, if it is the one in the URL. There is no GET import yet (issue #299). */
function useImport(importId?: string) {
  const imp = useOnboarding((s) => s.financialImport)
  return imp && (!importId || imp.id === importId) ? imp : null
}

function NoImport() {
  const t = useTranslations('company.finance.report')
  return (
    <div className="flex flex-col items-start gap-3 border border-line bg-panel p-6" role="status">
      <p className="m-0 text-ink-muted">{t('missing')}</p>
      <Button variant="pri" asChild>
        <AppLink href="/onboarding/finanzas"><Upload size={16} aria-hidden="true" />{t('upload')}</AppLink>
      </Button>
    </div>
  )
}

export function ReportPage({ importId }: { importId: string }) {
  const t = useTranslations('company.finance.report')
  const imp = useImport(importId)
  if (!imp) return <main id="contenido" className="max-w-[1200px] px-10 py-8"><NoImport /></main>
  return (
    <main id="contenido" className="flex max-w-[1200px] flex-col gap-8 px-10 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
          <p className="m-0 mt-1.5 text-ink-muted">{t('subtitle', { rows: imp.report.rows_ok + imp.report.rows_rejected })}</p>
        </div>
        <Button variant="sec" asChild>
          <AppLink href="/onboarding/finanzas"><Upload size={16} aria-hidden="true" />{t('upload')}</AppLink>
        </Button>
      </div>
      <ImportReport data={imp} />
      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
        <Button variant="pri" asChild>
          <AppLink href={`/onboarding/finanzas/${importId}/activar`}>{t('review')}<ArrowRight size={16} aria-hidden="true" /></AppLink>
        </Button>
        <span className="text-[13px] text-ink-muted">{t('rejectedDontBlock', { n: imp.report.rows_rejected })}</span>
      </div>
    </main>
  )
}

export function ActivatePage({ importId }: { importId: string }) {
  const t = useTranslations('company.finance.summary')
  const imp = useImport(importId)
  const sessionId = useOnboarding((s) => s.sessionId)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const [decisionId, setDecisionId] = useState<string | null>(null)
  if (!imp) return <main id="contenido" className="max-w-[1200px] px-10 py-8"><NoImport /></main>
  const activate = async () => {
    if (!sessionId) return
    setBusy(true)
    setFailed(false)
    try {
      setDecisionId((await api.activateFinancialSnapshot(sessionId, { import_id: imp.id })).decision_id)
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <main id="contenido" className="flex flex-wrap items-start">
      <div className="flex min-w-0 flex-[999_1_640px] flex-col gap-8 px-10 py-8">
        <div>
          <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
          <p className="m-0 mt-1.5 text-ink-muted">{t('subtitle', { date: imp.report.reference_date })}</p>
        </div>
        <SummaryView data={imp.report.derived} />
      </div>
      <aside className="sticky top-0 min-w-0 flex-[1_1_360px] px-6 py-8">
        <div className="flex flex-col gap-4 border border-line bg-panel p-6">
          <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={FileCheck} />{t('activateTitle')}</h2>
          <p className="m-0">{t('activateBody')}</p>
          <dl className="m-0">
            <div className="flex justify-between gap-4 py-1"><dt className="text-ink-muted">{t('rows')}</dt><dd className="m-0">{t('rowsValue', { n: imp.report.rows_ok })}</dd></div>
            {decisionId && <div className="flex justify-between gap-4 py-1"><dt className="text-ink-muted">{t('decision')}</dt><dd className="m-0 font-mono">{decisionId}</dd></div>}
          </dl>
          <Button variant="sec" asChild>
            <AppLink href={`/onboarding/finanzas/${importId}`}><ArrowLeft size={16} aria-hidden="true" />{t('back')}</AppLink>
          </Button>
          {decisionId ? (
            <>
              <p role="status" className="m-0">{t('requested')}</p>
              {/* La firma depende de D2-09 (decisiones firmadas); nunca se simula. */}
              <Button variant="pri" disabledReason={t('signPending')}><PenLine size={16} aria-hidden="true" />{t('activate')}</Button>
            </>
          ) : (
            <Button variant="pri" onClick={() => void activate()} disabled={busy} disabledReason={sessionId ? undefined : t('noSession')}>
              <PenLine size={16} aria-hidden="true" />{busy ? t('requesting') : t('request')}
            </Button>
          )}
          {failed && <p role="alert" className="m-0 text-bad">{t('requestError')}</p>}
          <p className="m-0 text-[13px] text-ink-muted">{t('allOrNothing')}</p>
        </div>
      </aside>
    </main>
  )
}

/** Resumen de `/empresa/finanzas`: lo último importado en esta sesión; el snapshot activo no tiene endpoint de lectura. */
export function CompanyFinance() {
  const t = useTranslations('company.finance.page')
  const imp = useImport()
  if (!imp) return <p className="m-0 text-ink-muted" role="status">{t('empty')}</p>
  return (
    <>
      <SummaryView data={imp.report.derived} />
      <h2 className="m-0 text-xl font-semibold">{t('lastImport')}</h2>
      <ImportReport data={imp} />
    </>
  )
}
