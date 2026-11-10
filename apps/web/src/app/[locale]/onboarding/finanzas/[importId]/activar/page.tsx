import { setRequestLocale } from 'next-intl/server'

import { ActivatePage } from '@/components/finance/finance-pages'

export default async function FinanceActivatePage({ params }: { params: Promise<{ locale: string; importId: string }> }) {
  const { locale, importId } = await params
  setRequestLocale(locale)
  return <ActivatePage importId={importId} />
}
