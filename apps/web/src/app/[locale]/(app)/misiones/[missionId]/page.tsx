import { setRequestLocale } from 'next-intl/server'

import { MissionLive } from '@/components/missions/mission-live'

export default async function MissionPage({ params }: { params: Promise<{ locale: string; missionId: string }> }) {
  const { locale, missionId } = await params
  setRequestLocale(locale)
  return <MissionLive missionId={missionId} />
}
