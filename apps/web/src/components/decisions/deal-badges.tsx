'use client'

import type { Deal } from '@apex/shared-types/contracts'
import { ConfidenceBandBadge, FinancialVerdictBadge, PriceBandBadge, SignatureStatusBadge } from '@apex/ui'
import { useTranslations } from 'next-intl'
import type { ReactNode } from 'react'

/** Orden fijo de columnas: banda · confianza · veredicto · firma (el precio va fuera). */
export function DealBadges({ deal, confidenceBreakdown }: { deal: Deal; confidenceBreakdown?: ReactNode }) {
  const t = useTranslations('decisions')
  const score = deal.offer.seller_confidence?.score
  return (
    <>
      <PriceBandBadge band={deal.price_band} label={t(`band.${deal.price_band}`)} />
      <ConfidenceBandBadge
        band={deal.confidence_band}
        label={t('confLabel', { band: t(`conf.${deal.confidence_band}`), score: score ?? '—' })}
        breakdown={confidenceBreakdown}
        breakdownTitle={t('detail.whyConfidence')}
      />
      <FinancialVerdictBadge verdict={deal.financial_verdict} label={t(`verdict.${deal.financial_verdict}`)} />
      <SignatureStatusBadge
        status={deal.signature_status === 'unsigned' ? 'pending' : deal.signature_status}
        label={t(`sig.${deal.signature_status}`)}
      />
    </>
  )
}
