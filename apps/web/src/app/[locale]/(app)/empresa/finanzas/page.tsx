import { getTranslations, setRequestLocale } from 'next-intl/server'

import { CompanyFinance } from '@/components/finance/finance-pages'

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  const t = await getTranslations('company.finance.page')
  return (
    <div className="flex max-w-[1200px] flex-col gap-8 px-10 py-8">
      <div>
        <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
        <p className="m-0 mt-1.5 text-ink-muted">{t('intro')}</p>
      </div>
      <CompanyFinance />
    </div>
  )
}
