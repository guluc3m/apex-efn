'use client'

import { useTranslations } from 'next-intl'

import { useDeals, useGateQueue } from '@/lib/api'

/** Solo cifras que la API ya entrega (cola de gate abierta y tratos firmados); sin tendencias inventadas. */
export function KpiStrip() {
  const t = useTranslations('decisions.kpi')
  const gate = useGateQueue({ status: 'open' })
  const signed = useDeals({ signature_status: 'signed' })
  const kpis = [
    { key: 'pending', value: gate.data?.items.length },
    { key: 'signed', value: signed.data?.items.length },
  ]
  return (
    <section aria-label={t('label')} className="grid grid-cols-1 gap-4 border-b border-line px-gutter-panel py-4 md:grid-cols-4">
      {kpis.map((k) => (
        <div key={k.key} className="min-w-0">
          <div className="text-[13px] text-ink-muted">{t(k.key)}</div>
          <div className="text-[22px] font-semibold tabular-nums">{k.value === undefined ? '—' : k.value}</div>
        </div>
      ))}
    </section>
  )
}
