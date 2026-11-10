import { Icon } from '@apex/ui'
import { Activity } from 'lucide-react'
import { useTranslations } from 'next-intl'

interface Item {
  id: string
  time: string
  kind: string
}

/** Live events of the mission (SSE `GET /v1/missions/{id}/events`), newest first. */
export function MissionActivity({ items, live }: { items: readonly Item[]; live: boolean }) {
  const t = useTranslations('missions.detail.activity')
  return (
    <section aria-labelledby="mission-activity">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 id="mission-activity" className="inline-flex items-center gap-1.5 text-[17px] font-semibold">
          <Icon icon={Activity} />
          {t('title')}
        </h2>
        <span className="text-[13px] text-ink-muted">{live ? t('live') : t('reconnecting')}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-ink-muted">{t('empty')}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-2.5 p-0" aria-live="polite">
          {items.map((it) => (
            <li key={it.id}>
              <span className="mr-2 font-mono text-[13px] text-ink-muted">{it.time}</span>
              {t(`events.${it.kind}`)}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
