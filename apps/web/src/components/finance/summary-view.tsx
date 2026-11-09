import { Badge, Icon } from '@apex/ui'
import { Wallet, WalletMinimal } from 'lucide-react'
import { useTranslations } from 'next-intl'

import type { FinanceSummary } from '@/fixtures/finance'

import { EnvelopeChart } from './envelope-chart'

const TH = 'border-b border-line px-3 py-2 text-left text-[13px] font-medium text-ink-muted'
const TD = 'border-b border-line px-3 py-2'

/** Capacidad de compra, BuyingPowerScore y envelopes con tabla alternativa. Reutilizable en /empresa/finanzas. */
export function SummaryView({ data }: { data: FinanceSummary }) {
  const t = useTranslations('company.finance.summary')
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap gap-12 border border-line bg-panel p-6">
        <div>
          <div className="text-[13px] text-ink-muted">{t('capacity')}</div>
          <div className="text-[32px] font-semibold">{data.netCapacity}</div>
          <div className="text-[13px] text-ink-muted">{t('capacityHint', { buffer: data.buffer })}</div>
        </div>
        <div>
          <div className="text-[13px] text-ink-muted">{t('score')}</div>
          <div className="text-2xl font-semibold">{data.buyingPowerScore}</div>
          <div className="text-[13px] text-ink-muted">{t('scoreHint')}</div>
        </div>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={Wallet} />{t('envelopes')}</h2>
        <EnvelopeChart envelopes={data.envelopes} />
        <table className="border-collapse text-sm">
          <thead><tr>
            <th className={TH}>{t('category')}</th><th className={TH}>{t('used')}</th>
            <th className={`${TH} text-right`}>{t('available')}</th><th className={`${TH} text-right`}>{t('limit')}</th>
          </tr></thead>
          <tbody>
            {data.envelopes.map((e) => (
              <tr key={e.key}>
                <th scope="row" className={`${TD} text-left font-normal`}>
                  <span className="flex flex-wrap items-center gap-2">{e.name}
                    {e.nearlyExhausted && <Badge tone="warn" icon={WalletMinimal}>{t('nearlyExhausted')}</Badge>}
                  </span>
                </th>
                <td className={TD}>{e.used} · {e.usedPct} %</td>
                <td className={`${TD} text-right`}>{e.available}</td>
                <td className={`${TD} text-right`}>{e.limit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
