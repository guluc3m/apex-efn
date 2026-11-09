import { setRequestLocale } from 'next-intl/server'

import { NegotiationView } from '@/components/negotiation/negotiation-view'
import { getNegotiation, type NegotiationState } from '@/fixtures/negotiation'

const STATES: readonly NegotiationState[] = ['active', 'human', 'aborted', 'reopened']

// //todo_#148: la negociación vendrá del BFF; `?estado=` solo elige el estado de la fixture
export default async function NegotiationPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string; missionId: string }>
  searchParams: Promise<{ estado?: string }>
}) {
  const { locale, missionId } = await params
  setRequestLocale(locale)
  const { estado } = await searchParams
  const state = STATES.find((s) => s === estado) ?? 'active'

  return <NegotiationView neg={getNegotiation(state)} missionId={missionId} />
}
