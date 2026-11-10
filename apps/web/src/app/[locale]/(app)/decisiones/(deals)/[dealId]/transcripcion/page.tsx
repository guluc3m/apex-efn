import { setRequestLocale } from 'next-intl/server'

// El trato lo resuelve DecisionsView contra GET /v1/dashboard/deals; aquí solo se fija el idioma.
export default async function DealTranscriptPage({ params }: { params: Promise<{ locale: string; dealId: string }> }) {
  setRequestLocale((await params).locale)
  return null
}
