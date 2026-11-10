'use client'

import type { MissionEvent } from '@apex/shared-types/contracts'
import { Button, Icon } from '@apex/ui'
import { useQueryClient } from '@tanstack/react-query'
import { CircleX, Columns3, Pause, Plus } from 'lucide-react'
import { useFormatter, useTranslations } from 'next-intl'
import { Suspense, useEffect, useState } from 'react'

import { AppLink } from '@/components/app-link'
import { ErrorPanel } from '@/components/error-panel'
import { ApiError, queryKeys, subscribeMissionEvents, useMission } from '@/lib/api'
import { PHASES, phaseStates, pushEvent } from '@/lib/missions'

import { MissionActivity } from './mission-activity'
import { MissionFunnel } from './mission-funnel'
import { MissionOffers } from './mission-offers'
import { MissionPhases } from './mission-phases'

/** Events that change the counters on the mission, so the mission is read again. */
const REFRESH: ReadonlySet<MissionEvent['type']> = new Set(['state_changed', 'offer_discovered', 'gate_opened', 'negotiation_state_changed', 'recommendation_ready'])

export function MissionLive({ missionId }: { missionId: string }) {
  const t = useTranslations('missions.detail')
  const format = useFormatter()
  const client = useQueryClient()
  const { data: mission, error, isPending, refetch } = useMission(missionId)
  const [events, setEvents] = useState<MissionEvent[]>([])
  const [streamLost, setStreamLost] = useState(false)

  useEffect(() => {
    const handle = subscribeMissionEvents(missionId, {
      onEvent: (event) => {
        setStreamLost(false)
        setEvents((list) => pushEvent(list, event))
        if (REFRESH.has(event.type)) void client.invalidateQueries({ queryKey: queryKeys.mission(missionId) })
      },
      onError: () => setStreamLost(true),
    })
    return handle.close
  }, [missionId, client])

  if (isPending) return <p className="px-gutter-page py-gutter-panel text-ink-muted" role="status">{t('loading')}</p>
  if (error) {
    const status = error instanceof ApiError ? error.status : 0
    if (status === 404) return <ErrorPanel kind="notFound" />
    if (status === 403) return <ErrorPanel kind="forbidden" />
    return <ErrorPanel kind="error" onRetry={() => void refetch()} />
  }

  const states = phaseStates(mission.state)
  const counts: Record<string, number> = { search: mission.offers_discovered, filter: mission.offers_in_gate, negotiation: mission.offers_negotiated, valuation: 0 }
  const phases = PHASES.map((id, i) => ({ id, state: states[i]!, values: { n: counts[id]! } }))

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-6 border-b border-line px-gutter-page py-gutter-panel">
        <div>
          <p className="text-[13px] text-ink-muted">
            {t('meta', { state: t(`state.${mission.state}`), date: format.dateTime(new Date(mission.started_at), { dateStyle: 'medium', timeStyle: 'short' }) })}
          </p>
          <h1 className="mt-1 text-[22px] font-semibold tracking-tight">{t('heading', { id: mission.id })}</h1>
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
          {/* //todo_#156: pausar y cancelar la misión (la API no tiene operación todavía: contract-change) */}
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
      {mission.error && (
        <p className="border-b border-warn bg-warn-subtle px-gutter-page py-3 text-warn" role="alert">
          {t('failed', { detail: mission.error.detail ?? mission.error.title })}
        </p>
      )}
      <MissionPhases phases={phases} />
      <div className="flex flex-wrap items-start">
        <div className="min-w-0 flex-[999_1_760px] px-gutter-page py-gutter-panel">
          <Suspense>
            <MissionOffers missionId={missionId} />
          </Suspense>
        </div>
        <aside className="min-w-0 flex-[1_1_340px] border-l border-line p-gutter-panel" aria-label={t('side')}>
          <MissionFunnel missionId={missionId} />
          <MissionActivity
            items={events.map((e) => ({ id: e.id, kind: e.type, time: format.dateTime(new Date(e.at), { timeStyle: 'medium' }) }))}
            live={!streamLost}
          />
        </aside>
      </div>
    </>
  )
}
