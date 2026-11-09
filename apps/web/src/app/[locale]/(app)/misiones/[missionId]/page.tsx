import { Button, Icon } from '@apex/ui'
import { CircleX, Columns3, Pause, Plus } from 'lucide-react'
import { notFound } from 'next/navigation'
import { getTranslations, setRequestLocale } from 'next-intl/server'
import { Suspense } from 'react'

import { AppLink } from '@/components/app-link'
import { MissionActivity } from '@/components/missions/mission-activity'
import { MissionFunnel } from '@/components/missions/mission-funnel'
import { MissionOffers } from '@/components/missions/mission-offers'
import { MissionPhases } from '@/components/missions/mission-phases'
import { mission } from '@/fixtures/missions'

export default async function MissionPage({ params }: { params: Promise<{ locale: string; missionId: string }> }) {
  const { locale, missionId } = await params
  setRequestLocale(locale)
  // //todo_#156: GET /v1/missions/{id}; un id inexistente devuelve 404
  if (missionId !== mission.id) notFound()
  const t = await getTranslations('missions.detail')

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-6 border-b border-line px-gutter-page py-gutter-panel">
        <div>
          <p className="text-[13px] text-ink-muted">{t('meta', { id: mission.id, minutes: mission.launchedMinutesAgo })}</p>
          <h1 className="mt-1 text-[22px] font-semibold tracking-tight">{mission.title}</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <AppLink href="/misiones/nueva">
              <Icon icon={Plus} />
              {t('new')}
            </AppLink>
          </Button>
          <Button asChild>
            <AppLink href={`/misiones/${mission.id}/comparativa`}>
              <Icon icon={Columns3} />
              {t('compare')}
            </AppLink>
          </Button>
          {/* //todo_#156: pausar y cancelar la misión */}
          <Button disabledReason={t('pending')}>
            <Icon icon={Pause} />
            {t('pause')}
          </Button>
          <Button variant="ghost" disabledReason={t('pending')}>
            <Icon icon={CircleX} />
            {t('cancel')}
          </Button>
        </div>
      </div>
      <MissionPhases phases={mission.phases} />
      <div className="flex flex-wrap items-start">
        <div className="min-w-0 flex-[999_1_760px] px-gutter-page py-gutter-panel">
          <Suspense>
            <MissionOffers offers={mission.offers} total={mission.total} />
          </Suspense>
        </div>
        <aside className="min-w-0 flex-[1_1_340px] border-l border-line p-gutter-panel" aria-label={t('side')}>
          <MissionFunnel stages={mission.funnel} />
          <MissionActivity items={mission.activity} workingOn={mission.workingOn} />
        </aside>
      </div>
    </>
  )
}
