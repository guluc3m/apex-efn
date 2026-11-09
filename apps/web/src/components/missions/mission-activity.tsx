import { Icon, ShiningText } from '@apex/ui'
import { Activity } from 'lucide-react'
import { useTranslations } from 'next-intl'

import { AppLink } from '@/components/app-link'

interface Item {
  time: string
  kind: string
  values: Record<string, string | number>
  href?: string
}

// //todo_#156: eventos en vivo por SSE (GET /v1/missions/{id}/events)
export function MissionActivity({ items, workingOn }: { items: readonly Item[]; workingOn: number }) {
  const t = useTranslations('missions.detail.activity')
  return (
    <section aria-labelledby="mission-activity">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 id="mission-activity" className="inline-flex items-center gap-1.5 text-[17px] font-semibold">
          <Icon icon={Activity} />
          {t('title')}
        </h2>
        <span className="text-[13px] text-ink-muted">{t('live')}</span>
      </div>
      <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
        {items.map((it, i) => (
          <li key={i}>
            <span className="mr-2 font-mono text-[13px] text-ink-muted">{it.time}</span>
            {t(it.kind, it.values)}{' '}
            {it.href && <AppLink href={it.href}>{t('review')}</AppLink>}
          </li>
        ))}
        <li>
          <ShiningText>{t('working', { n: workingOn })}</ShiningText>
        </li>
      </ul>
    </section>
  )
}
