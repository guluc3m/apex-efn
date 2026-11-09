import { Button } from '@apex/ui'
import { ArrowRight, Upload } from 'lucide-react'
import { getTranslations, setRequestLocale } from 'next-intl/server'

import { AppLink } from '@/components/app-link'
import { ImportReport } from '@/components/finance/import-report'
import { financeImport } from '@/fixtures/finance'

// //todo_#153: el informe vendrá del BFF por importId; inexistente → /onboarding/finanzas
export default async function FinanceImportPage({ params }: { params: Promise<{ locale: string; importId: string }> }) {
  const { locale, importId } = await params
  setRequestLocale(locale)
  const t = await getTranslations('company.finance.report')
  return (
    <main id="contenido" className="flex max-w-[1200px] flex-col gap-8 px-10 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="m-0 text-2xl font-semibold">{t('title', { file: financeImport.file })}</h1>
          <p className="m-0 mt-1.5 text-ink-muted">{t('subtitle', { rows: financeImport.rows })}</p>
        </div>
        {/* //todo_#153: subir otro archivo (paso finanzas del alta, aún sin ruta) */}
        <Button variant="sec" disabledReason={t('pending')}><Upload size={16} aria-hidden="true" />{t('upload')}</Button>
      </div>
      <ImportReport data={financeImport} />
      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
        <Button variant="pri" asChild>
          <AppLink href={`/onboarding/finanzas/${importId}/activar`}>{t('review')}<ArrowRight size={16} aria-hidden="true" /></AppLink>
        </Button>
        <span className="text-[13px] text-ink-muted">{t('rejectedDontBlock', { n: financeImport.rejected })}</span>
      </div>
    </main>
  )
}
