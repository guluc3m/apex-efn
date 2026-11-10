'use client'

import type { SellerConfidence } from '@apex/shared-types/contracts'
import { Button } from '@apex/ui'
import { useLocale, useTranslations } from 'next-intl'
import { useState } from 'react'

import { useSellerConfidence } from '@/lib/api'

/** Why a seller got this confidence: normalized signals, penalties, flags and model version, as the API returns them. */
export function ConfidenceBreakdown({ confidence }: { confidence: SellerConfidence }) {
  const t = useTranslations('sellers')
  const locale = useLocale()
  const pct = new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 0 })
  const [showPast, setShowPast] = useState(false)
  const past = useSellerConfidence(confidence.seller_id, showPast)
  const signals = Object.entries(confidence.signals_normalized)

  return (
    <div className="flex min-w-64 flex-col gap-3 text-[13px]">
      {signals.length > 0 ? (
        <dl className="m-0 flex flex-col gap-1">
          {signals.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-4">
              <dt className="text-ink-muted">{t.has(`signal.${k}`) ? t(`signal.${k}`) : k}</dt>
              <dd className="m-0 tabular-nums">{pct.format(v)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="m-0 text-ink-muted">{t('noSignals')}</p>
      )}
      {confidence.penalties.length > 0 && (
        <div>
          <div className="text-ink-muted">{t('penalties')}</div>
          <ul className="m-0 pl-4">
            {confidence.penalties.map((p) => (
              <li key={p}>{t.has(`penalty.${p}`) ? t(`penalty.${p}`) : p}</li>
            ))}
          </ul>
        </div>
      )}
      {confidence.flags.length > 0 && (
        <div>
          <div className="text-ink-muted">{t('flags')}</div>
          <ul className="m-0 pl-4">
            {confidence.flags.map((f) => (
              <li key={`${f.type}-${f.detected_at}`}>
                {t(`flag.${f.type}`)} · {t(`severity.${f.severity}`)}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="text-ink-muted">{t('model', { version: confidence.model_version })}</div>
      {!showPast ? (
        <Button onClick={() => setShowPast(true)}>{t('showHistory')}</Button>
      ) : past.isPending ? (
        <p className="m-0 text-ink-muted" role="status">{t('loading')}</p>
      ) : past.isError ? (
        <div role="alert">
          <p className="m-0">{t('error')}</p>
          <Button onClick={() => void past.refetch()}>{t('retry')}</Button>
        </div>
      ) : (
        <ul className="m-0 pl-4">
          {past.data.history.length === 0 && <li className="list-none text-ink-muted">{t('noHistory')}</li>}
          {past.data.history.map((h) => (
            <li key={h.computed_at}>
              {new Date(h.computed_at).toLocaleDateString(locale)} · {t(`band.${h.band}`)}
              {h.score !== null && ` · ${h.score}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
