import { setRequestLocale } from 'next-intl/server'

import { ReportPage } from '@/components/finance/finance-pages'

export default async function FinanceImportPage({ params }: { params: Promise<{ locale: string; importId: string }> }) {
  const { locale, importId } = await params
  setRequestLocale(locale)
  return <ReportPage importId={importId} />
}
