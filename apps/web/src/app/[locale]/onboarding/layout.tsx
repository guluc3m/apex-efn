import { getTranslations, setRequestLocale } from 'next-intl/server'

import { AppLink } from '@/components/app-link'

/** Cabecera reducida del alta: sin navegación de la app, solo salida y estado del borrador. */
export default async function OnboardingLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  setRequestLocale((await params).locale)
  const t = await getTranslations('onboarding.header')
  return (
    <>
      <header className="flex items-center gap-4 border-b border-line px-gutter-page py-3">
        <AppLink href="/decisiones" aria-label={t('home')} className="text-[17px] font-semibold tracking-[-0.04em] text-ink no-underline">
          TRATO
        </AppLink>
        {/* //todo_#152: estado de guardado real (guardado automático en servidor) */}
        <span className="ml-auto text-[13px] text-ink-muted">{t('draft')}</span>
      </header>
      {children}
    </>
  )
}
