'use client'

import { useTranslations } from 'next-intl'
import { Bar, BarChart, LabelList, ResponsiveContainer, XAxis, YAxis } from 'recharts'

import type { FinanceSummary } from '@/fixtures/finance'

/** Uso de cada envelope frente a su límite (la barra completa es el 100 %). Porcentajes ya calculados. */
export function EnvelopeChart({ envelopes }: { envelopes: FinanceSummary['envelopes'] }) {
  const t = useTranslations('company.finance.summary')
  return (
    <figure className="m-0 flex flex-col gap-2">
      <figcaption className="text-[13px] text-ink-muted">{t('chartCaption')}</figcaption>
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={envelopes.length * 52 + 8}>
          <BarChart data={envelopes} layout="vertical" margin={{ top: 0, right: 48, bottom: 0, left: 0 }}>
            <XAxis type="number" domain={[0, 100]} hide />
            <YAxis type="category" dataKey="name" width={140} tick={{ fill: 'var(--ink)', fontSize: 13 }} axisLine={false} tickLine={false} />
            <Bar dataKey="usedPct" fill="var(--accent)" background={{ fill: 'var(--line-strong)' }} barSize={14} isAnimationActive={false}>
              <LabelList dataKey="usedPct" position="right" fill="var(--ink)" fontSize={13} formatter={(v: unknown) => `${String(v)} %`} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}
