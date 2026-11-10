'use client'

import type { RankedOffer, ScoreCriterion } from '@apex/shared-types/contracts'
import { useLocale, useTranslations } from 'next-intl'
import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis } from 'recharts'

// One fill per criterion; a criterion keeps its colour across offers.
const FILL: Record<ScoreCriterion, string> = {
  landed_cost: 'var(--ink-muted)',
  lead_time: 'var(--line-strong)',
  seller_confidence: 'var(--accent)',
  financial_fit: 'var(--raised)',
  margin_potential: 'var(--good)',
  spec_match: 'var(--warn)',
  compliance_risk: 'var(--bad)',
  negotiation_gain: 'var(--ink-soft)',
}

export interface ScoreRow {
  name: string
  ranked: RankedOffer
}

/** Stacked bars of the contribution of each criterion. Contributions arrive computed; this only draws them. */
export function ScoreChart({ rows }: { rows: ScoreRow[] }) {
  const t = useTranslations('compare.chart')
  const locale = useLocale()
  const fmt = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const criteria = [...new Set(rows.flatMap((r) => r.ranked.breakdown.map((b) => b.criterion)))]
  const data = rows.map((r) => ({
    name: r.name,
    ...Object.fromEntries(r.ranked.breakdown.map((b) => [b.criterion, b.contribution])),
  }))

  return (
    <figure className="m-0 flex flex-col gap-2">
      <figcaption className="text-[13px] text-ink-muted">{t('caption')}</figcaption>
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
            <XAxis dataKey="name" tick={{ fill: 'var(--ink-muted)', fontSize: 13 }} stroke="var(--line-strong)" />
            <YAxis hide domain={[0, 1]} />
            {criteria.map((k) => (
              <Bar key={k} dataKey={k} stackId="s" fill={FILL[k]} stroke="var(--control-border)" isAnimationActive={false} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="m-0 flex flex-wrap gap-x-4 gap-y-1 p-0 text-[13px]">
        {criteria.map((k) => (
          <li key={k} className="flex list-none items-center gap-1.5">
            <span className="inline-block size-3 border border-control-border" style={{ background: FILL[k] }} aria-hidden="true" />
            {t(`criteria.${k}`)}
          </li>
        ))}
      </ul>
      <ul className="sr-only">
        {rows.map((r) => (
          <li key={r.ranked.offer_id}>
            {t('row', {
              name: r.name,
              score: fmt.format(r.ranked.score),
              parts: r.ranked.breakdown.map((b) => `${t(`criteria.${b.criterion}`)} ${fmt.format(b.contribution)}`).join(', '),
            })}
          </li>
        ))}
      </ul>
    </figure>
  )
}
