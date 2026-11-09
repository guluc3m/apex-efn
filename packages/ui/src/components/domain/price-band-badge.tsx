import { CircleCheck, CircleHelp, OctagonAlert, TriangleAlert, type LucideIcon } from 'lucide-react'

import { StatusBadge, type StatusTone } from './status-badge.js'

export type PriceBand = 'normal' | 'atypical' | 'implausible' | 'insufficient_reference'

const PRICE_BAND: Record<PriceBand, { tone: StatusTone; icon: LucideIcon }> = {
  normal: { tone: 'ok', icon: CircleCheck },
  atypical: { tone: 'warn', icon: TriangleAlert },
  implausible: { tone: 'bad', icon: OctagonAlert },
  insufficient_reference: { tone: 'neutro', icon: CircleHelp },
}

export interface PriceBandBadgeProps {
  band: PriceBand
  label: string
}

/** Banda de precio que devuelve la API (DESIGN §6). */
export function PriceBandBadge({ band, label }: PriceBandBadgeProps) {
  const v = PRICE_BAND[band]
  return <StatusBadge tone={v.tone} icon={v.icon} label={label} />
}
