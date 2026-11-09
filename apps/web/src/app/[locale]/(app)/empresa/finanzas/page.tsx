import { getTranslations, setRequestLocale } from 'next-intl/server'

import { ImportReport } from '@/components/finance/import-report'
import { SummaryView } from '@/components/finance/summary-view'
import { financeImport, financeSummary } from '@/fixtures/finance'

// //todo_#153: snapshot activo e histórico vendrán del BFF; reimportar reutiliza el flujo del alta
export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  const t = await getTranslations('company.finance.page')
  return (
    <div className="flex max-w-[1200px] flex-col gap-8 px-10 py-8">
      <div>
        <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
        <p className="m-0 mt-1.5 text-ink-muted">{t('intro', { date: financeSummary.referenceDate })}</p>
      </div>
      <SummaryView data={financeSummary} />
      <h2 className="m-0 text-xl font-semibold">{t('lastImport')}</h2>
      <ImportReport data={financeImport} />
    </div>
  )
}
