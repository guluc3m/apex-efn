'use client'

import type { DerivedFinancials } from '@apex/shared-types/contracts'
import { Icon, MoneyDisplay } from '@apex/ui'
import { Wallet } from 'lucide-react'
import { useLocale, useTranslations } from 'next-intl'

const TH = 'border-b border-line px-3 py-2 text-left text-[13px] font-medium text-ink-muted'
const TD = 'border-b border-line px-3 py-2'

/** Capacidad de compra, BuyingPowerScore y envelopes, tal como los devuelve el servidor (`derived`). */
export function SummaryView({ data }: { data: DerivedFinancials }) {
  const t = useTranslations('company.finance.summary')
  const locale = useLocale()
  const money = (m: DerivedFinancials['net_buying_capacity']) => (
    <MoneyDisplay amountMinor={m.amount_minor} currency={m.currency} locale={locale} />
  )
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap gap-12 border border-line bg-panel p-6">
        <div>
          <div className="text-[13px] text-ink-muted">{t('capacity')}</div>
          <div className="text-[32px] font-semibold">{money(data.net_buying_capacity)}</div>
        </div>
        <div>
          <div className="text-[13px] text-ink-muted">{t('score')}</div>
          <div className="text-2xl font-semibold">{data.buying_power_score ?? '—'}</div>
          <div className="text-[13px] text-ink-muted">{data.buying_power_score == null ? t('scoreEmpty') : t('scoreHint')}</div>
        </div>
      </div>

      <section className="flex flex-col gap-3">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold"><Icon icon={Wallet} />{t('envelopes')}</h2>
        {data.envelopes.length === 0 ? (
          <p className="m-0 text-ink-muted">{t('noEnvelopes')}</p>
        ) : (
          <table className="border-collapse text-sm">
            <thead><tr>
              <th className={TH}>{t('category')}</th>
              <th className={`${TH} text-right`}>{t('used')}</th>
              <th className={`${TH} text-right`}>{t('available')}</th>
              <th className={`${TH} text-right`}>{t('limit')}</th>
              <th className={TH}>{t('period')}</th>
            </tr></thead>
            <tbody>
              {data.envelopes.map((e) => (
                <tr key={`${e.category}-${e.period_start}`}>
                  <th scope="row" className={`${TD} text-left font-normal`}>{e.category}</th>
                  <td className={`${TD} text-right`}>{money(e.spent)}</td>
                  <td className={`${TD} text-right`}>{money(e.available)}</td>
                  <td className={`${TD} text-right`}>{money(e.allocated)}</td>
                  <td className={`${TD} font-mono`}>{e.period_start} / {e.period_end}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
