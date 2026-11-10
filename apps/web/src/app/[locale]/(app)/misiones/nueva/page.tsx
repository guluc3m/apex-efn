import { getTranslations, setRequestLocale } from 'next-intl/server'

import { MissionRequest } from '@/components/missions/mission-request'

export default async function NewMissionPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  const t = await getTranslations('missions.request')

  return (
    <div className="px-gutter-page py-gutter-panel">
      <h1 className="mb-6 text-[22px] font-semibold tracking-tight">{t('title')}</h1>
      <MissionRequest />
    </div>
  )
}
