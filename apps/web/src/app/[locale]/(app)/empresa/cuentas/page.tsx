import { getTranslations, setRequestLocale } from 'next-intl/server'

import { AccountsStep } from '@/components/onboarding/accounts-step'
import { platforms } from '@/fixtures/onboarding'

// //todo_#154: las cuentas vendrán de GET connected-accounts; solo owner y admin
export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  const t = await getTranslations('company.accounts')
  return (
    <div className="flex max-w-[1200px] flex-col gap-6 px-10 py-8">
      <div>
        <h1 className="m-0 text-2xl font-semibold">{t('title')}</h1>
        <p className="m-0 mt-1.5 text-ink-muted">{t('intro')}</p>
      </div>
      <AccountsStep platforms={platforms} />
    </div>
  )
}
