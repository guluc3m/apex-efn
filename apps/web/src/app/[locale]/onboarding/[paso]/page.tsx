import { notFound } from 'next/navigation'
import { setRequestLocale } from 'next-intl/server'

import { OnboardingWizard } from '@/components/onboarding'
import { STEP_IDS, type StepId } from '@/components/onboarding/schemas'
import { locales } from '@/i18n/routing'

export function generateStaticParams() {
  return locales.flatMap((locale) => STEP_IDS.map((paso) => ({ locale, paso })))
}

// //todo_#377: redirección a /decisiones si el onboarding está completo (necesita leer la sesión)
export default async function OnboardingStepPage({ params }: { params: Promise<{ locale: string; paso: string }> }) {
  const { locale, paso } = await params
  setRequestLocale(locale)
  if (!(STEP_IDS as readonly string[]).includes(paso)) notFound()
  return <OnboardingWizard step={paso as StepId} />
}
