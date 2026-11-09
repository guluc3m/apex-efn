import { Button, Icon } from '@apex/ui'
import { ArrowLeft, FileCheck, PenLine } from 'lucide-react'
import { getTranslations, setRequestLocale } from 'next-intl/server'

import { AppLink } from '@/components/app-link'
import { SummaryView } from '@/components/finance/summary-view'
import { financeImport, financeSummary } from '@/fixtures/finance'

// //todo_#153: el resumen vendrá del snapshot derivado del import
export default async function FinanceActivatePage({ params }: { params: Promise<{ locale: string; importId: string }> }) {
  const { locale, importId } = await params
  setRequestLocale(locale)
  const t = await getTranslations('company.finance.summary')
  const s = financeSummary
  const kv: { k: string; v: string; mono?: boolean }[] = [
    { k: t('rows'), v: t('rowsValue', { n: financeImport.accepted }) },
    { k: t('replaces'), v: t('replacesValue', { month: s.replaces }) },
    { k: t('expires'), v: s.expires },
    { k: 'payload_hash', v: s.payloadHash, mono: true },
  ]
  return (
    <main id="contenido" className="flex flex-wrap items-start">
      <div className="flex min-w-0 flex-[999_1_640px] flex-col gap-8 px-10 py-8">
        <div>
          <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
          <p className="m-0 mt-1.5 text-ink-muted">{t('subtitle', { date: s.referenceDate })}</p>
        </div>
        <SummaryView data={s} />
      </div>
      <aside className="sticky top-0 min-w-0 flex-[1_1_360px] px-6 py-8">
        <div className="flex flex-col gap-4 border border-line bg-panel p-6">
          <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={FileCheck} />{t('activateTitle')}</h2>
          <p className="m-0">{t('activateBody')}</p>
          <dl className="m-0">
            {kv.map((e) => (
              <div key={e.k} className="flex justify-between gap-4 py-1"><dt className="text-ink-muted">{e.k}</dt><dd className={`m-0 ${e.mono ? 'font-mono' : ''}`}>{e.v}</dd></div>
            ))}
          </dl>
          <Button variant="sec" asChild>
            <AppLink href={`/onboarding/finanzas/${importId}`}><ArrowLeft size={16} aria-hidden="true" />{t('back')}</AppLink>
          </Button>
          {/* //todo_#151: ceremonia de passkey y decisión firmada; //todo_#153: POST financial-csv/activate */}
          <Button variant="pri" disabledReason={t('pending')}><PenLine size={16} aria-hidden="true" />{t('activate')}</Button>
          <p className="m-0 text-[13px] text-ink-muted">{t('allOrNothing')}</p>
        </div>
      </aside>
    </main>
  )
}
