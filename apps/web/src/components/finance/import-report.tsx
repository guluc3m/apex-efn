import { Badge, Button, Icon } from '@apex/ui'
import { ArrowRightLeft, OctagonAlert, TriangleAlert } from 'lucide-react'
import { useTranslations } from 'next-intl'

import type { FinanceImport } from '@/fixtures/finance'

const TH = 'border-b border-line px-3 py-2 text-left text-[13px] font-medium text-ink-muted'
const TD = 'border-b border-line px-3 py-2'

/** Informe de importación: cifras, mapeo de cabeceras, filas rechazadas y avisos. Reutilizable en /empresa/finanzas. */
export function ImportReport({ data }: { data: FinanceImport }) {
  const t = useTranslations('company.finance.report')
  const stats: { label: string; value: number; cls?: string; note?: string }[] = [
    { label: t('accepted'), value: data.accepted },
    { label: t('rejected'), value: data.rejected, cls: 'text-bad' },
    { label: t('duplicated'), value: data.duplicated, cls: 'text-warn' },
    { label: t('periods'), value: data.periods, note: t('range', { range: data.periodRange }) },
    { label: t('converted'), value: data.converted },
  ]
  return (
    <div className="flex flex-col gap-8">
      <dl className="m-0 flex flex-wrap gap-12 border border-line bg-panel px-6 py-5">
        {stats.map((s) => (
          <div key={s.label}>
            <dt className="text-[13px] text-ink-muted">{s.label}</dt>
            <dd className={`m-0 text-2xl font-semibold ${s.cls ?? ''}`}>{s.value}</dd>
            {s.note && <dd className="m-0 text-[13px] text-ink-muted">{s.note}</dd>}
          </div>
        ))}
      </dl>

      <section className="flex flex-col gap-3">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={ArrowRightLeft} />{t('mappingTitle', { n: data.mapping.length })}</h2>
        <p className="m-0 text-[13px] text-ink-muted">{t('mappingHint')}</p>
        <table className="max-w-[760px] border-collapse text-sm">
          <thead><tr><th className={TH}>{t('column')}</th><th className={TH}>{t('field')}</th><th className={TH}>{t('origin')}</th></tr></thead>
          <tbody>
            {data.mapping.map((m) => (
              <tr key={m.column}>
                <td className={`${TD} font-mono`}>{m.column}</td>
                <td className={`${TD} font-mono`}>{m.field}</td>
                <td className={`${TD} text-ink-muted`}>{t('suggested')}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div>
          {/* //todo_#153: confirmar el mapeo (POST financial-csv/mapping) */}
          <Button variant="sec" disabledReason={t('pending')}>{t('confirmMapping')}</Button>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={OctagonAlert} />{t('rejectionsTitle')}</h2>
        <table className="border-collapse text-sm">
          <caption className="sr-only">{t('rejectionsCaption')}</caption>
          <thead><tr>
            <th scope="col" className={TH}>{t('metric')}</th><th scope="col" className={TH}>{t('period')}</th>
            <th scope="col" className={`${TH} text-right`}>{t('line')}</th><th scope="col" className={`${TH} text-right`}>{t('value')}</th>
            <th scope="col" className={TH}>{t('reason')}</th>
          </tr></thead>
          <tbody>
            {data.rejections.map((r) => (
              <tr key={r.line}>
                <th scope="row" className={`${TD} text-left font-mono font-normal`}>{r.metric}</th>
                <td className={`${TD} font-mono`}>{r.period}</td>
                <td className={`${TD} text-right`}>{r.line}</td>
                <td className={`${TD} text-right font-mono`}>{r.value}</td>
                <td className={TD}><Badge tone={r.reason === 'duplicate' ? 'warn' : 'bad'}>{t(`reasons.${r.reason}`, { line: r.keptLine ?? 0 })}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="flex max-w-[760px] flex-col gap-2">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={TriangleAlert} />{t('warningsTitle')}</h2>
        {data.warnings.map((w) => <p key={w} className="m-0">{t(`warnings.${w}`, { n: data.converted, month: data.taxReserveMonth })}</p>)}
      </section>
    </div>
  )
}
