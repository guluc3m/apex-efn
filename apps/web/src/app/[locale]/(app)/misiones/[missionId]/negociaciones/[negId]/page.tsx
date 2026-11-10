import { setRequestLocale } from 'next-intl/server'

import { NegotiationView } from '@/components/negotiation/negotiation-view'

export default async function NegotiationPage({
  params,
}: {
  params: Promise<{ locale: string; missionId: string; negId: string }>
}) {
  const { locale, missionId, negId } = await params
  setRequestLocale(locale)

  return <NegotiationView negotiationId={negId} missionId={missionId} />
}
