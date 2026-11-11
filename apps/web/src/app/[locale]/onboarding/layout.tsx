import { Logo } from '@apex/ui'
import { redirect } from 'next/navigation'
import { getTranslations, setRequestLocale } from 'next-intl/server'

import { AppLink } from '@/components/app-link'
import { getSession } from '@/server/auth/session'

/** Roles that may set up the company (docs/security/rbac.md). */
const ONBOARDING_ROLES = ['owner', 'admin', 'finance']

/** Cabecera reducida del alta: sin navegación de la app, solo salida y estado del borrador. */
export default async function OnboardingLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  setRequestLocale(locale)
  // The API stays authoritative; this only keeps other roles out of a flow they cannot finish.
  const session = await getSession()
  if (session && !session.user.roles.some((r) => ONBOARDING_ROLES.includes(r))) redirect(`/${locale}/decisiones`)
  const t = await getTranslations('onboarding.header')
  return (
    <>
      <header className="flex items-center gap-4 border-b border-line px-gutter-page py-3">
        <AppLink href="/decisiones" aria-label={t('home')} className="inline-flex items-center no-underline">
          <Logo size="sm" />
        </AppLink>
        {/* //todo_#377: estado de guardado real (guardado automático en servidor) */}
        <span className="ml-auto text-[13px] text-ink-muted">{t('draft')}</span>
      </header>
      {children}
    </>
  )
}
