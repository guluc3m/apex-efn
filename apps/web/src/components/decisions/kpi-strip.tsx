'use client'

import { MoneyDisplay } from '@apex/ui'
import { useLocale, useTranslations } from 'next-intl'
import { Bar, BarChart, Line, LineChart, ResponsiveContainer } from 'recharts'

import { kpis, savings } from '@/fixtures/decisions'

// Sin animación: respeta prefers-reduced-motion y evita parpadeo al hidratar. Colores por currentColor (tokens).
export function KpiStrip() {
  const t = useTranslations('decisions.kpi')
  const locale = useLocale()
  return (
    <section aria-label={t('label')} className="grid grid-cols-1 gap-4 border-b border-line px-gutter-panel py-4 md:grid-cols-4">
      {kpis.map((k) => (
        <div key={k.key} className="min-w-0">
          <div className="text-[13px] text-ink-muted">{t(k.key)}</div>
          <div className="text-[22px] font-semibold tabular-nums">{k.value}</div>
          <div className="h-8 text-accent" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={k.spark.map((v, i) => ({ i, v }))}>
                <Line dataKey="v" stroke="currentColor" strokeWidth={1.5} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <span className="sr-only">{t('trend', { values: k.spark.join(', ') })}</span>
        </div>
      ))}
      <div className="min-w-0">
        <div className="text-[13px] text-ink-muted">{t('savings')}</div>
        <MoneyDisplay amountMinor={savings.totalMinor} currency="EUR" locale={locale} className="text-[22px] font-semibold" />
        <div className="h-8 text-accent" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={savings.weeks}>
              <Bar dataKey="minor" fill="currentColor" isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <table className="sr-only">
          <caption>{t('savingsWeekly')}</caption>
          <thead>
            <tr>
              <th>{t('week')}</th>
              <th>{t('savings')}</th>
            </tr>
          </thead>
          <tbody>
            {savings.weeks.map((w) => (
              <tr key={w.week}>
                <td>{w.week}</td>
                <td>
                  <MoneyDisplay amountMinor={w.minor} currency="EUR" locale={locale} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
