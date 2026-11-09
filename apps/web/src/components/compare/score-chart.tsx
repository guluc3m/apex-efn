'use client'

import { useTranslations } from 'next-intl'
import { Bar, BarChart, LabelList, ResponsiveContainer, XAxis, YAxis } from 'recharts'

import type { CriterionKey } from '@/fixtures/compare'

const CRITERIA: CriterionKey[] = ['price', 'trust', 'lead', 'verdict']
const FILL: Record<CriterionKey, string> = { price: 'var(--ink-muted)', trust: 'var(--accent)', lead: 'var(--line-strong)', verdict: 'var(--raised)' }
const TEXT: Record<CriterionKey, string> = { price: 'var(--on-accent)', trust: 'var(--on-accent)', lead: 'var(--ink)', verdict: 'var(--ink)' }
const fmt = (v: number) => v.toFixed(2).replace('.', ',')

export interface ScoreRow {
  name: string
  score: string
  parts: Record<CriterionKey, number>
}

/** Barras apiladas por criterio MCDA. Las contribuciones llegan calculadas; aquí solo se dibujan. */
export function ScoreChart({ rows }: { rows: ScoreRow[] }) {
  const t = useTranslations('compare.chart')
  const data = rows.map((r) => ({ name: r.name, ...r.parts }))

  return (
    <figure className="m-0 flex flex-col gap-2">
      <figcaption className="text-[13px] text-ink-muted">{t('caption')}</figcaption>
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
            <XAxis dataKey="name" tick={{ fill: 'var(--ink-muted)', fontSize: 13 }} stroke="var(--line-strong)" />
            <YAxis hide domain={[0, 1]} />
            {CRITERIA.map((k) => (
              <Bar key={k} dataKey={k} stackId="s" fill={FILL[k]} stroke="var(--control-border)" isAnimationActive={false}>
                <LabelList dataKey={k} position="center" formatter={(v: number) => `${t(`criteria.${k}`)} ${fmt(v)}`} fill={TEXT[k]} fontSize={13} />
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="sr-only">
        {rows.map((r) => (
          <li key={r.name}>
            {t('row', { name: r.name, score: r.score, parts: CRITERIA.map((k) => `${t(`criteria.${k}`)} ${fmt(r.parts[k])}`).join(', ') })}
          </li>
        ))}
      </ul>
    </figure>
  )
}
