'use client'

import { useTranslations } from 'next-intl'
import { CartesianGrid, Line, LineChart, LabelList, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'

import type { NegotiationFixture } from '@/fixtures/negotiation'

/** Escalera de precio por ronda con objetivo y máximo. Los valores llegan calculados; aquí solo se dibujan. */
export function PriceLadder({ ladder }: { ladder: NegotiationFixture['ladder'] }) {
  const t = useTranslations('negotiation.chart')
  const data = ladder.points.map((p) => ({
    ...p,
    name: p.draft ? t('draft') : t('round', { n: p.round }),
  }))

  return (
    <figure className="m-0 flex flex-col gap-2">
      <figcaption className="text-[13px] text-ink-muted">{t('caption')}</figcaption>
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={224}>
          <LineChart data={data} margin={{ top: 24, right: 24, bottom: 4, left: 8 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="name" tick={{ fill: 'var(--ink-muted)', fontSize: 13 }} stroke="var(--line-strong)" />
            <YAxis hide domain={[(min: number) => Math.min(min, ladder.max.value) - 0.02, (max: number) => max + 0.02]} />
            <ReferenceLine y={ladder.target.value} stroke="var(--ink-muted)" strokeDasharray="4 3" label={{ value: t('target', { value: ladder.target.label }), position: 'insideTopRight', fill: 'var(--ink-muted)', fontSize: 13 }} />
            <ReferenceLine y={ladder.max.value} stroke="var(--ink-muted)" label={{ value: t('max', { value: ladder.max.label }), position: 'insideBottomRight', fill: 'var(--ink-muted)', fontSize: 13 }} />
            <Line
              type="stepAfter"
              dataKey="value"
              stroke="var(--accent)"
              strokeWidth={2}
              isAnimationActive={false}
              dot={(p: { cx?: number; cy?: number; payload?: { draft?: boolean } }) => (
                <circle key={`${p.cx}-${p.cy}`} cx={p.cx} cy={p.cy} r={5} stroke="var(--accent)" strokeWidth={2} fill={p.payload?.draft ? 'var(--bg)' : 'var(--accent)'} />
              )}
            >
              <LabelList dataKey="label" position="top" fill="var(--ink)" fontSize={13} />
            </Line>
          </LineChart>
        </ResponsiveContainer>
      </div>
      <ul className="sr-only">
        {ladder.points.map((p) => (
          <li key={p.round}>{p.draft ? t('tableDraft', { value: p.label }) : t('table', { round: p.round, value: p.label })}</li>
        ))}
        <li>{t('tableTarget', { value: ladder.target.label })}</li>
        <li>{t('tableMax', { value: ladder.max.label })}</li>
      </ul>
    </figure>
  )
}
