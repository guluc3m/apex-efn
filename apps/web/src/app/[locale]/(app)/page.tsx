import { getTranslations, setRequestLocale } from 'next-intl/server'

// Portada mínima: el contrato no tiene endpoint de resumen de empresa.
export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  const t = await getTranslations('common')

  return (
    <main className="px-gutter-page py-gutter-panel">
      <h1 className="text-[22px] font-semibold tracking-tight">{t('appName')}</h1>
      <p className="text-ink-soft">{t('tagline')}</p>
    </main>
  )
}
