'use client'

import type { Offer } from '@apex/shared-types/contracts'
import { ConfidenceBandBadge } from '@apex/ui'
import { useTranslations } from 'next-intl'

import { ConfidenceBreakdown } from './confidence-breakdown'

/** Seller confidence of an offer: band and score, with the breakdown popover. Shown next to every price. */
export function OfferConfidence({ confidence }: { confidence: Offer['seller_confidence'] }) {
  const t = useTranslations('sellers')
  if (!confidence) return <span className="text-ink-muted">{t('notEvaluated')}</span>
  const label =
    confidence.score === null ? t('band.insufficient_data') : t('bandScore', { band: t(`band.${confidence.band}`), score: confidence.score })
  return <ConfidenceBandBadge band={confidence.band} label={label} breakdownTitle={t('title')} breakdown={<ConfidenceBreakdown confidence={confidence} />} />
}
