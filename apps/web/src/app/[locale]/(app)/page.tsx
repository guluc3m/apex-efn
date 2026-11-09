import { getTranslations, setRequestLocale } from 'next-intl/server'

// Portada mínima. //todo_#148: portada real (resumen de empresa y accesos)
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
