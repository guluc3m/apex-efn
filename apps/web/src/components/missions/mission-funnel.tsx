'use client'

import { useTranslations } from 'next-intl'
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from 'recharts'

interface Stage {
  id: string
  n: number
}

// //todo_#157: embudo real de la misión (conteos de la API)
export function MissionFunnel({ stages }: { stages: readonly Stage[] }) {
  const t = useTranslations('missions.detail.funnel')
  const data = stages.map((s) => ({ ...s, name: t(`stages.${s.id}`) }))
  const last = stages.length - 1
  return (
    <figure className="m-0 mb-6">
      <figcaption className="mb-2 text-[13px] text-ink-muted">{t('caption')}</figcaption>
      <div role="img" aria-label={t('aria', Object.fromEntries(stages.map((s) => [s.id, s.n])))}>
        <ResponsiveContainer width="100%" height={190}>
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 28, bottom: 0, left: 0 }}>
            <XAxis type="number" hide domain={[0, stages[0]?.n ?? 0]} />
            <YAxis type="category" dataKey="name" width={150} axisLine={false} tickLine={false} tick={{ fill: 'var(--ink)', fontSize: 13 }} />
            <Bar dataKey="n" barSize={20} isAnimationActive={false}>
              {data.map((d, i) => (
                <Cell key={d.id} fill={i === last ? 'var(--accent)' : 'var(--ink-muted)'} />
              ))}
              <LabelList dataKey="n" position="right" fill="var(--ink)" fontSize={13} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="sr-only">
        {data.map((d) => (
          <li key={d.id}>
            {d.name}: {d.n}
          </li>
        ))}
      </ul>
    </figure>
  )
}
