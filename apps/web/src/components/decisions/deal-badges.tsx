'use client'

import { ConfidenceBandBadge, FinancialVerdictBadge, PriceBandBadge, SignatureStatusBadge } from '@apex/ui'
import { useTranslations } from 'next-intl'
import type { ReactNode } from 'react'

import type { Deal } from '@/fixtures/decisions'

/** Orden fijo de columnas: banda · confianza · veredicto · firma (el precio va fuera). */
export function DealBadges({ deal, confidenceBreakdown }: { deal: Deal; confidenceBreakdown?: ReactNode }) {
  const t = useTranslations('decisions')
  if (!deal.band || !deal.conf || !deal.verdict || !deal.sig) return null
  return (
    <>
      <PriceBandBadge band={deal.band} label={t(`band.${deal.band}`)} />
      <ConfidenceBandBadge
        band={deal.conf}
        label={t('confLabel', { band: t(`conf.${deal.conf}`), score: deal.score ?? 0 })}
        breakdown={confidenceBreakdown}
        breakdownTitle={t('detail.whyConfidence')}
      />
      <FinancialVerdictBadge verdict={deal.verdict} label={t(`verdict.${deal.verdict}`)} />
      <SignatureStatusBadge status={deal.sig.status} label={t(`sig.${deal.sig.key}`)} />
    </>
  )
}
