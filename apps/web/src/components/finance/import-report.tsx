'use client'

import type { FinancialImport } from '@apex/shared-types/contracts'
import { Badge, Button, Icon } from '@apex/ui'
import { ArrowRightLeft, OctagonAlert, TriangleAlert } from 'lucide-react'
import { useTranslations } from 'next-intl'

const TH = 'border-b border-line px-3 py-2 text-left text-[13px] font-medium text-ink-muted'
const TD = 'border-b border-line px-3 py-2'

/** Informe de importación tal como lo devuelve el servidor. Solo muestra campos del contrato. */
export function ImportReport({ data }: { data: FinancialImport }) {
  const t = useTranslations('company.finance.report')
  const r = data.report
  const stats: { label: string; value: string | number; cls?: string; note?: string }[] = [
    { label: t('accepted'), value: r.rows_ok },
    { label: t('rejected'), value: r.rows_rejected, cls: r.rows_rejected ? 'text-bad' : undefined },
    ...(r.rows_duplicated === undefined ? [] : [{ label: t('duplicated'), value: r.rows_duplicated }]),
    ...(r.rows_converted === undefined ? [] : [{ label: t('converted'), value: r.rows_converted }]),
    { label: t('periods'), value: r.periods_loaded, note: t(r.projection_enabled ? 'projectionOn' : 'projectionOff') },
    { label: t('referenceDate'), value: r.reference_date },
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

      <section className="flex max-w-[760px] flex-col gap-3">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={ArrowRightLeft} />{t('mappingTitle')}</h2>
        <p className="m-0 text-[13px] text-ink-muted">{t('mappingHint')}</p>
        <div>
          {/* Sin contrato de mapeo (issue #299, punto 2). */}
          <Button variant="sec" disabledReason={t('pending')}>{t('confirmMapping')}</Button>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={OctagonAlert} />{t('rejectionsTitle')}</h2>
        {r.rejections.length === 0 ? (
          <p className="m-0 text-ink-muted">{t('noRejections')}</p>
        ) : (
          <table className="border-collapse text-sm">
            <caption className="sr-only">{t('rejectionsCaption')}</caption>
            <thead><tr>
              <th scope="col" className={`${TH} text-right`}>{t('line')}</th>
              <th scope="col" className={TH}>{t('field')}</th>
              <th scope="col" className={TH}>{t('reason')}</th>
            </tr></thead>
            <tbody>
              {r.rejections.map((x) => (
                <tr key={`${x.row}-${x.reason_code}`}>
                  <td className={`${TD} text-right`}>{x.row}</td>
                  <td className={`${TD} font-mono`}>{x.field ?? '—'}</td>
                  <td className={TD}>
                    <Badge tone={x.reason_code === 'duplicate_period_metric' ? 'warn' : 'bad'}>{t(`reasons.${x.reason_code}`)}</Badge>
                    <span className="ml-2 text-[13px] text-ink-muted">{x.message}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {r.warnings.length > 0 && (
        <section className="flex max-w-[760px] flex-col gap-2">
          <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={TriangleAlert} />{t('warningsTitle')}</h2>
          {r.warnings.map((w) => <p key={w} className="m-0">{w}</p>)}
        </section>
      )}
    </div>
  )
}
